"""RFC 5424 structured-syslog forwarding sink for pysimplelog.

Design summary (see the code-audit notes this was born from):

    #. pysimplelog's ``add_sink()`` calls ``handler.write(record)`` by
       default, which only ever carries the plain formatted text -- no
       logType, no level. Recovering the real RFC 5424 severity by
       scraping that text back apart would be fragile (it breaks the
       moment someone changes the format string). Instead, this sink
       implements pysimplelog's optional ``write_record(record, logType,
       level)`` handler contract: when a handler exposes that method,
       pysimplelog's dispatch calls it instead of ``write()``, handing
       over the exact logType and numeric level for every record. That
       means ``attach()`` only needs to register ONE sink for the whole
       logger -- no more one-sink-per-logType. Handlers that only
       implement plain ``write()`` still work everywhere else in
       pysimplelog; this richer contract is purely additive and opt-in.

    #. pysimplelog's own dispatch -- whether synchronous or its
       ``enqueue=True`` background worker -- calls every active sink's
       handler **sequentially on one shared thread**. A sink that
       blocks on network I/O (a slow/unreachable SIEM, Security
       Information and Event Management, collector) stalls that
       thread, which backs up file and stdout logging for the whole
       application. pysimplelog's core solves this generically with an
       opt-in ``threaded=True`` sink: the sink gets its own private
       queue and dedicated worker thread, so dispatch only ever
       enqueues and returns. ``attach()`` turns this on by default for
       the SIEM sink specifically, since network sinks are the risky,
       blocking ones -- ``SiemForwardSink`` itself stays a plain
       synchronous handler (format, send, retry) and relies entirely on
       that core thread to stay out of everyone else's way.

    #. Network calls fail. A circuit breaker stops hammering a dead
       collector with per-record connection attempts (each of which
       would otherwise cost a full connect-timeout), and retries with
       backoff give a transient failure a couple of chances before the
       record is dropped for good.

Works with any pysimplelog ``Logger``: a core version without the
optional ``write_record()`` dispatch hook simply falls back to plain
``write()``, which still forwards every record, just always tagged as
Informational (severity 6) since the logType is unknown on that path.

Nothing here imports from ``SimpleLog.py`` beyond the public
``Logger.add_sink()`` / ``remove_sink()`` API, so it works against any
pysimplelog ``Logger`` instance without modification.
"""
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone

__all__ = [
    'SeverityMap', 'RFC5424Formatter', 'CircuitBreaker', 'SiemForwardSink',
    'attach', 'detach', 'quick_attach',
    'FACILITY_USER', 'FACILITY_LOCAL0', 'FACILITY_LOCAL1',
]

# RFC 5424 facility numbers (subset commonly used for application logs).
# LOCAL0-7 are the conventional choice for app-generated syslog so a SIEM
# or syslog-ng/rsyslog config can route/filter on facility without
# colliding with OS-level facilities like kern, auth, cron, etc.
FACILITY_USER = 1
FACILITY_LOCAL0 = 16
FACILITY_LOCAL1 = 17

_WHITESPACE_RE = re.compile(r'\s+')


