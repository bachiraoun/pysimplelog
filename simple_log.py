"""
The core of pysimplelog: the ``Logger`` class, and ``SingleLogger``, a version of it that every part of a program shares.

Most people never need this module directly. ``from pysimplelog import logger`` gives a ready logger, and
``from pysimplelog import Logger`` makes one with its own settings.

simple_log defines the Logger and SingleLogger classes for multi-sink,
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
import os, sys, copy, re, atexit, threading, traceback, functools, collections, time
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
    Turns a Unix time (seconds since 1970) into a date and time in the time zone of the machine, following the changes of daylight saving time.

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
    """Returns the current date and time in the time zone of the machine."""
    return _local_datetime(time.time())


# structured records and the sinks that receive them
try:
    from .record import LogRecord, ExceptionInfo, CallerInfo
    from .tracing import read_current_trace, trace_api_available
    from .formatters import resolve_formatter, ConsoleFormatter, stream_supports_color, describe_error
    from .message_format import render_message
    from .diagnose import DIAGNOSE_MODES, format_exception_with_values
    from .log_context import CURRENT_CONTEXT, context as open_context
    from .sinks import Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode
    from .sink_options import build_file_sink
    from .environment import ENV_PREFIX, COLOR_MODES, NOT_GIVEN, read_environment
    from .namespaces import is_disabled
    from . import namespaces
    from .traceback_cache import format_exception_text
    from .delivery_guard import mark_delivery_thread
    from .queues import BoundedQueue, QueueFull, validate_queue_policy
    from .forking import register_for_fork_reset
    from .spool import SpoolConfig
    from .durable import DurableDelivery, resolve_target_id
except ImportError:
    from record import LogRecord, ExceptionInfo, CallerInfo
    from tracing import read_current_trace, trace_api_available
    from formatters import resolve_formatter, ConsoleFormatter, stream_supports_color, describe_error
    from message_format import render_message
    from diagnose import DIAGNOSE_MODES, format_exception_with_values
    from log_context import CURRENT_CONTEXT, context as open_context
    from sinks import Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode
    from sink_options import build_file_sink
    from environment import ENV_PREFIX, COLOR_MODES, NOT_GIVEN, read_environment
    from namespaces import is_disabled
    import namespaces
    from traceback_cache import format_exception_text
    from delivery_guard import mark_delivery_thread
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
    """Says whether a queue item is a special marker (the one that stops a worker, or a flush) and not a record."""
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
    """Says whether a value is a number, or text that can be read as one such as ``'3.5'``."""
    if isinstance(number, (int, float, complex)):
        return True
    try:
        float(number)
    except Exception:
        return False
    else:
        return True

def _normalize_path(path):
    """Turns the backslashes of a Windows file path into forward slashes, so one path works on every system."""
    if os.sep=='\\':
        path = re.sub(r'([\\])\1+', r'\1', path).replace('\\','\\\\')
    return path


# Resolved once at import time so frame-walking comparisons skip string work.
_THIS_FILE = os.path.abspath(__file__)


def _get_caller_info(depth=0):
    """
    Finds which file, line and function made the log call, by looking up the call stack and skipping the logger's own code.

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
    Calls a value if it is a function and returns the answer, and returns any other value unchanged. It is how ``opt(lazy=True)`` runs its functions.

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
    Runs every function among the values of a log call, once each, and returns the results. It only runs when an output really wants the record.

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
    Writes a caller as the short tag ``file:line in function`` that goes before the message.

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
    Refuses the field names ``fields`` and ``tback``, which older versions used as arguments, so a call written for them cannot silently log the wrong thing.

    :Parameters:
        #. fields (dict): The keyword arguments of a log call that are not arguments of the method.

    :Raises:
        #. TypeError: If a field is named ``fields`` or ``tback``. They would be stored as ordinary fields and
           the call would silently log something other than what its author meant.
    """
    if fields and ('fields' in fields or 'tback' in fields):
        raise TypeError("'fields' and 'tback' are not arguments any more: pass the fields as keyword "
                        "arguments, and the exception as exc_info")


def _exception_info(excInfo, diagnose=False, diagnoseRedact=()):
    """
    Turns what you give as ``exc_info`` (``True``, an exception, a tuple or text) into the exception part of a record: its type, its message and its traceback text.

    :Parameters:
        #. excInfo (None, bool, BaseException, tuple, str, list): ``True`` means the exception being handled
           right now. An exception object gives its own type, message and traceback. A tuple
           ``(type, value, traceback)``, as ``sys.exc_info()`` returns, does the same. A string is the text of a
           traceback made elsewhere. A list of ``(filename, lineno, name, line)`` tuples, as
           ``traceback.extract_stack()`` returns, is formatted like a standard Python traceback.
        #. diagnose (boolean, str): False, 'summary' or 'full', see Logger.set_diagnose().
        #. diagnoseRedact (tuple): Sensitive variable names added to the default ones.

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
            if diagnose is False:
                text = format_exception_text(excType, excValue, excTraceback)
            else:
                text = format_exception_with_values(excType, excValue, excTraceback, diagnose, diagnoseRedact)
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
    """
    Removes colour codes and other control characters from a message so that it cannot repaint a terminal or hide text. Line breaks are kept.

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
    """
    The logger's record of one output: the sink object plus its switches, levels, filter and queue. You never make one, ``add()`` does.

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
        """
        Puts a record on the private queue of a threaded output, or does what the full-queue policy says when there is no room. It is only used for threaded outputs.

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
        """The loop of the thread that writes for a threaded output: take a record from its queue, write it, and repeat until told to stop. A failing output cannot crash the thread."""
        mark_delivery_thread()
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
                    ', record dropped. Error: %s\n' % describe_error(sinkError)
                )
            finally:
                self._queue.task_done()

    def _worker_of_groups(self):
        """The same loop for an output that sends records in groups: collect a group, send it in one call, and repeat. A group ends when it is full, when its time is up, or at a marker."""
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
                            ', %d records dropped. Error: %s\n' % (len(records), describe_error(sinkError))
                        )
            finally:
                for _ in range(len(records) + (0 if marker is None else 1)):
                    self._queue.task_done()
            if marker is _QUEUE_STOP:
                return

    def flush_threaded(self, timeout=5.0):
        """
        Waits, up to *timeout* seconds, until the output's queue is empty and its last record is written. Returns True if it finished.

        Waits for both the queue to empty AND the item currently being
        dispatched (if any) to finish -- a queue that looks empty while
        the worker is still mid-dispatch on the last item is not actually
        drained yet. No-op when threaded is False.

        :Parameters:
            #. timeout (float): Seconds to wait at most.

        :Returns:
            #. isDrained (bool): True when nothing is waiting any more, False when the timeout ended first.
        """
        if not self.threaded:
            return True
        if self.durable is not None:
            return self.durable.flush(timeout)
        if os.getpid() != self._pid:
            # The worker belongs to the parent, this process delivered its records itself
            return True
        if self.handler.batchSize > 1:
            # The worker may be waiting for its group to fill, this makes it send what it has now
            self._queue.put_last(_QUEUE_FLUSH)
        return self._queue.join(timeout)

    def stop_threaded(self, timeout=5.0):
        """
        Lets a threaded output write what it holds, for up to *timeout* seconds, then stops its thread. A message says how many records were left behind, if any.

        Called by remove_sink(), clear_sinks(), and atexit shutdown so a
        threaded sink's thread is never left running after it's gone --
        no leaked threads. No-op when threaded is False.

        :Parameters:
            #. timeout (float): Seconds to wait at most for the queue to empty before the thread is
               stopped.
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
        if self._thread.is_alive():
            waiting = max(self._queue.stats()['depth'] - 1, 0)
            if waiting > 0:
                sys.stderr.write(f"pysimplelog WARNING: {waiting} records were not written by the sink "
                                 f"{type(self.handler).__name__} before the program ended. Raise shutdownTimeout "
                                 "or call flush() before the end\n")

    def queue_stats(self):
        """Returns the counters of the output's private queue, or None when the output is not threaded."""
        if self.durable is not None:
            return self.durable.queue_stats()
        return None if self._queue is None else self._queue.stats()

    def spool_stats(self):
        """Returns what the output's disk spool holds and what its delivery did, or None when it has no spool."""
        return None if self.durable is None else self.durable.stats()

    def maintain(self):
        """
        Does the housekeeping of the output and of its spool, such as deleting old files.

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
        Replaces the sink object that this output writes to.

        :Parameters:
            #. handler (Sink): The new handler.
        """
        self.handler = handler

    def release(self, timeout=5.0):
        """
        Stops the output's thread, if it has one, then closes its sink, which flushes it.

        :Parameters:
            #. timeout (float): Seconds to wait for the private queue to drain.
        """
        self.stop_threaded(timeout=timeout)
        try:
            self.handler.close()
        except Exception as closeError:
            sys.stderr.write('pysimplelog WARNING: sink close failed. Error: %s\n' % describe_error(closeError))

    def __repr__(self):
        return (
            '_Sink(sinkType=%r, enabled=%r, minLevel=%r, maxLevel=%r)'
            % (self.sinkType, self.enabled, self.minLevel, self.maxLevel)
        )


