"""simple_log defines the Logger and SingleLogger classes for multi-sink,
thread-safe, formatted logging in Python applications.

Usage Examples
==============
    .. code-block:: python

        # import Logger
        from pysimplelog import Logger

        # initialize
        logger=Logger("log test")

        # change log file basename from simplelog to mylog
        logger.set_log_file_basename("mylog")

        # change log file extension from .log to .pylog
        logger.set_log_file_extension("pylog")

        # Add new log types.
        logger.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
        logger.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
        logger.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold"])

        # update error log type
        logger.update_log_type(logType='error', color='pink', attributes=['underline','bold'])

        # print logger
        print(logger, end="\\n\\n")

        # test logging
        logger.info("I am info, called using my shortcut method.")
        logger.log("info", "I am info, called using log method.")

        logger.warn("I am warn, called using my shortcut method.")
        logger.log("warn", "I am warn, called using log method.")

        logger.error("I am error, called using my shortcut method.")
        logger.log("error", "I am error, called using log method.")

        logger.critical("I am critical, called using my shortcut method.")
        logger.log("critical", "I am critical, called using log method.")

        logger.debug("I am debug, called using my shortcut method.")
        logger.log("debug", "I am debug, called using log method.")

        logger.log("super critical", "I am super critical, called using log method because I have no shortcut method.")
        logger.log("wrong", "I am wrong, called using log method because I have no shortcut method.")
        logger.log("important", "I am important, called using log method because I have no shortcut method.")

        # print last logged messages
        print("")
        print("Last logged messages are:")
        print("=========================")
        print(logger.lastRecord)
        print(logger.lastRecords['debug'])
        print(logger.lastRecords['info'])
        print(logger.lastRecords['warn'])
        print(logger.lastRecords['error'])
        print(logger.lastRecords['critical'])

        # log data
        print("")
        print("Log random data and traceback stack:")
        print("====================================")
        logger.info("Check out this data", data=list(range(10)), source="example")
        print("")

        # log error with traceback
        import traceback
        try:
            1/range(10)
        except Exception as err:
            logger.error('%s (is this python ?)'%err, exc_info=True)




**Output:**

.. raw:: html

        <body>
        <pre>

            Logger (Version %AUTO_VERSION)
            log type       |log name       |level     |std flag  |file flag |
            ---------------|---------------|----------|----------|----------|
            wrong          |info           |0.0       |True      |True      |
            debug          |DEBUG          |0.0       |True      |True      |
            important      |info           |0.0       |True      |True      |
            info           |INFO           |10.0      |True      |True      |
            warn           |WARNING        |20.0      |True      |True      |
            error          |ERROR          |30.0      |True      |True      |
            critical       |CRITICAL       |100.0     |True      |True      |
            super critical |SUPER CRITICAL |200.0     |True      |True      |

            2018-09-07 16:07:58 - log test &#60INFO&#62 I am info, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60INFO&#62 I am info, called using log method.
            2018-09-07 16:07:58 - log test &#60WARNING&#62 I am warn, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60WARNING&#62 I am warn, called using log method.
            <span style="color:pink"><b><ins>2018-09-07 16:07:58 - log test &#60ERROR&#62 I am error, called using my shortcut method.</ins></b></span>
            <span style="color:pink"><b><ins>2018-09-07 16:07:58 - log test &#60ERROR&#62 I am error, called using log method.</ins></b></span>
            2018-09-07 16:07:58 - log test &#60CRITICAL&#62 I am critical, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60CRITICAL&#62 I am critical, called using log method.
            2018-09-07 16:07:58 - log test &#60DEBUG&#62 I am debug, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60DEBUG&#62 I am debug, called using log method.
            <span style="color:red"><b><ins>2018-09-07 16:07:58 - log test &#60SUPER CRITICAL&#62 I am super critical, called using log method because I have no shortcut method.</ins></b></span>
            <span style="color:magenta"><del>2018-09-07 16:07:58 - log test &#60info&#62 I am wrong, called using log method because I have no shortcut method.</del></span>
            <style>mark{background-color: orange}</style><mark><b>2015-11-18 14:25:08 - log test &#60info&#62 I am important, called using log method because I have no shortcut method.</b></mark>

            Last logged messages are:
            =========================
            I am important, called using log method because I have no shortcut method.
            I am debug, called using log method.
            I am  info, called using log method.
            I am warn, called using log method.
            I am error, called using log method.
            I am critical, called using log method.

            Log random data and traceback stack:
            ====================================
            2018-09-07 16:07:58 - log test <INFO> Check out this data
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            <span style="color:pink"><b><ins>2015-11-18 14:25:08 - log test &#60ERROR&#62 unsupported operand type(s) for /: 'int' and 'list' (is this python ?)</ins></b></span>
            <font color="pink"><b><ins>  File "&#60stdin&#62", line 4, in &#60module&#62</ins></b></font>


        </pre>
        <body>



bind() — Structured Context Logging
=====================================
    ``bind()`` returns a thin wrapper that attaches key=value pairs to the context of
    every record it logs, without modifying the underlying logger.  Contexts are
    immutable and composable — each ``bind()`` call returns a new wrapper.  The text layout
    writes the context in brackets before the message, JSON writes it as the object ``context``.

    .. code-block:: python

        from pysimplelog import Logger

        logger = Logger("api-server", logToFile=False)

        ## attach request-level context once; use the bound logger everywhere
        def handle_request(requestId, user):
            log = logger.bind(requestId=requestId, user=user)
            log.info("request received")
            log.warn("slow query detected")

            ## compose a deeper context for a nested call
            dbLog = log.bind(table="orders")
            dbLog.debug("executing query")

        handle_request("abc", "alice")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - api-server <INFO>    [requestId=abc user=alice] request received
        2024-01-01 12:00:00 - api-server <WARNING>  [requestId=abc user=alice] slow query detected
        2024-01-01 12:00:00 - api-server <DEBUG>   [requestId=abc user=alice table=orders] executing query

    ``context()`` attaches values to every record made inside a ``with`` block, whatever logger
    makes them, and it follows the flow of the program: the functions the block calls, and each
    asynchronous task started inside it, keep their own values.

    .. code-block:: python

        def handle_request(requestId, user):
            with logger.context(requestId=requestId, user=user):
                logger.info("request received")
                process_order()            ## everything it logs carries requestId and user


catch() — Exception Capture
=============================
    ``catch()`` works as a **decorator**, a **parameterised decorator**, or
    a **context manager**.  It logs the exception and — by default — suppresses
    it so the application keeps running.

    .. code-block:: python

        from pysimplelog import Logger

        logger = Logger("my-app", logToFile=False)

        ## ── 1. bare decorator — uses defaults (logType='error', reraise=False) ──
        @logger.catch
        def parse_config(path):
            with open(path) as fh:
                return fh.read()

        parse_config("/nonexistent/path")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <ERROR> An exception was caught: [Errno 2] No such file or directory: '/nonexistent/path'
        Traceback (most recent call last):
          File "app.py", line 5, in parse_config
        FileNotFoundError: [Errno 2] No such file or directory: '/nonexistent/path'

    .. code-block:: python

        ## ── 2. parameterised decorator — custom level, re-raise enabled ──────
        @logger.catch(logType="critical", reraise=True)
        def connect_db(url):
            raise ConnectionError("timed out")

        try:
            connect_db("postgres://localhost/mydb")
        except ConnectionError:
            logger.warn("falling back to read-only replica")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <CRITICAL> An exception was caught: timed out
        Traceback (most recent call last):
          File "app.py", line 15, in connect_db
        ConnectionError: timed out

        2024-01-01 12:00:00 - my-app <WARNING> falling back to read-only replica

    .. code-block:: python

        ## ── 3. context manager — exception suppressed, execution continues ───
        with logger.catch(logType="warn", reraise=False):
            result = 1 / 0

        logger.info("execution continues after suppressed exception")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <WARNING> An exception was caught: division by zero
        Traceback (most recent call last):
          File "app.py", line 21, in <module>
        ZeroDivisionError: division by zero

        2024-01-01 12:00:00 - my-app <INFO> execution continues after suppressed exception

    .. code-block:: python

        ## ── 4. processors — scrub message + traceback before any sink sees them ──
        ## A processor runs on every record before any sink sees it, so every sink
        ## (local file, stdout, a SIEM/syslog sink via add_sink(), ...) only ever
        ## sees the rewritten record. redact_text() applies a text function to the
        ## message, the traceback and every string field. Useful for stripping
        ## local filesystem paths or other infrastructure detail that must never
        ## leave the process. See add_processor().
        from pysimplelog import redact_text

        def hide_paths(text):
            return text.replace("/opt/myapp/venv/lib/pysimplelog", "<redacted>")

        logger.add_processor(redact_text(hide_paths))

        @logger.catch(logType="error")
        def load_plugin(path):
            raise ImportError("/opt/myapp/venv/lib/pysimplelog/plugins.py not found")

        load_plugin("bad_plugin")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <ERROR> An exception was caught: <redacted>/plugins.py not found
        Traceback (most recent call last):
          File "<redacted>/simple_log.py", line 709, in wrapper
        ImportError: <redacted>/plugins.py not found


add_sink() — Custom Output Sinks
===================================
    Any file-like object with a ``write()`` method can be added as a sink. It is wrapped in a
    :class:`pysimplelog.sinks.StreamSink` that writes the readable text of every record. To choose
    the format, flush mode or destination yourself, add a :class:`pysimplelog.sinks.Sink` object
    instead, such as ``StreamSink(stream, formatter=None)`` for JSON lines.
    Common uses: capturing logs to an in-memory buffer for testing, writing
    to a network socket, or tee-ing to a secondary log file.

    .. code-block:: python

        import io
        from pysimplelog import Logger

        logger = Logger("my-app", logToFile=False)

        ## ── in-memory sink (useful in tests) ─────────────────────────────────
        buffer = io.StringIO()
        logger.add_sink("memory", buffer)

        logger.info("hello buffer")
        logger.error("something went wrong")

    **Output (stdout):**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <INFO>  hello buffer
        2024-01-01 12:00:00 - my-app <ERROR> something went wrong

    .. code-block:: python

        ## buffer captured the same records (no ANSI codes, plain text)
        print(buffer.getvalue())

    **Output (buffer.getvalue()):**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <INFO>  hello buffer
        2024-01-01 12:00:00 - my-app <ERROR> something went wrong

    .. code-block:: python

        ## ── secondary log file ────────────────────────────────────────────────
        audit = open("audit.log", "a")
        logger.add_sink("audit", audit)
        logger.warn("this goes to stdout, buffer, AND audit.log")

        ## ── remove a sink when no longer needed ───────────────────────────────
        logger.remove_sink("memory")
        logger.info("this no longer goes to the in-memory buffer")
        audit.close()

    **Output (stdout, after remove_sink):**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <WARNING> this goes to stdout, buffer, AND audit.log
        2024-01-01 12:00:00 - my-app <INFO>    this no longer goes to the in-memory buffer


enqueue — Non-blocking Mode
==============================
    Set ``enqueue=True`` to route all I/O through a background daemon thread.
    The calling thread returns immediately after each ``log()`` call.
    Call ``flush()`` before process exit to drain the queue.

    .. code-block:: python

        from pysimplelog import Logger

        ## enqueue=True — log calls return in microseconds regardless of I/O load
        logger = Logger("worker", enqueue=True, logToFile=False)

        for i in range(3):
            logger.info("processed item %d" % i)
            ## returns immediately; I/O happens in the background thread

        ## block until all records have been written
        logger.flush()

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - worker <INFO> processed item 0
        2024-01-01 12:00:00 - worker <INFO> processed item 1
        2024-01-01 12:00:00 - worker <INFO> processed item 2

    .. code-block:: python

        ## ── queue backpressure controls ───────────────────────────────────────

        ## throw the new record away when the queue is full
        l2 = Logger("bounded", enqueue=True, logToFile=False,
                    maxQueueSize=500, queueFullPolicy="drop_newest")

        ## throw the record that waited longest away, to keep the newest
        l3 = Logger("fresh", enqueue=True, logToFile=False,
                    maxQueueSize=100, queueFullPolicy="drop_oldest")

        ## block the caller until a slot is free (2-second deadline)
        l4 = Logger("blocking", enqueue=True, logToFile=False,
                    maxQueueSize=100, queueFullPolicy="block",
                    queueBlockTimeout=2.0)

        l2.flush(); l3.flush(); l4.flush()

    **Output (stderr, once for each run of dropped records):**

    .. code-block:: text

        pysimplelog WARNING: the log queue is full, records are being dropped (policy drop_oldest, 1 dropped so far)

    ``reject`` makes the log call raise ``QueueFull``. Every dropped or refused record is counted, and
    ``logger.queueStats`` and ``logger.sink_stats()`` show the counts, the depth and the latency of every sink.


callerInfo — Caller Tagging
==============================
    Set ``callerInfo=True`` to prepend the source file, line number, and
    function name to every log message automatically.

    .. code-block:: python

        from pysimplelog import Logger

        logger = Logger("my-app", callerInfo=True, logToFile=False)

        def process_order(orderId):
            logger.info("processing order %s" % orderId)

        process_order(42)

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <INFO> [orders.py:5 in process_order] processing order 42

    .. code-block:: python

        ## combine with bind() — caller tag and context both appear
        def handle_request(requestId):
            log = logger.bind(requestId=requestId)
            log.debug("request started")

        handle_request("req-001")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <DEBUG> [handler.py:3 in handle_request] [requestId=req-001] request started


Unknown log types
=================
    By default logging with an undefined log type raises ``KeyError``. Set
    ``unknownLogTypePolicy='fallback'`` to log the message under a fallback
    type instead, so a wrong type name never crashes the caller and stays visible.

    .. code-block:: python

        from pysimplelog import Logger

        logger = Logger("app", unknownLogTypePolicy='fallback', fallbackLogType='error', logToFile=False)
        logger.log('typo', 'hello')

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - app <ERROR> Unknown log type 'typo': hello


Processors
==========
    A processor is a function ``f(record) -> record`` that rewrites each log record
    before it reaches any sink (terminal, file, SIEM, ...). It receives the
    :class:`pysimplelog.record.LogRecord`, message, fields and traceback included, so one
    function can hide local paths or secrets everywhere. A processor applies to every
    record: to treat some differently, test ``record.logType`` inside the function. A processor
    that raises drops the record rather than let it through unchanged.
    :func:`pysimplelog.processors.redact_text` turns a text function into a processor, and
    :func:`pysimplelog.processors.redact_fields` hides the value of sensitive keys.

    .. code-block:: python

        from pysimplelog import Logger, redact_text, redact_fields

        def hide_paths(text):
            return text.replace("/opt/myapp", "...")

        logger = Logger("app", logToFile=False, processors=[redact_text(hide_paths)])
        logger.add_processor(redact_fields())
        logger.error("cannot open /opt/myapp/data.txt")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - app <ERROR> cannot open .../data.txt


"""
# python standard distribution imports
import os, sys, copy, re, atexit, threading, traceback, functools, inspect, collections, time
from types import MappingProxyType
from datetime import datetime, timedelta, timezone as FixedOffsetTimezone


# import pysimplelog version
try:
    from __pkginfo__ import __version__
except ImportError:
    from .__pkginfo__ import __version__

# fixed-offset time zone objects of the machine, by offset in seconds, so a record does not build one each time
_LOCAL_TIMEZONES = {}


def _local_datetime(seconds):
    """
    Returns a moment as a timezone aware datetime in the local timezone of the machine.

    The offset is read for that moment, so it follows daylight saving time changes.
    ``datetime.fromtimestamp(seconds).astimezone()`` gives the same result and is about four times slower.

    :Parameters:
        #. seconds (float): The moment, in seconds since the epoch, as ``time.time()`` gives.

    :Returns:
        #. moment (datetime.datetime): The local time with its offset from Coordinated Universal Time.
    """
    offset = time.localtime(seconds).tm_gmtoff
    zone = _LOCAL_TIMEZONES.get(offset)
    if zone is None:
        zone = FixedOffsetTimezone(timedelta(seconds=offset))
        _LOCAL_TIMEZONES[offset] = zone
    return datetime.fromtimestamp(seconds, zone)


def _now_local():
    """Returns the current time as a timezone aware datetime in the local timezone of the machine."""
    return _local_datetime(time.time())


# structured records and the sinks that receive them
try:
    from .record import LogRecord, ExceptionInfo, CallerInfo
    from .tracing import read_current_trace, trace_api_available
    from .formatters import resolve_formatter
    from .message_format import render_message
    from .log_context import CURRENT_CONTEXT, context as open_context
    from .sinks import Sink, StreamSink, ConsoleSink, FileSink, validate_flush_mode
    from .queues import BoundedQueue, QueueFull, validate_queue_policy
    from .forking import register_for_fork_reset
    from .spool import SpoolConfig
    from .durable import DurableDelivery, resolve_target_id
except ImportError:
    from record import LogRecord, ExceptionInfo, CallerInfo
    from tracing import read_current_trace, trace_api_available
    from formatters import resolve_formatter
    from message_format import render_message
    from log_context import CURRENT_CONTEXT, context as open_context
    from sinks import Sink, StreamSink, ConsoleSink, FileSink, validate_flush_mode
    from queues import BoundedQueue, QueueFull, validate_queue_policy
    from forking import register_for_fork_reset
    from spool import SpoolConfig
    from durable import DurableDelivery, resolve_target_id


# sentinel object used to signal the enqueue worker thread to stop
_QUEUE_STOP = object()
# Put in the queue of a sink that sends groups of records, so that its worker sends what it has now and does not wait for the
# group to fill
_QUEUE_FLUSH = object()


def _is_worker_marker(item):
    """True for the items that end a group of records in the queue of a sink: the one that stops the worker, and the flush."""
    return item is _QUEUE_STOP or item is _QUEUE_FLUSH

# sentinel keys for the two built-in sinks inside Logger.__sinks.
# Integer type guarantees they can never clash with user-supplied
# string sink names — different types, different hash buckets.
_SINK_STDOUT = -1   # key for the built-in stdout sink
_SINK_FILE   =  0   # key for the built-in file sink
CONSOLE_SINK = _SINK_STDOUT   # public name of the key of the built-in console sink
FILE_SINK    = _SINK_FILE     # public name of the key of the built-in file sink

# useful definitions
def _is_number(number):
    """Return True if value can be interpreted as a Python number."""
    if isinstance(number, (int, float, complex)):
        return True
    try:
        float(number)
    except Exception:
        return False
    else:
        return True

def _normalize_path(path):
    """Normalise backslash sequences in a file path for Windows compatibility."""
    if os.sep=='\\':
        path = re.sub(r'([\\])\1+', r'\1', path).replace('\\','\\\\')
    return path


# Resolved once at import time so frame-walking comparisons skip string work.
_THIS_FILE = os.path.abspath(__file__)


def _get_caller_info(depth=0):
    """
    Walks the call stack and returns where the user code made the log call.

    Finds the first frame whose file is not simple_log.py. Only called when Logger.callerInfo is True.

    :Parameters:
        #. depth (int): How many user frames to skip above the log call, for a wrapper around the logger.

    :Returns:
        #. caller (CallerInfo, None): The file, line, function and module of the log call, or None
           when the frame cannot be determined.
    """
    try:
        frame = sys._getframe(1)
        while frame is not None:
            fileName = frame.f_code.co_filename
            if os.path.abspath(fileName) != _THIS_FILE:
                if depth > 0:
                    depth -= 1
                    frame = frame.f_back
                    continue
                return CallerInfo(os.path.basename(fileName), frame.f_lineno, frame.f_code.co_name,
                                  frame.f_globals.get('__name__', ''))
            frame = frame.f_back
    except Exception:
        pass
    return None


def _call_lazy(value):
    """
    Returns the result of a callable value, and any other value as it is.

    :Parameters:
        #. value (object): A value given to a log call made with ``opt(lazy=True)``.

    :Returns:
        #. result (object): What the callable returned, or ``<lazy ErrorClass>`` when it raised. The text names the
           class of the error and never its message, which can hold sensitive text.
    """
    if not callable(value):
        return value
    try:
        return value()
    except Exception as error:
        return f"<lazy {type(error).__name__}>"


def _evaluate_lazy(args, fields):
    """
    Calls every callable among the positional arguments and the field values, once each.

    :Parameters:
        #. args (tuple): The positional arguments of the log call.
        #. fields (dict): The field values of the log call.

    :Returns:
        #. args (tuple): The arguments with the callables replaced by their results.
        #. fields (dict): A new dictionary with the callables replaced by their results.
    """
    return (tuple(_call_lazy(argument) for argument in args),
            {name: _call_lazy(value) for name, value in fields.items()})


def _caller_tag(caller):
    """
    Formats a caller as the tag written before the message.

    :Parameters:
        #. caller (CallerInfo, None): The caller to format.

    :Returns:
        #. tag (str): e.g. '[routes.py:142 in handle_request] ' including the trailing space, or an
           empty string when caller is None.
    """
    if caller is None:
        return ''
    return '[%s:%d in %s] ' % (caller.fileName, caller.line, caller.function)


