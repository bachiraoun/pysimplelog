"""
A sink that sends records to an OpenTelemetry receiver over OTLP/HTTP, in groups, with no third-party package.

It joins three parts: :class:`pysimplelog.contrib.otlp_encoder.OtlpLogEncoder` makes the body, :class:`pysimplelog.contrib.otlp_transport.
OtlpHttpTransport` posts it, and the group delivery of pysimplelog gathers up to ``batchSize`` records, or waits ``batchInterval``
seconds, before it sends them. Add it with ``threaded=True``, so that a log call never waits for the network, and with a ``spool`` when
a record must survive a receiver that is down or a crash. :func:`attach` does the first for you:

.. code-block:: python

    from pysimplelog import Logger
    from pysimplelog.contrib.otlp_sink import OtlpLogSink

    logger = Logger("orders")
    logger.add_sink(
        "otel",
        OtlpLogSink("https://collector.example.org:4318",
                    headers={"Authorization": "Bearer <token>"},
                    resource={"service.name": "orders", "deployment.environment": "production"},
                    compress=True),
        threaded=True, threadQueuePolicy="block",
        spool={"path": "/var/spool/orders/otel", "id": "orders-otel", "maxBytes": 50 * 1024 ** 2, "totalMaxBytes": 200 * 1024 ** 2})

What happens to a group, following the OTLP/HTTP specification:

* The receiver took it: the records are delivered. A ``partialSuccess`` that names refused records is counted in ``partial_rejected``
  and warned about once, and the group is not sent again.
* The receiver is busy or not reachable (429, 502, 503, 504, no answer): the sink tries again at once up to ``maxRetries`` times, after
  the ``Retry-After`` wait when the receiver gave one, or a growing wait with jitter. If it still fails, the group is *not delivered*.
  With a spool it stays on disk and the spool tries again, for ever unless ``maxAttempts`` is set. Without a spool it is dropped and counted.
* The receiver refuses the payload (400, 413, 422): the group is cut in halves until the one record at fault is alone, and that record
  goes to the ``dead`` file of the spool.
* Any other answer (401, 403, 404, 500, a redirect...): the protocol says never to retry. The sink does not retry at once and writes one
  warning. With a spool the records wait for a person to fix the address or the token, instead of being thrown away.
"""

import random
import sys
import threading
import time

try:
    from ..forking import register_for_fork_reset
    from ..sinks import Sink, SPLIT
    from ..tracing import trace_api_available
    from .otlp_encoder import OtlpLogEncoder
    from .otlp_transport import OtlpHttpTransport, OK, RETRY, REFUSED, ERROR
except ImportError:
    from forking import register_for_fork_reset
    from sinks import Sink, SPLIT
    from tracing import trace_api_available
    from contrib.otlp_encoder import OtlpLogEncoder
    from contrib.otlp_transport import OtlpHttpTransport, OK, RETRY, REFUSED, ERROR


# Different messages of partial successes that are reported, so that a receiver cannot fill the log with new ones
MAX_PARTIAL_MESSAGES = 20


def _no_text(record):
    """The sink makes its own body, so the text the base class asks for is empty and costs nothing."""
    return ''