class SeverityMap:
    """Maps a pysimplelog logType name to an RFC 5424 severity.

    RFC 5424 severities: 0 Emergency, 1 Alert, 2 Critical, 3 Error,
    4 Warning, 5 Notice, 6 Informational, 7 Debug.

    Resolution is one predictable step: exact, case-insensitive match
    against the name-based table (covers pysimplelog's built-in types --
    debug/info/warn/error/critical/... -- plus anything passed in via
    *overrides*). Any logType that doesn't match lands on 6
    (Informational) by default -- there is no guessing from the numeric
    level. If a custom logType needs a different severity, pass it
    explicitly via *overrides*.

    :Parameters:
        #. overrides (dict, None): Extra/overriding {name (str, lowercase): severity (0-7)} entries.
    """

    _NAME_OVERRIDES = {
        'debug': 7, 'trace': 7,
        'info': 6, 'important': 6, 'notice': 5,
        'warn': 4, 'warning': 4,
        'error': 3,
        'critical': 2,
        'super critical': 1, 'supercritical': 1, 'alert': 1,
        'emergency': 0,
    }

    def __init__(self, overrides=None):
        self._overrides = dict(self._NAME_OVERRIDES)
        if overrides:
            self._overrides.update({k.lower(): v for k, v in overrides.items()})

    def resolve(self, logType, level):
        """
        Return the RFC 5424 severity for a given logType.

        :Parameters:
            #. logType (str, None): The pysimplelog logType name to resolve.
            #. level (int, None): The numeric level registered for that
               logType. Not used by this base implementation -- kept in
               the signature so callers and subclasses can key overrides
               on level too if they ever need to.

        :Returns:
            #. severity (int): RFC 5424 severity, 0 (Emergency) through
               7 (Debug). Defaults to 6 (Informational) for any logType
               not found in the override table.
        """
        key = str(logType).strip().lower()
        return self._overrides.get(key, 6)


class RFC5424Formatter:
    """Wraps an already-formatted pysimplelog line in an RFC 5424 syslog header.

    Output shape::

        <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID [SD-ID key="val"] MSG

    Note on structured-data (SD-ID): RFC 5424 SD-IDs that include an
    enterprise number (``name@<PEN>``) are only globally unambiguous if
    ``<PEN>`` is an IANA-assigned Private Enterprise Number. This
    formatter defaults to ``meta@0``, which is a placeholder, not a real
    PEN -- fine for internal/self-hosted SIEM ingestion, but if you're
    shipping to a multi-tenant or standards-strict collector, pass your
    org's real PEN via ``enterpriseId``, or set ``includeStructuredData=False``
    to omit the SD block entirely (NILVALUE ``-``) rather than ship a
    technically-invalid one silently.

    :Parameters:
        #. appName (str): RFC 5424 APP-NAME field. Default 'pysimplelog'.
        #. facility (int): Syslog facility number. Default FACILITY_LOCAL0.
        #. hostname (str, None): Overrides ``socket.gethostname()``.
        #. enterpriseId (int): Enterprise number used in the SD-ID (see note above).
        #. includeStructuredData (bool): Emit the SD block. Default True.
        #. collapseNewlines (bool): Replace embedded newlines (tracebacks,
           ``data=`` payloads) with literal ``\\n`` so the wire message stays
           single-line for line-oriented collectors. Default True. Set False
           only when the transport guarantees unambiguous framing (e.g.
           TCPSyslogTransport's octet-counting).
    """

    def __init__(self, appName='pysimplelog', facility=FACILITY_LOCAL0,
                 hostname=None, enterpriseId=0, includeStructuredData=True,
                 collapseNewlines=True):
        self.appName = appName
        self.facility = facility
        self.hostname = self._nil_safe(hostname or socket.gethostname())
        self.enterpriseId = enterpriseId
        self.includeStructuredData = includeStructuredData
        self.collapseNewlines = collapseNewlines
        self._pid = os.getpid()

    def format(self, line, logType, severity):
        """Build one RFC 5424 syslog message for a single log record.

        :Parameters:
            #. line (str): The fully-formatted pysimplelog record text.
            #. logType (str): The pysimplelog logType this record belongs to.
            #. severity (int): RFC 5424 severity (0-7), from SeverityMap.

        :Returns:
            #. message (str): Ready-to-encode RFC 5424 syslog line.
        """
        messageText = line.rstrip('\n')
        if self.collapseNewlines:
            messageText = messageText.replace('\r\n', '\\n').replace('\n', '\\n')
        priorityValue = self.facility * 8 + severity
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        messageId = self._nil_safe(_WHITESPACE_RE.sub('_', str(logType))[:32])
        structuredData = self._build_structured_data(logType, severity)
        return f'<{priorityValue}>1 {timestamp} {self.hostname} {self.appName} {self._pid} {messageId} {structuredData} {messageText}'

    def _build_structured_data(self, logType, severity):
        """Builds the RFC 5424 structured-data element carrying log type and severity."""
        if not self.includeStructuredData:
            return self.NILVALUE
        escapedType = self._escape_structured_data(str(logType))
        return f'[meta@{self.enterpriseId} logtype="{escapedType}" severity="{severity}"]'

    NILVALUE = '-'

    @classmethod
    def _nil_safe(cls, value):
        """Returns the value, or the RFC 5424 nil value '-' when it is empty."""
        return value if value else cls.NILVALUE

    @staticmethod
    def _escape_structured_data(value):
        """Escapes backslash, quote and bracket characters as RFC 5424 requires."""
        return value.replace('\\', '\\\\').replace('"', '\\"').replace(']', '\\]')


