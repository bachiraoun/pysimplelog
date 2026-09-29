"""Stdlib-only network transports for shipping log bytes to a collector.

Every transport implements the same two-method contract (``send`` and
``close``) so :class:`pysimplelog.contrib.siem_sink.SiemForwardSink` can
treat them interchangeably. None of these classes know anything about
pysimplelog, RFC 5424, or log records -- they just move bytes over a
wire. That separation keeps each piece independently testable and
matches pysimplelog's own house rule of zero mandatory third-party
dependencies: everything here is built on ``socket``, ``ssl``, and
``urllib`` from the standard library.

:Transports:
    #. TCPSyslogTransport -- RFC 6587 octet-counted framing over TCP,
       optionally wrapped in TLS. The industry-standard way to ship
       syslog reliably (stream framing avoids the message-splitting
       ambiguity that plain newline-delimited TCP syslog has).
    #. UDPSyslogTransport -- fire-and-forget RFC 5424 datagrams. Lowest
       overhead, no delivery guarantee, but still what a lot of legacy
       SIEM (Security Information and Event Management)/syslog-ng/rsyslog
       collectors expect on port 514.
    #. HTTPTransport -- generic HTTP(S) POST for webhook-style or
       token-authenticated HTTP ingestion (e.g. Splunk HEC). Use
       ``splunk_hec_headers()`` for a ready-made Splunk-compatible
       header set.
"""
import json
import socket
import ssl
import threading
import urllib.request

__all__ = [
    'Transport', 'TCPSyslogTransport', 'UDPSyslogTransport', 'HTTPTransport',
    'splunk_hec_headers', 'splunk_hec_payload_builder',
]


class Transport:
    """Minimal transport contract: send bytes, close cleanly.

    Not an ``abc.ABC`` on purpose -- pysimplelog's own style favours
    duck typing (see ``add_sink``'s ``write()``-only handler contract)
    over enforced inheritance. Any object exposing ``send(bytes)`` and
    ``close()`` works.
    """

    def send(self, payload):
        """Send *payload* (bytes) to the collector or raise on failure."""
        raise NotImplementedError

    def close(self):
        """Release any held resources (sockets, connections). Idempotent."""


class TCPSyslogTransport(Transport):
    """RFC 6587 octet-counted TCP syslog transport, with optional TLS.

    Octet-counting (``f"{len(msg)} {msg}"``) is used instead of
    newline-delimited framing because pysimplelog messages may contain
    embedded newlines (tracebacks, ``data=`` payloads) -- octet-counting
    is the only TCP syslog framing that is unambiguous regardless of
    message content.

    The socket is opened lazily on first ``send`` and kept alive across
    calls; a failed send drops the socket so the next call reconnects.
    Thread-safe: a single instance may be shared, guarded by an internal
    lock (the sink normally only calls it from its own worker thread,
    but sharing across multiple sinks is safe too).

    :Parameters:
        #. host (str): Collector hostname or IP.
        #. port (int): Collector TCP port.
        #. useTls (bool): Wrap the connection in TLS. Default False.
        #. sslContext (ssl.SSLContext, None): Custom context (e.g. for
           mutual TLS via ``load_cert_chain``). When None and
           ``useTls`` is True, ``ssl.create_default_context()`` is used.
        #. connectTimeout (float): Seconds allowed for the TCP/TLS handshake.
        #. sendTimeout (float): Seconds allowed for each ``sendall``.
    """

    def __init__(self, host, port, useTls=False, sslContext=None,
                 connectTimeout=5.0, sendTimeout=5.0):
        self.host = host
        self.port = port
        self.useTls = useTls
        self.sslContext = sslContext or (ssl.create_default_context() if useTls else None)
        self.connectTimeout = connectTimeout
        self.sendTimeout = sendTimeout
        self._sock = None
        self._lock = threading.Lock()

    def _connect(self):
        raw = socket.create_connection((self.host, self.port), timeout=self.connectTimeout)
        if self.useTls:
            raw = self.sslContext.wrap_socket(raw, server_hostname=self.host)
        raw.settimeout(self.sendTimeout)
        return raw

    def send(self, payload):
        with self._lock:
            if self._sock is None:
                self._sock = self._connect()
            framed = f'{len(payload)} '.encode('ascii') + payload
            try:
                self._sock.sendall(framed)
            except Exception:
                self._close_locked()
                raise

    def _close_locked(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def close(self):
        with self._lock:
            self._close_locked()


class UDPSyslogTransport(Transport):
    """Fire-and-forget UDP syslog transport.

    No connection state, no delivery guarantee, effectively zero
    latency impact on the caller. RFC 5424 recommends keeping UDP
    datagrams under ~2048 bytes for broad collector compatibility --
    that truncation, if wanted, is the formatter's job, not this
    transport's.

    :Parameters:
        #. host (str): Collector hostname or IP.
        #. port (int): Collector UDP port (traditionally 514).
    """

    def __init__(self, host, port):
        self.addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, payload):
        self._sock.sendto(payload, self.addr)

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


