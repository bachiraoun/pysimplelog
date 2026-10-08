"""
Sends OTLP/JSON logs requests over HTTP or HTTPS with the standard library only, and says how the receiver answered.

The transport decides nothing about what to do with an answer: it classifies it, and the sink chooses. It never raises for a
network problem or an answer it does not like, it returns a result, because the code that calls it must not be broken by a
collector that is down.

How an answer is classified, following the OTLP/HTTP specification:

========================================  ===========  ===================================================================================
Answer                                    Outcome      Why
========================================  ===========  ===================================================================================
200 and any other 2xx                     ``OK``       Delivered. A body that says ``partialSuccess`` counts the records the receiver
                                                       refused, and the request is not sent again, as the specification requires.
429, 502, 503, 504                        ``RETRY``    The specification says to try again, after the ``Retry-After`` wait when there is one.
400, 413, 422                             ``REFUSED``  The receiver refuses this payload. Trying it again cannot help.
no answer: refused connection, timeout,   ``RETRY``    The receiver may be back later.
reset, TLS error
anything else: 401, 403, 404, 405, 415,   ``ERROR``    The specification says not to retry. A configuration problem, a wrong address or an
500, 3xx...                                            expired token, is for a person to fix, so the sink decides.
========================================  ===========  ===================================================================================
"""

import gzip
import http.client
import ipaddress
import json
import math
import os
import ssl
import sys
import threading
import time
import urllib.parse
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import NamedTuple

try:
    from ..__pkginfo__ import __version__
    from ..forking import register_for_fork_reset
except ImportError:
    from __pkginfo__ import __version__
    from forking import register_for_fork_reset

OK = 'ok'
RETRY = 'retry'
REFUSED = 'refused'
ERROR = 'error'

LOGS_PATH = '/v1/logs'
# The longest wait a receiver can ask for with Retry-After, so that a wrong value does not stop the sink for days
MAX_RETRY_AFTER = 300.0
# The largest answer that is read. A longer one closes the connection
MAX_RESPONSE_BYTES = 65536
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
REFUSED_STATUS = frozenset({400, 413, 422})
# These describe the request and the transport sets them, a caller cannot replace them
FIXED_HEADERS = frozenset({'content-type', 'content-encoding', 'content-length', 'host', 'connection', 'transfer-encoding'})


class OtlpResponse(NamedTuple):
    """
    How the receiver answered one request.

    :Parameters:
        #. outcome (str): ``OK``, ``RETRY``, ``REFUSED`` or ``ERROR``, see the table of the module.
        #. status (int, None): The HTTP status. None when there was no answer.
        #. retryAfter (float, None): Seconds the receiver asked to wait, between 0 and ``MAX_RETRY_AFTER``. None when it did not.
        #. rejected (int): The number of records the receiver accepted the request without, from ``partialSuccess``. 0 otherwise.
        #. message (str, None): The text the receiver gave in ``partialSuccess``, or the class of the error when there was no
           answer. Cut to 200 characters, on a single line.
    """

    outcome: str
    status: int | None = None
    retryAfter: float | None = None
    rejected: int = 0
    message: str | None = None


def _one_line(text, limit=200):
    """Returns a text on a single line, cut to a limit, so that a receiver cannot fill a log with it or forge lines in it."""
    text = ' '.join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + '...'


def parse_retry_after(value, now=None):
    """
    Reads the ``Retry-After`` header, a number of seconds or an HTTP date.

    :Parameters:
        #. value (str, None): The header.
        #. now (float, None): The current time, in seconds since the epoch. Given by tests.

    :Returns:
        #. seconds (float, None): The wait, from 0 to ``MAX_RETRY_AFTER``, or None when there is no usable value.
    """
    if value is None:
        return None
    text = str(value).strip()
    try:
        seconds = float(text)
    except ValueError:
        try:
            moment = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if moment is None:
            return None
        if moment.tzinfo is None:
            # A date written with "-0000" says no zone, and HTTP dates are in UTC
            moment = moment.replace(tzinfo=timezone.utc)
        seconds = moment.timestamp() - (time.time() if now is None else now)
    if not math.isfinite(seconds):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER)