class CircuitBreaker:
    """Stops hammering a dead collector with connection attempts.

    Simple closed/open state machine (no half-open bookkeeping beyond
    "let one probe through after the reset timeout"): after
    ``failureThreshold`` consecutive failures the breaker opens and
    ``allow()`` returns False for ``resetTimeout`` seconds, after which
    one call is allowed through to probe recovery.

    :Parameters:
        #. failureThreshold (int): Consecutive failures before opening.
        #. resetTimeout (float): Seconds before allowing a probe after opening.
    """

    def __init__(self, failureThreshold=5, resetTimeout=30.0):
        self.failureThreshold = failureThreshold
        self.resetTimeout = resetTimeout
        self._failures = 0
        self._openedAt = None
        self._lock = threading.Lock()

    def allow(self):
        """
        Return whether a send attempt should proceed right now.

        :Returns:
            #. allowed (bool): True if the breaker is closed or the reset timeout has elapsed.
        """
        with self._lock:
            if self._openedAt is None:
                return True
            return (time.monotonic() - self._openedAt) >= self.resetTimeout

    def record_success(self):
        """Reset the breaker back to closed after a successful send."""
        with self._lock:
            self._failures = 0
            self._openedAt = None

    def record_failure(self):
        """Count one failed send and open the breaker once the threshold is reached."""
        with self._lock:
            self._failures += 1
            if self._failures >= self.failureThreshold and self._openedAt is None:
                self._openedAt = time.monotonic()