class _CatchContext(object):
    """
    What ``logger.catch()`` returns: it works as a ``with`` block and as a decorator. Use ``logger.catch()`` and not this class.

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
            msg = f"{self._message}: {exc_val}"
            self._logger.log(self._logType, msg, exc_info=(exc_type, exc_val, exc_tb))
            return not self._reraise   # True suppresses; False re-raises
        return False

    def __call__(self, func):
        """Allow the context manager instance to be used as a decorator."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """
            Runs the wrapped function inside the catch context.

            :Parameters:
                #. args (tuple): The positional arguments of the decorated function, passed on unchanged.
                #. kwargs (dict): The keyword arguments of the decorated function, passed on unchanged.
            """
            with _CatchContext(self._logger, self._logType, self._reraise, self._message):
                return func(*args, **kwargs)
        return wrapper


class _BoundLogger(object):
    """
    The logger you get from ``logger.bind(...)``. It has the usual methods, and adds the values you bound to every record it writes.

    While one of its methods logs, the bound values are added to the context of the current thread or task,
    over the values of any ``context()`` block the program is in, so the record carries them in its
    ``context``. The wrapper holds no queue, no file handle, and no configuration state of its own -- all
    I/O is performed by the parent Logger unchanged.

    Instances are immutable after construction and therefore inherently
    thread-safe. Nested bind() calls produce a new _BoundLogger with a
    merged context dict; the originals are never modified.

    Do not instantiate directly -- use Logger.bind() or _BoundLogger.bind().

    .. code-block:: python

        log = logger.bind(request_id="r-42")
        log.info("started")          ## ... started request_id=r-42

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
        """
        Returns another bound logger with more values added. The values bound before stay, and a value with the same name is
        replaced.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log2 = log.bind(step="payment")        ## carries request_id and step

        :Parameters:
            #. **extra: Arbitrary key-value pairs to add or override.

        :Returns:
            #. result (_BoundLogger): A new wrapper with merged context.
        """
        merged = dict(self.__context)
        merged.update(extra)
        return _BoundLogger(self.__parent, merged)

    def context(self, **values):
        """
        Adds values to every record made inside a ``with`` block. See :func:`pysimplelog.log_context.context`.

        :Parameters:
            #. values (dict): Names and values to add to every record made inside the ``with`` block.
        """
        return open_context(**values)

    # ── core logging ─────────────────────────────────────────────────

    def log(self, logType, message, *args, exc_info=None, countConstraint=None, **fields):
        """
        Writes a record of a log type, with the bound values attached. See :meth:`Logger.log` for the arguments.

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

    def force_log(self, logType, message, *args, exc_info=None, countConstraint=None, sinks=None, **fields):
        """
        Writes a record that must appear, with the bound values attached. See :meth:`Logger.force_log`.

        .. code-block:: python

            log = logger.bind(job="nightly")
            log.force_log("info", "Job stopped", sinks=["audit"])

        :Parameters:
            #. logType (string): A defined log type.
            #. message (string): The message to log.
            #. args (tuple): Positional arguments that fill the ``{}`` placeholders of *message*, see Logger.log().
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see Logger.log().
            #. countConstraint (None, number): Max times to log this message.
            #. sinks (None, list): Names of the sinks to write to. None writes to every sink that is switched on.
            #. fields: Named values stored in the record, see Logger.log().

        :Returns:
            #. message (string): the logged message
        """
        return self._log_call(logType, message, args, fields, exc_info, countConstraint, False, 0, True, sinks)

    # ── shortcut methods (mirrors Logger shortcuts) ──────────────────

    def _is_silent(self, logType, message, fields):
        """Asks the parent logger whether a call can return at once because no output wants it."""
        return self.__parent._is_silent(logType, message, fields)

    def info(self, message, *args, **kwargs):
        """
        Logs a message at the information level, with the bound values attached: normal things worth knowing. Same as ``log("info", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.info("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('info', message, kwargs):
            return message
        return self.log('info', message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """
        Logs a message at the information level, with the bound values attached: another name for ``info``. Same as ``log("info", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.information("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('info', message, kwargs):
            return message
        return self.log('info', message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """
        Logs a message at the warning level, with the bound values attached: something unexpected that did not stop anything. Same as ``log("warn", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.warn("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('warn', message, kwargs):
            return message
        return self.log('warn', message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """
        Logs a message at the warning level, with the bound values attached: another name for ``warn``. Same as ``log("warn", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.warning("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('warn', message, kwargs):
            return message
        return self.log('warn', message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """
        Logs a message at the error level, with the bound values attached: something failed. Same as ``log("error", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.error("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('error', message, kwargs):
            return message
        return self.log('error', message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """
        Logs a message at the critical level, with the bound values attached: something failed so badly that the program may not go on. Same as ``log("critical", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.critical("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('critical', message, kwargs):
            return message
        return self.log('critical', message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """
        Logs a message at the debug level, with the bound values attached: detail for finding a problem. Same as ``log("debug", ...)``.

        .. code-block:: python

            log = logger.bind(request_id="r-42")
            log.debug("Order {} created", 7)

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent('debug', message, kwargs):
            return message
        return self.log('debug', message, *args, **kwargs)

    def exception(self, message, *args, logType='error', **fields):
        """
        Logs the exception being handled with its traceback, with the bound values attached. Call it inside an ``except`` block.

        :Parameters:
            #. message (str, callable): The text to log, as in :meth:`info`.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. logType (str): The log type to write the record as. The default is ``"error"``.
            #. fields (dict): Extra named values, kept as fields of the record and used to fill ``{name}``
               places.
        """
        if self._is_silent(logType, message, fields):
            return message
        return self.log(logType, message, *args, exc_info=True, **fields)

    def _log_call(self, logType, message, args, fields, exc_info, countConstraint, isLazy, depth,
                  forced=False, sinks=None):
        """Does the work of a log call with the bound values attached, then hands it to the parent logger."""
        previous = CURRENT_CONTEXT.get()
        token = CURRENT_CONTEXT.set({**previous, **self.__context} if len(previous) > 0 else self.__context)
        try:
            return self.__parent._log_call(logType, message, args, fields, exc_info, countConstraint, isLazy, depth,
                                           forced, sinks)
        finally:
            CURRENT_CONTEXT.reset(token)

    def opt(self, *, lazy=False, exception=None, depth=0):
        """
        Returns a logger with options (lazy values, an exception, a caller depth), with the bound values attached. See :meth:`Logger.opt`.

        :Parameters:
            #. lazy (bool): True calls any function given as a value only if the record is really written.
            #. exception (None, bool, BaseException, tuple): The exception to record with every call. None
               records none, True records the one being handled.
            #. depth (int): How many extra calls up the stack the record's caller is searched, for a
               wrapper function. It must not be negative.
        """
        return _OptLogger(self, lazy, exception, depth)

    # ── exception capture ────────────────────────────────────────────

    def catch(self, func=None, logType='error', reraise=False,
              message='An exception was caught'):
        """
        Logs an error instead of letting it stop the program, with the bound values attached. It works as a decorator and as a
        ``with`` block, like :meth:`Logger.catch`.

        .. code-block:: python

            log = logger.bind(job="nightly")

            @log.catch
            def run(): ...

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
        """
        Says whether a log type would be written anywhere. See :meth:`Logger.is_enabled`.

        :Parameters:
            #. logType (str): The log type to check.
        """
        return self.__parent.is_enabled(logType)

    def is_enabled_for_stdout(self, logType):
        """
        Says whether a log type would be written to the console. See :meth:`Logger.is_enabled_for_stdout`.

        :Parameters:
            #. logType (str): The log type to check.
        """
        return self.__parent.is_enabled_for_stdout(logType)

    def is_enabled_for_file(self, logType):
        """
        Says whether a log type would be written to the built-in log file. See :meth:`Logger.is_enabled_for_file`.

        :Parameters:
            #. logType (str): The log type to check.
        """
        return self.__parent.is_enabled_for_file(logType)

    def flush(self):
        """Waits until everything queued has been written and returns whether it finished in time. See :meth:`Logger.flush`."""
        return self.__parent.flush()

    # ── read-only properties ─────────────────────────────────────────

    @property
    def name(self):
        """The name of the logger this bound logger belongs to."""
        return self.__parent.name

    @property
    def enqueue(self):
        """True when the logger hands records to a background thread."""
        return self.__parent.enqueue

    @property
    def boundContext(self):
        """
        A copy of the values this logger adds to every record. Changing the copy changes nothing.

        :Returns:
            #. result (dict): Copy of the bound key-value pairs.
        """
        return dict(self.__context)


class _OptLogger(object):
    """
    What ``logger.opt(...)`` returns: a logger whose calls use the options you chose.

    .. code-block:: python

        logger.opt(lazy=True).debug("Result: {}", slow)
        logger.opt(depth=1).info("Done")

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
        """
        Writes a record of a log type with the options. See :meth:`Logger.log` for the arguments.

        :Parameters:
            #. logType (str): A defined log type, such as ``"info"``.
            #. message (str, callable): The text to log.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record. None uses
               the one set by ``opt(exception=...)``. See :meth:`Logger.log`.
            #. countConstraint (None, int): Writes this record at most this many times. None means no
               limit.
            #. fields (dict): Named values, kept as fields of the record.
        """
        if self.__parent._is_silent(logType, message, fields):
            return message
        if exc_info is None:
            exc_info = self.__exception
        return self.__parent._log_call(logType, message, args, fields, exc_info, countConstraint,
                                       self.__isLazy, self.__depth)

    def info(self, message, *args, **kwargs):
        """
        Logs a message at the information level, with the options of ``opt()``. Same as ``log("info", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("info", message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """
        Logs a message at the information level, with the options of ``opt()``. Same as ``log("info", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("info", message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """
        Logs a message at the warning level, with the options of ``opt()``. Same as ``log("warn", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("warn", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """
        Logs a message at the warning level, with the options of ``opt()``. Same as ``log("warn", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("warn", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """
        Logs a message at the error level, with the options of ``opt()``. Same as ``log("error", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """
        Logs a message at the critical level, with the options of ``opt()``. Same as ``log("critical", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("critical", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """
        Logs a message at the debug level, with the options of ``opt()``. Same as ``log("debug", ...)``.

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        return self.log("debug", message, *args, **kwargs)

    def exception(self, message, *args, logType='error', **fields):
        """
        Logs the exception being handled with its traceback, with the options of ``opt()``. Call it inside an ``except`` block.

        :Parameters:
            #. message (str, callable): The text to log, as in :meth:`info`.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. logType (str): The log type to write the record as. The default is ``"error"``.
            #. fields (dict): Extra named values, kept as fields of the record and used to fill ``{name}``
               places.
        """
        return self.log(logType, message, *args, exc_info=True, **fields)


    def force_log(self, logType, message, *args, exc_info=None, countConstraint=None, sinks=None, **fields):
        """
        Writes a record that must appear, with the options of ``opt()``. See :meth:`Logger.force_log` for the arguments.

        .. code-block:: python

            logger.opt(depth=1).force_log("info", "Stopped by {}", user)

        :Parameters:
            #. logType (str): A defined log type, such as ``"info"``.
            #. message (str, callable): The text to log.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record. None uses
               the one set by ``opt(exception=...)``. See :meth:`Logger.log`.
            #. countConstraint (None, int): Writes this record at most this many times. None means no
               limit.
            #. sinks (None, list): Names of the sinks to write to. None writes to every sink that is switched on.
            #. fields (dict): Named values, kept as fields of the record.
        """
        if exc_info is None:
            exc_info = self.__exception
        return self.__parent._log_call(logType, message, args, fields, exc_info, countConstraint,
                                       self.__isLazy, self.__depth, True, sinks)

class Logger(object):
    """
    The object you log with. It sends each message to its outputs: the console, an optional log file, and any others you add.

    In plain words: most programs use the ready-made ``logger`` (``from pysimplelog import logger``). Make a ``Logger`` yourself
    when a library needs its own, or when you want separate settings.

    .. code-block:: python

        from pysimplelog import Logger

        log = Logger("billing", logToFile=False)
        log.add("logs/billing.log", rotation="10 MB")
        log.info("Order {} created", 7, customer="ann")

    Every log call builds one immutable :class:`pysimplelog.record.LogRecord`. The sinks turn it into
    text with their own formatter. The readable text layout is:

    date time - loggerName <logTypeName> message

    To write records in another layout, such as JSON lines, give a sink another formatter, see
    :mod:`pysimplelog.formatters` and :mod:`pysimplelog.sinks`.

    Delivery guarantees:

    * By default a log call writes to the sinks before it returns and nothing is kept in memory by pysimplelog.
    * Records of one thread reach each sink in the order that thread logged them. Different sinks are independent
      of each other, and there is no order between a threaded sink and the others.
    * ``enqueue=True`` keeps records in one queue until a worker thread writes them. ``threaded=True`` gives a sink a
      queue of its own, 1000 records and the ``drop_oldest`` policy unless told otherwise, so a burst can lose records.
    * A record is never lost without being counted: see ``droppedMessages``, ``queueStats`` and ``sink_stats``. A run
      of losses also writes one line to the standard error stream.
    * At the normal end of the program the queues are written for up to *shutdownTimeout* seconds and what is
      left is lost and reported. ``flush()`` returns False when its timeout ended before everything was written. If
      the program is killed, or ends with ``os._exit``, what is in a memory queue is lost.
    * A sink that raises loses that record for itself only, and the failure is counted in ``sink_stats``. A processor that
      raises drops the record for every sink, and a filter that raises keeps it.
    * A sink with a ``spool`` keeps records on disk until they are delivered, in order, and survives a crash. Delivery is
      at least once, so a record can be delivered twice, and carries the same ``event_id`` each time.
    * A forked child writes its records itself, in the calling thread. The queues and workers belong to the parent. No queue
      is shared between processes.

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
       #. diagnose (boolean, string): False (default) writes Python's plain traceback. 'summary' adds the
          variables used on each frame's source line, with containers and objects shown by type and length.
          'full' shows the ``repr`` of every value. Values reach every sink, so use it in development.
          Names that contain password, token, authorization, api_key, ssn, credit_card or secret are
          always shown as ``<redacted>``. Can be updated at runtime via set_diagnose().
       #. diagnoseRedact (tuple, list): Sensitive variable names added to the default ones.
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
          of its log type are added to the ``'text'`` layout only. The default is ``'pretty'``, a tidy column layout, in colour when
          the console is a terminal, unless *env* is True and ``PYSIMPLELOG_FORMAT`` is set. ``'text'`` is the readable line, ``time - name <INFO> message``. None gives JSON, a
          string with ``{name}`` placeholders is a template, and a function ``f(record) -> str`` is used as it
          is. See :mod:`pysimplelog.formatters`. Change it later with set_sink_formatter().
       #. fileFormatter (None, string, callable): The same, for the log file.
       #. consoleColor (None, string): ``'auto'`` colours the console only when it is a terminal and ``NO_COLOR``
          is not set, ``'always'`` colours it, ``'never'`` does not. None leaves the choice to ``PYSIMPLELOG_COLOR``
          when *env* is True, then to ``'auto'``. It applies to the ``'pretty'`` and ``'text'`` layouts.
       #. env (boolean): When True, the console takes ``PYSIMPLELOG_LEVEL``, ``PYSIMPLELOG_FORMAT`` and
          ``PYSIMPLELOG_COLOR`` from the environment for every setting the arguments leave out. An argument that is
          given always wins. The level applies when *stdoutMinLevel* is None. The variables are read once.
       #. shutdownTimeout (int, float): Seconds the program waits at its normal end for the queued records to be
          written, for the queue of ``enqueue`` and again for each threaded sink. Records still waiting after that are
          lost, and one line on the standard error stream says how many.
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
                       consoleFormatter=NOT_GIVEN, fileFormatter='text',
                       diagnose=False, diagnoseRedact=(),
                       consoleColor=None, env=False, shutdownTimeout=5.0,
                       *args, **kwargs):
        # The environment fills only what the caller left out, so an explicit argument always wins
        if not isinstance(env, bool):
            raise TypeError("env must be a boolean")
        if consoleColor is not None and consoleColor not in COLOR_MODES:
            raise ValueError(f"consoleColor must be None or one of {COLOR_MODES}")
        if isinstance(shutdownTimeout, bool) or not isinstance(shutdownTimeout, (int, float)) or not shutdownTimeout > 0:
            raise ValueError("shutdownTimeout must be a positive number of seconds")
        environment = read_environment() if env else {}
        if consoleFormatter is NOT_GIVEN:
            consoleFormatter = environment.get('consoleFormatter', 'pretty')
        if consoleColor is None:
            consoleColor = environment.get('consoleColor', 'auto')
        envLevel = environment.get('stdoutMinLevel') if stdoutMinLevel is None else None
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
        # create default types
        self.add_log_type("debug",    name="DEBUG",    level=0,   stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("info",     name="INFO",     level=10,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("warn",     name="WARNING",  level=20,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("error",    name="ERROR",    level=30,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("critical", name="CRITICAL", level=100, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        # The levels can be log type names, so they are set once the default types exist
        self.set_minimum_level(stdoutMinLevel, stdoutFlag=True, fileFlag=False)
        self.set_maximum_level(stdoutMaxLevel, stdoutFlag=True, fileFlag=False)
        self.set_minimum_level(fileMinLevel, stdoutFlag=False, fileFlag=True)
        self.set_maximum_level(fileMaxLevel, stdoutFlag=False, fileFlag=True)
        if envLevel is not None:
            try:
                envMinLevel = self.__resolve_add_level(envLevel)
            except ValueError:
                raise ValueError(f"{ENV_PREFIX}LEVEL must be a number or a defined log type, got {envLevel!r}") from None
            self.set_minimum_level(envMinLevel, stdoutFlag=True, fileFlag=False)
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
        # diagnose — validate and store
        self.set_diagnose(diagnose, diagnoseRedact)
        # unknown log type policy
        self.__unknownLogTypePolicy = 'raise'
        self.__fallbackLogType      = None
        self.set_unknown_log_type_policy(unknownLogTypePolicy, fallbackLogType)
        # how the two built-in sinks turn a record into text
        self.__consoleFormatter = consoleFormatter
        self.__consoleColor = consoleColor
        self.__shutdownTimeout = float(shutdownTimeout)
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
        """Says whether a stream can show colours, which is true for a terminal."""
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
        """Returns the colour, background and text-style codes this stream can show, or empty codes when it cannot show any."""
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
        """Gives a process that was just forked its own locks, so it cannot wait for a lock held by a thread it does not have. See :func:`pysimplelog.forking.register_for_fork_reset`."""
        self.__processorLock = threading.Lock()
        self.__filterLock = threading.Lock()

    def _flush_atexit_logfile(self):
        """
        Runs when the program ends: writes what is queued, stops the threads, and closes the log file. See ``shutdownTimeout``.

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
            self.__logWorker.join(timeout=self.__shutdownTimeout)
            if self.__logWorker.is_alive():
                # The stop marker is the last item, so it is not a record
                waiting = max(self.__logQueue.stats()['depth'] - 1, 0)
                sys.stderr.write(f"pysimplelog WARNING: {waiting} records were not written before the program ended "
                                 "(the log queue). Raise shutdownTimeout or call flush() before the end\n")
        # every sink is flushed and closed, a threaded sink's private thread is stopped first.
        # A file-like object given to add_sink() is only flushed, its owner closes it
        for sink in self.__sinks.values():
            sink.release(self.__shutdownTimeout)

    @property
    def processors(self):
        """The processors in the order they run, as a tuple. A processor is a function that changes every record before a sink sees it."""
        return tuple(self.__processors)

    @property
    def filters(self):
        """The global filters in the order they run, as a tuple. A filter is a function that drops records for every sink."""
        return tuple(self.__filters)

    @property
    def filteredRecords(self):
        """How many records a global filter has dropped so far. A sink's own filter is counted by that sink."""
        return self.__filteredRecords

    @property
    def filterFailures(self):
        """How many times a filter crashed or gave an answer other than True or False. The record was kept each time."""
        return self.__filterFailures

    @property
    def processorFailures(self):
        """How many records were dropped because a processor crashed or did not return a record."""
        return self.__processorFailures

    @property
    def lastRecord(self):
        """The most recent record that reached a sink, or None if nothing was logged yet."""
        return self.__lastRecord

    @property
    def lastRecords(self):
        """The most recent record of each log type, as a dictionary such as ``{'info': record, 'error': record}``."""
        return dict(self.__lastRecords)

    @property
    def flush(self):
        """Flush flag."""
        return self.__flush

    @property
    def enqueue(self):
        """True when the logger hands records to a background thread instead of writing them in the calling thread."""
        return self.__enqueue

    @property
    def consoleColor(self):
        """``'auto'``, ``'always'`` or ``'never'``: whether the console is written in colour."""
        return self.__consoleColor

    @property
    def callerInfo(self):
        """
        True when every record also says which file, line and function made the log call.

        The logger has to look at the call stack for each call to find out, which costs a little (roughly 10 to 30 microseconds),
        so it is off by default. Change it with :meth:`set_caller_info`.
        """
        return self.__callerInfo

    @property
    def unknownLogTypePolicy(self):
        """What happens when you log with a type that was never defined: ``'raise'`` (an error) or ``'fallback'`` (log it under another type)."""
        return self.__unknownLogTypePolicy

    @property
    def fallbackLogType(self):
        """The log type used for unknown types when the policy is ``'fallback'``, otherwise None."""
        return self.__fallbackLogType

    @property
    def maxQueueSize(self):
        """The most records the ``enqueue`` queue can hold, or None for no limit. None as well when ``enqueue`` is off."""
        return self.__maxQueueSize

    @property
    def queueFullPolicy(self):
        """What the ``enqueue`` queue does when it is full: ``'block'``, ``'drop_newest'``, ``'drop_oldest'`` or ``'reject'``. None when ``enqueue`` is off."""
        return self.__queueFullPolicy

    @property
    def queueBlockTimeout(self):
        """How many seconds a log call waits for a free place when the policy is ``'block'``. None means as long as it takes, or that ``enqueue`` or ``'block'`` is not in use."""
        return self.__queueBlockTimeout

    @property
    def queueSize(self):
        """
        How many records are waiting in the ``enqueue`` queue right now, or 0 when ``enqueue`` is off.

        The number is a snapshot and can be a little off while other threads are logging. To be sure the queue is empty, call
        ``flush()``.
        """
        if self.__logQueue is None:
            return 0
        return self.__logQueue.depth

    @property
    def droppedMessages(self):
        """
        How many records the ``enqueue`` queue has thrown away because it was full, since the logger was made.

        It never goes back to zero, and it is 0 when ``enqueue`` is off or the queue has no size limit. Records refused by the
        ``reject`` policy are counted in ``queueStats``, not here.
        """
        if self.__logQueue is None:
            return 0
        return self.__logQueue.stats()['dropped']

    @property
    def queueStats(self):
        """
        The counters of the ``enqueue`` queue as a dictionary, or None when ``enqueue`` is off.

        The keys are ``policy``, ``capacity`` (None without a limit), ``depth`` (waiting now), ``queued`` (accepted so far),
        ``dropped`` (thrown away so far) and ``rejected`` (refused with ``QueueFull`` so far).

        .. code-block:: python

            log = Logger("app", enqueue=True, maxQueueSize=1000)
            log.queueStats      ## {'policy': 'block', 'capacity': 1000, 'depth': 0, 'queued': 0, 'dropped': 0, 'rejected': 0}
        """
        if self.__logQueue is None:
            return None
        return self.__logQueue.stats()

    @property
    def logTypes(self):
        """The names of all the log types the logger knows, such as ``'debug'`` and ``'info'``."""
        return list(self.__logTypeNames)

    @property
    def logTypeFileFlags(self):
        """A copy of the per-type switches for the log file: which log types are forced on or off there."""
        return copy.deepcopy(self.__logTypeFileFlags)

    @property
    def logTypeStdoutFlags(self):
        """A copy of the per-type switches for the console: which log types are forced on or off there."""
        return copy.deepcopy(self.__logTypeStdoutFlags)

    @property
    def stdoutMinLevel(self):
        """The lowest level written to the console, or None for no limit. Change it with :meth:`set_minimum_level`."""
        return self.__stdoutMinLevel

    @property
    def stdoutMaxLevel(self):
        """The highest level written to the console, or None for no limit. Change it with :meth:`set_maximum_level`."""
        return self.__stdoutMaxLevel

    @property
    def fileMinLevel(self):
        """The lowest level written to the built-in log file, or None for no limit."""
        return self.__fileMinLevel

    @property
    def fileMaxLevel(self):
        """The highest level written to the built-in log file, or None for no limit."""
        return self.__fileMaxLevel

    @property
    def forcedStdoutLevels(self):
        """A copy of the log types that are forced on or off on the console whatever the minimum and maximum levels say."""
        return copy.deepcopy(self.__forcedStdoutLevels)

    @property
    def forcedFileLevels(self):
        """A copy of the log types that are forced on or off in the log file whatever the minimum and maximum levels say."""
        return copy.deepcopy(self.__forcedFileLevels)

    @property
    def logTypeNames(self):
        """A copy of the display name of each log type, such as ``{'warn': 'WARNING'}``."""
        return copy.deepcopy(self.__logTypeNames)

    @property
    def logTypeLevels(self):
        """A copy of the importance number of each log type, such as ``{'debug': 0, 'info': 10}``."""
        return copy.deepcopy(self.__logTypeLevels)

    @property
    def logTypeFormat(self):
        """A copy of the colour codes (start and end) that each log type is written with on a terminal."""
        return copy.deepcopy(self.__logTypeFormat)

    @property
    def name(self):
        """The name of the logger, which every record carries."""
        return self.__name

    @property
    def logToStdout(self):
        """True when the console output is switched on."""
        if _SINK_STDOUT in self.__sinks:
            return self.__sinks[_SINK_STDOUT].enabled
        return self.__logToStdout

    @property
    def logFileRoll(self):
        """How many log files are kept before the oldest is deleted, or None to keep them all."""
        return self.__logFileRoll

    @property
    def logToFile(self):
        """True when the built-in log file is switched on."""
        if _SINK_FILE in self.__sinks:
            return self.__sinks[_SINK_FILE].enabled
        return self.__logToFile

    @property
    def stdout(self):
        """The stream the console writes to. It is ``sys.stdout`` unless you gave another one."""
        return self.__stdout

    @property
    def sinks(self):
        """
        A read-only snapshot of the outputs by name, with the handler each one writes to.

        The keys are ``CONSOLE_SINK`` and ``FILE_SINK`` for the two built-in outputs, and the name given to ``add()`` or
        ``add_sink()`` for the others. What a sink did is in :meth:`sink_stats`.
        """
        return MappingProxyType({name: sink.handler for name, sink in self.__sinks.items()})

    @property
    def logFileName(self):
        """The path of the log file being written right now."""
        return self.__sinks[_SINK_FILE].handler.path

    @property
    def logFileBasename(self):
        """The folder and file name of the log file without its extension, such as ``logs/app``."""
        return self.__logFileBasename

    @property
    def logFileExtension(self):
        """The extension of the log file, such as ``log``."""
        return self.__logFileExtension

    @property
    def logFileMaxSize(self):
        """The size in megabytes at which a new log file is started, or None for no limit."""
        return self.__logFileMaxSize

    @property
    def logMessageMaxSize(self):
        """The most characters a message may have before it is cut, or None for no limit."""
        return self.__maxMessageSize

    @property
    def logDataMaxSize(self):
        """The most characters the ``data`` field may have before it is cut, or None for no limit."""
        return self.__maxDataSize

    @property
    def logFileFirstNumber(self):
        """The number of the first log file, which is 0 in ``app_0.log``, or None for a first file with no number."""
        return self.__logFileFirstNumber

    @property
    def timezone(self):
        """The name of the time zone used for timestamps, or None for the time zone of the machine."""
        timezone = self.__timezone
        if timezone is not None:
            timezone = timezone.zone
        return timezone

    @property
    def _timezone(self):
        """The time zone object used for timestamps, or None when the machine's time zone is used."""
        return self.__timezone

    @property
    def logMessagesCounter(self):
        """How many times each message with a count constraint has been logged. See the ``countConstraint`` argument of :meth:`log`."""
        return self.__logMessagesCounter

    def set_caller_info(self, callerInfo):
        """
        Turns on or off the file, line and function that each record says it came from.

        It takes effect on the very next log call. The logger has to look at the call stack for each call to find the caller, which
        costs a little, so it is off by default.

        .. code-block:: python

            logger.set_caller_info(True)
            logger.info("with caller")      ## ... | INFO | pysimplelog | script.py:12 in main | with caller

        :Parameters:
            #. callerInfo (boolean): True to prepend
               ``[file:line in func]`` to each message, False to disable.

        :Raises:
            #. TypeError: If *callerInfo* is not a boolean.
        """
        if not isinstance(callerInfo, bool):
            raise TypeError("callerInfo must be a boolean")
        self.__callerInfo = callerInfo

    def set_diagnose(self, diagnose, diagnoseRedact=()):
        """
        Chooses whether a traceback also shows the values of the variables behind the error, and which variable names are hidden.

        It takes effect on the next record that carries an exception. Use it while you develop: the values are written to every
        output.

        .. code-block:: python

            logger.set_diagnose("summary")          ## numbers and text in full, lists and objects by size
            logger.set_diagnose("full")             ## the repr of everything
            logger.set_diagnose(False)              ## plain Python tracebacks again

        :Parameters:
            #. diagnose (boolean, str): False for Python's plain traceback. True is the same as 'summary', which adds the variables used
               on each source line, with containers and objects shown by type and length. 'full' shows the
               ``repr`` of every value.
            #. diagnoseRedact (tuple, list): Names added to the default sensitive names. A variable whose name
               contains one of them shows ``<redacted>``.

        :Raises:
            #. ValueError: If *diagnose* is not False, True, 'summary' or 'full'.
            #. TypeError: If *diagnoseRedact* is not a tuple or list of strings.
        """
        if diagnose is True:
            diagnose = 'summary'
        if diagnose is not False and diagnose not in DIAGNOSE_MODES:
            raise ValueError(f"diagnose must be False, True or one of {DIAGNOSE_MODES}")
        if not isinstance(diagnoseRedact, (tuple, list)) or not all(isinstance(name, str) for name in diagnoseRedact):
            raise TypeError("diagnoseRedact must be a tuple or list of strings")
        self.__diagnose = diagnose
        self.__diagnoseRedact = tuple(diagnoseRedact)

    @property
    def diagnose(self):
        """``False``, ``'summary'`` or ``'full'``: whether tracebacks show the values of variables. Change it with :meth:`set_diagnose`."""
        return self.__diagnose

    @property
    def diagnoseRedact(self):
        """The extra variable names, besides ``password``, ``token`` and the like, whose values a diagnosed traceback hides, as a tuple."""
        return self.__diagnoseRedact

    def add_processor(self, func):
        """
        Adds a function that changes every record before any output sees it. This is where secrets are removed or values are added.

        The function gets the :class:`pysimplelog.record.LogRecord` and returns a record, usually a changed copy made with
        ``record._replace(...)``. Functions run in the order they were added, for every record. To treat only some records
        differently, test the record inside the function, for example ``record.logType``.

        If the function crashes, or returns something that is not a record, the record is dropped for **every** output, because
        letting an unchanged record through could leak what the function was meant to hide. The failure is counted in
        ``processorFailures`` and one warning is written for each function. A processor must not log.

        See :func:`pysimplelog.processors.redact_fields` and :func:`pysimplelog.processors.redact_text`.

        .. code-block:: python

            from pysimplelog import redact_fields

            logger.add_processor(redact_fields())                          ## hides passwords, tokens, ...
            logger.add_processor(lambda record: record._replace(message=record.message.upper()))

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
        Takes a function out of the processors. Nothing happens if it was never added.

        .. code-block:: python

            logger.remove_processor(my_function)

        :Parameters:
            #. func (callable): The function to remove.
        """
        self.__processors = [processor for processor in self.__processors if processor != func]

    def add_filter(self, func):
        """
        Adds a function that decides whether a record goes on to the outputs. It runs after the processors.

        The function gets the :class:`pysimplelog.record.LogRecord` and returns True to keep it or False to drop it. A dropped
        record is dropped for every output: nothing is written and ``lastRecord`` is not updated. Functions run in the order they
        were added, and the first one that says False ends the check. To decide for one output only, use
        :meth:`set_sink_filter`. ``force_log`` does not use filters.

        If the function crashes, or answers something other than True or False, the record is **kept**: a broken filter must not
        make logs disappear. The failure is counted in ``filterFailures``, and one warning is written for each function. Records
        a filter dropped are counted in ``filteredRecords``. A filter must not log.

        .. code-block:: python

            from pysimplelog import sample

            logger.add_filter(lambda record: record.fields.get("path") != "/health")   ## no health checks
            logger.add_filter(sample(0.1))                                            ## about one record in ten

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
        Takes a function out of the filters. Nothing happens if it was never added.

        .. code-block:: python

            logger.remove_filter(my_function)

        :Parameters:
            #. func (callable): The function to remove.
        """
        self.__filters = [keep for keep in self.__filters if keep != func]

    def set_sink_formatter(self, name, formatter):
        """
        Changes how one output turns a record into text.

        It takes effect on the next record. The output can be the console (``CONSOLE_SINK``), the built-in file (``FILE_SINK``) or
        the name of an output you added.

        .. code-block:: python

            from pysimplelog import CONSOLE_SINK, FILE_SINK

            logger.set_sink_formatter(FILE_SINK, None)                      ## one JSON object per line
            logger.set_sink_formatter(CONSOLE_SINK, "pretty")               ## the tidy console layout
            logger.set_sink_formatter("audit", "{timestamp} {severity} {message} {user}")     ## a template
            logger.set_sink_formatter("audit", lambda record: record.message.upper())         ## any function

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
        Tells what one output, or every output, has done and what it lost. A loss is never silent.

        Each output has a dictionary with:

        * ``queue``: the counters of the private queue of a threaded output, None for one written in the calling thread. They are
          ``policy``, ``capacity``, ``depth`` (records waiting now), ``queued`` (accepted so far), ``dropped`` (thrown away so far)
          and ``rejected`` (refused so far).
        * ``spool``: what the disk spool of the output holds and what its delivery did, None for an output without a spool. It has
          ``depth`` (records not delivered), ``bytes``, ``segments``, ``spooled`` (records kept), ``dropped``, ``rejected``,
          ``dead`` (records parked in the ``dead`` file), ``retries``, ``replayed``, ``orphans_adopted`` and ``orphans_skipped``
          (slots of other processes), ``refused`` (records not kept because a forked child does not own the spool), ``errors``,
          ``torn``, ``corrupt``, ``lost`` and ``slot``. The ``queue`` of such an output is a queue of hints: a hint that was
          dropped lost no record.
        * ``filtered``: how many records the output's own filter skipped, see :meth:`set_sink_filter`.
        * ``delivery``: what the output reports about itself: ``processed``, ``failed``, ``last_error``, ``latency_mean`` and
          ``latency_max`` in seconds, and what a particular output adds, such as ``sent`` for the SIEM sink.

        .. code-block:: python

            logger.sink_stats()                        ## every output, by name
            logger.sink_stats("sink-1")["delivery"]    ## processed, failed, last_error, latency_mean, latency_max

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
        Sends what a crashed process left in its spool, once, through one output.

        A spool keeps records on disk until they are delivered. If a process dies, its files stay behind. This sends them, one
        record at a time and in order, and stops at the first one that cannot be delivered. Only files made for the same spool
        ``id``, output class and destination are taken, so records meant for one receiver never go to another. Files that a living
        process holds are skipped. With ``adoptOrphans=True`` in the spool settings the output does the same on its own whenever it
        is idle.

        .. code-block:: python

            logger.adopt_orphans("collector")

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
        Does the housekeeping of every output now: deletes log files that are too many or too old, queues rotated files for
        compression, and lets a spool drop segments that are too old.

        Nothing happens on its own for an output that is not written to, so call this from a scheduler, or a thread of your own,
        if files must go on time whether or not anything is logged. It is safe to call at any time and from any thread. It never
        sends or loses a record that is not already past its limit, and an error in one output is reported once and does not stop the
        others. :meth:`flush` is the one that pushes data out.

        .. code-block:: python

            logger.maintain()          ## for example once an hour

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
                                     f"Error: {describe_error(error)}\n")
                result = {'error': type(error).__name__}
            if result is not None:
                results[name] = result
        return results

    def set_sink_filter(self, name, recordFilter):
        """
        Gives one output its own filter, or removes it.

        The filter decides which records that output receives, and it is the last step before the output, after the routing by
        level and log type. It gets the :class:`pysimplelog.record.LogRecord` and returns True to give it to the output or False to
        skip it. Other outputs are not affected. If the function crashes or answers something other than True or False, the
        output gets the record, and the failure is counted like that of any filter. Skipped records are counted in the output's
        ``filtered`` number, see :meth:`sink_stats`.

        .. code-block:: python

            logger.set_sink_filter("audit", lambda record: record.logType == "audit")    ## only audit records
            logger.set_sink_filter("audit", None)                                         ## back to everything

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
        Chooses what happens when you log with a type that was never defined.

        With ``'raise'`` (the default) it is an error. With ``'fallback'`` the message is logged under *fallbackLogType* with the
        unknown name written in front, so a typo never crashes the program and stays visible.

        .. code-block:: python

            logger.set_unknown_log_type_policy("fallback", "error")
            logger.log("typo", "hello")        ## logged as an error: Unknown log type 'typo': hello

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
        """
        Sets how many records the ``enqueue`` queue may hold. None removes the limit.

        It can be called at any time and takes effect on the next log call.

        .. code-block:: python

            logger.set_max_queue_size(5000)

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
        """
        Chooses what the ``enqueue`` queue does when it is full: ``'block'``, ``'drop_newest'``, ``'drop_oldest'`` or ``'reject'``.

        It can be changed at any time and applies to the next call that finds the queue full. Everything that is thrown away or
        refused is counted, see :attr:`queueStats`.

        .. code-block:: python

            logger.set_queue_full_policy("drop_oldest")

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
        """
        Sets how many seconds a log call waits for a free place when the queue policy is ``'block'``. After that the new record
        is dropped and counted. None waits as long as it takes.

        .. code-block:: python

            logger.set_queue_block_timeout(0.5)

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
        Sets the time zone used for the time of each record, by name such as ``"Europe/Paris"``. None uses the time zone of the
        machine.

        A named time zone needs the optional ``pytz`` package.

        .. code-block:: python

            logger.set_timezone("UTC")

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
        """
        Says whether a log type is defined.

        .. code-block:: python

            logger.is_log_type("info")       ## True
            logger.is_log_type("nope")       ## False

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
        """
        Changes several settings of the logger at once, by name.

        The names that can be changed are ``name``, ``flush``, ``stdout``, ``logToStdout``, ``logFileRoll``, ``logToFile``,
        ``logFileMaxSize``, ``stdoutMinLevel``, ``stdoutMaxLevel``, ``fileMinLevel``, ``fileMaxLevel``, ``logFileFirstNumber``,
        ``logFile``, ``maxMessageSize``, ``maxDataSize``, ``maxQueueSize``, ``queueFullPolicy``, ``queueBlockTimeout``,
        ``callerInfo``, ``diagnose``, ``diagnoseRedact``, ``unknownLogTypePolicy`` and ``fallbackLogType``.

        .. code-block:: python

            logger.update(logToFile=False, stdoutMinLevel=10)
            other.update(**logger.parameters)           ## copy the settings of one logger to another

        :Parameters:
            #. kwargs (dict): The settings to change, each given as ``name=value``. The names are listed
               above.
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
        if "diagnose" in kwargs or "diagnoseRedact" in kwargs:
            self.set_diagnose(kwargs.get("diagnose", self.__diagnose),
                              kwargs.get("diagnoseRedact", self.__diagnoseRedact))
        if "unknownLogTypePolicy" in kwargs or "fallbackLogType" in kwargs:
            self.set_unknown_log_type_policy(kwargs.get("unknownLogTypePolicy", self.__unknownLogTypePolicy),
                                             kwargs.get("fallbackLogType", self.__fallbackLogType))


    @property
    def parameters(self):
        """
        The general settings of the logger as a dictionary.

        The dictionary can be given to the ``update()`` method of another logger to copy the configuration. Its ``userSinks`` entry
        lists the outputs added with ``add()`` or ``add_sink()``, with their switch, levels and log type flags. The two built-in
        outputs are described by the other keys.
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
                "diagnose":self.__diagnose,
                "diagnoseRedact":self.__diagnoseRedact,
                "unknownLogTypePolicy":self.__unknownLogTypePolicy,
                "fallbackLogType":self.__fallbackLogType,
                "userSinks":userSinks}


    def custom_init(self, *args, **kwargs):
        """
        A place for your own start-up code when you make a subclass of ``Logger``. It does nothing here.

        It is called as the very last step of ``Logger.__init__``, when the logger is completely built, so logging and ``add()``
        already work inside it. The ``logTypes`` argument of the constructor is applied right after it.

        .. code-block:: python

            class MyLogger(Logger):
                def custom_init(self, *args, **kwargs):
                    self.add_log_type("trace", name="TRACE", level=5)

        :Parameters:
            #. \\*args (): This is used to send non-keyworded variable length argument
               list to custom initialize.
            #. \\**kwargs (): This is keyworded variable length of arguments.
               kwargs can be anything other than __init__ arguments.
        """
        pass

    def set_name(self, name):
        """
        Sets the name of the logger, which every record carries.

        .. code-block:: python

            logger.set_name("billing.api")

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
        Chooses whether the console and the log file are flushed after every record. Flushing is safer, because a crash loses less,
        and a little slower.

        .. code-block:: python

            logger.set_flush(True)

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
        Sets the stream the console writes to. None goes back to ``sys.stdout``.

        The stream needs a ``write`` method and a ``read`` method.

        .. code-block:: python

            import io
            logger.set_stdout(io.StringIO())       ## keep the console output in memory
            logger.set_stdout(None)                ## back to the terminal

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
        Switches the console output on or off. When off, nothing is written to it, whatever the per-type settings say.

        .. code-block:: python

            logger.set_log_to_stdout_flag(False)

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
        Switches the built-in log file on or off. When off, nothing is written to it, whatever the per-type settings say.

        .. code-block:: python

            logger.set_log_to_file_flag(True)

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
        Forces a log type on or off for the console and for the log file, whatever the minimum and maximum levels say. None
        removes the forcing.

        .. code-block:: python

            logger.set_log_type_flags("debug", stdoutFlag=False, fileFlag=True)     ## debug only in the file

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
        Sets how many log files are kept. When there are more, the oldest are deleted. None keeps all of them.

        .. code-block:: python

            logger.set_log_file_roll(5)

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
        Sets the path of the log file, with its folder, name and extension, such as ``logs/app.log``.

        .. code-block:: python

            logger.set_log_file("logs/app.log")

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
        Sets the extension of the log file, such as ``log``.

        .. code-block:: python

            logger.set_log_file_extension("txt")

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
        Sets the folder and name of the log file without its extension, such as ``logs/app``.

        .. code-block:: python

            logger.set_log_file_basename("logs/app")

        :Parameters:
           #. logFileBasename (string): Logging file directory path and file basename.
              A logging file full name is set as logFileBasename.logFileExtension

        :Raises:
            #. TypeError: If *logFileBasename* is not a string.
        """
        self.__set_log_file_basename(logFileBasename)
        self.__select_log_file()

    def __set_log_file_basename(self, logFileBasename):
        """Stores the folder and name of the log file, without its extension. :meth:`set_log_file_basename` is the public way to change it."""
        if not isinstance(logFileBasename, str):
            raise TypeError("logFileBasename must be a string")
        self.__logFileBasename = _normalize_path(logFileBasename)#logFileBasename

    def __select_log_file(self):
        """Tells the file sink to continue in the file of the current base name and extension, once the sink exists."""
        if _SINK_FILE in self.__sinks:
            self.__sinks[_SINK_FILE].handler.set_path(self.__logFileBasename, self.__logFileExtension)

    def set_log_file_maximum_size(self, logFileMaxSize):
        """
        Sets the size, in megabytes, at which a new log file is started. None means a file grows without limit.

        .. code-block:: python

            logger.set_log_file_maximum_size(10)

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
        """
        Sets the most characters a message may have. A longer message is cut and ``[truncated]`` is added. None means no limit.

        .. code-block:: python

            logger.set_maximum_message_size(2000)

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
        """
        Sets the most characters the ``data`` field may have. A longer one is cut and ``[truncated]`` is added. None means no limit.

        .. code-block:: python

            logger.set_maximum_data_size(10000)

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
        Sets the number of the first log file. With 0 the files are ``app_0.log``, ``app_1.log`` and so on.

        .. code-block:: python

            logger.set_log_file_first_number(1)

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
        Hides every log call below a level, on the console and in the log file.

        In plain words: each log type has an importance number. A minimum of ``"warn"`` keeps warnings, errors and critical
        messages and drops the debug and info ones. Only the console and the built-in log file change, unless you name other
        outputs in *sinks*.

        .. code-block:: python

            logger.set_minimum_level("warn")      ## only warn, error and critical are written
            logger.set_minimum_level(None)        ## everything again

        :Parameters:
           #. level (None, number, str): The minimum level of logging.
              If None, minimum level checking is left out.
              If str, it must be the key or the name of a defined logtype, such as ``"warn"`` or ``"WARNING"``, and
              the minimum level is the level of this logtype.
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
                # A key such as "warn" or a name such as "WARNING", like the level of add()
                level = self.__resolve_add_level(level)
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
        Hides every log call above a level, on the console and in the log file. It is the opposite of :meth:`set_minimum_level`,
        and rarely needed: use it to send, say, only the debug and info records to one place.

        .. code-block:: python

            logger.set_maximum_level("info", stdoutFlag=False)     ## the log file gets nothing above info

        :Parameters:
           #. level (None, number, str): The maximum level of logging.
              If None, maximum level checking is left out.
              If str, it must be the key or the name of a defined logtype, such as ``"warn"`` or ``"WARNING"``, and
              the maximum level is the level of this logtype.
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
                # A key such as "warn" or a name such as "WARNING", like the level of add()
                level = self.__resolve_add_level(level)
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
        """Works out again, from the minimum and maximum levels, which log types are written to the console and to the log file."""
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
        """
        Works out, for each log type, which outputs will receive it, so a log call only has to look the answer up. It runs after any change that affects routing.

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
        """
        Hands a record to each output: a threaded output gets it on its queue, the others write it at once. One failing output cannot stop the others.

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

    def add(self, target, *, name=None, format=None, level=None, filter=None,
            rotation=None, retention=None, compression=None, **sinkOptions):
        """
        Adds an output in one call: a file, a stream, a function or a ready sink.

        It builds the sink and calls :meth:`add_sink`, so everything *add_sink* does applies.

        .. code-block:: python

            logger.add("logs/app.log", rotation="500 MB", retention="30 days", compression="gz")
            logger.add("logs/events.jsonl", format="json", level="ERROR")
            logger.add(sys.stderr, format="{timestamp} [{severity}] {message}")
            logger.add(lambda text, record: alerts.push(text), level="CRITICAL")

        :Parameters:
            #. target (str, os.PathLike, file-like, callable, Sink): A path with an extension makes a rotating
               file. An object with ``write(str)`` makes a stream sink, and the caller closes the stream. Any
               other function is called as ``f(text, record)``. A :class:`pysimplelog.sinks.Sink` is used as it is.
            #. name (None, str): The name of the sink. None gives ``sink-1``, ``sink-2``, and so on.
            #. format (None, str, callable): How a record becomes text, see
               :func:`pysimplelog.formatters.resolve_formatter`. None gives the ``'text'`` layout. It cannot be
               given with a Sink, which has its own.
            #. level (None, int, float, str): The lowest level the output receives. A log type key such as
               ``'error'``, its name such as ``'ERROR'``, or a number. None means no floor.
            #. filter (None, callable): ``f(record) -> bool`` that picks the records, see
               :func:`pysimplelog.filters.match_logger`.
            #. rotation (None, str, int, float): The size at which a file is rotated, ``"500 MB"`` or a number of
               megabytes. Files only.
            #. retention (None, str, int): ``"30 days"`` deletes rotated files that old. A whole number keeps that
               many files. Files only.
            #. compression (None, str): ``'gz'`` compresses a file when it is rotated. Files only.
            #. sinkOptions: Any other argument of :meth:`add_sink`, for example ``threaded=True``.

        :Returns:
            #. name (str): The name of the sink, to give to :meth:`remove_sink`.

        :Raises:
            #. TypeError: If *target* is not one of the kinds above, if rotation, retention or compression is
               given for something that is not a file, or if *format* is given with a Sink.
            #. ValueError: If *level* is unknown, or a size, an age or a path is wrong.
        """
        isFile = isinstance(target, (str, os.PathLike))
        if not isFile and (rotation is not None or retention is not None or compression is not None):
            raise TypeError("rotation, retention and compression apply to a file path only")
        minLevel = self.__resolve_add_level(level)
        isBuilt = not isinstance(target, Sink)
        if not isBuilt:
            if format is not None:
                raise TypeError("a Sink has its own formatter, so format cannot be given")
            handler = target
        else:
            formatter = 'text' if format is None else format
            if isFile:
                handler = build_file_sink(target, formatter, rotation, retention, compression)
            elif hasattr(target, 'write'):
                handler = StreamSink(target, formatter=formatter, flush=self.__plain_flush_mode(target))
            elif callable(target):
                handler = CallbackSink(target, formatter=formatter)
            else:
                raise TypeError("target must be a path, a file-like object, a function or a Sink")
        if name is None:
            number = 1
            while f"sink-{number}" in self.__sinks:
                number += 1
            name = f"sink-{number}"
        try:
            self.add_sink(name, handler, minLevel=minLevel, recordFilter=filter, **sinkOptions)
        except Exception:
            # A sink built here belongs to nobody if it was refused
            if isBuilt:
                handler.close()
            raise
        return name

    def __resolve_add_level(self, level):
        """Returns the number for a level given as None, a number, a log type key or a log type name."""
        if level is None or _is_number(level):
            return level
        if isinstance(level, str):
            if level in self.__logTypeLevels:
                return self.__logTypeLevels[level]
            for logType, logName in self.__logTypeNames.items():
                if logName.lower() == level.lower():
                    return self.__logTypeLevels[logType]
        raise ValueError(f"level must be a number or a defined log type, got {level!r}")

    def add_sink(self, name, handler, enabled=True,
                 minLevel=None, maxLevel=None, logTypeFlags=None,
                 defaultFlag=True, threaded=False, threadQueueSize=1000, recordFilter=None,
                 threadQueuePolicy='drop_oldest', threadBlockTimeout=None, spool=None):
        """
        Adds an output to the logger. This is the full form of :meth:`add`, which builds the output for you.

        In plain words: an output (a "sink") is where records go. After this call every record whose log type is allowed reaches it.
        You can give a ready :class:`pysimplelog.sinks.Sink`, or any object with a ``write(text)`` method, such as a file or
        ``sys.stderr``. Give it its own thread with ``threaded=True`` if it is slow.

        The sink receives every log record whose type passes the routing
        rules (enabled flag, per-type flags, and optional level bounds).

        A handler that is a :class:`pysimplelog.sinks.Sink` object receives the
        structured :class:`pysimplelog.record.LogRecord` and renders it with its own
        formatter. The logger closes such a sink when it is removed and at exit.

        Any other handler, a file-like object with a ``write(str)`` method, is wrapped in a
        :class:`pysimplelog.sinks.StreamSink` that writes the readable text of every record,
        the same text as the log file, without colour codes. The caller
        owns the handler's lifecycle -- the logger never closes it, it only flushes it.

        .. code-block:: python

            import sys
            logger.add_sink("errors", sys.stderr, minLevel=30)                 ## errors and above, to the error stream
            logger.add_sink("slow", MySlowSink(), threaded=True)               ## written by a thread of its own
            logger.remove_sink("errors")

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
        """
        Removes an output you added, by its name, and stops its thread if it has one.

        A threaded output is given up to *timeout* seconds to write what it still holds.

        .. code-block:: python

            logger.remove_sink("errors")

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

    def remove(self, name, timeout=5.0):
        """
        Removes an output by the name :meth:`add` returned. It is the same as :meth:`remove_sink`.

        .. code-block:: python

            name = logger.add("logs/audit.log")
            logger.remove(name)                    ## stops it and closes the file

        :Parameters:
            #. name (str): The name that :meth:`add` returned.
            #. timeout (float): Seconds a threaded output is given to write what it still holds.
        """
        return self.remove_sink(name, timeout)

    def clear_sinks(self, timeout=5.0):
        """
        Removes every output you added. The console and the built-in log file stay.

        A threaded output is given up to *timeout* seconds to write what it still holds. Nothing happens if you added none.

        .. code-block:: python

            logger.clear_sinks()

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
        Forces a log type on or off on the console, whatever the minimum and maximum levels say. None removes the forcing.

        .. code-block:: python

            logger.force_log_type_stdout_flag("debug", True)       ## debug always shows on the console

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
        Forces a log type on or off in the log file, whatever the minimum and maximum levels say. None removes the forcing.

        .. code-block:: python

            logger.force_log_type_file_flag("audit", True)

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
        Forces a log type on or off on the console and in the log file at once. None removes the forcing.

        .. code-block:: python

            logger.force_log_type_flags("audit", stdoutFlag=False, fileFlag=True)

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
        Changes the name a log type is shown with, such as ``WARNING`` for ``warn``.

        .. code-block:: python

            logger.set_log_type_name("warn", "WARN")

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
        Changes the importance number of a log type. The minimum and maximum levels compare against it.

        .. code-block:: python

            logger.set_log_type_level("info", 15)

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
        Deletes a log type you defined.

        .. code-block:: python

            logger.remove_log_type("audit")

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
        Defines a new kind of message, with its own name, importance and colour.

        In plain words: ``debug``, ``info``, ``warn``, ``error`` and ``critical`` come ready. Add your own, such as ``audit``, and
        log with ``logger.log("audit", "...")``. The level decides what the minimum and maximum levels keep or hide.

        The colours are: black, red, green, orange, blue, magenta, cyan, grey, dark grey, light red, light green, yellow, light blue,
        pink and light cyan. The highlights (background colours) are: black, red, green, orange, blue, magenta, cyan and grey. The
        attributes are: bold, underline, blink, invisible and strike through. They show only on a terminal that supports them.

        .. code-block:: python

            logger.add_log_type("audit", name="AUDIT", level=15, color="magenta")
            logger.log("audit", "user exported the report", user="ann")

        :Parameters:
           #. logType (string): The logtype.
           #. name (None, string): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (None, boolean): Force standard output logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. fileFlag (None, boolean): Force file logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. color (None, string): The logging text color. The defined colors are:

              black , red , green , orange , blue , magenta , cyan , grey , dark grey ,
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, string): The logging text highlight color. The defined highlights are:

              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, string): The logging text attribute. The defined attributes are:

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
        """Stores a log type's name, level, colours and switches. :meth:`add_log_type` and :meth:`update_log_type` use it after checking their arguments."""
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
        Changes some properties of a log type that already exists (its name, level, switches or colours). What you leave as None
        stays as it is.

        .. code-block:: python

            logger.update_log_type("audit", level=25, color="red")

        :Parameters:
           #. logType (string): The logtype.
           #. name (None, string): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (None, boolean): Force standard output logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. fileFlag (None, boolean): Force file logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. color (None, string): The logging text color. The defined colors are:

              black , red , green , orange , blue , magenta , cyan , grey , dark grey ,
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, string): The logging text highlight color. The defined highlights are:

              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, string): The logging text attribute. The defined attributes are:

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
        exception = None if exc_info is None else _exception_info(exc_info, self.__diagnose, self.__diagnoseRedact)
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
        Returns the current date and time as text, in the time zone of the logger.

        .. code-block:: python

            logger.get_timestamp()                 ## '2026-10-08 18:45:02'
            logger.get_timestamp("%H:%M")          ## '18:45'

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
                    sys.stderr.write('pysimplelog WARNING: processor %r raised %s, the record is dropped '
                                     'when it fails\n' % (processor, describe_error(processorError)))
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
                sys.stderr.write('pysimplelog WARNING: filter %r raised %s, the record is kept when it fails\n'
                                 % (keep, describe_error(filterError)))
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
        """
        The loop of the background thread of ``enqueue``: take items from the queue and write them until told to stop.

        Each item is a 2-tuple (sinks, record): sinks is a snapshot list of _Sink objects, taken from
        __activeSinks for a normal call, or chosen by force_log() for a forced one.
        The sentinel _QUEUE_STOP signals clean shutdown.
        task_done() is called after every item so flush() can join().
        """
        mark_delivery_thread()
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
        Delivers one item of the ``enqueue`` queue to its outputs.

        :Parameters:
            #. item (tuple): ``(sinks, record)``.
        """
        sinks, record = item
        try:
            self.__dispatch_sinks_sync(sinks, record)
        except QueueFull:
            # A sink refused it, its own queue counted that, and the caller is no longer here to be told
            pass

    def __put_to_queue(self, item):
        """
        Puts an item on the ``enqueue`` queue, or does what the full-queue policy says if there is no room.

        Called by log(), log_external() and force_log() whenever enqueue mode is active.
        The policy is read by the queue on every call, so changes made with
        set_queue_full_policy() take effect immediately.

        :Parameters:
            #. item (tuple): ``(sinks, record)``.

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
        # A switched off log file has nothing to start, so it does not read the folder until it is used
        return FileSink(self.__logFileBasename, self.__logFileExtension, formatter=self.__fileFormatter,
                        flush=self.__flushMode, maxSize=self.__logFileMaxSize, roll=self.__logFileRoll,
                        firstNumber=self.__logFileFirstNumber, startLazily=not self.__logToFile)

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
        isTextColored = self.__consoleFormatter == 'text' and self.__consoleColor != 'never'
        decorate = self.__decorate_console if isTextColored else None
        formatter = self.__consoleFormatter
        if formatter == 'pretty':
            # The pretty layout colours itself, and by default only when the stream is a terminal
            if self.__consoleColor == 'auto':
                isColored = stream_supports_color(sys.stdout if stream is None else stream)
            else:
                isColored = self.__consoleColor == 'always'
            formatter = ConsoleFormatter(colors=isColored, colorOf=self.__type_color)
        return ConsoleSink(stream, formatter=formatter, flush='flush' if isFlushed else 'none',
                           decorate=decorate)

    def __type_color(self, record):
        """Returns the colour code the developer gave to the log type of a record, or None when it has none."""
        wrap = self.__logTypeFormat.get(record.logType)
        return (wrap[0] or None) if wrap else None

    def __decorate_console(self, text, record):
        """Wraps the text of a record in the colour codes of its log type."""
        fmt = self.__logTypeFormat[record.logType]
        return "%s%s%s" % (fmt[0], text, fmt[1])

    def is_enabled_for_stdout(self, logType):
        """
        Says whether a log type would be written to the console right now. Both the console switch and the type's own setting
        must allow it.

        .. code-block:: python

            logger.is_enabled_for_stdout("debug")

        :Parameters:
           #. logType (string): A defined logging type.

        :Returns:
           #. enabled (bool): Whether stdout output is active for this log type.
        """
        return self.__logToStdout and self.__logTypeStdoutFlags[logType]

    def is_enabled_for_file(self, logType):
        """
        Says whether a log type would be written to the built-in log file right now. Both the file switch and the type's own setting
        must allow it.

        .. code-block:: python

            logger.is_enabled_for_file("debug")

        :Parameters:
           #. logType (string): A defined logging type.

        :Returns:
           #. enabled (bool): Whether file output is active for this log type.
        """
        return self.__logToFile and self.__logTypeFileFlags[logType]

    def is_enabled(self, logType):
        """
        Says whether a log type would be written to at least one output, so you can skip building an expensive message when nobody would see it.

        In plain words: it answers "would this message go anywhere?". Every output counts: the console, the log file and the ones you added. A log
        type that is switched off, or below the level of every output, gives False.

        .. code-block:: python

            if logger.is_enabled("debug"):
                logger.debug(json.dumps(large_object))        ## the dumps call is made only when someone will see the result

            ## Or let the logger decide, and call the function only if the record is written
            logger.opt(lazy=True).debug("Object: {}", lambda: json.dumps(large_object))

        :Parameters:
            #. logType (string): A defined logging type.

        :Returns:
            #. result (bool): True if at least one output would receive a message of this logType, False otherwise.
        """
        # use the pre-computed active-sink cache: covers stdout, file,
        # AND any user-added sinks — a non-empty list means dispatch happens
        return bool(self.__activeSinks.get(logType))


    def log(self, logType, message, *args, exc_info=None, countConstraint=None, **fields):
        """
        Writes one record of a log type. This is the call behind ``info()``, ``error()`` and the other shortcuts.

        In plain words: you give a log type, a message and any values you want to keep with it. The values passed as keywords
        become fields of the record, and ``{}`` in the message is filled from the other values.

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

        .. code-block:: python

            logger.log("info", "User {} logged in", user)                  ## filled in order
            logger.log("info", "Order created", order_id=123, amount=12.5)  ## kept as fields
            logger.log("audit", "report exported", count=3, countConstraint=5)   ## logged at most 5 times

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

    def _log_call(self, logType, message, args, fields, exc_info, countConstraint, isLazy, depth,
                  forced=False, sinks=None):
        """
        The shared body of every log call: checks it, finds the outputs that want it, builds the record and delivers it.

        :Parameters:
            #. logType (string): A defined log type.
            #. message (string): The message to log.
            #. args (tuple): Values that fill the ``{}`` places of the message.
            #. fields (dict): The named values of the record.
            #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record.
            #. countConstraint (None, number): Maximum number of times to log the given message.
            #. isLazy (bool): True calls the functions given as values, only when the record is wanted.
            #. depth (int): How many extra calls up the stack the caller is searched.
            #. forced (bool): True for :meth:`force_log`: the levels, the type flags, ``disable()`` and the filters are
               ignored, and a sink that is switched off still receives nothing.
            #. sinks (None, list): The sinks of a forced record, see :meth:`force_log`. Only used when *forced* is True.
        """
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
        if forced:
            # A forced record ignores the levels, the type flags, disable() and the filters, but not a sink that is
            # switched off. A wrong sink name fails here, before anything is written
            activeSinks = self.__forced_sinks(sinks)
        else:
            # Wrong calls still fail above, a disabled namespace only stops the work below
            if namespaces.NEEDS_CHECK and is_disabled(self.__name):
                return message
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
        self.__deliver(logType, record, activeSinks, forced)
        # always return logged message
        return message

    def log_external(self, logType, message, *, created, processId, threadId, threadName,
                     caller=None, exc_info=None, fields=None):
        """
        Writes a record that another logging system made, keeping its time, process, thread and caller. It is for bridges, such as
        the one that carries Python's standard ``logging`` records in.

        The record goes through exactly what a record of :meth:`log` goes through: the routing, the
        processors, the filters and the sinks. It is made for bridges, such as
        :class:`pysimplelog.standard_logging.StandardLoggingHandler`. Unlike :meth:`log`, the fields are
        given as one dictionary, so any name can be a field.

        .. code-block:: python

            import time

            logger.log_external("warn", "disk is almost full", created=time.time(), processId=1234,
                                threadId=1, threadName="MainThread", fields={"disk": "/dev/sda1"})

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
        # A bridged record keeps the name of its own logger in the field logger_name
        bridgedName = None if fields is None else fields.get('logger_name')
        if namespaces.NEEDS_CHECK and (is_disabled(self.__name) or (isinstance(bridgedName, str) and is_disabled(bridgedName))):
            return message
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

    def __forced_sinks(self, sinks):
        """
        Returns the outputs a forced record goes to: the ones named, or all that are switched on.

        A sink that is switched off (``enabled`` is False, as ``logToFile=False`` does for the built-in file) is left out.

        :Parameters:
            #. sinks (None, list, tuple, set): Names given to :meth:`add` or :meth:`add_sink`, or ``CONSOLE_SINK`` and
               ``FILE_SINK``. None means every registered sink.

        :Returns:
            #. targets (list): The _Sink objects that receive the record.

        :Raises:
            #. TypeError: If *sinks* is not a list, a tuple, a set or None.
            #. ValueError: If a name is not registered.
        """
        if sinks is None:
            return [sink for sink in self.__sinks.values() if sink.enabled]
        if not isinstance(sinks, (list, tuple, set, frozenset)):
            raise TypeError("sinks must be a list of sink names, or None for every sink")
        targets = []
        for name in sinks:
            if name not in self.__sinks:
                raise ValueError(f"sink {name!r} is not registered")
            if self.__sinks[name].enabled:
                targets.append(self.__sinks[name])
        return targets

    def __deliver(self, logType, record, activeSinks, forced=False):
        """
        Gives a record to the sinks that want it, after the processors and the filters.

        :Parameters:
            #. logType (string): The log type of the record.
            #. record (LogRecord): The record built for the log call.
            #. activeSinks (list): The _Sink objects that passed the routing for this log type.
            #. forced (bool): True when the record is not filtered. The processors still run.
        """
        if self.__processors:
            # None when a processor failed: the record is dropped for every sink
            record = self._process_record(record)
        # A forced record is not filtered: the filters pick records, and the caller picked this one
        if record is not None and not forced:
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

    def force_log(self, logType, message, *args, exc_info=None, countConstraint=None, sinks=None, **fields):
        """
        Writes a record that must appear, even when its log type is switched off, below a level, filtered or silenced by ``disable()``.

        Use it for the few messages that must always be written, such as "the program is stopping". It goes to every
        sink that is switched on, or only to the ones you name. A sink that is switched off stays silent. The processors
        still run, so redaction applies.

        .. code-block:: python

            logger.force_log("info", "Shutting down")                          ## every sink that is on
            logger.force_log("error", "Audit trail broken", sinks=["audit"])   ## only the sink named audit
            logger.opt(depth=1).force_log("info", "Stopped by {}", user)       ## the options of opt() work too

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log, as in :meth:`log`.
           #. args (tuple): Positional arguments that fill the ``{}`` and ``{0}`` placeholders of *message*. They are
              text only, they are not stored as fields. Keyword arguments fill ``{name}`` and stay fields.
           #. exc_info (None, bool, BaseException, tuple, str, list): The exception to record, see :meth:`log`.
           #. countConstraint (None, number): Maximum number of times to log the given message.
           #. sinks (None, list): Names of the sinks to write to, ``CONSOLE_SINK`` and ``FILE_SINK`` for the built-in
              ones. None writes to every sink that is switched on. An empty list writes to none: the processors run and
              the record is kept as the last record.
           #. fields: The named values of the record, any number of keyword arguments, see :meth:`log`.

        :Returns:
            #. message (string): the logged message

        :Raises:
            #. TypeError: If *message* is callable, or *sinks* is not a list.
            #. ValueError: If a name in *sinks* is not registered.
        """
        return self._log_call(logType, message, args, fields, exc_info, countConstraint, False, 0, True, sinks)

    def opt(self, *, lazy=False, exception=None, depth=0):
        """
        Gives you a logger with options for the calls you make through it. The normal calls stay simple, and the options live here.

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
        """
        Logs an error instead of letting it stop the program. It works as a decorator and as a ``with`` block.

        The message and the traceback pass through your processors like any other record, see :meth:`add_processor`.

        .. code-block:: python

            @logger.catch
            def risky():
                raise ValueError("something went wrong")      ## logged, and the program continues

            @logger.catch(logType="critical", reraise=True)   ## logged, then raised again
            def very_risky(): ...

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
        """
        Returns a logger that remembers some values and adds them to every record it writes.

        In plain words: you tag a logger with what it is working for, such as a request, a user or a job. Every line it writes
        carries the tag, so you do not repeat the values in each call. The original logger does not change, and binding again adds
        to what is already bound.

        The plain text layout shows the values in brackets before the message, and the pretty layout after it. In JSON they are in
        ``context``, apart from the fields. The bound logger is immutable and safe to share between threads.

        .. code-block:: python

            log = logger.bind(request_id="r-42", user="ann")
            log.info("started")                    ## ... started request_id=r-42 user=ann
            log2 = log.bind(table="orders")        ## adds to what is already bound
            log3 = log.bind(request_id="new")      ## replaces request_id only

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
        Adds values to every record made inside a ``with`` block, without passing them to each call.

        This is :func:`pysimplelog.log_context.context`, see it for how the values follow threads and
        asynchronous tasks and how blocks nest.

        .. code-block:: python

            with logger.context(request_id="r-42"):
                logger.info("inside")              ## carries request_id

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
        """
        Waits until everything queued has been written, then flushes the streams. It returns whether it finished in time.

        Call it before the program ends if you use ``enqueue=True`` or ``threaded=True``. With ``enqueue`` it waits for the main
        queue, and each threaded output is given up to *timeout* seconds to empty its own queue.

        .. code-block:: python

            if not logger.flush(timeout=5):
                print("some records are still waiting")

        :Parameters:
            #. timeout (float): Seconds to wait at most for each queue to empty.
        """
        isDrained = True
        if self.__enqueue and self.__logQueue is not None and os.getpid() == self.__ownerPid:
            isDrained = self.__logQueue.join(timeout)
        # flush every registered sink
        for sink in self.__sinks.values():
            if sink.threaded:
                isDrained = sink.flush_threaded(timeout=timeout) and isDrained
            try:
                sink.handler.flush()
            except Exception as flushError:
                sys.stderr.write('pysimplelog WARNING: sink flush failed. Error: %s\n' % describe_error(flushError))
        return isDrained

    def _is_silent(self, logType, message, fields):
        """
        Says whether a log call can return at once, because no sink wants its log type.

        A call that the full path has to look at, a message that is a function or a field named ``fields`` or ``tback``,
        is never silent, so its error is raised as it is when the level is on.

        :Parameters:
            #. logType (str): The log type of the call.
            #. message (object): The message given by the caller.
            #. fields (dict): The keyword arguments of the call.

        :Returns:
            #. isSilent (bool): True when the call can return without doing anything.
        """
        activeSinks = self.__activeSinks.get(logType)
        if activeSinks is None or len(activeSinks) > 0 or namespaces.NEEDS_CHECK or callable(message):
            return False
        return not (fields and ('fields' in fields or 'tback' in fields))

    def info(self, message, *args, **kwargs):
        """
        Logs a message at the information level: normal things worth knowing. Same as ``log("info", ...)``.

        .. code-block:: python

            logger.info("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("info", message, kwargs):
            return message
        return self.log("info", message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """
        Logs a message at the information level: normal things worth knowing. It is another name for ``info``. Same as ``log("info", ...)``.

        .. code-block:: python

            logger.information("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("info", message, kwargs):
            return message
        return self.log("info", message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """
        Logs a message at the warning level: something unexpected that did not stop anything. Same as ``log("warn", ...)``.

        .. code-block:: python

            logger.warn("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("warn", message, kwargs):
            return message
        return self.log("warn", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """
        Logs a message at the warning level: something unexpected that did not stop anything. It is another name for ``warn``. Same as ``log("warn", ...)``.

        .. code-block:: python

            logger.warning("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("warn", message, kwargs):
            return message
        return self.log("warn", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """
        Logs a message at the error level: something failed. Same as ``log("error", ...)``.

        .. code-block:: python

            logger.error("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("error", message, kwargs):
            return message
        return self.log("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """
        Logs a message at the critical level: something failed so badly that the program may not go on. Same as ``log("critical", ...)``.

        .. code-block:: python

            logger.critical("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("critical", message, kwargs):
            return message
        return self.log("critical", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """
        Logs a message at the debug level: detail for finding a problem, usually hidden in production. Same as ``log("debug", ...)``.

        .. code-block:: python

            logger.debug("Order {} created", 7, customer="ann")

        :Parameters:
            #. message (str, callable): The text to log. Put ``{}`` or ``{name}`` where values should go. A
               function is also accepted: it is called to build the text only if the record is
               really written.
            #. args (tuple): Values that fill the ``{}`` places of the message, in order.
            #. kwargs (dict): Values that fill the ``{name}`` places of the message. They are also kept as
               fields of the record. The options of :meth:`Logger.log` (``exc_info``,
               ``countConstraint``) are accepted too.
        """
        if self._is_silent("debug", message, kwargs):
            return message
        return self.log("debug", message, *args, **kwargs)

    def exception(self, message, *args, logType='error', **fields):
        """
        Logs an error together with the traceback of the exception you are handling. Call it inside an ``except`` block.

        Logs a message with the exception being handled, at error level unless *logType* says otherwise.

        .. code-block:: python

            try:
                charge(order)
            except PaymentError:
                logger.exception("Payment of {} failed", order.id)

        :Parameters:
            #. message (str): The message, a template when arguments are given, see :meth:`log`.
            #. args: The positional values of the template.
            #. logType (str): The log type of the record. A field of that name cannot be given.
            #. fields: The structured values of the record.
        """
        if self._is_silent(logType, message, fields):
            return message
        return self.log(logType, message, *args, exc_info=True, **fields)



class SingleLogger(Logger):
    """
    A ``Logger`` that exists only once: every ``SingleLogger(...)`` in the program gives the same object. Use it when several
    modules must share one configuration without passing a logger around.

    .. code-block:: python

        from pysimplelog import SingleLogger

        log = SingleLogger("app")
        same = SingleLogger()            ## the same object, not a new one

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