def _is_local_host(host):
    """True for ``localhost`` and for an address that stays on this machine."""
    if host == 'localhost' or host.endswith('.localhost'):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OtlpHttpTransport:
    """
    Posts OTLP/JSON logs requests to a receiver, keeping one connection open between requests.

    :Parameters:
        #. endpoint (str): The address of the receiver, ``https://collector.example.org:4318``. The path ``/v1/logs`` is added to it.
           It holds no user name, no query and no fragment: put a token in *headers*.
        #. headers (dict, None): Extra headers, such as ``Authorization``. ``Content-Type``, ``Content-Encoding``, ``Content-Length``,
           ``Host``, ``Connection`` and ``Transfer-Encoding`` are set by the transport and cannot be given.
        #. timeout (int, float): Seconds allowed for each step of a request: connecting, sending, and waiting for the answer.
        #. compress (bool): True to gzip the body of every request.
        #. sslContext (ssl.SSLContext, None): For ``https``. None uses ``ssl.create_default_context()``. Give one to trust your own
           certificate authority or to present a client certificate.

    :Raises:
        #. TypeError: If an argument has the wrong type.
        #. ValueError: If the endpoint is not an http or https address with a host, holds a user name, a query or a fragment, or a
           header name or value is not allowed.
    """

    def __init__(self, endpoint, headers=None, timeout=10.0, compress=False, sslContext=None):
        if not isinstance(endpoint, str):
            raise TypeError("endpoint must be a string")
        if headers is not None and not isinstance(headers, dict):
            raise TypeError("headers must be a dictionary")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise TypeError("timeout must be a number")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        if not isinstance(compress, bool):
            raise TypeError("compress must be a boolean")
        if sslContext is not None and not isinstance(sslContext, ssl.SSLContext):
            raise TypeError("sslContext must be an ssl.SSLContext or None")
        parts = urllib.parse.urlsplit(endpoint.strip())
        if parts.scheme.lower() not in ('http', 'https'):
            raise ValueError("endpoint must start with http:// or https://")
        if not parts.hostname:
            raise ValueError("endpoint must have a host")
        if parts.username is not None or parts.password is not None:
            raise ValueError("endpoint must not hold a user name or a password, give an Authorization header")
        if parts.query or parts.fragment:
            raise ValueError("endpoint must not hold a query or a fragment")
        self.__isSecure = parts.scheme.lower() == 'https'
        self.__host = parts.hostname.lower()
        # An invalid port makes urlsplit raise a ValueError here, which is the right answer for a wrong endpoint
        self.__port = parts.port or (443 if self.__isSecure else 80)
        self.__path = parts.path.rstrip('/') + LOGS_PATH
        self.__headers = {'Content-Type': 'application/json', 'User-Agent': f'pysimplelog/{__version__}'}
        if compress:
            self.__headers['Content-Encoding'] = 'gzip'
        for name, value in (headers or {}).items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("a header name and a header value must be text")
            if len(name) == 0 or any(character in name for character in ' \t:\r\n'):
                raise ValueError(f"not a valid header name: {name!r}")
            if '\r' in value or '\n' in value:
                raise ValueError(f"a header value must be on a single line, see the header {name!r}")
            try:
                name.encode('ascii')
                value.encode('latin-1')
            except UnicodeEncodeError:
                # http.client could not write it, and every send would fail the same way for ever
                raise ValueError(f"the header {name!r} has characters that cannot be sent in a header") from None
            if name.lower() in FIXED_HEADERS:
                raise ValueError(f"the header {name!r} is set by the transport and cannot be given")
            self.__headers[name] = value
        if not self.__isSecure and not _is_local_host(self.__host) and any(name.lower() == 'authorization' for name in self.__headers):
            sys.stderr.write(f"pysimplelog WARNING: the endpoint {self.url} is not https and not on this machine, its Authorization "
                             "header is sent in clear text\n")
        self.__timeout = float(timeout)
        self.__compress = compress
        self.__sslContext = (sslContext or ssl.create_default_context()) if self.__isSecure else None
        self.__connection = None
        self.__isClosed = False
        self.__lock = threading.Lock()
        register_for_fork_reset(self)

    def __repr__(self):
        # The headers are left out on purpose: they can hold a token
        return f"{type(self).__name__}({self.url!r})"

    def _reset_after_fork(self):
        """A forked process opens a connection of its own: two processes writing into one stream would mix their requests."""
        self.__lock = threading.Lock()
        connection, self.__connection = self.__connection, None
        if connection is not None and connection.sock is not None:
            # Only this process's copy of the descriptor is closed, with nothing said to the receiver: the connection itself
            # belongs to the parent, which goes on using it
            try:
                os.close(connection.sock.detach())
            except Exception:
                pass

    @property
    def url(self):
        """The full address requests are posted to, without the headers."""
        scheme = 'https' if self.__isSecure else 'http'
        host = f"[{self.__host}]" if ':' in self.__host else self.__host
        return f"{scheme}://{host}:{self.__port}{self.__path}"

    def describe_destination(self):
        """Returns the protocol, the host, the port and the path, which make the receiver. The headers are left out, they hold a token."""
        return {'protocol': 'https' if self.__isSecure else 'http', 'host': self.__host, 'port': self.__port, 'path': self.__path}

    def _connect(self):
        """Makes a connection object. It connects when it is first used."""
        if self.__isSecure:
            return http.client.HTTPSConnection(self.__host, self.__port, timeout=self.__timeout, context=self.__sslContext)
        return http.client.HTTPConnection(self.__host, self.__port, timeout=self.__timeout)

    def _close_connection(self):
        """Closes the connection if there is one. The lock must be held."""
        connection, self.__connection = self.__connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def send(self, body):
        """
        Posts a body to the receiver and says how it answered.

        A connection that the receiver closed while it was idle is replaced and the request is sent again at once, once. If the
        receiver had already handled the first one, it gets the same records twice, which the identifier ``log.record.uid`` of each
        record lets it recognise.

        :Parameters:
            #. body (bytes): The JSON body of the request, see :class:`pysimplelog.contrib.otlp_encoder.OtlpLogEncoder`.

        :Returns:
            #. response (OtlpResponse): How it went. Nothing is raised for a network problem or for an answer.

        :Raises:
            #. TypeError: If *body* is not bytes, which is a mistake of the caller and not a problem of the network.
        """
        if not isinstance(body, (bytes, bytearray)):
            raise TypeError("body must be bytes")
        try:
            payload = gzip.compress(body, compresslevel=3, mtime=0) if self.__compress else body
        except Exception as error:
            return OtlpResponse(ERROR, message=type(error).__name__)
        with self.__lock:
            if self.__isClosed:
                return OtlpResponse(RETRY, message='closed')
            for attempt in (1, 2):
                isReused = self.__connection is not None
                if self.__connection is None:
                    self.__connection = self._connect()
                try:
                    self.__connection.request('POST', self.__path, body=payload, headers=self.__headers)
                    reply = self.__connection.getresponse()
                    data = reply.read(MAX_RESPONSE_BYTES + 1)
                    status, retryAfterText = reply.status, reply.getheader('Retry-After')
                    # The connection is reused only when the reply was read to its end. One that is too long, one that stopped
                    # early, and one the receiver said to close all end up here
                    mustClose = not reply.isclosed()
                except (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError, http.client.CannotSendRequest) as error:
                    self._close_connection()
                    if isReused and attempt == 1:
                        continue
                    return OtlpResponse(RETRY, message=type(error).__name__)
                except Exception as error:
                    self._close_connection()
                    return OtlpResponse(RETRY, message=type(error).__name__)
                retryAfter = parse_retry_after(retryAfterText)
                if mustClose:
                    self._close_connection()
                return self._classify(status, retryAfter, data)
            return OtlpResponse(RETRY, message='no answer')

    @staticmethod
    def _classify(status, retryAfter, data):
        """Turns a status and a body into an :class:`OtlpResponse`."""
        if 200 <= status < 300:
            rejected, message = 0, None
            try:
                partial = json.loads(data.decode('utf-8')).get('partialSuccess') if len(data) > 0 else None
                if isinstance(partial, dict):
                    rejected = max(int(partial.get('rejectedLogRecords') or 0), 0)
                    message = _one_line(partial['errorMessage']) if partial.get('errorMessage') else None
            except Exception:
                # A body that is not JSON, or has other types, says nothing more: the request was accepted
                pass
            return OtlpResponse(OK, status, None, rejected, message)
        if status in RETRYABLE_STATUS:
            return OtlpResponse(RETRY, status, retryAfter)
        if status in REFUSED_STATUS:
            return OtlpResponse(REFUSED, status)
        return OtlpResponse(ERROR, status)

    def close(self):
        """Closes the connection. Idempotent, and a send after it answers ``RETRY`` without trying."""
        with self.__lock:
            self.__isClosed = True
            self._close_connection()