class SiemForwardSink:
    """Formats and sends one RFC 5424 record at a time -- safe to register
    directly via ``add_sink()``, but only non-blocking when registered
    with ``threaded=True`` (which ``attach()`` does by default).

    This sink does its own work synchronously: format, resolve severity,
    try the transport, retry with backoff, trip the circuit breaker on
    repeated failure. It owns no queue and no thread of its own --
    when used through ``attach()``, pysimplelog's core ``threaded=True``
    sink support is what keeps a slow or unreachable SIEM (Security
    Information and Event Management) collector from blocking your
    application's other logging. If you ever register this sink
    yourself with ``threaded=False``, every ``logger.error(...)`` call
    blocks on the network until delivery succeeds, fails for good, or
    the circuit breaker rejects it outright -- don't do that unless you
    specifically want synchronous delivery.

    Exposes both handler contracts pysimplelog understands:
    ``write_record(record, logType, level)`` is used automatically when
    pysimplelog's dispatch supports it, giving an accurate RFC 5424
    severity per record. Plain ``write(record)`` is the fallback for
    dispatchers that don't know about ``write_record`` -- it still
    forwards every record, just always as Informational since the
    logType is unknown on that path.

    Delivery guarantees: this is best-effort, not guaranteed. A failed
    send is retried with backoff up to ``maxRetries`` times; once that
    is exhausted, or once the circuit breaker is open, the record is
    dropped permanently (watch ``onDrop``/``onError`` and ``.stats`` to
    see this happen). Nothing here is queued to disk, and nothing
    survives a process crash mid-delivery. When registered threaded,
    records queued but not yet handed to write_record() also don't
    survive a crash -- see pysimplelog's ``threaded`` sink docs.

    Use ``attach(logger, transport)`` rather than constructing and
    wiring this by hand -- it takes care of registration and threading.

    :Parameters:
        #. transport: Object with ``send(bytes)`` / ``close()`` -- see
           :mod:`pysimplelog.contrib.siem_transport`.
        #. formatter (RFC5424Formatter, None): Defaults to a stock instance.
        #. severityMap (SeverityMap, None): Resolves a pysimplelog logType
           to an RFC 5424 severity. Defaults to a stock instance -- see
           :class:`SeverityMap` for the built-in name table and how to
           add overrides for custom log types.
        #. breakerFailureThreshold (int): Consecutive send failures before
           the circuit opens and records are dropped without even trying.
        #. breakerResetTimeout (float): Seconds before probing a dead collector again.
        #. retryBackoffBase (float): Initial retry delay in seconds.
        #. retryBackoffMax (float): Retry delay ceiling in seconds.
        #. maxRetries (int): Extra attempts per record after the first
           failure. Each retry sleeps, blocking whichever thread called
           write_record() -- normally your dedicated core sink thread,
           never pysimplelog's shared dispatch thread.
        #. onDrop (callable, None): ``f((record, logType, severity))``, called
           whenever a record is dropped (breaker open, or retries exhausted).
           Exceptions from it are swallowed.
        #. onError (callable, None): ``f(exception, (record, logType, severity))``,
           called on every failed send attempt. Exceptions from it are swallowed.
    """

    def __init__(self, transport, formatter=None, severityMap=None,
                 breakerFailureThreshold=5, breakerResetTimeout=30.0,
                 retryBackoffBase=0.5, retryBackoffMax=10.0, maxRetries=2,
                 onDrop=None, onError=None):
        self._transport = transport
        self._formatter = formatter or RFC5424Formatter()
        self._severityMap = severityMap or SeverityMap()
        self._breaker = CircuitBreaker(breakerFailureThreshold, breakerResetTimeout)
        self._retryBackoffBase = retryBackoffBase
        self._retryBackoffMax = retryBackoffMax
        self._maxRetries = maxRetries
        self._onDrop = onDrop
        self._onError = onError
        self._statsLock = threading.Lock()
        self.stats = {'sent': 0, 'dropped': 0, 'errors': 0}

    def write(self, record):
        """
        Plain fallback for dispatchers that only know the base
        ``write(str)`` sink contract. The logType is unknown on this
        path, so severity always resolves to whatever :class:`SeverityMap`
        returns for an unrecognized type (Informational by default).
        """
        self.write_record(record, None, None)

    def write_record(self, record, logType, level):
        """
        Preferred entry point: called by pysimplelog with the logType and
        numeric level alongside the formatted text, so the real RFC 5424
        severity can be resolved instead of defaulted. Formats and sends
        the record right here, synchronously, retrying on failure --
        register this sink with ``threaded=True`` (the ``attach()``
        default) so this work happens on its own dedicated thread
        instead of blocking pysimplelog's shared dispatch.

        :Parameters:
            #. record (str): The fully-formatted pysimplelog record text.
            #. logType (str, None): The pysimplelog logType this record belongs to.
            #. level (int, None): The numeric level registered for that logType.
        """
        severity = self._severityMap.resolve(logType, level)
        item = (record, logType, severity)
        if not self._breaker.allow():
            self._record_drop(item)
            return
        payload = self._formatter.format(record, logType, severity).encode('utf-8')
        attempt = 0
        while True:
            try:
                self._transport.send(payload)
            except Exception as exc:
                attempt += 1
                self._breaker.record_failure()
                with self._statsLock:
                    self.stats['errors'] += 1
                if self._onError:
                    self._safe_callback(self._onError, exc, item)
                if attempt > self._maxRetries or not self._breaker.allow():
                    self._record_drop(item)
                    return
                time.sleep(min(self._retryBackoffBase * (2 ** (attempt - 1)), self._retryBackoffMax))
                continue
            self._breaker.record_success()
            with self._statsLock:
                self.stats['sent'] += 1
            return

    def _record_drop(self, item):
        """Counts a dropped record and notifies the onDrop callback."""
        with self._statsLock:
            self.stats['dropped'] += 1
        if self._onDrop:
            self._safe_callback(self._onDrop, item)

    @staticmethod
    def _safe_callback(callback, *args):
        """Calls a user callback and swallows its errors."""
        try:
            callback(*args)
        except Exception:
            pass  # a broken user callback must never take down the calling thread

    def close(self, timeout=5.0):
        """Close the transport.

        :Parameters:
            #. timeout (float): Accepted for backward compatibility, unused --
               there is no internal queue or thread left to drain here. If this
               sink is registered threaded, call ``logger.flush(timeout=...)``
               first to wait for pysimplelog's own per-sink queue to drain.
        """
        self._transport.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def attach(logger, transport, formatter=None, severityMap=None, sinkName='siem',
           enabled=True, minLevel=None, maxLevel=None,
           logTypeFlags=None, defaultFlag=True, threaded=True, threadQueueSize=1000,
           **sinkKwargs):
    """Wire a SIEM (Security Information and Event Management) forwarder
    into a pysimplelog ``Logger`` as a single sink.

    Delivery is best-effort, not guaranteed -- see :class:`SiemForwardSink`
    for exactly what happens when a send fails or its queue fills up.

    Registers exactly ONE ``add_sink()`` entry, threaded by default. Thanks
    to pysimplelog's optional ``write_record(record, logType, level)``
    handler contract, that one sink receives the real logType and numeric
    level for every record, so severity is resolved correctly without
    needing one sink per logType. And because network sinks are the risky,
    slow ones, ``threaded=True`` by default means all the formatting,
    sending, and retrying happens on its own dedicated thread -- a slow or
    dead SIEM collector can never stall your application's other logging.
    Use *logTypeFlags*/*defaultFlag* (forwarded straight to ``add_sink()``)
    to restrict which log types actually reach it -- e.g.
    ``logTypeFlags={'error': True, 'critical': True}, defaultFlag=False``
    to forward only errors and criticals.

    :Parameters:
        #. logger (pysimplelog.Logger): The logger to attach to.
        #. transport: A ``send(bytes)``/``close()`` transport (see ``siem_transport``).
        #. formatter (RFC5424Formatter, None): Defaults to a stock instance.
        #. severityMap (SeverityMap, None): Defaults to a stock instance.
        #. sinkName (str): The ``add_sink()`` name to register under.
        #. enabled (bool): Forwarded to ``add_sink()``.
        #. minLevel (number, None): Forwarded to ``add_sink()``.
        #. maxLevel (number, None): Forwarded to ``add_sink()``.
        #. logTypeFlags (dict, None): Forwarded to ``add_sink()`` -- per-type
           enable/disable for this one sink.
        #. defaultFlag (bool): Forwarded to ``add_sink()`` -- the fallback
           for any logType missing from *logTypeFlags*. True (default)
           means "everything unless excluded"; False means "nothing
           unless explicitly included."
        #. threaded (bool): Forwarded to ``add_sink()``. Default True --
           see above for why. Only set this False if you specifically
           want synchronous, blocking delivery.
        #. threadQueueSize (int): Forwarded to ``add_sink()`` as the
           bounded capacity of this sink's private queue when *threaded*
           is True. Ignored otherwise.
        #. sinkKwargs: Forwarded to ``SiemForwardSink()`` (retries,
           breaker tuning, callbacks...).

    :Returns:
        #. sink (SiemForwardSink): The forwarder. Keep a reference and
           call ``sink.close()`` (or ``detach()``) at shutdown.

    Basic TCP syslog::

        from pysimplelog.contrib import siem_transport
        transport = siem_transport.TCPSyslogTransport('collector.mycompany.com', 6514)
        sink = attach(logger, transport)

    Only forward errors and criticals::

        sink = attach(logger, transport,
                       logTypeFlags={'error': True, 'critical': True}, defaultFlag=False)

    Custom formatter and severity overrides::

        formatter = RFC5424Formatter(appName='myapp', facility=FACILITY_LOCAL1)
        severityMap = SeverityMap(overrides={'audit': 5})
        sink = attach(logger, transport, formatter=formatter, severityMap=severityMap)

    More than one SIEM sink on the same logger -- different collectors, or
    splitting log types across endpoints -- just give each its own sinkName::

        criticalSink = attach(logger, criticalTransport, sinkName='siem-critical',
                                logTypeFlags={'error': True, 'critical': True}, defaultFlag=False)
        auditSink = attach(logger, auditTransport, sinkName='siem-audit',
                             logTypeFlags={'info': True}, defaultFlag=False)

    Synchronous, blocking delivery -- only if you specifically want it::

        sink = attach(logger, transport, threaded=False)

    Tuning retries, breaker, and callbacks (forwarded to SiemForwardSink)::

        sink = attach(logger, transport, maxRetries=1, breakerFailureThreshold=3,
                       onDrop=lambda item: print('dropped', item))
    """
    sink = SiemForwardSink(transport, formatter=formatter, severityMap=severityMap, **sinkKwargs)
    logger.add_sink(sinkName, sink, enabled=enabled, minLevel=minLevel, maxLevel=maxLevel,
                     logTypeFlags=logTypeFlags, defaultFlag=defaultFlag,
                     threaded=threaded, threadQueueSize=threadQueueSize)
    return sink