def _check_field_names(fields):
    """
    Rejects the two names that older versions took as arguments, so a call written for them never logs wrongly.

    :Parameters:
        #. fields (dict): The keyword arguments of a log call that are not arguments of the method.

    :Raises:
        #. TypeError: If a field is named ``fields`` or ``tback``. They would be stored as ordinary fields and
           the call would silently log something other than what its author meant.
    """
    if fields and ('fields' in fields or 'tback' in fields):
        raise TypeError("'fields' and 'tback' are not arguments any more: pass the fields as keyword "
                        "arguments, and the exception as exc_info")


def _exception_info(excInfo):
    """
    Turns what a caller gives as ``exc_info`` into the exception information of a record.

    :Parameters:
        #. excInfo (None, bool, BaseException, tuple, str, list): ``True`` means the exception being handled
           right now. An exception object gives its own type, message and traceback. A tuple
           ``(type, value, traceback)``, as ``sys.exc_info()`` returns, does the same. A string is the text of a
           traceback made elsewhere. A list of ``(filename, lineno, name, line)`` tuples, as
           ``traceback.extract_stack()`` returns, is formatted like a standard Python traceback.

    :Returns:
        #. exception (ExceptionInfo, None): None when there is nothing to record, for example ``True`` when no
           exception is being handled.
    """
    if excInfo is None or excInfo is False:
        return None
    if excInfo is True:
        excInfo = sys.exc_info()
    if isinstance(excInfo, BaseException):
        excInfo = (type(excInfo), excInfo, excInfo.__traceback__)
    if isinstance(excInfo, tuple) and len(excInfo) == 3 and (excInfo[0] is None or isinstance(excInfo[0], type)):
        excType, excValue, excTraceback = excInfo
        if excType is None:
            return None
        try:
            text = ''.join(traceback.format_exception(excType, excValue, excTraceback)).rstrip('\n')
            return ExceptionInfo(excType.__name__, str(excValue), text)
        except Exception:
            # An exception whose own text cannot be made must not make the log call fail
            return ExceptionInfo(excType.__name__, None, excType.__name__)
    if isinstance(excInfo, str):
        return ExceptionInfo(None, None, excInfo)
    try:
        lines = []
        for filename, lineno, name, line in excInfo:
            lines.append('  File "%s", line %d, in %s' % (filename, lineno, name))
            if line:
                lines.append('    %s' % (line.strip(),))
        return ExceptionInfo(None, None, '\n'.join(lines))
    except Exception:
        return ExceptionInfo(None, None, str(excInfo))


# Compiled once at import time — used by _sanitize_message on every log call
_CONTROL_CHAR_RE = re.compile(
    r'\x1b(?:\[[0-9;]*[mGKHFABCDsuJrhl]|\(B|[A-Z])'  # ANSI + VT escape sequences
    r'|\x00'                                              # null bytes
    r'|\r(?!\n)'                                         # bare CR not followed by LF
)


def _sanitize_message(message):
    """Strip control characters and ANSI escape sequences from a log message.

    Uses a fast early-exit 'in' check before invoking the regex engine so the
    overhead on clean messages (the vast majority of calls) is ~80 ns. Non-string
    types pass through unchanged and are handled by %s formatting downstream.
    CRLF sequences are preserved; only bare CR (without following LF) is removed.

    :Parameters:
        #. message (str, object): The raw message value from the caller.

    :Returns:
        #. result (str): Sanitized string. Non-strings are coerced via '%s'
           formatting before control-character stripping, so a str is always returned.
    """
    if not isinstance(message, str):
        message = '%s' % (message,)
    if '\x1b' not in message and '\x00' not in message and '\r' not in message:
        return message
    return _CONTROL_CHAR_RE.sub('', message)



class _Sink(object):
    """Internal descriptor for a single log output target.

    Not part of the public API. Created and managed exclusively by
    Logger. Every writable destination -- stdout, file, or any
    user-supplied sink -- is represented as a _Sink instance stored
    under a key in Logger.__sinks:

      _SINK_STDOUT (-1) : the built-in stdout sink
      _SINK_FILE   ( 0) : the built-in rotating file sink
      str               : any user-added sink (unique string name)

    :Parameters:
        #. handler (Sink): The Sink object that receives every record that
           passes the routing, and renders it with its own formatter.
        #. enabled (bool): Master switch. When False the sink is
           skipped entirely during dispatch without inspecting any
           other field.
        #. logTypeFlags (dict): Mapping of {logType (str): bool}.
           Controls per-type enable/disable for this sink only.
           Missing keys fall back to *defaultFlag*.
        #. minLevel (int or None): Minimum level integer for this
           sink. Records whose level is below this value are not
           dispatched. None means no floor.
        #. maxLevel (int or None): Maximum level integer for this
           sink. Records whose level is above this value are not
           dispatched. None means no ceiling.
        #. sinkType (str): ``stdout`` and ``file`` for the two built-in sinks, ``user``
           for every sink added with Logger.add_sink().
        #. defaultFlag (bool): Fallback enabled-state used for any
           logType missing from logTypeFlags. True (default) gives an
           opt-out sink (gets every type unless explicitly turned off).
           False gives an opt-in sink (gets nothing unless explicitly
           turned on) -- including any logType added later.
        #. threaded (bool): When True, this sink owns a private bounded
           queue and a dedicated worker thread. Dispatch only enqueues onto it, so slow or
           unreliable I/O in this one sink's handler can never stall any other sink or
           pysimplelog's own file/stdout logging. What a full queue does is the
           threadQueuePolicy. Default False -- the sink is written to on the calling thread.
        #. threadQueueSize (int): Bounded capacity for the private
           queue when threaded is True. Ignored otherwise.
        #. threadQueuePolicy (str): What the private queue does with a record when it is full:
           ``block``, ``drop_newest``, ``drop_oldest`` or ``reject``. Ignored when not threaded.
        #. threadBlockTimeout (None, number): Seconds the ``block`` policy waits for a free place, None
           waits as long as it takes. Ignored when not threaded.
        #. recordFilter (callable, None): ``f(record) -> bool`` that decides which
           records this sink receives, after the routing. None means all of them.
           Set later with Logger.set_sink_filter(). The attribute filteredCount
           counts the records it skipped.
        #. isWrapped (bool): True when the handler is a StreamSink that the logger made around
           a file-like object given to add_sink(), so the logger keeps its flush mode up to date.
        #. durable (DurableDelivery, None): When given, the records of this sink are kept on disk and delivered by it,
           and the private queue and worker of a threaded sink are not made. *threaded* must be True.
    """

    def __init__(self, handler, enabled, logTypeFlags,
                 minLevel=None, maxLevel=None, sinkType='stdout',
                 defaultFlag=True, threaded=False, threadQueueSize=1000, recordFilter=None, isWrapped=False,
                 threadQueuePolicy='drop_oldest', threadBlockTimeout=None, durable=None):
        self.recordFilter  = recordFilter
        self.filteredCount = 0
        self.isWrapped    = isWrapped
        self.enabled      = enabled
        self.logTypeFlags = logTypeFlags
        self.minLevel     = minLevel
        self.maxLevel     = maxLevel
        self.sinkType     = sinkType   # 'stdout' | 'file' | 'user'
        self.defaultFlag  = defaultFlag   # fallback for logTypes missing from logTypeFlags
        self.set_handler(handler)
        self.threaded = threaded
        self.durable = durable
        # The process that owns the queue and the worker thread: a forked child has neither
        self._pid = os.getpid()
        self._queue = None
        self._thread = None
        if threaded and durable is None:
            self._queue = BoundedQueue(threadQueueSize, threadQueuePolicy, threadBlockTimeout, name='sink queue')
            self._thread = threading.Thread(
                target=self._worker, name='pysimplelog-sink-worker', daemon=True,
            )
            self._thread.start()

    def enqueue(self, record):
        """Push one record onto this sink's private queue, or do what the queue policy says when it is full.

        Only called when threaded is True.

        :Parameters:
            #. record (LogRecord): The record to deliver on the worker thread.

        :Raises:
            #. QueueFull: If the queue is full and the policy is ``reject``, or the spool is full and its policy is
               ``reject``.
        """
        if self.durable is not None:
            self.durable.submit(record)
            return
        if os.getpid() != self._pid:
            # In a forked child the worker thread does not exist, so nothing would ever take the record from the queue
            self.handler.emit(record)
            return
        self._queue.put(record)

    def _worker(self):
        """Background loop for a threaded sink: drain the private queue and deliver.

        Runs until stop_threaded() puts the stop marker at the end of the queue. A Sink never
        raises, and anything unexpected is reported by one warning line, never a crash of the thread.
        """
        if self.handler.batchSize > 1:
            self._worker_of_groups()
            return
        while True:
            record = self._queue.get()
            try:
                if record is _QUEUE_STOP:
                    return
                self.handler.emit(record)
            except Exception as sinkError:
                sys.stderr.write(
                    'pysimplelog WARNING: sink delivery failed'
                    ', record dropped. Error: %s\n' % sinkError
                )
            finally:
                self._queue.task_done()

    def _worker_of_groups(self):
        """Background loop for a threaded sink that sends groups of records: take a group, deliver it in one call.

        A group ends when it is full, when the sink's batch interval is over since its first record, or at a marker. The marker is
        dealt with after the group, so the records before a stop or a flush are delivered first.
        """
        handler = self.handler
        while True:
            records, marker = self._queue.get_batch(handler.batchSize, handler.batchInterval, _is_worker_marker)
            try:
                if len(records) > 0:
                    try:
                        handler.emit_batch(records)
                    except Exception as sinkError:
                        sys.stderr.write(
                            'pysimplelog WARNING: sink delivery failed'
                            ', %d records dropped. Error: %s\n' % (len(records), sinkError)
                        )
            finally:
                for _ in range(len(records) + (0 if marker is None else 1)):
                    self._queue.task_done()
            if marker is _QUEUE_STOP:
                return

    def flush_threaded(self, timeout=5.0):
        """Best-effort wait (up to *timeout* seconds) for this sink's queue to drain.

        Waits for both the queue to empty AND the item currently being
        dispatched (if any) to finish -- a queue that looks empty while
        the worker is still mid-dispatch on the last item is not actually
        drained yet. No-op when threaded is False.
        """
        if not self.threaded:
            return
        if self.durable is not None:
            self.durable.flush(timeout)
            return
        if os.getpid() != self._pid:
            return
        if self.handler.batchSize > 1:
            # The worker may be waiting for its group to fill, this makes it send what it has now
            self._queue.put_last(_QUEUE_FLUSH)
        self._queue.join(timeout)

    def stop_threaded(self, timeout=5.0):
        """Drain what fits in *timeout* seconds, then stop and join the worker thread.

        Called by remove_sink(), clear_sinks(), and atexit shutdown so a
        threaded sink's thread is never left running after it's gone --
        no leaked threads. No-op when threaded is False.
        """
        if not self.threaded:
            return
        if self.durable is not None:
            self.durable.stop(timeout)
            return
        if os.getpid() != self._pid:
            # The worker belongs to the parent, which stops it
            return
        self.flush_threaded(timeout=timeout)
        self._queue.put_last(_QUEUE_STOP)
        self._thread.join(timeout=timeout)

    def queue_stats(self):
        """Returns the counters of the private queue, or None when the sink is not threaded."""
        if self.durable is not None:
            return self.durable.queue_stats()
        return None if self._queue is None else self._queue.stats()

    def spool_stats(self):
        """Returns what the spool of this sink holds and what its delivery did, or None when it has no spool."""
        return None if self.durable is None else self.durable.stats()

    def maintain(self):
        """
        Does the housekeeping of the handler and of the spool, if there is one.

        :Returns:
            #. result (dict, None): What the handler did, and under ``spool`` what the spool did, or None when there was nothing
               to do.
        """
        result = self.handler.maintain()
        spool = None if self.durable is None else self.durable.maintain()
        if result is None and spool is None:
            return None
        merged = {} if result is None else dict(result)
        if spool is not None:
            merged['spool'] = spool
        return merged

    def set_handler(self, handler):
        """
        Sets the Sink object that receives the records.

        :Parameters:
            #. handler (Sink): The new handler.
        """
        self.handler = handler

    def release(self, timeout=5.0):
        """
        Stops the private worker thread, if any, then closes the Sink object, which flushes it.

        :Parameters:
            #. timeout (float): Seconds to wait for the private queue to drain.
        """
        self.stop_threaded(timeout=timeout)
        try:
            self.handler.close()
        except Exception as closeError:
            sys.stderr.write('pysimplelog WARNING: sink close failed. Error: %s\n' % closeError)

    def __repr__(self):
        return (
            '_Sink(sinkType=%r, enabled=%r, minLevel=%r, maxLevel=%r)'
            % (self.sinkType, self.enabled, self.minLevel, self.maxLevel)
        )