class OtlpLogSink(Sink):
    """
    Sends records to an OTLP/HTTP receiver, in groups.

    :Parameters:
        #. endpoint (str): The address of the receiver, ``https://collector.example.org:4318``, see
           :class:`pysimplelog.contrib.otlp_transport.OtlpHttpTransport`.
        #. headers (dict, None): Extra headers, such as ``Authorization``.
        #. resource (dict, None): Who is sending: ``service.name``, ``service.version``, ``deployment.environment``, see
           :class:`pysimplelog.contrib.otlp_encoder.OtlpLogEncoder`. Without a ``service.name`` the receiver shows ``unknown_service``.
        #. timeout (int, float): Seconds allowed for each step of a request.
        #. compress (bool): True to gzip the body of every request.
        #. sslContext (ssl.SSLContext, None): For ``https``, to trust your own authority or present a client certificate.
        #. batchSize (int): Largest number of records in a request. 512 is the default of the OpenTelemetry SDKs.
        #. batchInterval (int, float): Seconds a group may wait to fill. 1 is the default of the OpenTelemetry SDKs for logs.
        #. captureTrace (bool, None): True to record the identifiers of the active OpenTelemetry span in each record, so that the
           receiver can link the record to its trace. False to not. None, the default, does it when the package ``opentelemetry-api``
           is installed and says nothing when it is not.
        #. severityMap (OtlpSeverityMap, None): How a log type gets its severity number.
        #. eventIdField (str, None): The name of the field that holds the stable identifier of a record, the one a spool adds. Give the same
           name as in the settings of the spool.
        #. scopeVersion (str, None): The version written in each scope.
        #. maxRetries (int): Times a request that failed for a reason that can pass is sent again at once, before the group is given back.
        #. retryBackoffBase (int, float): Seconds before the first of those retries. The wait doubles each time, with a jitter of 20 percent.
        #. retryBackoffMax (int, float): The longest of those waits.

    :Raises:
        #. TypeError: If an argument has the wrong type.
        #. ValueError: If the endpoint, a header or a number is not valid.
    """

    def __init__(self, endpoint, headers=None, resource=None, timeout=10.0, compress=False, sslContext=None, batchSize=512,
                 batchInterval=1.0, captureTrace=None, severityMap=None, eventIdField='event_id', scopeVersion=None, maxRetries=2,
                 retryBackoffBase=0.5, retryBackoffMax=10.0):
        if not isinstance(maxRetries, int) or isinstance(maxRetries, bool):
            raise TypeError("maxRetries must be an integer")
        if maxRetries < 0:
            raise ValueError(f"maxRetries cannot be negative, got {maxRetries}")
        for name, value in (('retryBackoffBase', retryBackoffBase), ('retryBackoffMax', retryBackoffMax)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be a number")
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")
        if retryBackoffBase > retryBackoffMax:
            raise ValueError("retryBackoffBase cannot be larger than retryBackoffMax")
        if captureTrace is not None and not isinstance(captureTrace, bool):
            raise TypeError("captureTrace must be a boolean or None")
        self._transport = OtlpHttpTransport(endpoint, headers=headers, timeout=timeout, compress=compress, sslContext=sslContext)
        self._encoder = OtlpLogEncoder(resource=resource, severityMap=severityMap, eventIdField=eventIdField, scopeVersion=scopeVersion)
        if captureTrace is None:
            captureTrace = trace_api_available()
        super().__init__(formatter=_no_text, terminator='', captureTrace=captureTrace, batchSize=batchSize, batchInterval=batchInterval)
        self._maxRetries = maxRetries
        self._backoffBase = float(retryBackoffBase)
        self._backoffMax = float(retryBackoffMax)
        self._closing = threading.Event()
        self._countsLock = threading.Lock()
        self._counts = {'sent': 0, 'batches': 0, 'bytes': 0, 'partial_rejected': 0, 'retries': 0, 'refused': 0, 'errors': 0,
                        'last_status': None}
        self._warned = set()
        # The messages of partial successes already reported. A success does not clear it, the same message is not worth a line each time
        self._partialWarned = set()

    def _reset_after_fork(self):
        """Gives a forked process locks of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        super()._reset_after_fork()
        self._countsLock = threading.Lock()

    @property
    def url(self):
        """The address requests are posted to, without the headers."""
        return self._transport.url

    @property
    def stats(self):
        """
        Dictionary with the counts of the sink and of the sending: ``sent`` (records the receiver took), ``batches`` (requests it
        took), ``bytes`` (the size of the JSON bodies of those requests, before any compression), ``partial_rejected`` (records a ``partialSuccess`` said
        the receiver refused), ``retries`` (requests sent again at once), ``refused`` (groups refused as a payload), ``errors`` (answers
        the protocol does not retry), ``last_status`` (the last HTTP status, None for no answer), and what every sink counts.
        """
        counts = dict(super().stats)
        with self._countsLock:
            counts.update(self._counts)
        return counts

    def spool_destination(self):
        """Returns the protocol, the host, the port and the path of the receiver. The headers are left out, they hold a token."""
        return self._transport.describe_destination()

    def write_batch(self, items):
        """
        Sends a group of records in one request, and says what became of it. See the description of the module.

        :Parameters:
            #. items (list): The group, as tuples ``(text, record)``. The text is not used.

        :Returns:
            #. outcome (bool, str, None): None when the receiver took the group, False when it is to be tried again, ``SPLIT`` when the
               receiver refuses the payload or the group cannot be encoded.
        """
        try:
            body = self._encoder.encode([record for _, record in items], time.time_ns())
        except Exception as error:
            # Nothing in a record should stop the encoder. If something does, the group cannot be sent as it is, and cutting it
            # in halves finds the record at fault
            self._count('errors')
            self._warn('encode', f"a group of {len(items)} records could not be encoded ({type(error).__name__}), it is cut in halves")
            return SPLIT
        attempt = 0
        while True:
            response = self._transport.send(body)
            with self._countsLock:
                self._counts['last_status'] = response.status
            if response.outcome == OK:
                self._on_success(len(items), len(body), response)
                return None
            if response.outcome == REFUSED:
                self._count('refused')
                what = "the record is given up on" if len(items) == 1 else "smaller groups are sent"
                self._warn(('refused', response.status), f"the receiver at {self.url} refused a group of {len(items)} records with "
                           f"status {response.status}, {what}")
                return SPLIT
            if response.outcome == ERROR:
                self._count('errors')
                self._warn(('error', response.status), f"the receiver at {self.url} answered status {response.status}, which the protocol "
                           "does not retry. Check the address and the credentials. With a spool the records wait")
                return False
            detail = f"status {response.status}" if response.status is not None else f"no answer ({response.message})"
            self._warn(('retry', response.status, response.message), f"the receiver at {self.url} did not take a group of {len(items)} "
                       f"records: {detail}")
            wait = response.retryAfter
            if wait is None and attempt < self._maxRetries:
                wait = min(self._backoffBase * 2 ** attempt, self._backoffMax) * random.uniform(0.8, 1.2)
            if attempt >= self._maxRetries:
                # The caller will try again, and not before the receiver asked
                if wait is not None:
                    self._closing.wait(wait)
                return False
            attempt += 1
            self._count('retries')
            if self._closing.wait(wait):
                return False

    def _on_success(self, count, size, response):
        """Counts a group the receiver took, warns once about records it refused, and ends the run of warnings."""
        with self._countsLock:
            self._counts['sent'] += count
            self._counts['batches'] += 1
            self._counts['bytes'] += size
            self._counts['partial_rejected'] += min(response.rejected, count)
            self._warned.clear()
        if response.rejected > 0 or response.message:
            with self._countsLock:
                isNew = response.message not in self._partialWarned and len(self._partialWarned) < MAX_PARTIAL_MESSAGES
                if isNew:
                    self._partialWarned.add(response.message)
            if isNew:
                self._write_warning(f"the receiver at {self.url} took a request but refused {min(response.rejected, count)} records"
                                    + (f": {response.message}" if response.message else ""))

    def _count(self, name):
        """Adds one to a counter."""
        with self._countsLock:
            self._counts[name] += 1

    def _warn(self, key, text):
        """Writes a warning the first time something happens in a run of failures. A group that goes through ends the run."""
        with self._countsLock:
            if key in self._warned:
                return
            self._warned.add(key)
        self._write_warning(text)

    @staticmethod
    def _write_warning(text):
        """Writes one warning line to the error stream."""
        try:
            sys.stderr.write(f"pysimplelog WARNING: OTLP sink: {text}\n")
        except (OSError, ValueError):
            # The error stream is closed or broken, the counts are still there
            pass

    def close(self):
        """Stops the waits between retries and closes the connection. Idempotent."""
        self._closing.set()
        self._transport.close()


def attach(logger, endpoint, sinkName='otlp', enabled=True, minLevel=None, maxLevel=None, logTypeFlags=None, defaultFlag=True,
           threadQueueSize=10000, threadQueuePolicy='drop_oldest', threadBlockTimeout=None, spool=None, **sinkKwargs):
    """
    Adds an :class:`OtlpLogSink` to a logger as a threaded sink, so that a log call never waits for the network.

    It registers exactly one sink and does nothing else. Without a *spool* the records wait in a queue of memory, and the policy says
    what a full one does. With a spool the records are on disk first, a full queue loses nothing, and *threadQueuePolicy* is not used.

    :Parameters:
        #. logger (Logger): The logger to add the sink to.
        #. endpoint (str): The address of the receiver, see :class:`OtlpLogSink`.
        #. sinkName (str): The name to register the sink under.
        #. enabled (bool): Forwarded to ``add_sink()``.
        #. minLevel (number, None): Forwarded to ``add_sink()``.
        #. maxLevel (number, None): Forwarded to ``add_sink()``.
        #. logTypeFlags (dict, None): Forwarded to ``add_sink()``: which log types reach the sink.
        #. defaultFlag (bool): Forwarded to ``add_sink()``: the answer for a log type missing from *logTypeFlags*.
        #. threadQueueSize (int): Forwarded to ``add_sink()``: the capacity of the queue of the sink.
        #. threadQueuePolicy (str): Forwarded to ``add_sink()``: what a full queue does, ``block``, ``drop_newest``, ``drop_oldest`` or
           ``reject``.
        #. threadBlockTimeout (None, int, float): Forwarded to ``add_sink()``: seconds the ``block`` policy waits.
        #. spool (SpoolConfig, dict, None): Forwarded to ``add_sink()``: keeps the records on disk until the receiver has them.
        #. sinkKwargs: Forwarded to :class:`OtlpLogSink`: ``headers``, ``resource``, ``compress``, ``batchSize`` and the rest.

    :Returns:
        #. sink (OtlpLogSink): The sink. ``logger.remove_sink(sinkName)`` sends what it holds and closes it.

    :Raises:
        #. TypeError, ValueError: If an argument of the sink or of ``add_sink()`` is not valid. Nothing is added then.

    .. code-block:: python

        sink = attach(logger, "https://collector.example.org:4318", resource={"service.name": "orders"}, compress=True,
                      spool={"path": "/var/spool/orders/otel", "id": "orders-otel", "maxBytes": 50 * MB, "totalMaxBytes": 200 * MB})
    """
    sink = OtlpLogSink(endpoint, **sinkKwargs)
    try:
        logger.add_sink(sinkName, sink, enabled=enabled, minLevel=minLevel, maxLevel=maxLevel, logTypeFlags=logTypeFlags,
                        defaultFlag=defaultFlag, threaded=True, threadQueueSize=threadQueueSize, threadQueuePolicy=threadQueuePolicy,
                        threadBlockTimeout=threadBlockTimeout, spool=spool)
    except Exception:
        sink.close()
        raise
    return sink