def detach(logger, sink, sinkName='siem', close=True, timeout=5.0):
    """Undo ``attach()``: remove the registered sink and close the transport.

    :Parameters:
        #. logger (pysimplelog.Logger): The logger ``attach()`` was called on.
        #. sink (SiemForwardSink): The value returned by ``attach()``.
        #. sinkName (str): Must match the name used in ``attach()``.
        #. close (bool): Also call ``sink.close()`` (closes the transport).
           Default True.
        #. timeout (float): Forwarded to ``logger.remove_sink()`` -- seconds
           to wait for a threaded sink's private queue to drain before its
           thread is stopped anyway.
    """
    try:
        logger.remove_sink(sinkName, timeout=timeout)
    except (ValueError, TypeError):
        pass
    if close:
        sink.close(timeout=timeout)


def quick_attach(logger, protocol, host=None, port=None, url=None,
                  useTls=False, sslContext=None, headers=None,
                  connectTimeout=5.0, sendTimeout=5.0, timeout=5.0,
                  payloadBuilder=None, stream=None, consolePrefix='[SIEM] ',
                  **sinkKwargs):
    """
    Build the right transport from a plain protocol string, then wire it
    into *logger* with :func:`attach`.

    This is the fastest way to turn on SIEM (Security Information and
    Event Management) forwarding: no need to import
    :mod:`pysimplelog.contrib.siem_transport` yourself or construct a
    transport object by hand.

    Delivery is best-effort, not guaranteed -- see :class:`SiemForwardSink`
    for exactly what happens when a send fails or the queue fills up.

    :Parameters:
        #. logger (pysimplelog.Logger): The logger to attach to.
        #. protocol (str): One of 'tcp', 'tcps' (TCP wrapped in TLS),
           'udp', 'http', 'https', or 'console' (prints instead of
           sending -- see ``ConsoleTransport``). Case-insensitive.
        #. host (str, None): Collector hostname or IP. Required for
           'tcp', 'tcps', and 'udp'.
        #. port (int, None): Collector port. Required for 'tcp', 'tcps',
           and 'udp'.
        #. url (str, None): Full endpoint URL. Required for 'http' and
           'https'.
        #. useTls (bool): Force TLS on for 'tcp'. Always True for 'tcps'
           regardless of this flag.
        #. sslContext (ssl.SSLContext, None): Custom TLS context, only
           used for 'tcp'/'tcps'.
        #. headers (dict, None): Extra HTTP headers, only used for
           'http'/'https'.
        #. connectTimeout (float): Seconds allowed for the TCP/TLS
           handshake, only used for 'tcp'/'tcps'.
        #. sendTimeout (float): Seconds allowed for each TCP send, only
           used for 'tcp'/'tcps'.
        #. timeout (float): Seconds allowed for the whole HTTP request,
           only used for 'http'/'https'.
        #. payloadBuilder (callable, None): Custom HTTP body builder,
           only used for 'http'/'https'. See ``splunk_hec_payload_builder``.
        #. stream (file-like, None): Where to print, only used for
           'console'. Defaults to ``sys.stdout``.
        #. consolePrefix (str): Line prefix, only used for 'console'.
           Default ``'[SIEM] '``.
        #. sinkKwargs: Forwarded to :func:`attach` (``formatter``,
           ``severityMap``, ``sinkName``, ``logTypeFlags``, ``defaultFlag``,
           ``threaded``, ``threadQueueSize``, retry/breaker tuning,
           ``onDrop``, ``onError``, ...).

    :Returns:
        #. sink (SiemForwardSink): The forwarder. Keep a reference and
           call ``detach(logger, sink)`` at shutdown.

    :Raises:
        #. ValueError: If *protocol* is not recognized, or a required
           parameter for that protocol (*host*/*port*, or *url*) is missing.

    Plain TCP syslog::

        sink = quick_attach(logger, protocol='tcp',
                             host='collector.mycompany.com', port=6514)

    TCP syslog wrapped in TLS::

        sink = quick_attach(logger, protocol='tcps',
                             host='collector.mycompany.com', port=6514)

    TCP with mutual TLS (custom client certificate)::

        import ssl
        ctx = ssl.create_default_context()
        ctx.load_cert_chain('client.crt', 'client.key')
        sink = quick_attach(logger, protocol='tcps', host='collector.mycompany.com',
                             port=6514, sslContext=ctx)

    Fire-and-forget UDP syslog::

        sink = quick_attach(logger, protocol='udp',
                             host='collector.mycompany.com', port=514)

    Generic HTTPS webhook ingestion::

        sink = quick_attach(logger, protocol='https',
                             url='https://collector.mycompany.com/ingest')

    Development/demo mode -- print instead of sending, swap the protocol
    string for a real one when you're ready to go live::

        sink = quick_attach(logger, protocol='console')

    Splunk HTTP Event Collector (HEC)::

        from pysimplelog.contrib import siem_transport
        sink = quick_attach(
            logger, protocol='https',
            url='https://splunk.mycompany.com:8088/services/collector/event',
            headers=siem_transport.splunk_hec_headers('SECRET-TOKEN'),
            payloadBuilder=siem_transport.splunk_hec_payload_builder(sourcetype='pysimplelog'),
        )

    Forward only errors and criticals::

        sink = quick_attach(logger, protocol='tcp', host='collector.mycompany.com', port=6514,
                             logTypeFlags={'error': True, 'critical': True}, defaultFlag=False)

    Tuning the forwarder itself (works with any protocol above)::

        sink = quick_attach(logger, protocol='tcp', host='collector.mycompany.com', port=6514,
                             threadQueueSize=5000, maxRetries=1,
                             onDrop=lambda item: print('dropped', item))
    """
    from . import siem_transport
    protocol = protocol.lower()
    if protocol in ('tcp', 'tcps'):
        if host is None or port is None:
            raise ValueError(f"protocol '{protocol}' requires host and port")
        transport = siem_transport.TCPSyslogTransport(
            host, port, useTls=(useTls or protocol == 'tcps'), sslContext=sslContext,
            connectTimeout=connectTimeout, sendTimeout=sendTimeout,
        )
    elif protocol == 'udp':
        if host is None or port is None:
            raise ValueError("protocol 'udp' requires host and port")
        transport = siem_transport.UDPSyslogTransport(host, port)
    elif protocol in ('http', 'https'):
        if url is None:
            raise ValueError(f"protocol '{protocol}' requires url")
        transport = siem_transport.HTTPTransport(
            url, headers=headers, timeout=timeout, payloadBuilder=payloadBuilder,
        )
    elif protocol in ('console', 'print'):
        transport = siem_transport.ConsoleTransport(stream=stream, prefix=consolePrefix)
    else:
        raise ValueError(
            f"unknown protocol '{protocol}' -- expected one of "
            "tcp, tcps, udp, http, https, console"
        )
    return attach(logger, transport, **sinkKwargs)