class _CatchContext(object):
    """Context manager and decorator returned by Logger.catch().

    Catches any exception escaping the wrapped callable or the ``with``
    block, logs it through the parent Logger, and optionally re-raises.

    Do not instantiate directly -- use ``Logger.catch()``.
    """

    def __init__(self, logger, logType, reraise, message):
        self._logger    = logger
        self._logType   = logType
        self._reraise   = reraise
        self._message   = message

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            msg = '%s: %s' % (self._message, exc_val)
            self._logger.log(self._logType, msg, exc_info=(exc_type, exc_val, exc_tb))
            return not self._reraise   # True suppresses; False re-raises
        return False

    def __call__(self, func):
        """Allow the context manager instance to be used as a decorator."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """Runs the wrapped function inside the catch context."""
            with _CatchContext(self._logger, self._logType, self._reraise, self._message):
                return func(*args, **kwargs)
        return wrapper


class _BoundLogger(object):
    """Lightweight wrapper returned by Logger.bind(), it attaches fixed values to the context of every record.

    While one of its methods logs, the bound values are added to the context of the current thread or task,
    over the values of any ``context()`` block the program is in, so the record carries them in its
    ``context``. The wrapper holds no queue, no file handle, and no configuration state of its own -- all
    I/O is performed by the parent Logger unchanged.

    Instances are immutable after construction and therefore inherently
    thread-safe. Nested bind() calls produce a new _BoundLogger with a
    merged context dict; the originals are never modified.

    Do not instantiate directly -- use Logger.bind() or _BoundLogger.bind().

    :Parameters:
        #. parent (Logger, _BoundLogger): The logger that performs all
           actual I/O. The root Logger is always stored, so delegation
           stays one hop deep however many bind() calls are chained.
        #. context (dict): Key-value pairs attached to every record.
    """

    def __init__(self, parent, context):
        self.__parent  = parent
        self.__context = dict(context)   # defensive copy -- never mutate

    # ── context nesting ──────────────────────────────────────────────

    def bind(self, **extra):
        """Return a new _BoundLogger with additional context key-value pairs.

        The new wrapper shares the same parent Logger. Existing context
        keys are preserved; any key present in both dicts takes the value
        from the extra kwargs (right-hand side wins).

        :Parameters:
            #. **extra: Arbitrary key-value pairs to add or override.

        :Returns:
            #. result (_BoundLogger): A new wrapper with merged context.
        """
        merged = dict(self.__context)
        merged.update(extra)
        return _BoundLogger(self.__parent, merged)

    def context(self, **values):
        """Attach values to every record made inside a ``with`` block. See :func:`pysimplelog.log_context.context`."""
        return open_context(**values)

    # ── core logging ─────────────────────────────────────────────────

    def log(self, logType, message, *args, exc_info=None, countConstraint=None, **fields):
        """Log a message at the given logType, with the bound values in the context of the record.

        Delegates entirely to parent.log(). All level filtering, count constraints,
        backpressure, and I/O are handled by the parent unchanged.

        :Parameters:
            #. logType (string): A defined log type.
            #. message (string): The message to log.
            #. args (tuple): Positional arguments that fill the ``{}`` placeholders of *message*, see Logger.log().
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see Logger.log().
            #. countConstraint (None, number): Max times to log this message.
            #. fields: Named values stored in the record, see Logger.log().

        :Returns:
            #. result (string): The logged message returned by parent.log().
        """
        previous = CURRENT_CONTEXT.get()
        token = CURRENT_CONTEXT.set({**previous, **self.__context} if len(previous) > 0 else self.__context)
        try:
            return self.__parent.log(logType, message, *args, exc_info=exc_info, countConstraint=countConstraint, **fields)
        finally:
            CURRENT_CONTEXT.reset(token)

    def force_log(self, logType, message, *args, exc_info=None, stdout=True, file=True, **fields):
        """Force-log a message, bypassing level checks, with the bound values in the context of the record.

        Delegates to parent.force_log().

        :Parameters:
            #. logType (string): A defined log type.
            #. message (string): The message to log.
            #. args (tuple): Positional arguments that fill the ``{}`` placeholders of *message*, see Logger.log().
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see Logger.log().
            #. stdout (boolean): Whether to force stdout output.
            #. file (boolean): Whether to force file output.
            #. fields: Named values stored in the record, see Logger.log().

        :Returns:
            #. result (string): The logged message returned by parent.force_log().
        """
        previous = CURRENT_CONTEXT.get()
        token = CURRENT_CONTEXT.set({**previous, **self.__context} if len(previous) > 0 else self.__context)
        try:
            return self.__parent.force_log(logType, message, *args, exc_info=exc_info, stdout=stdout, file=file, **fields)
        finally:
            CURRENT_CONTEXT.reset(token)

    # ── shortcut methods (mirrors Logger shortcuts) ──────────────────

    def info(self, message, *args, **kwargs):
        """Log at info level, with the bound values in the context."""
        return self.log('info', message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """Log at info level (alias for info)."""
        return self.log('info', message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """Log at warn level, with the bound values in the context."""
        return self.log('warn', message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log at warn level (alias for warn)."""
        return self.log('warn', message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log at error level, with the bound values in the context."""
        return self.log('error', message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log at critical level, with the bound values in the context."""
        return self.log('critical', message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Log at debug level, with the bound values in the context."""
        return self.log('debug', message, *args, **kwargs)

    def _log_call(self, logType, message, args, fields, exc_info, countConstraint, isLazy, depth):
        """Logs with the bound values in the context, see :meth:`Logger._log_call`."""
        previous = CURRENT_CONTEXT.get()
        token = CURRENT_CONTEXT.set({**previous, **self.__context} if len(previous) > 0 else self.__context)
        try:
            return self.__parent._log_call(logType, message, args, fields, exc_info, countConstraint, isLazy, depth)
        finally:
            CURRENT_CONTEXT.reset(token)

    def opt(self, *, lazy=False, exception=None, depth=0):
        """Returns a logger that applies options to the calls made through it, see :meth:`Logger.opt`."""
        return _OptLogger(self, lazy, exception, depth)

    # ── exception capture ────────────────────────────────────────────

    def catch(self, func=None, logType='error', reraise=False,
              message='An exception was caught'):
        """Decorator and context manager that catches and logs exceptions.

        Identical to Logger.catch() but the logged exception record
        carries the bound values in its context automatically, because
        _CatchContext calls self.log() on this _BoundLogger rather
        than on the parent Logger directly.

        :Parameters:
            #. func (None, callable): Decorated function for bare-decorator use.
            #. logType (string): Log type for the caught exception entry.
            #. reraise (boolean): Whether to re-raise after logging.
            #. message (string): Prefix text for the exception log line.

        :Returns:
            #. result (_CatchContext): A _CatchContext usable as decorator or
               context manager.
        """
        ctx = _CatchContext(self, logType=logType, reraise=reraise, message=message)
        if func is not None:
            return ctx(func)
        return ctx

    # ── delegation — query / control methods ─────────────────────────

    def is_enabled(self, logType):
        """Delegate to parent.is_enabled(). See Logger.is_enabled()."""
        return self.__parent.is_enabled(logType)

    def is_enabled_for_stdout(self, logType):
        """Delegate to parent.is_enabled_for_stdout()."""
        return self.__parent.is_enabled_for_stdout(logType)

    def is_enabled_for_file(self, logType):
        """Delegate to parent.is_enabled_for_file()."""
        return self.__parent.is_enabled_for_file(logType)

    def flush(self):
        """Delegate to parent.flush(). See Logger.flush()."""
        return self.__parent.flush()

    # ── read-only properties ─────────────────────────────────────────

    @property
    def name(self):
        """Parent logger name."""
        return self.__parent.name

    @property
    def enqueue(self):
        """Whether the parent logger is in non-blocking enqueue mode."""
        return self.__parent.enqueue

    @property
    def boundContext(self):
        """A copy of the values this wrapper attaches to every record.

        Returns a fresh copy so callers cannot accidentally mutate the
        internal state of this _BoundLogger.

        :Returns:
            #. result (dict): Copy of the bound key-value pairs.
        """
        return dict(self.__context)


class _OptLogger(object):
    """
    Logs with options that apply to the calls made through it, see :meth:`Logger.opt`. It holds no state besides the options.

    :Parameters:
        #. parent (Logger, _BoundLogger): The logger that does the work.
        #. isLazy (boolean): Whether callable arguments and field values are called when the message is wanted.
        #. exception (None, bool, BaseException, tuple): The exception to record when the call gives no ``exc_info``.
        #. depth (int): How many user frames to skip when the caller is looked for.

    :Raises:
        #. TypeError: If *isLazy* is not a boolean.
        #. ValueError: If *depth* is not a non-negative integer.
    """

    def __init__(self, parent, isLazy, exception, depth):
        if not isinstance(isLazy, bool):
            raise TypeError("lazy must be a boolean")
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ValueError("depth must be an integer that is not negative")
        self.__parent = parent
        self.__isLazy = isLazy
        self.__exception = None if exception is False else exception
        self.__depth = depth

    def log(self, logType, message, *args, exc_info=None, countConstraint=None, **fields):
        """Logs a message of a log type with the options, see :meth:`Logger.log`."""
        if exc_info is None:
            exc_info = self.__exception
        return self.__parent._log_call(logType, message, args, fields, exc_info, countConstraint,
                                       self.__isLazy, self.__depth)

    def info(self, message, *args, **kwargs):
        """Logs at info level with the options."""
        return self.log("info", message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """Logs at info level with the options (alias for info)."""
        return self.log("info", message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """Logs at warn level with the options."""
        return self.log("warn", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Logs at warn level with the options (alias for warn)."""
        return self.log("warn", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Logs at error level with the options."""
        return self.log("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Logs at critical level with the options."""
        return self.log("critical", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Logs at debug level with the options."""
        return self.log("debug", message, *args, **kwargs)


class Logger(object):
    """
    This is simplelog main Logger class definition.\n

    Every log call builds one immutable :class:`pysimplelog.record.LogRecord`. The sinks turn it into
    text with their own formatter. The readable text layout is:\n
    date time - loggerName <logTypeName> message\n

    To write records in another layout, such as JSON lines, give a sink another formatter, see
    :mod:`pysimplelog.formatters` and :mod:`pysimplelog.sinks`.

    When used in a Python application, it is advisable to use the Logger singleton
    implementation rather than Logger itself. If no subclassing is needed, simply
    import the singleton:

    .. code-block:: python

        from pysimplelog import SingleLogger as Logger


    Basic usage example:

    .. code-block:: python

        from pysimplelog import Logger

        ## create a logger instance
        logger = Logger("my-app")

        ## log at built-in levels
        logger.info("application started")
        logger.warn("disk usage above 80 percent")
        logger.error("connection refused")

        ## add a custom log type
        logger.add_log_type("trace", name="TRACE", level=5, color="cyan")
        logger.log("trace", "entering request handler")

        ## bind context for structured logging
        requestLogger = logger.bind(requestId="abc123", user="alice")
        requestLogger.info("request received")


    A new Logger instantiates with the following logType list (logTypes <NAME>: level)

       * debug <DEBUG>: 0
       * info <INFO>: 10
       * warn <WARNING>: 20
       * error <ERROR>: 30
       * critical <CRITICAL>: 100


    Recommended overloading implementation, this is how it could be done:

    .. code-block:: python

        from pysimplelog import SingleLogger as LOG

        class Logger(LOG):
            # *args and **kwargs can be replace by fixed arguments
            def custom_init(self, *args, **kwargs):
                # hereinafter any further instantiation can be coded



    In case overloading __init__ is needed, this is how it could be done:

    .. code-block:: python

        from pysimplelog import SingleLogger as LOG

        class Logger(LOG):
            # custom_init will still be called in super(Logger, self).__init__(*args, **kwargs)
            def __init__(self, *args, **kwargs):
                if self._isInitialized: return
                super(Logger, self).__init__(*args, **kwargs)
                # hereinafter any further instantiation can be coded


    :Parameters:
       #. name (string): The logger name.
       #. flush (boolean): Whether to always flush the logging streams.
       #. logToStdout (boolean): Whether to log to the standard output stream.
       #. stdout (None, stream): The standard output stream. If None, system
          standard output will be set automatically. Otherwise any stream with
          read and write methods can be passed
       #. logToFile (boolean): Whether to enable logging to file.
       #. logFile (None, string): the full log file path including directory
          basename and extension. If this is given, all of logFileBasename and
          logFileExtension will be discarded. logfile is equivalent to
          logFileBasename.logFileExtension
       #. logFileBasename (string): Logging file directory path and file
          basename. A logging file full name is set as
          logFileBasename.logFileExtension
       #. logFileExtension (string): Logging file extension. A logging file
          full name is set as logFileBasename.logFileExtension
       #. logFileMaxSize (None, number): The maximum size in Megabytes
          of a logging file. Once exceeded, another logging file as
          logFileBasename_N.logFileExtension will be created.
          Where N is an automatically incremented number. If None or a
          negative number is given, the logging file will grow
          indefinitely
       #. logFileFirstNumber (None, integer): first log file number 'N' in
          logFileBasename_N.logFileExtension. If None is given then
          first log file will be logFileBasename.logFileExtension and once
          logFileMaxSize is reached second log file will be
          logFileBasename_0.logFileExtension and so on and so forth.
          If number is given it must be an integer >=0
       #. logFileRoll (None, integer): If given, it sets the maximum number of
          log files to write. Exceeding the number will result in deleting
          previous ones. This also insures always increasing files numbering.
       #. stdoutMinLevel(None, number): The minimum logging to system standard
          output level. If None, standard output minimum level checking is left
          out.
       #. stdoutMaxLevel(None, number): The maximum logging to system standard
          output level. If None, standard output maximum level checking is
          left out.
       #. fileMinLevel(None, number): The minimum logging to file level.
          If None, file minimum level checking is left out.
       #. fileMaxLevel(None, number): The maximum logging to file level.
          If None, file maximum level checking is left out.
       #. logTypes (None, dict): Used to create and update existing log types
          upon initialization. Given dictionary keys are logType
          (new or existing) and values can be None or a dictionary of kwargs
          to call update_log_type upon. This argument will be called after
          custom_init
       #. timezone (None, str): Logging time timezone. If provided
          pytz must be installed and it must be the timezone name. If not
          provided, the machine default timezone will be used.
       #. maxMessageSize (None, integer): Maximum number of characters allowed
          in a single log message string. If None, no limit is applied. Messages
          exceeding the limit are truncated and '[truncated]' is appended.
       #. maxDataSize (None, integer): Maximum number of characters allowed in
          the string representation of the data argument. If None, no limit is
          applied. Data strings exceeding the limit are truncated and
          '[truncated]' is appended.
       #. enqueue (boolean): When True, log() and force_log() push records
          onto an internal queue and return immediately. A background daemon
          thread performs all I/O. Useful for high-throughput or latency-
          sensitive callers. Call flush() to block until the queue drains.
          Cannot be changed after construction.
       #. maxQueueSize (None, integer): Maximum number of records the internal
          queue may hold at once. Only meaningful when enqueue=True.
          None (default) means unbounded -- the queue grows without limit,
          which is safe but can exhaust memory under extreme load.
          When set to a positive integer the queueFullPolicy controls what
          happens when that limit is reached. Can be updated at runtime via
          set_max_queue_size().
       #. queueFullPolicy (string): Determines what happens to a record when the
          queue is full (only applies when maxQueueSize is not None).
          Four values are accepted:
          ``'block'``  -- the calling thread parks until space opens.
          If queueBlockTimeout is set, the park is bounded; after that
          many seconds the new record is dropped. If queueBlockTimeout is None
          the thread parks forever (safe but dangerous if the worker dies).
          ``'drop_newest'`` -- the new record is discarded.
          ``'drop_oldest'`` -- the record that has waited longest is discarded
          and the new one is kept.
          ``'reject'`` -- the log call raises ``pysimplelog.queues.QueueFull`` (a ``queue.Full``) so
          the caller can decide what to do.
          Every record that is discarded is counted, in droppedMessages and queueStats, and one warning
          line is written to stderr for each run of them.
          Default is ``'block'``. Can be updated at runtime via
          set_queue_full_policy().
       #. queueBlockTimeout (None, number): Seconds to wait before giving
          up when queueFullPolicy is ``'block'``. None (default) means wait
          indefinitely. When a positive number is given and the timeout
          expires the new record is dropped and counted. Has no effect
          when queueFullPolicy is not ``'block'``. Can be updated at runtime
          via set_queue_block_timeout().
       #. callerInfo (boolean): When True, every log line is prefixed
          with the file name, line number and function name of the call
          site that triggered the log call, e.g.:
          ``[routes.py:142 in handle_request]``.
          Uses inspect.stack() with context=0 (no source lines read)
          which adds roughly 10-30 us per call. Default is False so
          existing callers pay zero overhead. Can be toggled at runtime
          via set_caller_info(). Does not apply to bound loggers
          created with bind() — those inherit the parent setting.
       #. unknownLogTypePolicy (string): What log() and force_log() do with a log
          type that is not defined. 'raise' (default) raises KeyError. 'fallback'
          logs the message under *fallbackLogType* with the text
          "Unknown log type 'X': " in front, so a wrong type name never crashes
          the caller and stays visible. Can be updated at runtime via
          set_unknown_log_type_policy().
       #. fallbackLogType (None, string): The log type used by the 'fallback'
          policy. Required when the policy is 'fallback'. It may be defined later,
          for example in custom_init, and is checked when it is first used.
       #. processors (None, list, tuple): Functions that rewrite every record before it
          reaches any sink, in the order they run. Each function is ``f(record) -> record``.
          Same as calling add_processor() for each one, after custom_init and the *logTypes* argument.
       #. consoleFormatter (None, string, callable): How a record becomes the text of the console. The colours
          of its log type are added to the ``'text'`` layout only. The default ``'text'`` is the readable line. None gives JSON, a
          string with ``{name}`` placeholders is a template, and a function ``f(record) -> str`` is used as it
          is. See :mod:`pysimplelog.formatters`. Change it later with set_sink_formatter().
       #. fileFormatter (None, string, callable): The same, for the log file.
       #. \\*args: This is used to send non-keyworded variable length argument
           list to custom initialize. args will be parsed and used in
           custom_init method.
       #. \\**kwargs: This allows passing keyworded variable length of
           arguments to custom_init method. kwargs can be anything other
           than __init__ arguments.

    :Raises:
        #. TypeError: If *logTypes* is not a dict or None, if its keys are not
           strings, if its values are not dicts or None, if *enqueue* is not a
           boolean, if *callerInfo* is not a boolean, or if *unknownLogTypePolicy*
           is 'fallback' and *fallbackLogType* is not a string. Each setter called
           during construction may also raise ``TypeError`` or ``ValueError``
           for its own parameter — see the individual setter docstrings.
        #. ValueError: If *unknownLogTypePolicy* is not 'raise' or 'fallback'.
        #. TypeError: If *processors* is not None or a list or tuple of callables.
    """
    def __init__(self, name="logger", flush=True,
                       logToStdout=True, stdout=None,
                       logToFile=True, logFile=None,
                       logFileBasename="simplelog", logFileExtension="log",
                       logFileMaxSize=10, logFileFirstNumber=0, logFileRoll=None,
                       stdoutMinLevel=None, stdoutMaxLevel=None,
                       fileMinLevel=None, fileMaxLevel=None,
                       logTypes=None, timezone=None,
                       maxMessageSize=None, maxDataSize=None,
                       enqueue=False,
                       maxQueueSize=None,
                       queueFullPolicy='block',
                       queueBlockTimeout=None,
                       callerInfo=False,
                       unknownLogTypePolicy='raise', fallbackLogType=None,
                       processors=None,
                       consoleFormatter='text', fileFormatter='text',
                       *args, **kwargs):
        # set last logged message
        self.__lastRecords   = {}
        self.__lastRecord    = None
        # sink registry and cache — pre-created empty so every setter
        # called during __init__ can safely guard with
        # "if _SINK_STDOUT in self.__sinks". The real _Sink objects are
        # inserted at the END of __init__ (sink registry block).
        self.__sinks       = {}
        self.__activeSinks = {}
        # set timezone
        self.set_timezone(timezone)
        # set name
        self.set_name(name)
        # set flush
        self.set_flush(flush)
        # set log to stdout
        self.set_log_to_stdout_flag(logToStdout)
        # set stdout
        self.set_stdout(stdout)
        # set log file roll
        self.set_log_file_roll(logFileRoll)
        # set log to file
        self.set_log_to_file_flag(logToFile)
        # set maximum logFile size
        self.set_log_file_maximum_size(logFileMaxSize)
        # set maximum message and data sizes
        self.set_maximum_message_size(maxMessageSize)
        self.set_maximum_data_size(maxDataSize)
        # set logFile first number
        self.set_log_file_first_number(logFileFirstNumber)
        # set logFile basename and extension
        if logFile is not None:
            self.set_log_file(logFile)
        else:
            self.__set_log_file_basename(logFileBasename)
            self.set_log_file_extension(logFileExtension)
        # initialize types parameters
        self.__logTypeFileFlags   = {}
        self.__logTypeStdoutFlags = {}
        self.__logTypeNames       = {}
        self.__logTypeLevels      = {}
        self.__logTypeFormat      = {}
        self.__logTypeColor       = {}
        self.__logTypeHighlight   = {}
        self.__logTypeAttributes  = {}
        # initialize forced levels
        self.__forcedStdoutLevels = {}
        self.__forcedFileLevels   = {}
        # set levels
        self.__stdoutMinLevel = None
        self.__stdoutMaxLevel = None
        self.__fileMinLevel   = None
        self.__fileMaxLevel   = None
        # create log messages counter
        self.__logMessagesCounter = {}
        self.set_minimum_level(stdoutMinLevel, stdoutFlag=True, fileFlag=False)
        self.set_maximum_level(stdoutMaxLevel, stdoutFlag=True, fileFlag=False)
        self.set_minimum_level(fileMinLevel, stdoutFlag=False, fileFlag=True)
        self.set_maximum_level(fileMaxLevel, stdoutFlag=False, fileFlag=True)
        # create default types
        self.add_log_type("debug",    name="DEBUG",    level=0,   stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("info",     name="INFO",     level=10,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("warn",     name="WARNING",  level=20,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("error",    name="ERROR",    level=30,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("critical", name="CRITICAL", level=100, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        # enqueue mode — validate policy params first so errors surface early
        if not isinstance(enqueue, bool):
            raise TypeError("enqueue must be a boolean")
        self.__enqueue          = enqueue
        # The process that owns the queue and the worker thread: a forked child has neither
        self.__ownerPid         = os.getpid()
        self.__logQueue         = None
        self.__logWorker        = None
        # validate and store queue policy settings via setters so all
        # validation logic lives in one place
        self.__maxQueueSize      = None   # set by setter below
        self.__queueFullPolicy   = None   # set by setter below
        self.__queueBlockTimeout = None   # set by setter below
        self.set_queue_full_policy(queueFullPolicy)
        self.set_queue_block_timeout(queueBlockTimeout)
        self.set_max_queue_size(maxQueueSize)   # must come after policy set
        if self.__enqueue:
            self.__logQueue  = BoundedQueue(self.__maxQueueSize, self.__queueFullPolicy, self.__queueBlockTimeout,
                                            name='log queue')
            self.__logWorker = threading.Thread(
                target=self.__enqueue_worker,
                name="pysimplelog-writer",
            )
            self.__logWorker.daemon = True
            self.__logWorker.start()
        # callerInfo — validate and store
        if not isinstance(callerInfo, bool):
            raise TypeError("callerInfo must be a boolean")
        self.__callerInfo = callerInfo
        # unknown log type policy
        self.__unknownLogTypePolicy = 'raise'
        self.__fallbackLogType      = None
        self.set_unknown_log_type_policy(unknownLogTypePolicy, fallbackLogType)
        # how the two built-in sinks turn a record into text
        self.__consoleFormatter = consoleFormatter
        self.__fileFormatter = fileFormatter
        # processors rewrite the LogRecord that the sinks receive, they run for every record
        self.__processors = []
        self.__maintainWarned = set()
        self.__failedProcessors = set()
        self.__processorFailures = 0
        self.__processorLock = threading.Lock()
        # filters drop a whole record when one of them returns False, they run for every record
        self.__filters = []
        self.__hasSinkFilters = False
        # True while a sink asks for the identifiers of the active trace, so that nothing is read when none does
        self.__capturesTrace = False
        self.__failedFilters = set()
        self.__filterFailures = 0
        self.__filteredRecords = 0
        self.__filterLock = threading.Lock()
        register_for_fork_reset(self)
        # ── unified sink registry ─────────────────────────────────────────
        # Both built-in sinks are always created. The logTypeFlags dicts
        # are the SAME objects as __logTypeStdoutFlags/__logTypeFileFlags
        # so __update_stdout_flags() and __update_file_flags() keep them
        # current automatically — no extra code required.
        # Scalar fields (enabled, minLevel, maxLevel) are snapshots;
        # setters write to both the old attributes and the sink fields
        # so the cache stays accurate after config changes.
        self.__sinks = {
            _SINK_STDOUT: _Sink(
                handler      = self.__make_console_sink(),
                enabled      = self.__logToStdout,
                logTypeFlags = self.__logTypeStdoutFlags,  # shared dict
                minLevel     = self.__stdoutMinLevel,
                maxLevel     = self.__stdoutMaxLevel,
                sinkType     = 'stdout',
            ),
            _SINK_FILE: _Sink(
                handler      = self.__make_file_sink(),    # opens its file on the first record
                enabled      = self.__logToFile,
                logTypeFlags = self.__logTypeFileFlags,    # shared dict
                minLevel     = self.__fileMinLevel,
                maxLevel     = self.__fileMaxLevel,
                sinkType     = 'file',
            ),
        }
        self.__activeSinks = {}
        self.__rebuild_active_sinks()
        # flush at python exit
        atexit.register(self._flush_atexit_logfile)
        # custom initialize runs last, so queue, sinks and logging all work inside it
        self.custom_init( *args, **kwargs )
        # add logTypes, still applied after custom_init so they can update types it created
        if logTypes is not None:
            if not isinstance(logTypes, dict):
                raise TypeError("logTypes must be None or a dictionary")
            if not all([isinstance(lt, str) for lt in logTypes]):
                raise TypeError("logTypes dictionary keys must be strings")
            if not all([isinstance(logTypes[lt], dict) for lt in logTypes if logTypes[lt] is not None]):
                raise TypeError("logTypes dictionary values must be all None or dictionaries")
            for lt in logTypes:
                ltv = logTypes[lt]
                if ltv is None:
                    ltv = {}
                if not self.is_log_type(lt):
                    self.add_log_type(lt, **ltv)
                elif len(ltv):
                    self.update_log_type(lt, **ltv)
        # add processors
        if processors is not None:
            if not isinstance(processors, (list, tuple)):
                raise TypeError("processors must be None or a list of functions")
            for func in processors:
                self.add_processor(func)

    def __str__(self):
        """Return a formatted configuration table for this Logger instance."""
        # create version
        string  = self.__class__.__name__+" (Version "+str(__version__)+")"
        string += "\n - Log To Stdout: Flag (%s) - Min Level (%s) - Max Level (%s)"%(self.__logToStdout,self.__stdoutMinLevel,self.__stdoutMaxLevel)
        string += "\n - Log To File:   Flag (%s) - Min Level (%s) - Max Level (%s)"%(self.__logToFile,self.__fileMinLevel,self.__fileMaxLevel)
        string += "\n                  File Size (%s) - First Number (%s) - Roll (%s)"%(self.__logFileMaxSize,self.__logFileFirstNumber,self.__logFileRoll)
        string += "\n                  Message Max Size (%s) - Data Max Size (%s)"%(self.__maxMessageSize,self.__maxDataSize)
        string += "\n - Enqueue mode: %s  Queue max size: %s  Policy: %s  Block timeout: %s  Dropped: %s"%(self.__enqueue, self.__maxQueueSize, self.__queueFullPolicy,
          self.__queueBlockTimeout, self.droppedMessages)
        string += "\n - Caller info: %s"%(self.__callerInfo,)
        string += "\n - Unknown log type policy: %s"%(self.__unknownLogTypePolicy,)
        string += "\n - Processors: %s"%(len(self.__processors),)
        string += "\n                  Current log file (%s)"%(self.logFileName)
        # add log types table
        if not len(self.__logTypeNames):
            string += "\nlog type  |log name  |level     |std flag   |file flag"
            string += "\n----------|----------|----------|-----------|---------"
            return string
        # get maximum logType and logTypeZName and maxLogLevel
        maxLogType  = max( max([len(k)+1 for k in self.__logTypeNames]),   len("log type  "))
        maxLogName  = max( max([len(self.__logTypeNames[k])+1 for k in self.__logTypeNames]), len("log name  "))
        maxLogLevel = max( max([len(str(self.__logTypeLevels[k]))+1 for k in self.__logTypeLevels]), len("level     "))
        # create header
        string += "\n"+ "log type".ljust(maxLogType) + "|" +\
                        "log name".ljust(maxLogName) + "|" +\
                        "level".ljust(maxLogLevel) + "|" +\
                        "std flag".ljust(10) + "|" +\
                        "file flag".ljust(10) + "|"
        # create separator
        string += "\n"+ "-"*maxLogType + "|" +\
                        "-"*maxLogName + "|" +\
                        "-"*maxLogLevel + "|" +\
                        "-"*10 + "|" +\
                        "-"*10 + "|"
        # order from min level to max level
        keys = sorted(self.__logTypeLevels, key=self.__logTypeLevels.__getitem__)
        # append log types
        for k in keys:
            string += "\n"+ str(k).ljust(maxLogType) + "|" +\
                            str(self.__logTypeNames[k]).ljust(maxLogName) + "|" +\
                            str(self.__logTypeLevels[k]).ljust(maxLogLevel) + "|" +\
                            str(self.__logTypeStdoutFlags[k]).ljust(10) + "|" +\
                            str(self.logTypeFileFlags[k]).ljust(10) + "|"
        # user sinks section
        userSinkItems = [(k, s) for k, s in self.__sinks.items() if s.sinkType == 'user']
        if userSinkItems:
            string += "\n - User sinks (%d):"%len(userSinkItems)
            for sinkName, s in userSinkItems:
                levelStr = ""
                if s.minLevel is not None:
                    levelStr += " minLevel=%s"%s.minLevel
                if s.maxLevel is not None:
                    levelStr += " maxLevel=%s"%s.maxLevel
                string += ("\n     [%s] enabled=%s%s"
                           % (sinkName, s.enabled, levelStr))
        return string

    def __stream_format_allowed(self, stream):
        """
        Check whether a stream supports ANSI colour formatting.
        Approach adapted from the Python Cookbook (recipe 475186).
        """
        # curses isn't available on all platforms
        try:
            import curses as CURSES
        except ImportError:
            return False
        try:
            CURSES.setupterm()
            return CURSES.tigetnum("colors") >= 2
        except Exception:
            return False

    def __get_stream_fonts_attributes(self, stream):
        """Return a dict of ANSI escape codes for colour, highlight, and text attributes.

        Keys are 'color', 'highlight', 'attributes', and 'reset'. Values are
        dicts mapping human-readable names to ANSI code strings. All code
        strings are empty when the stream does not support formatting.
        """
        # foreground color
        fgNames = ["black","red","green","orange","blue","magenta","cyan","grey"]
        fgCode  = [str(idx) for idx in range(30,38,1)]
        fgNames.extend(["dark grey","light red","light green","yellow","light blue","pink","light cyan"])
        fgCode.extend([str(idx) for idx in range(90,97,1)])
        # background color
        bgNames = ["black","red","green","orange","blue","magenta","cyan","grey"]
        bgCode  = [str(idx) for idx in range(40,48,1)]
        # attributes
        attrNames = ["bold","underline","blink","invisible","strike through"]
        attrCode  = ["1","4","5","8","9"]
        # set reset
        resetCode = "0"
        # if attributing is not allowed
        if not self.__stream_format_allowed(stream):
            fgCode    = ["" for idx in fgCode]
            bgCode    = ["" for idx in bgCode]
            attrCode  = ["" for idx in attrCode]
            resetCode = ""
        # set font attributes dict
        color = dict( [(fgNames[idx],fgCode[idx]) for idx in range(len(fgCode))] )
        highlight = dict( [(bgNames[idx],bgCode[idx]) for idx in range(len(bgCode))] )
        attributes = dict( [(attrNames[idx],attrCode[idx]) for idx in range(len(attrCode))] )
        return {"color":color, "highlight":highlight, "attributes":attributes, "reset":resetCode}

    def _reset_after_fork(self):
        """Gives a forked process locks of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        self.__processorLock = threading.Lock()
        self.__filterLock = threading.Lock()

    def _flush_atexit_logfile(self):
        """Drain the queue and flush all open streams at Python interpreter shutdown.

        Registered with atexit at the end of __init__. Sends the stop sentinel
        to the background worker thread (if enqueue mode is active) and waits
        up to 5 seconds for it to finish. Then flushes and closes the log file
        stream. User-supplied sinks are never closed here (their lifecycle is
        owned by the caller) -- but a threaded sink's own private worker
        thread was started by pysimplelog, so it IS drained and stopped here
        too, to avoid leaving a thread running past interpreter shutdown.
        Non-threaded user sinks are simply flushed, as before.
        """
        if self.__enqueue and self.__logQueue is not None and os.getpid() == self.__ownerPid:
            self.__logQueue.put_last(_QUEUE_STOP)
            self.__logWorker.join(timeout=5)
        # every sink is flushed and closed, a threaded sink's private thread is stopped first.
        # A file-like object given to add_sink() is only flushed, its owner closes it
        for sink in self.__sinks.values():
            sink.release()

    @property
    def processors(self):
        """Tuple of the processor functions, in the order they run."""
        return tuple(self.__processors)

    @property
    def filters(self):
        """Tuple of the filter functions, in the order they run."""
        return tuple(self.__filters)

    @property
    def filteredRecords(self):
        """Number of records dropped because a filter returned False. Records a sink skipped are counted by the sink."""
        return self.__filteredRecords

    @property
    def filterFailures(self):
        """Number of times a filter, global or of a sink, raised or returned something that is not True or False. The record was kept."""
        return self.__filterFailures

    @property
    def processorFailures(self):
        """Number of records dropped because a processor raised or returned something that is not a record."""
        return self.__processorFailures

    @property
    def lastRecord(self):
        """The record of the last log call that reached a sink, or None when nothing was logged yet."""
        return self.__lastRecord

    @property
    def lastRecords(self):
        """Dictionary with the record of the last log call that reached a sink, for each log type that was logged."""
        return dict(self.__lastRecords)

    @property
    def flush(self):
        """Flush flag."""
        return self.__flush

    @property
    def enqueue(self):
        """Whether non-blocking enqueue mode is active."""
        return self.__enqueue

    @property
    def callerInfo(self):
        """Whether caller file/line/function is prepended to each log line.

        When True every log() and force_log() call walks the call stack
        to find the first frame outside simple_log.py and prepends a
        ``[file:line in func]`` tag before the message. The overhead is
        roughly 10-30 us per call. Default is False.
        """
        return self.__callerInfo

    @property
    def unknownLogTypePolicy(self):
        """The policy applied to undefined log types, 'raise' or 'fallback'."""
        return self.__unknownLogTypePolicy

    @property
    def fallbackLogType(self):
        """The log type used by the 'fallback' policy, None for 'raise'."""
        return self.__fallbackLogType

    @property
    def maxQueueSize(self):
        """Maximum number of records the queue may hold, or None if unbounded.

        Returns None when enqueue mode is not active.
        """
        return self.__maxQueueSize

    @property
    def queueFullPolicy(self):
        """Active policy when the queue is full.

        One of ``'block'``, ``'drop_newest'``, ``'drop_oldest'``, ``'reject'``.
        Returns None when enqueue mode is not active.
        """
        return self.__queueFullPolicy

    @property
    def queueBlockTimeout(self):
        """Seconds to wait before giving up when policy is ``'block'``.

        None means block indefinitely. Returns None when enqueue mode
        is not active or policy is not ``'block'``.
        """
        return self.__queueBlockTimeout

    @property
    def queueSize(self):
        """Current number of log records waiting in the queue.

        Returns 0 when enqueue mode is not active.
        Note: qsize() is an approximation on some platforms -- use
        flush() to guarantee the queue is empty before reading results.
        """
        if self.__logQueue is None:
            return 0
        return self.__logQueue.depth

    @property
    def droppedMessages(self):
        """Cumulative count of log records dropped due to a full queue.

        Accumulates for the lifetime of the logger and is never reset.
        Always 0 when enqueue mode is not active or maxQueueSize is None.
        Records refused by the ``reject`` policy are not in it, see ``queueStats``.
        """
        if self.__logQueue is None:
            return 0
        return self.__logQueue.stats()['dropped']

    @property
    def queueStats(self):
        """
        The counters of the queue of the enqueue mode, or None when that mode is not active.

        A dictionary with ``policy``, ``capacity`` (None without a limit), ``depth`` (records waiting now),
        ``queued`` (records accepted so far), ``dropped`` (records thrown away so far) and ``rejected`` (records
        refused with ``QueueFull`` so far).
        """
        if self.__logQueue is None:
            return None
        return self.__logQueue.stats()

    @property
    def logTypes(self):
        """List of all defined log types."""
        return list(self.__logTypeNames)

    @property
    def logTypeFileFlags(self):
        """Dictionary copy of all defined log types logging to a file flags."""
        return copy.deepcopy(self.__logTypeFileFlags)

    @property
    def logTypeStdoutFlags(self):
        """Dictionary copy of all defined log types logging to Standard output flags."""
        return copy.deepcopy(self.__logTypeStdoutFlags)

    @property
    def stdoutMinLevel(self):
        """Standard output minimum logging level."""
        return self.__stdoutMinLevel

    @property
    def stdoutMaxLevel(self):
        """Standard output maximum logging level."""
        return self.__stdoutMaxLevel

    @property
    def fileMinLevel(self):
        """File logging minimum level."""
        return self.__fileMinLevel

    @property
    def fileMaxLevel(self):
        """File logging maximum level."""
        return self.__fileMaxLevel

    @property
    def forcedStdoutLevels(self):
        """Dictionary copy of forced flags of logging to standard output."""
        return copy.deepcopy(self.__forcedStdoutLevels)

    @property
    def forcedFileLevels(self):
        """Dictionary copy of forced flags of logging to file."""
        return copy.deepcopy(self.__forcedFileLevels)

    @property
    def logTypeNames(self):
        """Dictionary copy of all defined log types logging names."""
        return copy.deepcopy(self.__logTypeNames)

    @property
    def logTypeLevels(self):
        """Dictionary copy of all defined log type levels."""
        return copy.deepcopy(self.__logTypeLevels)

    @property
    def logTypeFormat(self):
        """Dictionary copy of all defined log type ANSI format strings."""
        return copy.deepcopy(self.__logTypeFormat)

    @property
    def name(self):
        """Logger name."""
        return self.__name

    @property
    def logToStdout(self):
        """Whether logging to standard output is enabled.

        Reads from the unified sink registry when available so the
        value always reflects the live routing state.
        """
        if _SINK_STDOUT in self.__sinks:
            return self.__sinks[_SINK_STDOUT].enabled
        return self.__logToStdout

    @property
    def logFileRoll(self):
        """Log file roll parameter."""
        return self.__logFileRoll

    @property
    def logToFile(self):
        """Whether logging to file is enabled.

        Reads from the unified sink registry when available so the
        value always reflects the live routing state.
        """
        if _SINK_FILE in self.__sinks:
            return self.__sinks[_SINK_FILE].enabled
        return self.__logToFile

    @property
    def stdout(self):
        """The current standard output stream.

        Returns the live stream object (never None — returns sys.stdout when
        no custom stream has been set). Compare with ``parameters['stdout']``
        which returns None in that case for historical reasons.
        """
        return self.__stdout

    @property
    def sinks(self):
        """Read-only snapshot of the sinks by name, with the handler each one writes to.

        Keys are ``CONSOLE_SINK`` and ``FILE_SINK`` for the two built-in sinks, and the name given to
        ``add_sink()`` for the others. A value is the :class:`pysimplelog.sinks.Sink` or the handler that was
        added. Routing is changed with the setters of the logger, and what a sink did is in :meth:`sink_stats`.
        """
        return MappingProxyType({name: sink.handler for name, sink in self.__sinks.items()})

    @property
    def logFileName(self):
        """Currently used log file name."""
        return self.__sinks[_SINK_FILE].handler.path

    @property
    def logFileBasename(self):
        """Log file basename."""
        return self.__logFileBasename

    @property
    def logFileExtension(self):
        """Log file extension."""
        return self.__logFileExtension

    @property
    def logFileMaxSize(self):
        """Maximum allowed logfile size in megabytes."""
        return self.__logFileMaxSize

    @property
    def logMessageMaxSize(self):
        """Maximum allowed message character count. None means no limit."""
        return self.__maxMessageSize

    @property
    def logDataMaxSize(self):
        """Maximum allowed data string character count. None means no limit."""
        return self.__maxDataSize

    @property
    def logFileFirstNumber(self):
        """Log file first number."""
        return self.__logFileFirstNumber

    @property
    def timezone(self):
        """The active timezone name as a string, or None if using the machine default."""
        timezone = self.__timezone
        if timezone is not None:
            timezone = timezone.zone
        return timezone

    @property
    def _timezone(self):
        """Internal pytz timezone object, or None if using the machine default."""
        return self.__timezone

    @property
    def logMessagesCounter(self):
        """Counter look-up table for logged messages that have a count constraint applied."""
        return self.__logMessagesCounter

    def set_caller_info(self, callerInfo):
        """Enable or disable automatic caller file/line/function tagging.

        Safe to call at any time. Takes effect on the very next log()
        or force_log() call. When disabled the overhead drops to a single
        boolean read (~5 ns) per log call.

        :Parameters:
            #. callerInfo (boolean): True to prepend
               ``[file:line in func]`` to each message, False to disable.

        :Raises:
            #. TypeError: If *callerInfo* is not a boolean.
        """
        if not isinstance(callerInfo, bool):
            raise TypeError("callerInfo must be a boolean")
        self.__callerInfo = callerInfo

    def add_processor(self, func):
        """
        Add a function that rewrites every record before any sink receives it.

        The function receives the :class:`pysimplelog.record.LogRecord` and returns a record, usually a changed
        copy made with ``record._replace(...)``. Functions run in the order they were added, for every record.
        To treat only some records differently, test the record inside the function, for example
        ``record.logType``. The result is also what ``lastRecord`` keeps. See
        :func:`pysimplelog.processors.redact_fields` and :func:`pysimplelog.processors.redact_text`.

        A function that raises, or returns something that is not a record, makes the logger drop the record for
        every sink: letting the unchanged record through could leak what the function was meant to hide.
        The failure is counted in ``processorFailures`` and one warning is written for each function.
        A function must not log.

        :Parameters:
            #. func (callable): ``f(record) -> record``.

        :Raises:
            #. TypeError: If *func* is not callable.
        """
        if not callable(func):
            raise TypeError("record processor func must be callable")
        self.__processors = self.__processors + [func]

    def remove_processor(self, func):
        """
        Remove a function from the processors. Nothing happens when it was never added.

        :Parameters:
            #. func (callable): The function to remove.
        """
        self.__processors = [processor for processor in self.__processors if processor != func]

    def add_filter(self, func):
        """
        Add a function that decides whether a record goes on, after the record processors have run.

        The function receives the :class:`pysimplelog.record.LogRecord` and returns True to keep it or
        False to drop it. Dropped means dropped for every sink: nothing is written, and ``lastRecord`` is not
        updated. Functions run in the order they were added, for every record, and the first one that
        returns False ends the check. They see the record as the record processors left it. To decide for one
        sink only, see :meth:`set_sink_filter`. ``force_log`` does not use filters. A record that a record
        processor failed on is not filtered, because there is no record to look at.

        A function that raises, or returns something that is not True or False, keeps the record: a broken
        filter must not make logs disappear. The failure is counted in ``filterFailures`` and one warning is
        written for each function. Records that a filter dropped are counted in ``filteredRecords``.
        A function must not log. See :func:`pysimplelog.filters.sample`.

        :Parameters:
            #. func (callable): ``f(record) -> bool``.

        :Raises:
            #. TypeError: If *func* is not callable.
        """
        if not callable(func):
            raise TypeError("filter func must be callable")
        self.__filters = self.__filters + [func]

    def remove_filter(self, func):
        """
        Remove a function from the filters. Nothing happens when it was never added.

        :Parameters:
            #. func (callable): The function to remove.
        """
        self.__filters = [keep for keep in self.__filters if keep != func]

    def set_sink_formatter(self, name, formatter):
        """
        Change how one sink turns a record into text.

        .. code-block:: python

            ## One JSON object per line in the log file, readable text on the console
            from pysimplelog import FILE_SINK
            logger.set_sink_formatter(FILE_SINK, None)
            ## A template
            logger.set_sink_formatter('audit', '{timestamp} {severity} {message} {user}')
            ## Any function of the record
            logger.set_sink_formatter('audit', lambda record: record.message.upper())

        :Parameters:
            #. name (str, int): The name the sink was added with. The two built-in sinks are in ``sinks`` under
               their own keys.
            #. formatter (None, str, callable): None gives JSON, a keyword such as ``'text'`` or ``'json'``, a
               string with ``{name}`` placeholders, or a function ``f(record) -> str``. See
               :func:`pysimplelog.formatters.resolve_formatter`.

        :Raises:
            #. ValueError: If no sink is registered under *name*, or *formatter* is a string that is neither a
               keyword nor a template.
            #. TypeError: If *formatter* is none of the accepted types.
        """
        if name not in self.__sinks:
            raise ValueError("sink %r is not registered" % (name,))
        sink = self.__sinks[name]
        if name == _SINK_STDOUT:
            # the console is rebuilt, because only the text layout is coloured
            resolve_formatter(formatter)
            self.__consoleFormatter = formatter
            sink.set_handler(self.__make_console_sink())
        else:
            # the sink checks the formatter and keeps the old one when it is not valid
            sink.handler.set_formatter(formatter)
            if name == _SINK_FILE:
                self.__fileFormatter = formatter

    def sink_stats(self, name=None):
        """
        Returns what one sink, or every sink, did and what it lost, so a loss is never silent.

        Each sink has a dictionary with:

        * ``queue``: the counters of the private queue of a threaded sink, None for a sink written to on the calling
          thread. They are ``policy``, ``capacity``, ``depth`` (records waiting now), ``queued`` (records accepted so
          far), ``dropped`` (records thrown away so far) and ``rejected`` (records refused so far).
        * ``spool``: what the spool of the sink holds and what its delivery did, None for a sink without a spool.
          It has ``depth`` (records not delivered), ``bytes``, ``segments``, ``spooled`` (records kept), ``dropped``,
          ``rejected``, ``dead`` (records parked in the ``dead`` file), ``retries``, ``replayed`` and
          ``orphans_adopted`` and ``orphans_skipped`` (slots of other processes), ``refused`` (records not kept
          because a forked child does not own the spool), ``errors``, ``torn``, ``corrupt``, ``lost`` and ``slot``.
          The ``queue`` of such a sink is the queue of hints: a hint that was dropped lost no record.
        * ``filtered``: the number of records the filter of the sink skipped, see :meth:`set_sink_filter`.
        * ``delivery``: what the sink itself reports, see ``Sink.stats``: ``processed``, ``failed``, ``last_error``,
          ``latency_mean`` and ``latency_max`` in seconds, and what a particular sink adds, such as ``sent`` for
          the SIEM sink.

        :Parameters:
            #. name (None, str, int): The name a sink was added with, ``CONSOLE_SINK`` or ``FILE_SINK``. None
               gives every sink.

        :Returns:
            #. stats (dict): The dictionary of one sink, or a dictionary of them by name when *name* is None.

        :Raises:
            #. ValueError: If no sink is registered under *name*.
        """
        if name is None:
            return {key: self.sink_stats(key) for key in list(self.__sinks)}
        if name not in self.__sinks:
            raise ValueError("sink %r is not registered" % (name,))
        sink = self.__sinks[name]
        return {'queue': sink.queue_stats(), 'spool': sink.spool_stats(), 'filtered': sink.filteredCount,
                'delivery': sink.handler.stats}

    def adopt_orphans(self, name, timeout=30.0):
        """
        Sends, once, what the spool slots left behind by dead processes hold, through one sink.

        Only slots made for the same spool id, sink class and target are taken, a slot made for something else is left
        alone and counted. Slots that a live process holds are skipped. The worker of the sink does the sending, one
        record at a time and in order, and stops at the first record that cannot be delivered. Setting
        ``adoptOrphans=True`` in the spool settings makes the sink do the same on its own, every ``adoptInterval``
        seconds, when it is idle.

        :Parameters:
            #. name (str): The name of a sink that was added with a spool.
            #. timeout (int, float): Seconds to wait for the worker to be done.

        :Returns:
            #. result (dict, None): ``replayed`` (records sent), ``orphans_adopted`` (slots emptied) and
               ``orphans_skipped`` (slots left alone), as counts since the sink was added. None when the worker was not
               done in time.

        :Raises:
            #. ValueError: If no sink is registered under *name*, or it has no spool.
        """
        if name not in self.__sinks:
            raise ValueError("sink %r is not registered" % (name,))
        sink = self.__sinks[name]
        if sink.durable is None:
            raise ValueError("sink %r has no spool" % (name,))
        return sink.durable.adopt_orphans(timeout)

    def maintain(self):
        """
        Does the housekeeping of every sink, now: files that are too many or too old are deleted and rotated files are queued
        for compression, a spool drops the segments that are too old and tries again to delete files that were in use.

        Nothing happens on its own for a sink that is not written to, so call this from a scheduler, or from a thread of your
        own, if files must go on time whether or not anything is logged. It never sends or loses a record that is not already
        past its limit, it is safe to call at any time and from any thread, and an error in one sink is reported once and does
        not stop the others. Each sink can be asked separately with its own ``maintain()``. :meth:`flush` is the one that
        pushes data out.

        :Returns:
            #. results (dict): For each sink that had something to do, by the name it is known by (``CONSOLE_SINK``,
               ``FILE_SINK`` or the name given to ``add_sink``), what it did. For a file sink ``files_deleted``, for a spool
               under ``spool``: ``dropped`` and ``undeleted``.

        .. code-block:: python

            ## A thread of your own that tidies up every hour, until stop.set() is called
            def keep_tidy(logger, everySeconds=3600):
                stop = threading.Event()
                def run():
                    while not stop.wait(everySeconds):
                        logger.maintain()
                threading.Thread(target=run, daemon=True).start()
                return stop
        """
        results = {}
        for name, sink in list(self.__sinks.items()):
            try:
                result = sink.maintain()
            except Exception as error:
                with self.__processorLock:
                    isNew = name not in self.__maintainWarned
                    self.__maintainWarned.add(name)
                if isNew:
                    sys.stderr.write(f"pysimplelog WARNING: the housekeeping of sink {name!r} failed. "
                                     f"Error: {type(error).__name__}: {error}\n")
                result = {'error': type(error).__name__}
            if result is not None:
                results[name] = result
        return results

    def set_sink_filter(self, name, recordFilter):
        """
        Set, or remove, the function that decides which records one sink receives.

        This is the last step of the pipeline, after the sink has passed the routing by level and log type.
        The function receives the :class:`pysimplelog.record.LogRecord` and returns True to give it to this
        sink or False to skip it. Other sinks are not affected. A function that raises, or returns something
        that is not True or False, gives the record to the sink and is counted like a failing filter.
        Skipped records are counted in ``filteredCount`` of the sink, see ``sinks``.

        .. code-block:: python

            ## Only audit records go to the audit file
            logger.set_sink_filter('audit', lambda record: record.logType == 'audit')
            ## Back to receiving everything that passes the routing
            logger.set_sink_filter('audit', None)

        :Parameters:
            #. name (str, int): The name the sink was added with. The two built-in sinks are in ``sinks`` under
               their own keys.
            #. recordFilter (callable, None): ``f(record) -> bool``, or None to remove the function.

        :Raises:
            #. ValueError: If no sink is registered under *name*.
            #. TypeError: If *recordFilter* is neither callable nor None.
        """
        if name not in self.__sinks:
            raise ValueError("sink %r is not registered" % (name,))
        if recordFilter is not None and not callable(recordFilter):
            raise TypeError("recordFilter must be callable or None")
        self.__sinks[name].recordFilter = recordFilter
        self.__update_sink_filter_flag()

    def __update_sink_filter_flag(self):
        """Remembers whether any sink has a filter, so log() skips the check when none has."""
        self.__hasSinkFilters = any(sink.recordFilter is not None for sink in self.__sinks.values())

    def __update_trace_flag(self):
        """Remembers whether any sink asks for trace identifiers, so _build_record reads the span only then."""
        self.__capturesTrace = any(sink.handler.captureTrace for sink in self.__sinks.values())

    def set_unknown_log_type_policy(self, policy, fallbackLogType=None):
        """
        Set what log() and force_log() do with an undefined log type.

        :Parameters:
            #. policy (string): 'raise' or 'fallback'.
            #. fallbackLogType (None, string): The log type to use when policy is
               'fallback'. It is checked when first used, so it can be defined later.

        :Raises:
            #. ValueError: If *policy* is not 'raise' or 'fallback'.
            #. TypeError: If *policy* is 'fallback' and *fallbackLogType* is not a string.
        """
        if policy not in ('raise', 'fallback'):
            raise ValueError("unknownLogTypePolicy must be 'raise' or 'fallback'")
        if policy == 'fallback' and not isinstance(fallbackLogType, str):
            raise TypeError("fallbackLogType must be a string when unknownLogTypePolicy is 'fallback'")
        self.__unknownLogTypePolicy = policy
        self.__fallbackLogType      = fallbackLogType if policy == 'fallback' else None

    def set_max_queue_size(self, maxQueueSize):
        """Set the maximum number of records the internal queue may hold.

        Can be called at any time -- takes effect on the very next log()
        call because Python's queue.Queue checks maxsize dynamically on
        every put(). Setting to None removes the cap entirely.

        :Parameters:
            #. maxQueueSize (None, integer): Maximum queue depth. Must be
               a positive integer or None. Zero is not accepted because it
               is ambiguous (CPython treats Queue(maxsize=0) as unbounded).

        :Raises:
            #. TypeError: If *maxQueueSize* is not an integer or None.
            #. ValueError: If *maxQueueSize* is zero or negative.
        """
        if maxQueueSize is not None:
            if not isinstance(maxQueueSize, int) or isinstance(maxQueueSize, bool):
                raise TypeError("maxQueueSize must be a positive integer or None")
            if maxQueueSize <= 0:
                raise ValueError("maxQueueSize must be a positive integer, got %d" % maxQueueSize)
        self.__maxQueueSize = maxQueueSize
        # sync the live queue object if one already exists
        if self.__logQueue is not None:
            self.__logQueue.set_max_size(maxQueueSize)

    def set_queue_full_policy(self, queueFullPolicy):
        """Set the backpressure policy applied when the queue is full.

        Can be changed at runtime -- takes effect on the very next log()
        call that finds the queue at capacity.

        :Parameters:
            #. queueFullPolicy (string): One of four values:

               ``'block'``  -- the calling thread parks until a slot opens.
               If queueBlockTimeout is set, parking is bounded; after that
               many seconds the new record is dropped. If queueBlockTimeout is
               None the thread parks indefinitely -- safe against message loss
               but risky if the worker thread dies.

               ``'drop_newest'`` -- the new record is discarded.

               ``'drop_oldest'`` -- the record that has waited longest is
               discarded and the new one is kept.

               ``'reject'`` -- raises ``pysimplelog.queues.QueueFull``, a ``queue.Full``, to the caller. The caller
               must handle the exception. Useful when the caller has its
               own retry or circuit-breaker logic.

               Every record that is discarded is counted, see ``droppedMessages`` and ``queueStats``, and one warning
               line is written to stderr for each run of them. Every refusal is counted in ``queueStats``.

        :Raises:
            #. TypeError: If *queueFullPolicy* is not a string.
            #. ValueError: If *queueFullPolicy* is not one of ``'block'``,
               ``'drop_newest'``, ``'drop_oldest'``, or ``'reject'``.
        """
        self.__queueFullPolicy = validate_queue_policy(queueFullPolicy)
        if self.__logQueue is not None:
            self.__logQueue.set_policy(queueFullPolicy)

    def set_queue_block_timeout(self, queueBlockTimeout):
        """Set the maximum seconds to wait when queueFullPolicy is ``'block'``.

        Can be changed at runtime -- takes effect on the very next log()
        call that blocks on a full queue.

        :Parameters:
            #. queueBlockTimeout (None, number): Seconds to wait before
               giving up. None means wait indefinitely -- the thread parks
               until the worker drains a slot, no matter how long that
               takes. A positive number caps the wait; after expiry the
               record is dropped, droppedMessages is incremented, and one
               warning line is written to stderr. Has no effect when
               queueFullPolicy is not ``'block'``.

        :Raises:
            #. TypeError: If *queueBlockTimeout* is not a number or None.
            #. ValueError: If *queueBlockTimeout* is zero or negative.
        """
        if queueBlockTimeout is not None:
            if not _is_number(queueBlockTimeout):
                raise TypeError("queueBlockTimeout must be a positive number or None")
            if float(queueBlockTimeout) <= 0:
                raise ValueError("queueBlockTimeout must be positive, got %s" % queueBlockTimeout)
        self.__queueBlockTimeout = queueBlockTimeout
        if self.__logQueue is not None:
            self.__logQueue.set_block_timeout(queueBlockTimeout)

    def set_timezone(self, timezone):
        """
        Set the logging timezone.

        :Parameters:
            #. timezone (None, str): Logging time timezone. If provided,
               pytz must be installed and it must be the timezone name. If not
               provided, the machine default timezone will be used.

        :Raises:
            #. TypeError: If *timezone* is not a string or None.
            #. pytz.exceptions.UnknownTimeZoneError: If *timezone* is a string
               that does not match any timezone known to pytz.
        """
        if timezone is not None:
            if not isinstance(timezone, str):
                raise TypeError("timezone must be None or a string")
            import pytz
            timezone = pytz.timezone(timezone)
        self.__timezone = timezone

    def is_log_type(self, logType):
        """Return True if the given log type has been defined, False otherwise.

        :Parameters:
           #. logType (string): The log type name to check.

        :Returns:
           #. result (boolean): True when logType is a registered log type.
        """
        try:
            return logType in self.__logTypeNames
        except Exception:
            return False

    def update(self, **kwargs):
        """Update logger general parameters using key value pairs.
        Updatable parameters are name, flush, stdout, logToStdout, logFileRoll,
        logToFile, logFileMaxSize, stdoutMinLevel, stdoutMaxLevel, fileMinLevel,
        fileMaxLevel, logFileFirstNumber, unknownLogTypePolicy and fallbackLogType.
        """
        # update name
        if "name" in kwargs:
            self.set_name(kwargs["name"])
        # update flush
        if "flush" in kwargs:
            self.set_flush(kwargs["flush"])
        # update stdout
        if "stdout" in kwargs:
            self.set_stdout(kwargs["stdout"])
        # update logToStdout
        if "logToStdout" in kwargs:
            self.set_log_to_stdout_flag(kwargs["logToStdout"])
        # update logFileRoll
        if "logFileRoll" in kwargs:
            self.set_log_file_roll(kwargs["logFileRoll"])
        # update logToFile
        if "logToFile" in kwargs:
            self.set_log_to_file_flag(kwargs["logToFile"])
        # update logFileMaxSize
        if "logFileMaxSize" in kwargs:
            self.set_log_file_maximum_size(kwargs["logFileMaxSize"])
        # update logFileFirstNumber
        if "logFileFirstNumber" in kwargs:
            self.set_log_file_first_number(kwargs["logFileFirstNumber"])
        # update stdoutMinLevel
        if "stdoutMinLevel" in kwargs:
            self.set_minimum_level(kwargs["stdoutMinLevel"], stdoutFlag=True, fileFlag=False)
        # update stdoutMaxLevel
        if "stdoutMaxLevel" in kwargs:
            self.set_maximum_level(kwargs["stdoutMaxLevel"], stdoutFlag=True, fileFlag=False)
        # update fileMinLevel
        if "fileMinLevel" in kwargs:
            self.set_minimum_level(kwargs["fileMinLevel"], stdoutFlag=False, fileFlag=True)
        # update fileMaxLevel
        if "fileMaxLevel" in kwargs:
            self.set_maximum_level(kwargs["fileMaxLevel"], stdoutFlag=False, fileFlag=True)
        # update maxMessageSize
        if "maxMessageSize" in kwargs:
            self.set_maximum_message_size(kwargs["maxMessageSize"])
        # update maxDataSize
        if "maxDataSize" in kwargs:
            self.set_maximum_data_size(kwargs["maxDataSize"])
        # update logfile
        if "logFile" in kwargs:
            self.set_log_file(kwargs["logFile"])
        # update queue settings (all runtime-safe)
        if "maxQueueSize" in kwargs:
            self.set_max_queue_size(kwargs["maxQueueSize"])
        if "queueFullPolicy" in kwargs:
            self.set_queue_full_policy(kwargs["queueFullPolicy"])
        if "queueBlockTimeout" in kwargs:
            self.set_queue_block_timeout(kwargs["queueBlockTimeout"])
        if "callerInfo" in kwargs:
            self.set_caller_info(kwargs["callerInfo"])
        if "unknownLogTypePolicy" in kwargs or "fallbackLogType" in kwargs:
            self.set_unknown_log_type_policy(kwargs.get("unknownLogTypePolicy", self.__unknownLogTypePolicy),
                                             kwargs.get("fallbackLogType", self.__fallbackLogType))


    @property
    def parameters(self):
        """Return a dictionary of logger general parameters.

        The returned dictionary can be passed directly to another Logger
        instance's update() method to copy this configuration. It includes
        a ``userSinks`` key whose value is a dict mapping each user-added
        sink name to its current configuration snapshot (enabled, minLevel,
        maxLevel, logTypeFlags). Built-in sinks are not included there;
        they are described by the surrounding keys.
        """
        userSinks = {}
        for k, s in self.__sinks.items():
            if s.sinkType == 'user':
                userSinks[k] = {
                    'enabled':      s.enabled,
                    'minLevel':     s.minLevel,
                    'maxLevel':     s.maxLevel,
                    'logTypeFlags': dict(s.logTypeFlags),
                }
        return {"name":self.__name,
                "flush":self.__flushSetting,
                "stdout":None if self.__stdout is sys.stdout else self.__stdout,
                "logToStdout":self.__logToStdout,
                "logFileRoll":self.__logFileRoll,
                "logToFile":self.__logToFile,
                "logFileMaxSize":self.__logFileMaxSize,
                "logFileFirstNumber":self.__logFileFirstNumber,
                "stdoutMinLevel":self.__stdoutMinLevel,
                "stdoutMaxLevel":self.__stdoutMaxLevel,
                "fileMinLevel":self.__fileMinLevel,
                "fileMaxLevel":self.__fileMaxLevel,
                "maxMessageSize":self.__maxMessageSize,
                "maxDataSize":self.__maxDataSize,
                "logFile":self.__logFileBasename+"."+self.__logFileExtension,
                "enqueue":self.__enqueue,
                "maxQueueSize":self.__maxQueueSize,
                "queueFullPolicy":self.__queueFullPolicy,
                "queueBlockTimeout":self.__queueBlockTimeout,
                "callerInfo":self.__callerInfo,
                "unknownLogTypePolicy":self.__unknownLogTypePolicy,
                "fallbackLogType":self.__fallbackLogType,
                "userSinks":userSinks}


    def custom_init(self, *args, **kwargs):
        """
        Custom initialize hook, called as the very last step of Logger.__init__.

        The logger is fully built when this runs: log types, the stdout and
        file sinks, the queue and caller info all exist, so logging and
        add_sink() work inside it. The ``logTypes`` constructor argument is
        applied right after it.

        Override this method to perform application-specific setup on Logger
        instances without modifying __init__ directly.

        :Parameters:
            #. \\*args (): This is used to send non-keyworded variable length argument
               list to custom initialize.
            #. \\**kwargs (): This is keyworded variable length of arguments.
               kwargs can be anything other than __init__ arguments.
        """
        pass

    def set_name(self, name):
        """
        Set the logger name.

        :Parameters:
           #. name (string): The logger name.

        :Raises:
            #. TypeError: If *name* is not a string.
        """
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        self.__name = name

    def set_flush(self, flush):
        """
        Set how the logging streams are flushed after every record.

        :Parameters:
           #. flush (boolean, string, None): True flushes every record to the operating system, which
              survives a crash of the application. False or ``'none'`` or None leaves the data in the
              buffers. ``'fsync'`` also forces every record of the log file to the disk, which survives a
              crash of the operating system and costs several times more per record. The console never
              uses ``fsync``, it is flushed.

        :Raises:
            #. TypeError: If *flush* is not a boolean, a string or None.
            #. ValueError: If *flush* is a string but not ``'none'``, ``'flush'`` or ``'fsync'``.
        """
        if isinstance(flush, bool):
            flushMode = 'flush' if flush else 'none'
        else:
            flushMode = validate_flush_mode(flush)
        self.__flushSetting = flush
        self.__flushMode = flushMode
        # file-like objects added with add_sink() are flushed whenever the mode is not none
        self.__flush = flushMode != 'none'
        if _SINK_STDOUT in self.__sinks:
            self.__sinks[_SINK_STDOUT].set_handler(self.__make_console_sink())
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].handler.set_flush_mode(flushMode)
        for sink in self.__sinks.values():
            if sink.isWrapped:
                sink.handler.set_flush_mode(self.__plain_flush_mode(sink.handler.stream))

    def set_stdout(self, stream=None):
        """
        Set the logger standard output stream.

        :Parameters:
           #. stream (None, stream): The standard output stream. If None, system standard
              output will be set automatically. Otherwise any object with read and write
              methods can be passed.

        :Raises:
            #. TypeError: If *stream* is not None and does not expose both
               ``read`` and ``write`` methods.
        """
        if stream is None:
            self.__stdout = sys.stdout
        else:
            if not (hasattr(stream, 'read') and hasattr(stream, 'write')):
                raise TypeError("stdout stream is not valid")
            self.__stdout = stream
        # set stdout colors
        self.__stdoutFontFormat = self.__get_stream_fonts_attributes(stream)
        # sync handler into unified sink registry if already built
        if _SINK_STDOUT in self.__sinks:
            self.__sinks[_SINK_STDOUT].set_handler(self.__make_console_sink())

    def set_log_to_stdout_flag(self, logToStdout):
        """
        Set the global flag controlling logging to standard output.

        When set to False, no logging to standard output will happen
        regardless of any per-logType stdout flag.

        :Parameters:
           #. logToStdout (boolean): Whether to log to the standard output stream.

        :Raises:
            #. TypeError: If *logToStdout* is not a boolean.
        """
        if not isinstance(logToStdout, bool):
            raise TypeError("logToStdout must be boolean")
        self.__logToStdout = logToStdout
        if _SINK_STDOUT in self.__sinks:
            self.__sinks[_SINK_STDOUT].enabled = logToStdout
            self.__rebuild_active_sinks()

    def set_log_to_file_flag(self, logToFile):
        """
        Set the global flag controlling logging to file.

        When set to False, no logging to file will happen regardless of any
        per-logType file flag.

        :Parameters:
           #. logToFile (boolean): Whether to enable logging to file.

        :Raises:
            #. TypeError: If *logToFile* is not a boolean.
        """
        if not isinstance(logToFile, bool):
            raise TypeError("logToFile must be boolean")
        self.__logToFile = logToFile
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].enabled = logToFile
            self.__rebuild_active_sinks()

    def set_log_type_flags(self, logType, stdoutFlag, fileFlag):
        """
        Set a defined log type flags.

        :Parameters:
           #. logType (string): A defined logging type.
           #. stdoutFlag (boolean): Whether to log to the standard output stream.
           #. fileFlag (boolean): Whether to enable logging to file.

        :Raises:
            #. ValueError: If *logType* is not a defined log type.
            #. TypeError: If *stdoutFlag* or *fileFlag* is not a boolean.
        """
        if logType not in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' not defined" %logType)
        if not isinstance(stdoutFlag, bool):
            raise TypeError("stdoutFlag must be boolean")
        if not isinstance(fileFlag, bool):
            raise TypeError("fileFlag must be boolean")
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        self.__logTypeFileFlags[logType]   = fileFlag
        if _SINK_STDOUT in self.__sinks:
            self.__rebuild_active_sinks()

    def set_log_file_roll(self, logFileRoll):
        """
        Set roll parameter to determine the maximum number of log files allowed.
        Beyond the maximum, older will be removed.

        :Parameters:
            #. logFileRoll (None, integer): If given, it sets the maximum number of
               log files to write. Exceeding the number will result in deleting
               older files. This also insures always increasing files numbering.
               Log files will be identified in increasing N order of
               logFileBasename_N.logFileExtension pattern. Be careful setting
               this parameter as old log files will be permanently deleted if
               the number of files exceeds the value of logFileRoll

        :Raises:
            #. TypeError: If *logFileRoll* is not an integer or None.
            #. ValueError: If *logFileRoll* is not greater than zero.
        """
        if logFileRoll is not None:
            if not isinstance(logFileRoll, int):
                raise TypeError("logFileRoll must be None or integer")
            if logFileRoll<=0:
                raise ValueError("integer logFileRoll must be >0")
        self.__logFileRoll = logFileRoll
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].handler.set_roll(logFileRoll)

    def set_log_file(self, logfile):
        """
        Set the log file full path including directory path basename and extension.

        :Parameters:
           #. logfile (string): the full log file path including basename and
              extension. If this is given, all of logFileBasename and logFileExtension
              will be discarded. logfile is equivalent to logFileBasename.logFileExtension

        :Raises:
            #. TypeError: If *logfile* is not a string.
        """
        if not isinstance(logfile, str):
            raise TypeError("logfile must be a string")
        basename, extension = os.path.splitext(logfile)
        self.__set_log_file_basename(logFileBasename=basename)
        self.set_log_file_extension(logFileExtension=extension)

    def set_log_file_extension(self, logFileExtension):
        """
        Set the log file extension.

        :Parameters:
           #. logFileExtension (string): Logging file extension. A logging file full name is
              set as logFileBasename.logFileExtension

        :Raises:
            #. TypeError: If *logFileExtension* is not a string.
            #. ValueError: If *logFileExtension* resolves to an empty string
               after stripping leading and trailing dots.
        """
        if not isinstance(logFileExtension, str):
            raise TypeError("logFileExtension must be a string")
        if not len(logFileExtension):
            raise ValueError("logFileExtension can't be empty")
        if logFileExtension[0] == ".":
            logFileExtension = logFileExtension[1:]
        if not len(logFileExtension):
            raise ValueError("logFileExtension is not allowed to be single dot")
        if logFileExtension[-1] == ".":
            logFileExtension = logFileExtension[:-1]
        if not len(logFileExtension):
            raise ValueError("logFileExtension is not allowed to be double dots")
        self.__logFileExtension = logFileExtension
        self.__select_log_file()

    def set_log_file_basename(self, logFileBasename):
        """
        Set the log file basename.

        :Parameters:
           #. logFileBasename (string): Logging file directory path and file basename.
              A logging file full name is set as logFileBasename.logFileExtension

        :Raises:
            #. TypeError: If *logFileBasename* is not a string.
        """
        self.__set_log_file_basename(logFileBasename)
        self.__select_log_file()

    def __set_log_file_basename(self, logFileBasename):
        if not isinstance(logFileBasename, str):
            raise TypeError("logFileBasename must be a string")
        self.__logFileBasename = _normalize_path(logFileBasename)#logFileBasename

    def __select_log_file(self):
        """Tells the file sink to continue in the file of the current base name and extension, once the sink exists."""
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].handler.set_path(self.__logFileBasename, self.__logFileExtension)

    def set_log_file_maximum_size(self, logFileMaxSize):
        """
        Set the log file maximum size in megabytes.

        :Parameters:
           #. logFileMaxSize (None, number): The maximum size in Megabytes
              of a logging file. Once exceeded, another logging file as
              logFileBasename_N.logFileExtension will be created.
              Where N is an automatically incremented number. If None or a
              negative number is given, the logging file will grow
              indefinitely

        :Raises:
            #. TypeError: If *logFileMaxSize* is not a number or None.
        """
        if logFileMaxSize is not None:
            if not _is_number(logFileMaxSize):
                raise TypeError("logFileMaxSize must be a number")
            logFileMaxSize = float(logFileMaxSize)
            if logFileMaxSize <=0:
                logFileMaxSize = None
        #assert logFileMaxSize>=1, "logFileMaxSize minimum size is 1 megabytes"
        self.__logFileMaxSize = logFileMaxSize
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].handler.set_max_size(logFileMaxSize)

    def set_maximum_message_size(self, maxMessageSize):
        """Set the maximum number of characters allowed in a single log message.

        :Parameters:
            #. maxMessageSize (None, integer): Maximum character count for the
               message string. If None, no limit is applied. Messages exceeding
               this limit are truncated and '[truncated]' is appended. Must be
               a positive integer when given.

        :Raises:
            #. TypeError: If *maxMessageSize* is not a positive integer or None.
        """
        if maxMessageSize is not None:
            if not isinstance(maxMessageSize, int) or maxMessageSize <= 0:
                raise TypeError("maxMessageSize must be None or a positive integer")
        self.__maxMessageSize = maxMessageSize

    def set_maximum_data_size(self, maxDataSize):
        """Set the maximum character count for the string representation of the data argument.

        Applies to the data argument passed to log() or force_log().

        :Parameters:
            #. maxDataSize (None, integer): Maximum character count for the
               string representation of data. If None, no limit is applied.
               Data strings exceeding this limit are truncated and '[truncated]'
               is appended. Must be a positive integer when given.

        :Raises:
            #. TypeError: If *maxDataSize* is not a positive integer or None.
        """
        if maxDataSize is not None:
            if not isinstance(maxDataSize, int) or maxDataSize <= 0:
                raise TypeError("maxDataSize must be None or a positive integer")
        self.__maxDataSize = maxDataSize

    def set_log_file_first_number(self, logFileFirstNumber):
        """
        Set log file first number.

        :Parameters:
            #. logFileFirstNumber (None, integer): first log file number 'N' in
               logFileBasename_N.logFileExtension. If None is given then
               first log file will be logFileBasename.logFileExtension and once
               logFileMaxSize is reached second log file will be
               logFileBasename_0.logFileExtension and so on and so forth.
               If number is given it must be an integer >=0

        :Raises:
            #. TypeError: If *logFileFirstNumber* is not an integer or None.
            #. ValueError: If *logFileFirstNumber* is a negative integer.
        """
        if logFileFirstNumber is not None:
            if not isinstance(logFileFirstNumber, int):
                raise TypeError("logFileFirstNumber must be None or an integer")
            if logFileFirstNumber<0:
                raise ValueError("logFileFirstNumber integer must be >=0")
        self.__logFileFirstNumber = logFileFirstNumber
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].handler.set_first_number(logFileFirstNumber)

    def set_minimum_level(self, level=0, stdoutFlag=True, fileFlag=True, sinks=None):
        """
        Set the minimum logging level. All levels below the minimum will be ignored at logging.

        :Parameters:
           #. level (None, number, str): The minimum level of logging.
              If None, minimum level checking is left out.
              If str, it must be a defined logtype and therefore the minimum level would be the level of this logtype.
           #. stdoutFlag (boolean): Whether to apply this minimum level to standard output logging.
           #. fileFlag (boolean): Whether to apply this minimum level to file logging.
           #. sinks (None, list): Optional list of user sink names to update.
              Each name must have been registered via add_sink(). When None
              (default) user sinks are left unchanged.

        :Raises:
            #. TypeError: If *stdoutFlag* or *fileFlag* is not a boolean, if *sinks*
               is not iterable or contains non-string entries, or if *level* is not
               a number when given as a numeric type.
            #. ValueError: If *level* is given as a string that is not a defined log
               type, if *level* exceeds the current maximum level for a target stream,
               or if a named sink in *sinks* is not registered or is a built-in sink.
        """
        # check flags
        if not isinstance(stdoutFlag, bool):
            raise TypeError("stdoutFlag must be boolean")
        if not isinstance(fileFlag, bool):
            raise TypeError("fileFlag must be boolean")
        # validate sinks list
        if sinks is not None:
            if not hasattr(sinks, '__iter__'):
                raise TypeError("sinks must be None or a list of sink names")
            sinks = list(sinks)
            for sinkName in sinks:
                if not isinstance(sinkName, str):
                    raise TypeError("each entry in sinks must be a string sink name")
                if sinkName not in self.__sinks:
                    raise ValueError("sink '%s' is not registered" % sinkName)
                if self.__sinks[sinkName].sinkType != 'user':
                    raise ValueError("sink '%s' is a built-in sink; use stdoutFlag/fileFlag for built-ins" % sinkName)
        if not (stdoutFlag or fileFlag or sinks):
            return
        # check level
        if level is not None:
            if isinstance(level, str):
                level = str(level)
                if level not in self.__logTypeStdoutFlags:
                    raise ValueError("level '%s' given as string, is not defined logType" %level)
                level = self.__logTypeLevels[level]
            if not _is_number(level):
                raise TypeError("level must be a number")
            level = float(level)
            if stdoutFlag:
                if self.__stdoutMaxLevel is not None:
                    if level>self.__stdoutMaxLevel:
                        raise ValueError("stdoutMinLevel must be smaller or equal to stdoutMaxLevel %s"%self.__stdoutMaxLevel)
            if fileFlag:
                if self.__fileMaxLevel is not None:
                    if level>self.__fileMaxLevel:
                        raise ValueError("fileMinLevel must be smaller or equal to fileMaxLevel %s"%self.__fileMaxLevel)
            if sinks:
                for sinkName in sinks:
                    sinkObj = self.__sinks[sinkName]
                    if sinkObj.maxLevel is not None and level > sinkObj.maxLevel:
                        raise ValueError(
                            "minLevel %s exceeds maxLevel %s for sink '%s'"
                            % (level, sinkObj.maxLevel, sinkName))
        # set flags
        if stdoutFlag:
            self.__stdoutMinLevel = level
            self.__update_stdout_flags()   # triggers rebuild internally
        if fileFlag:
            self.__fileMinLevel = level
            self.__update_file_flags()     # triggers rebuild internally
        if sinks:
            for sinkName in sinks:
                self.__sinks[sinkName].minLevel = level
            # always rebuild after user-sink mutation so the active-sink
            # cache reflects the new level even when built-ins also rebuilt
            self.__rebuild_active_sinks()

    def set_maximum_level(self, level=0, stdoutFlag=True, fileFlag=True, sinks=None):
        """
        Set the maximum logging level. All levels above the maximum will be ignored at logging.

        :Parameters:
           #. level (None, number, str): The maximum level of logging.
              If None, maximum level checking is left out.
              If str, it must be a defined logtype and therefore the maximum level would be the level of this logtype.
           #. stdoutFlag (boolean): Whether to apply this maximum level to standard output logging.
           #. fileFlag (boolean): Whether to apply this maximum level to file logging.
           #. sinks (None, list): Optional list of user sink names to update.
              Each name must have been registered via add_sink(). When None
              (default) user sinks are left unchanged.

        :Raises:
            #. TypeError: If *stdoutFlag* or *fileFlag* is not a boolean, if *sinks*
               is not iterable or contains non-string entries, or if *level* is not
               a number when given as a numeric type.
            #. ValueError: If *level* is given as a string that is not a defined log
               type, if *level* falls below the current minimum level for a target
               stream, or if a named sink in *sinks* is not registered or is a
               built-in sink.
        """
        # check flags
        if not isinstance(stdoutFlag, bool):
            raise TypeError("stdoutFlag must be boolean")
        if not isinstance(fileFlag, bool):
            raise TypeError("fileFlag must be boolean")
        # validate sinks list
        if sinks is not None:
            if not hasattr(sinks, '__iter__'):
                raise TypeError("sinks must be None or a list of sink names")
            sinks = list(sinks)
            for sinkName in sinks:
                if not isinstance(sinkName, str):
                    raise TypeError("each entry in sinks must be a string sink name")
                if sinkName not in self.__sinks:
                    raise ValueError("sink '%s' is not registered" % sinkName)
                if self.__sinks[sinkName].sinkType != 'user':
                    raise ValueError("sink '%s' is a built-in sink; use stdoutFlag/fileFlag for built-ins" % sinkName)
        if not (stdoutFlag or fileFlag or sinks):
            return
        # check level
        if level is not None:
            if isinstance(level, str):
                level = str(level)
                if level not in self.__logTypeStdoutFlags:
                    raise ValueError("level '%s' given as string, is not defined logType"%level)
                level = self.__logTypeLevels[level]
            if not _is_number(level):
                raise TypeError("level must be a number")
            level = float(level)
            if stdoutFlag:
                if self.__stdoutMinLevel is not None:
                    if level<self.__stdoutMinLevel:
                        raise ValueError("stdoutMaxLevel must be bigger or equal to stdoutMinLevel %s"%self.__stdoutMinLevel)
            if fileFlag:
                if self.__fileMinLevel is not None:
                    if level<self.__fileMinLevel:
                        raise ValueError("fileMaxLevel must be bigger or equal to fileMinLevel %s"%self.__fileMinLevel)
            if sinks:
                for sinkName in sinks:
                    sinkObj = self.__sinks[sinkName]
                    if sinkObj.minLevel is not None and level < sinkObj.minLevel:
                        raise ValueError(
                            "maxLevel %s is below minLevel %s for sink '%s'"
                            % (level, sinkObj.minLevel, sinkName))
        # set flags
        if stdoutFlag:
            self.__stdoutMaxLevel = level
            self.__update_stdout_flags()   # triggers rebuild internally
        if fileFlag:
            self.__fileMaxLevel = level
            self.__update_file_flags()     # triggers rebuild internally
        if sinks:
            for sinkName in sinks:
                self.__sinks[sinkName].maxLevel = level
            self.__rebuild_active_sinks()

    def __update_flags(self):
        self.__update_stdout_flags()
        self.__update_file_flags()

    def __update_stdout_flags(self):
        """Recompute per-logType stdout routing flags from current level bounds."""
        stdoutkeys = list(self.__forcedStdoutLevels)
        for logType, l in self.__logTypeLevels.items():
            if logType not in stdoutkeys:
                minOk = (self.__stdoutMinLevel is None) or (l >= self.__stdoutMinLevel)
                maxOk = (self.__stdoutMaxLevel is None) or (l <= self.__stdoutMaxLevel)
                self.__logTypeStdoutFlags[logType] = minOk and maxOk
        if _SINK_STDOUT in self.__sinks:
            self.__rebuild_active_sinks()

    def __update_file_flags(self):
        """Recompute per-logType file routing flags from current level bounds."""
        filekeys = list(self.__forcedFileLevels)
        for logType, l in self.__logTypeLevels.items():
            if logType not in filekeys:
                minOk = (self.__fileMinLevel is None) or (l >= self.__fileMinLevel)
                maxOk = (self.__fileMaxLevel is None) or (l <= self.__fileMaxLevel)
                self.__logTypeFileFlags[logType] = minOk and maxOk
        if _SINK_FILE in self.__sinks:
            self.__rebuild_active_sinks()

    def __rebuild_active_sinks(self):
        """Rebuild the per-logType active sink cache.

        Called once after any configuration change that affects routing:
        add_sink(), remove_sink(), set_log_to_stdout_flag(),
        set_minimum_level(), set_log_type_stdout_flag(), and so on.

        After this runs, ``__activeSinks[logType]`` holds exactly the
        _Sink objects that will receive a message of that type. The
        dispatch loop in log() and force_log() reads this list directly
        -- no per-call filtering is needed.

        Key invariant: for the built-in sinks (_SINK_STDOUT and
        _SINK_FILE) the sink.logTypeFlags dict is kept current by
        __update_stdout_flags() and __update_file_flags() respectively.
        Those methods already fold minLevel/maxLevel constraints into
        the flags, so this method only needs to read enabled + flags.
        For user-added sinks the same invariant is maintained by
        add_sink() and set_log_type_sink_flag().
        """
        result = {}
        for logType in self.__logTypeNames:
            activeSinks = []
            level = self.__logTypeLevels.get(logType)
            for sink in self.__sinks.values():
                if not sink.enabled:
                    continue
                if not sink.logTypeFlags.get(logType, sink.defaultFlag):
                    continue
                # user sinks carry their own minLevel/maxLevel that are
                # not pre-baked into logTypeFlags — apply them here
                if sink.sinkType == 'user' and level is not None:
                    if sink.minLevel is not None and level < sink.minLevel:
                        continue
                    if sink.maxLevel is not None and level > sink.maxLevel:
                        continue
                activeSinks.append(sink)
            result[logType] = activeSinks
        self.__activeSinks = result

    def __dispatch_sinks_sync(self, sinks, record):
        """Give a record to a list of sinks, on this thread, or on the private queue of a threaded sink.

        Called by both log() on the synchronous path and __enqueue_worker()
        inside the background thread. A threaded sink gets the record pushed onto its
        own private queue (never blocks -- its dedicated worker thread does the actual
        write), any other sink renders and writes it right here. A Sink never raises, so one
        broken sink cannot stop the others.

        :Parameters:
            #. sinks (list): List of _Sink objects to dispatch to.
            #. record (None, LogRecord): The record. None when a record processor failed,
               nothing is delivered then.
        """
        if record is None:
            return
        refusal = None
        for sink in sinks:
            if sink.threaded:
                try:
                    sink.enqueue(record)
                except QueueFull as error:
                    # The other sinks still get the record, the caller is told after them
                    if refusal is None:
                        refusal = error
            else:
                sink.handler.emit(record)
        if refusal is not None:
            raise refusal

    def add_sink(self, name, handler, enabled=True,
                 minLevel=None, maxLevel=None, logTypeFlags=None,
                 defaultFlag=True, threaded=False, threadQueueSize=1000, recordFilter=None,
                 threadQueuePolicy='drop_oldest', threadBlockTimeout=None, spool=None):
        """Add a user-supplied output sink to the logger.

        The sink receives every log record whose type passes the routing
        rules (enabled flag, per-type flags, and optional level bounds).

        A handler that is a :class:`pysimplelog.sinks.Sink` object receives the
        structured :class:`pysimplelog.record.LogRecord` and renders it with its own
        formatter. The logger closes such a sink when it is removed and at exit.

        Any other handler, a file-like object with a ``write(str)`` method, is wrapped in a
        :class:`pysimplelog.sinks.StreamSink` that writes the readable text of every record,
        the same text as the log file, without colour codes. The caller
        owns the handler's lifecycle -- the logger never closes it, it only flushes it.

        :Parameters:
            #. name (str): Unique string key for this sink. Must not
               clash with any existing name or reserved integer keys.
            #. handler (Sink, file-like): A Sink object, or any object with a write(str)
               method. A file-like object is flushed after every record when
               the logger's flush setting is not none and it has a flush() method.
            #. enabled (bool): Master switch for this sink. Default True.
            #. minLevel (number, None): Records whose level is strictly
               below this value are suppressed. None means no floor.
            #. maxLevel (number, None): Records whose level is strictly
               above this value are suppressed. None means no ceiling.
            #. logTypeFlags (dict, None): Per-type override map
               {logType (str): bool}. Missing keys fall back to
               *defaultFlag*. None means every type falls back to
               *defaultFlag*.
            #. defaultFlag (bool): Fallback enabled-state for any
               logType not listed in logTypeFlags. True (default) is an
               opt-out sink -- it receives every type, including ones
               added later via add_log_type(), unless you explicitly
               turn one off. False is an opt-in sink -- it receives
               nothing unless a type is explicitly listed as True,
               which also means it stays silent for any type added
               later until you list it too.
            #. threaded (bool): When True, this sink gets its own
               private queue and dedicated worker thread -- dispatch
               only ever enqueues onto it and returns immediately, so
               slow or unreliable I/O in this one sink can never stall
               any other sink or pysimplelog's own file/stdout logging.
               Default False. Turn this on for sinks that do blocking
               work (network calls, slow disks, ...); leave it off for
               fast, simple, in-memory sinks where the extra thread
               would just be overhead.
            #. threadQueueSize (int): Bounded capacity for the private
               queue when *threaded* is True. Ignored otherwise.
            #. threadQueuePolicy (str): What the private queue does with a record when it is full:
               ``'block'`` waits for a free place, ``'drop_newest'`` discards the new record,
               ``'drop_oldest'`` (the default) discards the record that has waited longest, and ``'reject'``
               makes the log call raise ``pysimplelog.queues.QueueFull`` after the other sinks have the record.
               Every discarded or refused record is counted, see :meth:`sink_stats`. Ignored when not threaded.
            #. threadBlockTimeout (None, number): Seconds the ``'block'`` policy waits for a free place. After that the
               new record is dropped and counted. None waits as long as it takes. Ignored when not threaded.
            #. recordFilter (callable, None): ``f(record) -> bool`` that decides which
               records this sink receives, after the routing by level and log type. None
               means all of them. See :meth:`set_sink_filter`.
            #. spool (SpoolConfig, dict, None): The settings that keep the records of this sink on disk until the sink
               has delivered them, see :class:`pysimplelog.spool.SpoolConfig`. A dictionary with the same names is
               accepted. None, the default, keeps nothing: the sink delivers what it gets as fast as it can, and what is
               waiting in memory is lost with the process.

               A spool needs ``threaded=True`` and a :class:`pysimplelog.sinks.Sink` object that writes to something
               outside this process and says where it sends, or a ``target`` in the settings. The record is written to
               the spool in the thread that logs it, which costs the caller about 30 microseconds more than a threaded
               sink without a spool, and up to about 90 while the worker delivers at the same time (measured with
               ``flush='flush'`` on one machine, treat it as an order of magnitude), more with ``fsync`` or ``fullsync``.
               Delivery is at-least-once: after a crash a few records can be sent twice, and
               each carries the same ``event_id`` field each time so a receiver can tell.
               *threadQueueSize* is then the size of the queue of hints, and *threadQueuePolicy* and *threadBlockTimeout*
               are ignored: a hint that is dropped loses no record, the worker finds it on disk.

        :Raises:
            #. TypeError: If *name* is not a string, if *handler* has no ``write()``
               method, if *enabled* is not a boolean, if *minLevel* or *maxLevel* is
               not a number, if *logTypeFlags* is not a dict with string keys and
               boolean values, if *defaultFlag* or *threaded* is not a boolean, or
               if *threadQueueSize* is not a positive integer.
            #. ValueError: If *threadQueuePolicy* is not one of the four policies, or *threadBlockTimeout* is
               not positive.
            #. ValueError: If *name* is empty or already registered as a sink.
            #. TypeError, ValueError: If *spool* is wrong, if the handler cannot be spooled, or if *threaded* is False
               with a spool. These are raised here, when the sink is added, never while logging.
        """
        if not isinstance(name, str):
            raise TypeError("sink name must be a non-empty string")
        if not len(name):
            raise ValueError("sink name must be non-empty")
        if name in self.__sinks:
            raise ValueError("sink '%s' is already registered -- "
                             "call remove_sink() first" % name)
        if not hasattr(handler, 'write'):
            raise TypeError("handler must expose a write() method")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        if minLevel is not None and not _is_number(minLevel):
            raise TypeError("minLevel must be a number or None")
        if maxLevel is not None and not _is_number(maxLevel):
            raise TypeError("maxLevel must be a number or None")
        if not isinstance(defaultFlag, bool):
            raise TypeError("defaultFlag must be a boolean")
        if recordFilter is not None and not callable(recordFilter):
            raise TypeError("recordFilter must be callable or None")
        if not isinstance(threaded, bool):
            raise TypeError("threaded must be a boolean")
        if not isinstance(threadQueueSize, int) or isinstance(threadQueueSize, bool) or threadQueueSize <= 0:
            raise TypeError("threadQueueSize must be a positive integer")
        validate_queue_policy(threadQueuePolicy)
        if threadBlockTimeout is not None:
            if not _is_number(threadBlockTimeout):
                raise TypeError("threadBlockTimeout must be a positive number or None")
            if float(threadBlockTimeout) <= 0:
                raise ValueError("threadBlockTimeout must be positive, got %s" % threadBlockTimeout)
        if logTypeFlags is not None:
            if not isinstance(logTypeFlags, dict):
                raise TypeError("logTypeFlags must be a dict or None")
            for k, v in logTypeFlags.items():
                if not isinstance(k, str):
                    raise TypeError("logTypeFlags keys must be strings")
                if not isinstance(v, bool):
                    raise TypeError("logTypeFlags values must be booleans")
        isWrapped = not isinstance(handler, Sink)
        if isWrapped:
            handler = StreamSink(handler, formatter='text', flush=self.__plain_flush_mode(handler))
        spoolConfig = SpoolConfig.coerce(spool)
        durable = None
        if spoolConfig is not None:
            if not threaded:
                raise ValueError("a spool needs threaded=True: the records are delivered by the thread of the sink")
            if isWrapped:
                raise TypeError("a spool needs a Sink object, a file-like object cannot be kept for later")
            durable = DurableDelivery(handler, spoolConfig, resolve_target_id(handler, spoolConfig), threadQueueSize)
        self.__sinks[name] = _Sink(
            handler      = handler,
            enabled      = enabled,
            logTypeFlags = dict(logTypeFlags) if logTypeFlags is not None else {},
            minLevel     = float(minLevel) if minLevel is not None else None,
            maxLevel     = float(maxLevel) if maxLevel is not None else None,
            sinkType     = 'user',
            defaultFlag  = defaultFlag,
            threaded     = threaded,
            threadQueueSize = threadQueueSize,
            recordFilter = recordFilter,
            isWrapped    = isWrapped,
            threadQueuePolicy  = threadQueuePolicy,
            threadBlockTimeout = threadBlockTimeout,
            durable      = durable,
        )
        self.__update_sink_filter_flag()
        self.__update_trace_flag()
        if handler.captureTrace and not trace_api_available():
            sys.stderr.write(f"pysimplelog WARNING: sink {name!r} asks for trace identifiers but the OpenTelemetry API is not "
                             "installed, its records go without them. Install the package opentelemetry-api\n")
        self.__rebuild_active_sinks()

    def remove_sink(self, name, timeout=5.0):
        """Remove a user-added sink by its registered name.

        If the sink is threaded, its private worker thread is drained
        (up to *timeout* seconds) and stopped here -- no thread is ever
        left running after its sink is gone.

        :Parameters:
            #. name (str): The key used when the sink was registered
               with add_sink().
            #. timeout (float): Seconds to wait for a threaded sink's
               private queue to drain before stopping its thread anyway.
               Ignored for non-threaded sinks.

        :Raises:
            #. TypeError: If *name* is not a string.
            #. ValueError: If *name* is not currently registered as a sink.
        """
        if not isinstance(name, str):
            raise TypeError("sink name must be a string")
        if name not in self.__sinks:
            raise ValueError("sink '%s' is not registered" % name)
        sink = self.__sinks.pop(name)
        self.__update_sink_filter_flag()
        self.__update_trace_flag()
        self.__rebuild_active_sinks()
        sink.release(timeout=timeout)

    def clear_sinks(self, timeout=5.0):
        """Remove all user-added sinks.

        The two built-in sinks (_SINK_STDOUT and _SINK_FILE) are
        always preserved. Any threaded sink among them has its private
        worker thread drained (up to *timeout* seconds) and stopped
        here. This is a no-op if no user sinks are registered.

        :Parameters:
            #. timeout (float): Seconds to wait for each threaded sink's
               private queue to drain before stopping its thread anyway.
        """
        userKeys = [k for k in self.__sinks if isinstance(k, str)]
        removedSinks = [self.__sinks.pop(k) for k in userKeys]
        if userKeys:
            self.__update_sink_filter_flag()
            self.__update_trace_flag()
            self.__rebuild_active_sinks()
        for sink in removedSinks:
            sink.release(timeout=timeout)

    def force_log_type_stdout_flag(self, logType, flag):
        """
        Force a logtype standard output logging flag despite minimum and maximum logging level boundaries.

        :Parameters:
           #. logType (string): A defined logging type.
           #. flag (None, boolean): The standard output logging flag.
              If None, logtype existing forced flag is released.

        :Raises:
            #. ValueError: If *logType* is not a defined log type.
            #. TypeError: If *flag* is not a boolean or None.
        """
        if logType not in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' not defined" %logType)
        if flag is None:
            self.__forcedStdoutLevels.pop(logType, None)
            self.__update_stdout_flags()
        else:
            if not isinstance(flag, bool):
                raise TypeError("flag must be boolean")
            self.__logTypeStdoutFlags[logType] = flag
            self.__forcedStdoutLevels[logType] = flag
            if _SINK_STDOUT in self.__sinks:
                self.__rebuild_active_sinks()

    def force_log_type_file_flag(self, logType, flag):
        """
        Force a logtype file logging flag despite minimum and maximum logging level boundaries.

        :Parameters:
           #. logType (string): A defined logging type.
           #. flag (None, boolean): The file logging flag.
              If None, logtype existing forced flag is released.

        :Raises:
            #. ValueError: If *logType* is not a defined log type.
            #. TypeError: If *flag* is not a boolean or None.
        """
        if logType not in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' not defined" %logType)
        if flag is None:
            self.__forcedFileLevels.pop(logType, None)
            self.__update_file_flags()
        else:
            if not isinstance(flag, bool):
                raise TypeError("flag must be boolean")
            self.__logTypeFileFlags[logType] = flag
            self.__forcedFileLevels[logType] = flag
            if _SINK_FILE in self.__sinks:
                self.__rebuild_active_sinks()

    def force_log_type_flags(self, logType, stdoutFlag, fileFlag):
        """
        Force a logtype logging flags.

        :Parameters:
           #. logType (string): A defined logging type.
           #. stdoutFlag (None, boolean): The standard output logging flag.
              If None, logtype stdoutFlag forcing is released.
           #. fileFlag (None, boolean): The file logging flag.
              If None, logtype fileFlag forcing is released.

        :Raises:
            #. ValueError: If *logType* is not a defined log type.
            #. TypeError: If *stdoutFlag* or *fileFlag* is not a boolean or None.
        """
        self.force_log_type_stdout_flag(logType, stdoutFlag)
        self.force_log_type_file_flag(logType, fileFlag)

    def set_log_type_name(self, logType, name):
        """
        Set a logtype name.

        :Parameters:
           #. logType (string): A defined logging type.
           #. name (string): The logtype new name.

        :Raises:
            #. ValueError: If *logType* is not a defined log type.
            #. TypeError: If *name* is not a string.
        """
        if logType not in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' not defined" %logType)
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        name = str(name)
        self.__logTypeNames[logType] = name

    def set_log_type_level(self, logType, level):
        """
        Set a logtype logging level.

        :Parameters:
           #. logType (string): A defined logging type.
           #. level (number): The level of logging.

        :Raises:
            #. ValueError: If *logType* is not a defined log type.
            #. TypeError: If *level* is not a number.
        """
        if logType not in self.__logTypeNames:
            raise ValueError("logType '%s' not defined" % logType)
        if not _is_number(level):
            raise TypeError("level must be a number")
        self.__logTypeLevels[logType] = float(level)

    def remove_log_type(self, logType, _assert=False):
        """
        Remove a logtype.

        :Parameters:
           #. logType (string): The logtype.
           #. _assert (boolean): Raise a ValueError if logType is not defined.

        :Raises:
            #. ValueError: If *_assert* is True and *logType* is not a defined log type.
        """
        # check logType
        if _assert:
            if logType not in self.__logTypeStdoutFlags:
                raise ValueError("logType '%s' is not defined" %logType)
        # remove logType
        self.__logTypeColor.pop(logType, None)
        self.__logTypeHighlight.pop(logType, None)
        self.__logTypeAttributes.pop(logType, None)
        self.__logTypeNames.pop(logType, None)
        self.__logTypeLevels.pop(logType, None)
        self.__logTypeFormat.pop(logType, None)
        self.__logTypeStdoutFlags.pop(logType, None)
        self.__logTypeFileFlags.pop(logType, None)
        self.__forcedStdoutLevels.pop(logType, None)
        self.__forcedFileLevels.pop(logType, None)
        if _SINK_STDOUT in self.__sinks:
            self.__rebuild_active_sinks()

    def add_log_type(self, logType, name=None, level=0, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None):
        """
        Add a new logtype.

        :Parameters:
           #. logType (string): The logtype.
           #. name (None, string): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (None, boolean): Force standard output logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. fileFlag (None, boolean): Force file logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. color (None, string): The logging text color. The defined colors are:\n
              black , red , green , orange , blue , magenta , cyan , grey , dark grey ,
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, string): The logging text highlight color. The defined highlights are:\n
              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, string): The logging text attribute. The defined attributes are:\n
              bold , underline , blink , invisible , strike through

        **Note:** *logging colour, highlight, and attributes are not supported on all stream types.*

        :Raises:
            #. TypeError: If *logType* is not a string, if *level* is not a number,
               or if *stdoutFlag* or *fileFlag* is not a boolean.
            #. ValueError: If *logType* is already defined, or if *color*, *highlight*,
               or an item in *attributes* is not a recognised formatting token.
        """
        # check logType
        if not isinstance(logType, str):
            raise TypeError("logType must be a string")
        if logType in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' already defined" %logType)
        logType = str(logType)
        # set log type
        self.__set_log_type(logType=logType, name=name, level=level,
                            stdoutFlag=stdoutFlag, fileFlag=fileFlag,
                            color=color, highlight=highlight, attributes=attributes)


    def __set_log_type(self, logType, name, level, stdoutFlag, fileFlag, color, highlight, attributes):
        # check name
        if name is None:
            name = logType
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        name = str(name)
        # check level
        if not _is_number(level):
            raise TypeError("level must be a number")
        level = float(level)
        # check color
        if color is not None:
            if color not in self.__stdoutFontFormat["color"]:
                raise ValueError("color %s not known"%str(color))
        # check highlight
        if highlight is not None:
            if highlight not in self.__stdoutFontFormat["highlight"]:
                raise ValueError("highlight %s not known"%str(highlight))
        # check attributes
        if attributes is not None:
            for attr in attributes:
                if attr not in self.__stdoutFontFormat["attributes"]:
                    raise ValueError("attribute %s not known"%str(attr))
        # check flags
        if stdoutFlag is not None:
            if not isinstance(stdoutFlag, bool):
                raise TypeError("stdoutFlag must be boolean")
        if fileFlag is not None:
            if not isinstance(fileFlag, bool):
                raise TypeError("fileFlag must be boolean")
        # set wrapFancy
        wrapFancy=["",""]
        if color is not None:
            code = self.__stdoutFontFormat["color"][color]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if highlight is not None:
            code = self.__stdoutFontFormat["highlight"][highlight]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if attributes is None:
            attributes = []
        elif isinstance(attributes, str):
            attributes = [str(attributes)]
        for attr in attributes:
            code = self.__stdoutFontFormat["attributes"][attr]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if len(wrapFancy[0]):
            wrapFancy = ["\033["+self.__stdoutFontFormat["reset"]+wrapFancy[0]+"m" , "\033["+self.__stdoutFontFormat["reset"]+"m" ]
        # add logType
        self.__logTypeColor[logType]       = color
        self.__logTypeHighlight[logType]   = highlight
        self.__logTypeAttributes[logType]  = attributes
        self.__logTypeNames[logType]       = name
        self.__logTypeLevels[logType]      = level
        self.__logTypeFormat[logType]      = wrapFancy
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        if stdoutFlag is not None:
            self.__forcedStdoutLevels[logType] = stdoutFlag
        else:
            self.__forcedStdoutLevels.pop(logType, None)
            self.__update_stdout_flags()
        self.__logTypeFileFlags[logType] = fileFlag
        if fileFlag is not None:
            self.__forcedFileLevels[logType] = fileFlag
        else:
            self.__forcedFileLevels.pop(logType, None)
            self.__update_file_flags()
        # ensure cache is fresh for forced-flag paths that skip __update_*
        if _SINK_STDOUT in self.__sinks:
            self.__rebuild_active_sinks()

    def update_log_type(self, logType, name=None, level=None, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None):
        """
        Update a logtype.

        :Parameters:
           #. logType (string): The logtype.
           #. name (None, string): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (None, boolean): Force standard output logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. fileFlag (None, boolean): Force file logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. color (None, string): The logging text color. The defined colors are:\n
              black , red , green , orange , blue , magenta , cyan , grey , dark grey ,
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, string): The logging text highlight color. The defined highlights are:\n
              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, string): The logging text attribute. The defined attributes are:\n
              bold , underline , blink , invisible , strike through

        **Note:** *logging colour, highlight, and attributes are not supported on all stream types.*

        :Raises:
            #. TypeError: If *level* is not a number, or if *stdoutFlag* or
               *fileFlag* is not a boolean.
            #. ValueError: If *logType* is not a defined log type, or if *color*,
               *highlight*, or an item in *attributes* is not a recognised formatting token.
        """
        # check logType
        if logType not in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' is not defined" %logType)
        # get None updates
        if name is None:       name       = self.__logTypeNames[logType]
        if level is None:      level      = self.__logTypeLevels[logType]
        if stdoutFlag is None: stdoutFlag = self.__logTypeStdoutFlags[logType]
        if fileFlag is None:   fileFlag   = self.__logTypeFileFlags[logType]
        if color is None:      color      = self.__logTypeColor[logType]
        if highlight is None:  highlight  = self.__logTypeHighlight[logType]
        if attributes is None: attributes = self.__logTypeAttributes[logType]
        # update log type
        self.__set_log_type(logType=logType, name=name, level=level,
                            stdoutFlag=stdoutFlag, fileFlag=fileFlag,
                            color=color, highlight=highlight, attributes=attributes)

    def _resolve_log_type(self, logType, message):
        """
        Applies the unknown log type policy and returns the log type and message to log.

        :Parameters:
            #. logType (string): The log type given by the caller.
            #. message (string): The message given by the caller.

        :Returns:
            #. logType (string): *logType*, or the fallback type when it is undefined and the policy is 'fallback'.
            #. message (string): *message*, with the unknown type named in front when the fallback is used.

        :Raises:
            #. ValueError: If the policy is 'fallback' and the fallback type is itself undefined.
        """
        if self.__unknownLogTypePolicy == 'raise' or logType in self.__logTypeNames:
            return logType, message
        if self.__fallbackLogType not in self.__logTypeNames:
            raise ValueError("fallbackLogType %r is not a defined log type" % (self.__fallbackLogType,))
        return self.__fallbackLogType, "Unknown log type %r: %s" % (logType, message)

    def _prepare_message(self, message):
        """
        Sanitizes a message and cuts it to the maximum message size.

        :Parameters:
            #. message (object): The message given by the caller.

        :Returns:
            #. message (str): The message without control characters, cut when it is too long.
        """
        message = _sanitize_message(message)
        if self.__maxMessageSize is not None and len(message) > self.__maxMessageSize:
            message = message[:self.__maxMessageSize] + '[truncated]'
        return message

    def _build_record(self, logType, message, fields, exc_info, caller, origin=None):
        """
        Builds the structured record that every sink receives.

        :Parameters:
            #. logType (str): A registered log type name.
            #. message (object): The message given by the caller.
            #. fields (dict): The named values given by the caller. The dictionary is used as it is, so it must be
               one the caller does not use again. A field named ``data`` is cut to the maximum data size when one is set.
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see Logger.log().
            #. caller (CallerInfo, None): Where the log call was made, None when callerInfo is off.
            #. origin (None, tuple): ``(timestamp, processId, threadId, threadName)`` of a record that another
               logging system made. None means the moment, process and thread of this call.

        :Returns:
            #. record (LogRecord): The record for this log call.
        """
        if 'data' in fields and fields['data'] is None:
            # a caller that forwards data=None means there is no data
            del fields['data']
        if self.__maxDataSize is not None and 'data' in fields:
            dataText = '%s' % (fields['data'],)
            if len(dataText) > self.__maxDataSize:
                fields['data'] = dataText[:self.__maxDataSize] + '[truncated]'
        exception = None if exc_info is None else _exception_info(exc_info)
        if origin is None:
            if self.__timezone is not None:
                timestamp = datetime.now(self.__timezone)
            else:
                timestamp = _now_local()
            processId, threadId, threadName = os.getpid(), threading.get_ident(), threading.current_thread().name
        else:
            timestamp, processId, threadId, threadName = origin
        context = CURRENT_CONTEXT.get()
        # Read here, on the calling thread: a sink that runs later, on another thread, cannot know the active span
        trace = read_current_trace() if self.__capturesTrace else None
        return LogRecord.create(timestamp, self.__logTypeNames[logType], logType, self.__logTypeLevels.get(logType),
                                self.__name, self._prepare_message(message), processId, threadId, threadName,
                                fields, context if len(context) > 0 else None, exception, caller, trace)

    def get_timestamp(self, format='%Y-%m-%d %H:%M:%S'):
        """
        Returns the current date and time in the timezone of the logger as text.

        :Parameters:
            #. format (str): A strftime-compatible format string.

        :Returns:
            #. timestamp (str): The formatted current date and time.
        """
        return datetime.strftime(datetime.now(self.__timezone), format)

    def _process_record(self, record):
        """
        Runs the record processors over a record.

        :Parameters:
            #. record (LogRecord): The record built for this log call.

        :Returns:
            #. record (LogRecord, None): The record after every processor, or None when a processor raised or
               returned something that is not a record.
        """
        for processor in self.__processors:
            try:
                result = processor(record)
                if not isinstance(result, LogRecord):
                    raise TypeError("a record processor must return a LogRecord, got %s" % type(result).__name__)
            except Exception as processorError:
                with self.__processorLock:
                    self.__processorFailures += 1
                    isFirstFailure = id(processor) not in self.__failedProcessors
                    self.__failedProcessors.add(id(processor))
                if isFirstFailure:
                    sys.stderr.write('pysimplelog WARNING: processor %r raised %s: %s, the record is dropped '
                                     'when it fails\n' % (processor, type(processorError).__name__, processorError))
                return None
            record = result
        return record

    def _filter_keeps(self, keep, record):
        """
        Runs one filter function over a record.

        :Parameters:
            #. keep (callable): The filter function ``f(record) -> bool``.
            #. record (LogRecord): The record to decide on.

        :Returns:
            #. isKept (bool): The answer of the function. True when the function raised or answered something
               that is not True or False, the failure is counted and warned about once for each function.
        """
        try:
            result = keep(record)
            if result is not True and result is not False:
                raise TypeError("a filter must return True or False, got %s" % type(result).__name__)
        except Exception as filterError:
            with self.__filterLock:
                self.__filterFailures += 1
                isFirstFailure = id(keep) not in self.__failedFilters
                self.__failedFilters.add(id(keep))
            if isFirstFailure:
                sys.stderr.write('pysimplelog WARNING: filter %r raised %s: %s, the record is kept when it fails\n'
                                 % (keep, type(filterError).__name__, filterError))
            return True
        return result

    def _passes_filters(self, record):
        """
        Runs the filters over a record.

        :Parameters:
            #. record (LogRecord): The record, after the record processors.

        :Returns:
            #. passes (bool): False when a filter dropped the record, True otherwise.
        """
        for keep in self.__filters:
            if not self._filter_keeps(keep, record):
                with self.__filterLock:
                    self.__filteredRecords += 1
                return False
        return True

    def _sinks_accepting(self, record, sinks):
        """
        Keeps the sinks whose own filter accepts a record.

        :Parameters:
            #. record (LogRecord): The record, after the processors and the filters.
            #. sinks (list): The _Sink objects that passed the routing.

        :Returns:
            #. accepted (list): The sinks without a filter, and those whose filter returned True.
        """
        accepted = []
        for sink in sinks:
            keep = sink.recordFilter
            if keep is None or self._filter_keeps(keep, record):
                accepted.append(sink)
            else:
                with self.__filterLock:
                    sink.filteredCount += 1
        return accepted

    def __enqueue_worker(self):
        """Background thread: drain the log queue and perform all I/O.

        Items are one of two formats:
          - 2-tuple (sinks, record) from normal log() calls;
            sinks is a snapshot list of _Sink objects from __activeSinks.
          - 3-tuple (toStdout, toFile, record) from force_log();
            toStdout/toFile are caller-supplied booleans that bypass routing.
        The sentinel _QUEUE_STOP signals clean shutdown.
        task_done() is called after every item so flush() can join().
        """
        while True:
            item = self.__logQueue.get()
            try:
                if item is _QUEUE_STOP:
                    return
                self.__process_item(item)
            finally:
                self.__logQueue.task_done()

    def __process_item(self, item):
        """
        Delivers one item of the queue of the enqueue mode.

        :Parameters:
            #. item (tuple): ``(sinks, record)`` from a normal log call, or ``(toStdout, toFile, record)`` from force_log().
        """
        if len(item) == 2:
            sinks, record = item
            try:
                self.__dispatch_sinks_sync(sinks, record)
            except QueueFull:
                # A sink refused it, its own queue counted that, and the caller is no longer here to be told
                pass
        else:
            # force_log() path, bypasses routing
            toStdout, toFile, record = item
            if record is not None:
                if toStdout:
                    self.__sinks[_SINK_STDOUT].handler.emit(record)
                if toFile:
                    self.__sinks[_SINK_FILE].handler.emit(record)

    def __put_to_queue(self, item):
        """Put one item on the queue of the enqueue mode, honouring the overflow policy.

        Called by log(), log_external() and force_log() whenever enqueue mode is active.
        The policy is read by the queue on every call, so changes made with
        set_queue_full_policy() take effect immediately.

        :Parameters:
            #. item (tuple): ``(sinks, record)`` from a normal log call, or
               ``(toStdout, toFile, record)`` from force_log().

        In a forked child the worker thread does not exist, so the item is delivered at once by the calling thread.

        :Raises:
            #. QueueFull: If the queue is full and the policy is ``reject``.
        """
        if os.getpid() != self.__ownerPid:
            self.__process_item(item)
            return
        self.__logQueue.put(item)

    def __make_file_sink(self):
        """
        Builds the FileSink of the log file from the current file settings and flush mode.

        :Returns:
            #. sink (FileSink): A sink that writes the readable text of a record to the log files.
        """
        return FileSink(self.__logFileBasename, self.__logFileExtension, formatter=self.__fileFormatter,
                        flush=self.__flushMode, maxSize=self.__logFileMaxSize, roll=self.__logFileRoll,
                        firstNumber=self.__logFileFirstNumber)

    def __plain_flush_mode(self, stream):
        """
        Works out the flush mode of a file-like object added with add_sink().

        :Parameters:
            #. stream (file-like): The object given to add_sink().

        :Returns:
            #. flush (str): ``flush`` when the logger flushes and the object has a flush() method, ``none`` otherwise.
        """
        return 'flush' if self.__flush and hasattr(stream, 'flush') else 'none'

    def __make_console_sink(self):
        """
        Builds the ConsoleSink of the standard output for the current stream and flush flag.

        :Returns:
            #. sink (ConsoleSink): A sink that writes a record with the console formatter, in the colours of its
               log type when that formatter is ``'text'``.
        """
        stream = self.__stdout
        isFlushed = self.__flush and hasattr(stream, 'flush')
        # colour codes would break any other layout, JSON for example, so only the text layout gets them
        decorate = self.__decorate_console if self.__consoleFormatter == 'text' else None
        return ConsoleSink(stream, formatter=self.__consoleFormatter, flush='flush' if isFlushed else 'none',
                           decorate=decorate)

    def __decorate_console(self, text, record):
        """Wraps the text of a record in the colour codes of its log type."""
        fmt = self.__logTypeFormat[record.logType]
        return "%s%s%s" % (fmt[0], text, fmt[1])

    def is_enabled_for_stdout(self, logType):
        """Return True if the given log type is enabled for standard output logging.

        Both the global stdout flag and the per-type stdout flag must be True
        for the log type to produce any stdout output.

        :Parameters:
           #. logType (string): A defined logging type.

        :Returns:
           #. enabled (bool): Whether stdout output is active for this log type.
        """
        return self.__logToStdout and self.__logTypeStdoutFlags[logType]

    def is_enabled_for_file(self, logType):
        """Return True if the given log type is enabled for file logging.

        Both the global file flag and the per-type file flag must be True
        for the log type to produce any file output.

        :Parameters:
           #. logType (string): A defined logging type.

        :Returns:
           #. enabled (bool): Whether file output is active for this log type.
        """
        return self.__logToFile and self.__logTypeFileFlags[logType]

    def is_enabled(self, logType):
        """Return True if logType would write to at least one output stream.

        Combines the stdout and file checks into one call so callers can
        guard expensive message construction without repeating the two-flag
        check themselves::

            if logger.is_enabled('debug'):
                logger.debug(json.dumps(large_object))

        This is the recommended pattern for deferring costly work -- it keeps
        the logger's role purely passive (no callables, no execution) while
        still avoiding unnecessary computation when the level is filtered.

        :Parameters:
            #. logType (string): A defined logging type.

        :Returns:
            #. result (bool): True if at least stdout or file would receive
               a message of this logType, False otherwise.
        """
        # use the pre-computed active-sink cache: covers stdout, file,
        # AND any user-added sinks — a non-empty list means dispatch happens
        return bool(self.__activeSinks.get(logType))


    def log(self, logType, message, *args, exc_info=None, countConstraint=None, **fields):
        """
        Log a message of the specified log type.

        Every other keyword argument is a field of the record: ``logger.info("Order created", order_id=123)``.
        The text layout writes the fields as ``key=value`` after the message, JSON keeps them as they are.
        A field named ``data`` is written on its own line in the text layout, and it is left out when its value is
        None, so a wrapper that forwards ``data=None`` logs no data. The names ``logType``, ``message``,
        ``exc_info`` and ``countConstraint`` belong to this method, so they cannot be field names, and ``fields`` and
        ``tback``, which older versions took as arguments, are rejected.

        Placeholders are filled when the call has positional arguments or fields:
        ``logger.info("User {} logged in", userId)`` and ``logger.info("Order {orderId}", orderId=7)``.
        Nothing is formatted otherwise, so a message with braces is written as it is, and a template that
        does not fit its values is written unchanged: a log call never raises for it. A placeholder cannot
        reach inside a value (``{0.name}`` is refused). The message is rendered before the processors run,
        so ``redact_fields``, which works by name, cannot see a positional value: use ``redact_text`` for
        the text of the message, or pass the secret as a field.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. args (tuple): Positional arguments that fill the ``{}`` and ``{0}`` placeholders of *message*. They are
              text only, they are not stored as fields. Keyword arguments fill ``{name}`` and stay fields.
           #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record. ``True`` records the
              exception being handled, an exception object or a ``sys.exc_info()`` tuple records its type, message and
              traceback, a string is the text of a traceback made elsewhere, and a list of
              ``(filename, lineno, name, line)`` tuples, as ``traceback.extract_stack()`` returns, is formatted
              like a traceback. None records nothing.
           #. countConstraint (None, number): maximum number of time to log
              the given message
           #. fields: The named values of the record, any number of keyword arguments.

        :Returns:
            #. message (string): the logged message

        :Raises:
            #. TypeError: If *message* is callable. Use ``is_enabled(logType)`` to
               guard expensive message construction instead of passing a callable.
        """
        return self._log_call(logType, message, args, fields, exc_info, countConstraint, False, 0)

    def _log_call(self, logType, message, args, fields, exc_info, countConstraint, isLazy, depth):
        """Does the work of :meth:`log` and of the loggers made by :meth:`opt`, see :meth:`log`."""
        # reject callables -- the logger is a passive recorder, not an executor.
        # to defer expensive message construction use is_enabled(logType) instead:
        #   if logger.is_enabled('debug'): logger.debug(expensive_fn())
        if callable(message):
            raise TypeError(
                "log() message must be a string or string-coercible value, "
                "not a callable. To defer expensive message construction "
                "guard the call with is_enabled('%s') instead." % logType
            )
        _check_field_names(fields)
        logType, message = self._resolve_log_type(logType, message)
        # routing comes first: read from the pre-computed active-sink cache (O(1) lookup), the
        # list contains only sinks whose enabled flag and logTypeFlags both pass for this logType.
        # A log type that no sink wants costs nothing more. An unknown log type is not in the
        # cache, it goes on and fails when its record is built, as it always did
        activeSinks = self.__activeSinks.get(logType)
        if activeSinks is not None and len(activeSinks) == 0:
            return message
        if countConstraint is not None:
            self.__logMessagesCounter.setdefault(message, -1)
            self.__logMessagesCounter[message] += 1
            if countConstraint<=self.__logMessagesCounter[message]:
                return message
        # Rendered after the routing check, so a message no sink wants costs nothing
        if isLazy:
            args, fields = _evaluate_lazy(args, fields)
        message = render_message(message, args, fields)
        # build on caller thread so timestamp is captured at call time
        # capture caller frame BEFORE any internal calls so the stack depth
        # is minimal and the user frame is as close to the top as possible
        caller = _get_caller_info(depth) if self.__callerInfo else None
        record = self._build_record(logType, message, fields, exc_info, caller)
        self.__deliver(logType, record, activeSinks)
        # always return logged message
        return message

    def log_external(self, logType, message, *, created, processId, threadId, threadName,
                     caller=None, exc_info=None, fields=None):
        """
        Log what another logging system produced, keeping its time, process, thread and caller.

        The record goes through exactly what a record of :meth:`log` goes through: the routing, the
        processors, the filters and the sinks. It is made for bridges, such as
        :class:`pysimplelog.standard_logging.StandardLoggingHandler`. Unlike :meth:`log`, the fields are
        given as one dictionary, so any name can be a field.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): The message, already formatted.
           #. created (float): The moment of the original record, in seconds since the epoch, as ``time.time()`` gives.
           #. processId (int): Operating system process identifier of the original record.
           #. threadId (int): Identifier of the thread that made the original record.
           #. threadName (str): Name of the thread that made the original record.
           #. caller (None, CallerInfo): Where the original record was made. None leaves it out.
           #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see :meth:`log`.
           #. fields (None, dict): The named values of the record. The dictionary is copied.

        :Returns:
            #. message (string): the logged message
        """
        logType, message = self._resolve_log_type(logType, message)
        activeSinks = self.__activeSinks.get(logType)
        if activeSinks is not None and len(activeSinks) == 0:
            return message
        if self.__timezone is not None:
            timestamp = datetime.fromtimestamp(created, self.__timezone)
        else:
            timestamp = _local_datetime(created)
        record = self._build_record(logType, message, {} if fields is None else dict(fields), exc_info, caller,
                                    (timestamp, processId, threadId, threadName))
        self.__deliver(logType, record, activeSinks)
        return message

    def __deliver(self, logType, record, activeSinks):
        """
        Gives a record to the sinks that want it, after the processors and the filters.

        :Parameters:
            #. logType (string): The log type of the record.
            #. record (LogRecord): The record built for the log call.
            #. activeSinks (list): The _Sink objects that passed the routing for this log type.
        """
        if self.__processors:
            # None when a processor failed: the record is dropped for every sink
            record = self._process_record(record)
        if record is not None:
            if self.__filters and not self._passes_filters(record):
                return
            if self.__hasSinkFilters:
                activeSinks = self._sinks_accepting(record, activeSinks)
                if len(activeSinks) == 0:
                    return
        if self.__enqueue:
            # snapshot so the worker sees a stable list even if config
            # changes between put() and the item being processed
            self.__put_to_queue((list(activeSinks), record))
        else:
            self.__dispatch_sinks_sync(activeSinks, record)
        # keep the record of this call (on caller thread for immediate visibility)
        if record is not None:
            self.__lastRecords[logType] = record
            self.__lastRecord           = record

    def force_log(self, logType, message, *args, exc_info=None, stdout=True, file=True, **fields):
        """
        Force logging a message of a certain logtype whether logtype level is allowed or not.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. args (tuple): Positional arguments that fill the ``{}`` and ``{0}`` placeholders of *message*. They are
              text only, they are not stored as fields. Keyword arguments fill ``{name}`` and stay fields.
           #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see :meth:`log`.
           #. stdout (boolean): Whether to force logging to standard output.
           #. file (boolean): Whether to force logging to file.
           #. fields: The named values of the record, any number of keyword arguments, see :meth:`log`.

        :Returns:
            #. message (string): the logged message

        :Raises:
            #. TypeError: If *message* is callable. Use ``is_enabled(logType)`` to
               guard expensive message construction instead of passing a callable.
        """
        # reject callables — same policy as log()
        if callable(message):
            raise TypeError(
                "force_log() message must be a string or string-coercible value, "
                "not a callable. To defer expensive message construction "
                "guard the call with is_enabled('%s') instead." % logType
            )
        _check_field_names(fields)
        logType, message = self._resolve_log_type(logType, message)
        message = render_message(message, args, fields)
        # build on caller thread so timestamp is captured at call time
        caller = _get_caller_info() if self.__callerInfo else None
        record = self._build_record(logType, message, fields, exc_info, caller)
        if self.__processors:
            record = self._process_record(record)
        if self.__enqueue:
            self.__put_to_queue((stdout, file, record))
        elif record is not None:
            if stdout:
                self.__sinks[_SINK_STDOUT].handler.emit(record)
            if file:
                self.__sinks[_SINK_FILE].handler.emit(record)
        # keep the record of this call (on caller thread for immediate visibility)
        if record is not None:
            self.__lastRecords[logType] = record
            self.__lastRecord           = record
        # always return logged message
        return message

    def opt(self, *, lazy=False, exception=None, depth=0):
        """
        Returns a logger that applies options to the calls made through it.

        .. code-block:: python

            logger.opt(lazy=True).debug("Result: {}", lambda: slow())
            logger.opt(exception=True).error("Payment failed")
            logger.opt(depth=1).info("Done")

        :Parameters:
            #. lazy (boolean): When True, the positional arguments and field values that are callable are called, once,
               in the calling thread, and only when a sink wants the log type. Filters and processors read the
               finished record, so a message they drop has been computed already.
            #. exception (None, bool, BaseException, tuple): The exception to record, as ``exc_info`` of :meth:`log`.
               An ``exc_info`` given to the call wins.
            #. depth (int): How many frames of the program to skip when the caller is looked for, for a wrapper
               around the logger. It only matters when the logger was made with ``callerInfo=True``.

        :Returns:
            #. optLogger (_OptLogger): It has ``log`` and the shortcuts ``info``, ``warn``, ``error``, ``critical`` and ``debug``.

        :Raises:
            #. TypeError: If *lazy* is not a boolean.
            #. ValueError: If *depth* is not a non-negative integer.
        """
        return _OptLogger(self, lazy, exception, depth)

    def catch(self, func=None, logType='error', reraise=False,
              message='An exception was caught'):
        """Decorator and context manager that catches and logs exceptions.

        The exception message and traceback go through the processors like any other record,
        see add_processor().

        Can be used in three ways::

            @logger.catch
            def risky(): ...

            @logger.catch(logType='critical', reraise=True)
            def risky(): ...

            with logger.catch():
                risky_code()

        :Parameters:
            #. func (None, callable): When used as a bare decorator
               (without parentheses) Python passes the decorated
               function here. Leave None when calling with options
               or as a context manager.
            #. logType (string): The log type used when recording
               the exception. Must be a defined log type. Default
               is 'error'.
            #. reraise (boolean): Whether to re-raise the exception
               after logging it. When False the exception is
               suppressed. When True it propagates after logging.
            #. message (string): Prefix text prepended to the
               exception description in the log entry.

        :Returns:
            #. result (_CatchContext): A _CatchContext usable as decorator or context
               manager, or the wrapped callable for bare-decorator use.
        """
        ctx = _CatchContext(self, logType=logType, reraise=reraise, message=message)
        if func is not None:
            return ctx(func)
        return ctx

    def bind(self, **context):
        """Return a _BoundLogger that attaches values to the context of every record it logs.

        The bound logger delegates all I/O to this Logger unchanged.
        It holds no state of its own beyond the context dict and the
        reference to this parent. It is immutable and thread-safe.
        The bound values are written in the ``context`` of the record, apart from its fields.
        The text layout shows them in brackets before the message.

        Typical usage in a web request handler::

            def handle(requestId, user):
                L = logger.bind(requestId=requestId, user=user)
                L.info('started')    # [requestId=x user=y] started
                L.error('failed')    # [requestId=x user=y] failed

        Nested bind() calls merge contexts (right-hand key wins)::

            L2 = L.bind(table='orders')  # adds table to existing context
            L3 = L.bind(requestId='new')  # overrides requestId only

        This Logger is never modified. All bind() calls are additive
        and return new _BoundLogger instances.

        :Parameters:
            #. context (dict): Arbitrary keyword key-value pairs. Keys should be
               valid Python identifiers for readability, but any string
               key is accepted.

        :Returns:
            #. result (_BoundLogger): An immutable context-aware wrapper
            around this Logger.
        """
        return _BoundLogger(self, context)

    def context(self, **values):
        """
        Attach values to every record made inside a ``with`` block, whatever logger makes it.

        This is :func:`pysimplelog.log_context.context`, see it for how the values follow threads and
        asynchronous tasks and how blocks nest.

        :Parameters:
            #. values: The values to attach, any number of keyword arguments.

        :Returns:
            #. scope (ContextScope): The context manager.

        .. code-block:: python

            with logger.context(request_id=request_id, user_id=user_id):
                logger.info("Order created")
        """
        return open_context(**values)

    def flush(self, timeout=5.0):
        """Flush all streams.

        When enqueue mode is active, blocks until all queued log
        records have been written before flushing the streams. Any
        threaded sink's own private queue is drained too (up to
        *timeout* seconds) before its handler is flushed.

        :Parameters:
            #. timeout (float): Seconds to wait for each threaded
               sink's private queue to drain. Ignored for non-threaded sinks.
        """
        if self.__enqueue and self.__logQueue is not None and os.getpid() == self.__ownerPid:
            self.__logQueue.join(timeout)
        # flush every registered sink
        for sink in self.__sinks.values():
            if sink.threaded:
                sink.flush_threaded(timeout=timeout)
            try:
                sink.handler.flush()
            except Exception as flushError:
                sys.stderr.write('pysimplelog WARNING: sink flush failed. Error: %s\n' % flushError)

    def info(self, message, *args, **kwargs):
        """Log at information level (alias for log('info', ...))."""
        return self.log("info", message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """Log at information level (alias for log('info', ...))."""
        return self.log("info", message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """Log at warning level (alias for log('warn', ...))."""
        return self.log("warn", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log at warning level (alias for log('warn', ...))."""
        return self.log("warn", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log at error level (alias for log('error', ...))."""
        return self.log("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log at critical level (alias for log('critical', ...))."""
        return self.log("critical", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Log at debug level (alias for log('debug', ...))."""
        return self.log("debug", message, *args, **kwargs)



class SingleLogger(Logger):
    """Singleton implementation of Logger.

    The first instantiation creates the shared Logger instance and performs
    full initialisation. Every subsequent instantiation with any arguments
    returns that same instance without re-initialising it. This guarantees
    that all modules in an application share one consistent logging
    configuration without passing a logger object around explicitly.

    To customise the logger, subclass SingleLogger and override custom_init()
    rather than __init__:

    .. code-block:: python

        from pysimplelog import SingleLogger as LOG

        class AppLogger(LOG):
            def custom_init(self, *args, **kwargs):
                ## add application-specific log types here
                self.add_log_type("trace", name="TRACE", level=5)

        ## First call — creates and initialises the singleton.
        logger = AppLogger("my-app")
        logger.info("application started")

        ## Second call — returns the existing instance; arguments are ignored.
        sameLogger = AppLogger()
        assert sameLogger is logger
    """
    __thisInstance = None

    def __new__(cls, *args, **kwds):
        """Return the singleton instance, creating it on the first call."""
        if cls.__thisInstance is None:
            cls.__thisInstance = super(SingleLogger, cls).__new__(cls)
            cls.__thisInstance._isInitialized = False
        return cls.__thisInstance

    def __init__(self, *args, **kwargs):
        """Initialise the singleton on the first call; no-op on subsequent calls."""
        if self._isInitialized:
            return
        ## initialize
        super(SingleLogger, self).__init__(*args, **kwargs)
        ## update flag
        self._isInitialized = True



if __name__ == "__main__":
    import time
    logger=Logger("log test")
    logger.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
    logger.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
    logger.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold","blink"])
    print(logger, '\n')
    # print available logs and logging time.
    for logType in logger.logTypes:
        tic = time.time()
        logger.log(logType, "this is '%s' level log message."%logType)
        print("%s seconds\n"%str(time.time()-tic))