class HTTPTransport(Transport):
    """Generic HTTP(S) POST transport using only ``urllib`` (no ``requests``).

    Suitable for webhook-style ingestion or token-authenticated HTTP
    endpoints (Splunk HEC, Elastic ingest pipelines fronted by an HTTP
    listener, custom SIEM collectors, etc.). The raw formatted syslog
    line is handed to ``payloadBuilder`` so callers control the exact
    JSON envelope; the default wraps it as ``{"event": "<line>"}``.

    :Parameters:
        #. url (str): Full endpoint URL, e.g. ``https://collector:8088/services/collector/event``.
        #. headers (dict, None): Extra HTTP headers (auth tokens, etc.).
        #. timeout (float): Seconds allowed for the whole request.
        #. payloadBuilder (callable, None): ``f(raw_bytes) -> bytes``.
           Defaults to UTF-8 JSON ``{"event": ...}``.
    """

    def __init__(self, url, headers=None, timeout=5.0, payloadBuilder=None):
        self.url = url
        self.headers = dict(headers or {})
        self.headers.setdefault('Content-Type', 'application/json')
        self.timeout = timeout
        self.payloadBuilder = payloadBuilder or self._default_payload_builder

    @staticmethod
    def _default_payload_builder(raw):
        return json.dumps({'event': raw.decode('utf-8', 'replace')}).encode('utf-8')

    def send(self, payload):
        body = self.payloadBuilder(payload)
        request = urllib.request.Request(self.url, data=body, headers=self.headers, method='POST')
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status >= 300:
                raise RuntimeError(f'HTTP sink received status {response.status} from {self.url}')

    def close(self):
        pass


def splunk_hec_headers(token):
    """Build the ``Authorization`` header Splunk's HTTP Event Collector expects.

    :Parameters:
        #. token (str): The HEC token configured on the Splunk input.

    :Returns:
        #. headers (dict): Ready to pass as ``HTTPTransport(..., headers=...)``.
    """
    return {'Authorization': f'Splunk {token}'}


def splunk_hec_payload_builder(sourcetype='pysimplelog', index=None, source=None):
    """Build a ``payloadBuilder`` producing Splunk HEC-shaped JSON events.

    :Parameters:
        #. sourcetype (str): Splunk sourcetype tag for these events.
        #. index (str, None): Target Splunk index, if not the HEC token's default.
        #. source (str, None): Splunk source tag, if wanted.

    :Returns:
        #. builder (callable): ``f(raw_bytes) -> bytes`` for ``HTTPTransport``.
    """
    def _build(raw):
        event = {'event': raw.decode('utf-8', 'replace'), 'sourcetype': sourcetype}
        if index is not None:
            event['index'] = index
        if source is not None:
            event['source'] = source
        return json.dumps(event).encode('utf-8')
    return _build
