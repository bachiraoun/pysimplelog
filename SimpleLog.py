"""SimpleLog defines the Logger and SingleLogger classes for multi-sink,
thread-safe, formatted logging in Python applications.

Usage Examples
==============
    .. code-block:: python

        # import Logger
        from pysimplelog import Logger

        # initialize
        l=Logger("log test")

        # change log file basename from simplelog to mylog
        l.set_log_file_basename("mylog")

        # change log file extension from .log to .pylog
        l.set_log_file_extension("pylog")

        # Add new log types.
        l.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
        l.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
        l.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold"])

        # update error log type
        l.update_log_type(logType='error', color='pink', attributes=['underline','bold'])

        # print logger
        print(l, end="\\n\\n")

        # test logging
        l.info("I am info, called using my shortcut method.")
        l.log("info", "I am info, called using log method.")

        l.warn("I am warn, called using my shortcut method.")
        l.log("warn", "I am warn, called using log method.")

        l.error("I am error, called using my shortcut method.")
        l.log("error", "I am error, called using log method.")

        l.critical("I am critical, called using my shortcut method.")
        l.log("critical", "I am critical, called using log method.")

        l.debug("I am debug, called using my shortcut method.")
        l.log("debug", "I am debug, called using log method.")

        l.log("super critical", "I am super critical, called using log method because I have no shortcut method.")
        l.log("wrong", "I am wrong, called using log method because I have no shortcut method.")
        l.log("important", "I am important, called using log method because I have no shortcut method.")

        # print last logged messages
        print("")
        print("Last logged messages are:")
        print("=========================")
        print(l.lastLoggedMessage)
        print(l.lastLoggedDebug)
        print(l.lastLoggedInfo)
        print(l.lastLoggedWarning)
        print(l.lastLoggedError)
        print(l.lastLoggedCritical)

        # log data
        print("")
        print("Log random data and traceback stack:")
        print("====================================")
        l.info("Check out this data", data=list(range(10)))
        print("")

        # log error with traceback
        import traceback
        try:
            1/range(10)
        except Exception as err:
            l.error('%s (is this python ?)'%err, tback=traceback.extract_stack())




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
    ``bind()`` returns a thin wrapper that prepends key=value context pairs
    to every message without modifying the underlying logger.  Contexts are
    immutable and composable — each ``bind()`` call returns a new wrapper.

    .. code-block:: python

        from pysimplelog import Logger

        l = Logger("api-server", logToFile=False)

        ## attach request-level context once; use the bound logger everywhere
        def handle_request(requestId, user):
            log = l.bind(requestId=requestId, user=user)
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


catch() — Exception Capture
=============================
    ``catch()`` works as a **decorator**, a **parameterised decorator**, or
    a **context manager**.  It logs the exception and — by default — suppresses
    it so the application keeps running.

    .. code-block:: python

        from pysimplelog import Logger

        l = Logger("my-app", logToFile=False)

        ## ── 1. bare decorator — uses defaults (logType='error', reraise=False) ──
        @l.catch
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
        @l.catch(logType="critical", reraise=True)
        def connect_db(url):
            raise ConnectionError("timed out")

        try:
            connect_db("postgres://localhost/mydb")
        except ConnectionError:
            l.warn("falling back to read-only replica")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <CRITICAL> An exception was caught: timed out
        Traceback (most recent call last):
          File "app.py", line 15, in connect_db
        ConnectionError: timed out

        2024-01-01 12:00:00 - my-app <WARNING> falling back to read-only replica

    .. code-block:: python

        ## ── 3. context manager — exception suppressed, execution continues ───
        with l.catch(logType="warn", reraise=False):
            result = 1 / 0

        l.info("execution continues after suppressed exception")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <WARNING> An exception was caught: division by zero
        Traceback (most recent call last):
          File "app.py", line 21, in <module>
        ZeroDivisionError: division by zero

        2024-01-01 12:00:00 - my-app <INFO> execution continues after suppressed exception


add_sink() — Custom Output Sinks
===================================
    Any file-like object with a ``write()`` method can be added as a sink.
    Common uses: capturing logs to an in-memory buffer for testing, writing
    to a network socket, or tee-ing to a secondary log file.

    .. code-block:: python

        import io
        from pysimplelog import Logger

        l = Logger("my-app", logToFile=False)

        ## ── in-memory sink (useful in tests) ─────────────────────────────────
        buffer = io.StringIO()
        l.add_sink("memory", buffer)

        l.info("hello buffer")
        l.error("something went wrong")

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
        l.add_sink("audit", audit)
        l.warn("this goes to stdout, buffer, AND audit.log")

        ## ── remove a sink when no longer needed ───────────────────────────────
        l.remove_sink("memory")
        l.info("this no longer goes to the in-memory buffer")
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
        l = Logger("worker", enqueue=True, logToFile=False)

        for i in range(3):
            l.info("processed item %d" % i)
            ## returns immediately; I/O happens in the background thread

        ## block until all records have been written
        l.flush()

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - worker <INFO> processed item 0
        2024-01-01 12:00:00 - worker <INFO> processed item 1
        2024-01-01 12:00:00 - worker <INFO> processed item 2

    .. code-block:: python

        ## ── queue backpressure controls ───────────────────────────────────────

        ## drop records silently when queue is full
        l2 = Logger("bounded", enqueue=True, logToFile=False,
                    maxQueueSize=500, queueFullPolicy="drop")

        ## warn on stderr when a record is dropped
        l3 = Logger("noisy", enqueue=True, logToFile=False,
                    maxQueueSize=100, queueFullPolicy="warn")

        ## block the caller until a slot is free (2-second deadline)
        l4 = Logger("blocking", enqueue=True, logToFile=False,
                    maxQueueSize=100, queueFullPolicy="block",
                    queueBlockTimeout=2.0)

        l2.flush(); l3.flush(); l4.flush()

    **Output (stderr, when queue is full with policy="warn"):**

    .. code-block:: text

        pysimplelog WARNING: queue full, record dropped (1 total dropped)


callerInfo — Caller Tagging
==============================
    Set ``callerInfo=True`` to prepend the source file, line number, and
    function name to every log message automatically.

    .. code-block:: python

        from pysimplelog import Logger

        l = Logger("my-app", callerInfo=True, logToFile=False)

        def process_order(orderId):
            l.info("processing order %s" % orderId)

        process_order(42)

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <INFO> [orders.py:5 in process_order] processing order 42

    .. code-block:: python

        ## combine with bind() — caller tag and context both appear
        def handle_request(requestId):
            log = l.bind(requestId=requestId)
            log.debug("request started")

        handle_request("req-001")

    **Output:**

    .. code-block:: text

        2024-01-01 12:00:00 - my-app <DEBUG> [handler.py:3 in handle_request] [requestId=req-001] request started


"""
# python standard distribution imports
import os, sys, copy, re, atexit, threading, traceback, functools, inspect
from datetime import datetime

# python 2/3 queue compatibility
if sys.version_info >= (3, 0):
    import queue as _queue_module
else:
    import Queue as _queue_module

# python version dependant imports
if sys.version_info >= (3, 0):
    # This is python 3
    str        = str
    long       = int
    unicode    = str
    bytes      = bytes
    basestring = str
else:
    str        = str
    unicode    = unicode
    bytes      = str
    long       = long
    basestring = basestring

# import pysimplelog version
try:
    from __pkginfo__ import __version__
except ImportError:
    from .__pkginfo__ import __version__


# sentinel object used to signal the enqueue worker thread to stop
_QUEUE_STOP = object()

# sentinel keys for the two built-in sinks inside Logger.__sinks.
# Integer type guarantees they can never clash with user-supplied
# string sink names — different types, different hash buckets.
_SINK_STDOUT = -1   # key for the built-in stdout sink
_SINK_FILE   =  0   # key for the built-in file sink

# useful definitions
def _is_number(number):
    """Return True if value can be interpreted as a Python number."""
    if isinstance(number, (int, long, float, complex)):
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


def _get_caller_str():
    """Walk the call stack and return a formatted caller string.

    Finds the first frame whose file is not SimpleLog.py -- that is the
    line in user code that triggered the log call. Uses inspect.stack()
    with context=0 (no source lines read from disk) for efficiency.
    Only called when Logger.callerInfo is True.

    :Returns:
        #. result (str): e.g. '[routes.py:142 in handle_request] ' including
        trailing space so it sits neatly before the message. Returns an
        empty string if the frame cannot be determined.
    """
    try:
        for frameInfo in inspect.stack(context=0):
            # frameInfo[1] is filename, [2] is lineno, [3] is function name
            if os.path.abspath(frameInfo[1]) != _THIS_FILE:
                fName = os.path.basename(frameInfo[1])
                fLine = frameInfo[2]
                fFunc = frameInfo[3]
                return '[%s:%d in %s] ' % (fName, fLine, fFunc)
    except Exception:
        pass
    return ''


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
        result (str): Sanitized string. Non-strings are coerced via '%s'
        formatting before control-character stripping, so a str is always returned.
    """
    if not isinstance(message, basestring):
        message = '%s' % (message,)
    if '\x1b' not in message and '\x00' not in message and '\r' not in message:
        return message
    return _CONTROL_CHAR_RE.sub('', message)



class _Sink(object):
    """Internal descriptor for a single log output target.

    Not part of the public API. Created and managed exclusively by
    Logger. Every writable destination — stdout, file, or any
    user-supplied handler — is represented as a _Sink instance stored
    under a key in Logger.__sinks:

      _SINK_STDOUT (-1) : the built-in stdout sink
      _SINK_FILE   ( 0) : the built-in rotating file sink
      str               : any user-added sink (unique string name)

    :Parameters:
        #. handler (file-like): Object implementing write(str) and
           flush(). The logger calls both after every record that
           passes the level and flag filters.
        #. enabled (bool): Master switch. When False the sink is
           skipped entirely during dispatch without inspecting any
           other field.
        #. logTypeFlags (dict): Mapping of {logType (str): bool}.
           Controls per-type enable/disable for this sink only.
           Missing keys default to True (enabled).
        #. minLevel (int or None): Minimum level integer for this
           sink. Records whose level is below this value are not
           dispatched. None means no floor.
        #. maxLevel (int or None): Maximum level integer for this
           sink. Records whose level is above this value are not
           dispatched. None means no ceiling.
        #. isFileSink (bool): True only for _SINK_FILE. Signals the
           dispatch loop to run rotation checks after each write.
           Always False for stdout and user-added sinks.
    """

    def __init__(self, handler, enabled, logTypeFlags,
                 minLevel=None, maxLevel=None, sinkType='stdout'):
        self.handler      = handler
        self.enabled      = enabled
        self.logTypeFlags = logTypeFlags
        self.minLevel     = minLevel
        self.maxLevel     = maxLevel
        self.sinkType     = sinkType   # 'stdout' | 'file' | 'user'

    @property
    def isFileSink(self):
        """Backward-compatible read-only property. True when sinkType is 'file'."""
        return self.sinkType == 'file'

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
        self._logger  = logger
        self._logType = logType
        self._reraise = reraise
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            tbackStr = traceback.format_exc()
            self._logger.log(
                self._logType,
                '%s: %s' % (self._message, exc_val),
                tback=tbackStr,
            )
            return not self._reraise   # True suppresses; False re-raises
        return False

    def __call__(self, func):
        """Allow the context manager instance to be used as a decorator."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with _CatchContext(self._logger, self._logType,
                               self._reraise, self._message):
                return func(*args, **kwargs)
        return wrapper


class _BoundLogger(object):
    """Lightweight context-aware wrapper returned by Logger.bind().

    Prepends a fixed set of key=value pairs to every message before
    delegating to the parent Logger. The wrapper holds no queue, no
    file handle, and no configuration state of its own -- all I/O is
    performed by the parent Logger unchanged.

    Instances are immutable after construction and therefore inherently
    thread-safe. Nested bind() calls produce a new _BoundLogger with a
    merged context dict; the originals are never modified.

    Do not instantiate directly -- use Logger.bind() or _BoundLogger.bind().
    """

    def __init__(self, parent, context):
        """Initialise a bound logger wrapping a parent Logger.

        :Parameters:
            #. parent (Logger or _BoundLogger): The logger that will
               perform all actual I/O. Always store the root Logger so
               the delegation chain stays one hop deep regardless of
               how many bind() calls are chained.
            #. context (dict): Key-value pairs to prepend to every
               message. Values are converted to strings at prefix-build
               time via str().
        """
        self.__parent  = parent
        self.__context = dict(context)   # defensive copy -- never mutate

    # ── internal helpers ────────────────────────────────────────────

    def __build_prefix(self):
        """Build the bracketed context prefix string.

        :Returns:
            result (str): e.g. '[requestId=abc user=mike] '.
            Empty string when context is empty.
        """
        if not self.__context:
            return ''
        pairs = ' '.join('%s=%s' % (k, v) for k, v in self.__context.items())
        return '[' + pairs + '] '

    def __prefixed(self, message):
        """Prepend the context prefix to a message.

        :Parameters:
            #. message (object): The raw message. Non-string types are
               coerced via str() so the prefix concatenation is safe.

        :Returns:
            result (str): Prefix + message as a single string, or the
            original message unchanged when context is empty.
        """
        prefix = self.__build_prefix()
        if not prefix:
            return message
        return prefix + str(message)

    # ── context nesting ──────────────────────────────────────────────

    def bind(self, **extra):
        """Return a new _BoundLogger with additional context key-value pairs.

        The new wrapper shares the same parent Logger. Existing context
        keys are preserved; any key present in both dicts takes the value
        from the extra kwargs (right-hand side wins).

        :Parameters:
            #. **extra: Arbitrary key-value pairs to add or override.

        :Returns:
            result (_BoundLogger): A new wrapper with merged context.
        """
        merged = dict(self.__context)
        merged.update(extra)
        return _BoundLogger(self.__parent, merged)

    # ── core logging ─────────────────────────────────────────────────

    def log(self, logType, message, data=None, tback=None, countConstraint=None):
        """Log a prefixed message at the given logType.

        Prepends the context prefix then delegates entirely to
        parent.log(). All level filtering, count constraints,
        backpressure, and I/O are handled by the parent unchanged.

        :Parameters:
            #. logType (string): A defined log type.
            #. message (string): The message to log.
            #. data (None, object): Optional data payload.
            #. tback (None, str, list): Optional traceback string.
            #. countConstraint (None, number): Max times to log this message.

        :Returns:
            result (string): The logged message returned by parent.log().
        """
        return self.__parent.log(
            logType,
            self.__prefixed(message),
            data=data,
            tback=tback,
            countConstraint=countConstraint,
        )

    def force_log(self, logType, message, data=None, tback=None,
                  stdout=True, file=True):
        """Force-log a prefixed message, bypassing level checks.

        Prepends the context prefix then delegates to parent.force_log().

        :Parameters:
            #. logType (string): A defined log type.
            #. message (string): The message to log.
            #. data (None, object): Optional data payload.
            #. tback (None, str, list): Optional traceback string.
            #. stdout (boolean): Whether to force stdout output.
            #. file (boolean): Whether to force file output.

        :Returns:
            result (string): The logged message returned by parent.force_log().
        """
        return self.__parent.force_log(
            logType,
            self.__prefixed(message),
            data=data,
            tback=tback,
            stdout=stdout,
            file=file,
        )

    # ── shortcut methods (mirrors Logger shortcuts) ──────────────────

    def info(self, message, *args, **kwargs):
        """Log at info level with context prefix."""
        return self.log('info', message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """Log at info level with context prefix (alias for info)."""
        return self.log('info', message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """Log at warn level with context prefix."""
        return self.log('warn', message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log at warn level with context prefix (alias for warn)."""
        return self.log('warn', message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log at error level with context prefix."""
        return self.log('error', message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log at critical level with context prefix."""
        return self.log('critical', message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Log at debug level with context prefix."""
        return self.log('debug', message, *args, **kwargs)

    # ── exception capture ────────────────────────────────────────────

    def catch(self, func=None, logType='error', reraise=False,
              message='An exception was caught'):
        """Decorator and context manager that catches and logs exceptions.

        Identical to Logger.catch() but the logged exception line
        carries the bound context prefix automatically, because
        _CatchContext calls self.log() on this _BoundLogger rather
        than on the parent Logger directly.

        :Parameters:
            #. func (None, callable): Decorated function for bare-decorator use.
            #. logType (string): Log type for the caught exception entry.
            #. reraise (boolean): Whether to re-raise after logging.
            #. message (string): Prefix text for the exception log line.

        :Returns:
            result: A _CatchContext usable as decorator or context manager.
        """
        ctx = _CatchContext(self, logType=logType,
                            reraise=reraise, message=message)
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
    def context(self):
        """A copy of this wrapper's context dictionary.

        Returns a fresh copy so callers cannot accidentally mutate the
        internal state of this _BoundLogger.

        :Returns:
            result (dict): Copy of the current context key-value pairs.
        """
        return dict(self.__context)


class Logger(object):
    """
    This is simplelog main Logger class definition.\n

    A logging is constituted of a header a message and a footer.
    In the current implementation the footer is empty and the header is as the following:\n
    date time - loggerName <logTypeName>\n

    In order to change any of the header or the footer, '_get_header' and '_get_footer'
    methods must be overloaded.

    When used in a Python application, it is advisable to use the Logger singleton
    implementation rather than Logger itself. If no subclassing is needed, simply
    import the singleton:

    .. code-block:: python

        from pysimplelog import SingleLogger as Logger


    Basic usage example:

    .. code-block:: python

        from pysimplelog import Logger

        ## create a logger instance
        l = Logger("my-app")

        ## log at built-in levels
        l.info("application started")
        l.warn("disk usage above 80 percent")
        l.error("connection refused")

        ## add a custom log type
        l.add_log_type("trace", name="TRACE", level=5, color="cyan")
        l.log("trace", "entering request handler")

        ## bind context for structured logging
        requestLogger = l.bind(requestId="abc123", user="alice")
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
       #. logToFile (boolean): Whether to log to to file.
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
       #. queueFullPolicy (string): Determines caller behaviour when the
          queue is full (only applies when maxQueueSize is not None).
          Four values are accepted:
          ``'block'``  -- the calling thread parks until space opens.
          If queueBlockTimeout is set, the park is bounded; after that
          many seconds the message is dropped and a warning is written
          to stderr. If queueBlockTimeout is None the thread parks forever
          (safe but dangerous if the worker dies).
          ``'drop'``   -- the record is silently discarded and the
          droppedMessages counter is incremented. Zero latency impact.
          ``'warn'``   -- same as drop but also writes one line to stderr
          so the loss is visible without being fatal.
          ``'raise'``  -- raises queue.Full to the caller so it can decide
          what to do. The caller must handle the exception.
          Default is ``'block'``. Can be updated at runtime via
          set_queue_full_policy().
       #. queueBlockTimeout (None, number): Seconds to wait before giving
          up when queueFullPolicy is ``'block'``. None (default) means wait
          indefinitely. When a positive number is given and the timeout
          expires the message is dropped, droppedMessages is incremented,
          and a single warning line is written to stderr. Has no effect
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
       #. \\*args: This is used to send non-keyworded variable length argument
           list to custom initialize. args will be parsed and used in
           custom_init method.
       #. \\**kwargs: This allows passing keyworded variable length of
           arguments to custom_init method. kwargs can be anything other
           than __init__ arguments.
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
                       *args, **kwargs):
        # set last logged message
        self.__lastLogged    = {}
        # sink registry and cache — pre-created empty so every setter
        # called during __init__ can safely guard with
        # "if _SINK_STDOUT in self.__sinks". The real _Sink objects are
        # inserted at the END of __init__ (Phase 3 block).
        self.__sinks       = {}
        self.__activeSinks = {}
        # instantiate file stream
        self.__logFileStream = None
        # rotation lock — guards the multi-step check/rotate/open sequence
        self.__rotationLock = threading.RLock()
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
        # custom initialize
        self.custom_init( *args, **kwargs )
        # add logTypes
        if logTypes is not None:
            if not isinstance(logTypes, dict):
                raise TypeError("logTypes must be None or a dictionary")
            if not all([isinstance(lt, basestring) for lt in logTypes]):
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
        # enqueue mode — validate policy params first so errors surface early
        if not isinstance(enqueue, bool):
            raise TypeError("enqueue must be a boolean")
        self.__enqueue          = enqueue
        self.__logQueue         = None
        self.__logWorker        = None
        self.__droppedMessages  = 0
        self.__droppedLock      = threading.Lock()
        # validate and store queue policy settings via setters so all
        # validation logic lives in one place
        self.__maxQueueSize      = None   # set by setter below
        self.__queueFullPolicy   = None   # set by setter below
        self.__queueBlockTimeout = None   # set by setter below
        self.set_queue_full_policy(queueFullPolicy)
        self.set_queue_block_timeout(queueBlockTimeout)
        self.set_max_queue_size(maxQueueSize)   # must come after policy set
        if self.__enqueue:
            self.__logQueue  = _queue_module.Queue(
                maxsize=self.__maxQueueSize if self.__maxQueueSize is not None else 0
            )
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
        # ── unified sink registry ─────────────────────────────────────────
        # Both built-in sinks are always created. The logTypeFlags dicts
        # are the SAME objects as __logTypeStdoutFlags/__logTypeFileFlags
        # so __update_stdout_flags() and __update_file_flags() keep them
        # current automatically — no extra code required.
        # Scalar fields (enabled, minLevel, maxLevel) are Phase-3 snapshots;
        # Phase 4 setters will write to both old attributes and sink fields
        # simultaneously so the cache stays accurate after config changes.
        self.__sinks = {
            _SINK_STDOUT: _Sink(
                handler      = self.__stdout,
                enabled      = self.__logToStdout,
                logTypeFlags = self.__logTypeStdoutFlags,  # shared dict
                minLevel     = self.__stdoutMinLevel,
                maxLevel     = self.__stdoutMaxLevel,
                sinkType     = 'stdout',
            ),
            _SINK_FILE: _Sink(
                handler      = self.__logFileStream,       # None until first write
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

    def __str__(self):
        # create version
        string  = self.__class__.__name__+" (Version "+str(__version__)+")"
        string += "\n - Log To Stdout: Flag (%s) - Min Level (%s) - Max Level (%s)"%(self.__logToStdout,self.__stdoutMinLevel,self.__stdoutMaxLevel)
        string += "\n - Log To File:   Flag (%s) - Min Level (%s) - Max Level (%s)"%(self.__logToFile,self.__fileMinLevel,self.__fileMaxLevel)
        string += "\n                  File Size (%s) - First Number (%s) - Roll (%s)"%(self.__logFileMaxSize,self.__logFileFirstNumber,self.__logFileRoll)
        string += "\n                  Message Max Size (%s) - Data Max Size (%s)"%(self.__maxMessageSize,self.__maxDataSize)
        string += "\n - Enqueue mode: %s  Queue max size: %s  Policy: %s  Block timeout: %s  Dropped: %s"%(self.__enqueue, self.__maxQueueSize, self.__queueFullPolicy,
          self.__queueBlockTimeout, self.__droppedMessages)
        string += "\n - Caller info: %s"%(self.__callerInfo,)
        string += "\n                  Current log file (%s)"%(self.__logFileName)
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

    def _flush_atexit_logfile(self):
        """Drain the queue and flush all open streams at Python interpreter shutdown.

        Registered with atexit at the end of __init__. Sends the stop sentinel
        to the background worker thread (if enqueue mode is active) and waits
        up to 5 seconds for it to finish. Then flushes and closes the log file
        stream, and flushes any user-supplied sinks (their lifecycle is owned
        by the caller, so they are flushed but never closed here).
        """
        if self.__enqueue and self.__logQueue is not None:
            self.__logQueue.put(_QUEUE_STOP)
            self.__logWorker.join(timeout=5)
        if self.__logFileStream is not None:
            self.__flush_stream(self.__logFileStream)
            self.__logFileStream.close()
        # flush user sinks at exit — we never close them (caller owns lifecycle)
        for sink in self.__sinks.values():
            if sink.sinkType == 'user' and sink.handler is not None:
                self.__flush_stream(sink.handler)

    @property
    def lastLogged(self):
        """Return a dictionary of the last logged message for each log type."""
        d = copy.deepcopy(self.__lastLogged)
        d.pop(-1, None)
        return d

    @property
    def lastLoggedMessage(self):
        """Get last logged message of any type. Returns None if no message was logged."""
        return self.__lastLogged.get(-1, None)

    @property
    def lastLoggedDebug(self):
        """Get last logged message of type 'debug'. Returns None if no message was logged."""
        return self.__lastLogged.get('debug', None)

    @property
    def lastLoggedInfo(self):
        """Get last logged message of type 'info'. Returns None if no message was logged."""
        return self.__lastLogged.get('info', None)

    @property
    def lastLoggedWarning(self):
        """Get last logged message of type 'warn'. Returns None if no message was logged."""
        return self.__lastLogged.get('warn', None)

    @property
    def lastLoggedError(self):
        """Get last logged message of type 'error'. Returns None if no message was logged."""
        return self.__lastLogged.get('error', None)

    @property
    def lastLoggedCritical(self):
        """Get last logged message of type 'critical'. Returns None if no message was logged."""
        return self.__lastLogged.get('critical', None)

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
        to find the first frame outside SimpleLog.py and prepends a
        ``[file:line in func]`` tag before the message. The overhead is
        roughly 10-30 us per call. Default is False.
        """
        return self.__callerInfo

    @property
    def maxQueueSize(self):
        """Maximum number of records the queue may hold, or None if unbounded.

        Returns None when enqueue mode is not active.
        """
        return self.__maxQueueSize

    @property
    def queueFullPolicy(self):
        """Active policy when the queue is full.

        One of ``'block'``, ``'drop'``, ``'warn'``, ``'raise'``.
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
        return self.__logQueue.qsize()

    @property
    def droppedMessages(self):
        """Cumulative count of log records dropped due to a full queue.

        Accumulates for the lifetime of the logger and is never reset.
        Always 0 when enqueue mode is not active or maxQueueSize is None.
        """
        with self.__droppedLock:
            return self.__droppedMessages

    @property
    def logTypes(self):
        """List of all defined log types."""
        return list(self.__logTypeNames)

    @property
    def logLevels(self):
        """dictionary copy of all defined log types levels."""
        return copy.deepcopy(self.__logTypeLevels)

    @property
    def logTypeFileFlags(self):
        """dictionary copy of all defined log types logging to a file flags."""
        return copy.deepcopy(self.__logTypeFileFlags)

    @property
    def logTypeStdoutFlags(self):
        """dictionary copy of all defined log types logging to Standard output flags."""
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
        """dictionary copy of forced flags of logging to standard output."""
        return copy.deepcopy(self.__forcedStdoutLevels)

    @property
    def forcedFileLevels(self):
        """dictionary copy of forced flags of logging to file."""
        return copy.deepcopy(self.__forcedFileLevels)

    @property
    def logTypeNames(self):
        """dictionary copy of all defined log types logging names."""
        return copy.deepcopy(self.__logTypeNames)

    @property
    def logTypeLevels(self):
        """dictionary copy of all defined log types levels showing when logging."""
        return copy.deepcopy(self.__logTypeLevels)

    @property
    def logTypeFormat(self):
        """dictionary copy of all defined log types format showing when logging."""
        return copy.deepcopy(self.__logTypeFormat)

    @property
    def name(self):
        """logger name."""
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
        if _SINK_STDOUT in self.__sinks:
            return self.__sinks[_SINK_STDOUT].handler
        return self.__stdout

    @property
    def sinks(self):
        """Shallow-copy snapshot of the unified sink registry.

        Keys: ``_SINK_STDOUT`` (-1) and ``_SINK_FILE`` (0) for the two
        built-in sinks; string keys for any user-added sinks (Phase 9).
        Values are live ``_Sink`` instances — do not mutate them directly;
        use the public setter API to change routing configuration.
        """
        return dict(self.__sinks)

    @property
    def activeSinks(self):
        """Read-only snapshot of the active-sink cache.

        Returns a dict mapping each log-type name to the list of ``_Sink``
        instances that will receive messages of that type. The cache is
        rebuilt automatically whenever routing configuration changes.
        """
        return {lt: list(sinks) for lt, sinks in self.__activeSinks.items()}

    @property
    def logFileName(self):
        """currently used log file name."""
        return self.__logFileName

    @property
    def logFileBasename(self):
        """log file basename."""
        return self.__logFileBasename

    @property
    def logFileExtension(self):
        """log file extension."""
        return self.__logFileExtension

    @property
    def logFileMaxSize(self):
        """maximum allowed logfile size in megabytes."""
        return self.__logFileMaxSize

    @property
    def logMessageMaxSize(self):
        """maximum allowed message character count. None means no limit."""
        return self.__maxMessageSize

    @property
    def logDataMaxSize(self):
        """maximum allowed data string character count. None means no limit."""
        return self.__maxDataSize

    @property
    def logFileFirstNumber(self):
        """log file first number"""
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
        """
        if not isinstance(callerInfo, bool):
            raise TypeError("callerInfo must be a boolean")
        self.__callerInfo = callerInfo

    def set_max_queue_size(self, maxQueueSize):
        """Set the maximum number of records the internal queue may hold.

        Can be called at any time -- takes effect on the very next log()
        call because Python's queue.Queue checks maxsize dynamically on
        every put(). Setting to None removes the cap entirely.

        :Parameters:
            #. maxQueueSize (None, integer): Maximum queue depth. Must be
               a positive integer or None. Zero is not accepted because it
               is ambiguous (CPython treats Queue(maxsize=0) as unbounded).
        """
        if maxQueueSize is not None:
            if not isinstance(maxQueueSize, int) or isinstance(maxQueueSize, bool):
                raise TypeError("maxQueueSize must be a positive integer or None")
            if maxQueueSize <= 0:
                raise ValueError("maxQueueSize must be a positive integer, got %d" % maxQueueSize)
        self.__maxQueueSize = maxQueueSize
        # sync the live queue object if one already exists
        if self.__logQueue is not None:
            self.__logQueue.maxsize = maxQueueSize if maxQueueSize is not None else 0

    def set_queue_full_policy(self, queueFullPolicy):
        """Set the backpressure policy applied when the queue is full.

        Can be changed at runtime -- takes effect on the very next log()
        call that finds the queue at capacity.

        :Parameters:
            #. queueFullPolicy (string): One of four values:

               ``'block'``  -- the calling thread parks until a slot opens.
               If queueBlockTimeout is set, parking is bounded; after that
               many seconds the record is dropped and one warning line is
               written to stderr. If queueBlockTimeout is None the thread
               parks indefinitely -- safe against message loss but risky if
               the worker thread dies.

               ``'drop'``   -- the record is silently discarded. The
               droppedMessages counter is incremented so you can detect
               loss after the fact via the droppedMessages property.

               ``'warn'``   -- same as ``'drop'`` but also writes a single
               line to sys.stderr so the loss is immediately visible in
               terminal output without being fatal to the caller.

               ``'raise'``  -- raises queue.Full to the caller. The caller
               must handle the exception. Useful when the caller has its
               own retry or circuit-breaker logic.
        """
        validPolicies = ('block', 'drop', 'warn', 'raise')
        if not isinstance(queueFullPolicy, basestring):
            raise TypeError("queueFullPolicy must be a string, one of %s" % str(validPolicies))
        if queueFullPolicy not in validPolicies:
            raise ValueError("queueFullPolicy must be one of %s, got '%s'"
                             % (str(validPolicies), queueFullPolicy))
        self.__queueFullPolicy = queueFullPolicy

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
        """
        if queueBlockTimeout is not None:
            if not _is_number(queueBlockTimeout):
                raise TypeError("queueBlockTimeout must be a positive number or None")
            if float(queueBlockTimeout) <= 0:
                raise ValueError("queueBlockTimeout must be positive, got %s" % queueBlockTimeout)
        self.__queueBlockTimeout = queueBlockTimeout

    def set_timezone(self, timezone):
        """
        Set the logging timezone.

        :Parameters:
            #. timezone (None, str): Logging time timezone. If provided,
               pytz must be installed and it must be the timezone name. If not
               provided, the machine default timezone will be used.
        """
        if timezone is not None:
            if not isinstance(timezone, basestring):
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

    def is_logType(self, logType):
        """Deprecated alias for is_log_type().

        .. deprecated::
            Use ``is_log_type(logType)`` instead. This camelCase alias will
            be removed in the next major version.
        """
        import warnings
        warnings.warn(
            "is_logType() is deprecated and will be removed in the next major "
            "version. Use is_log_type() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.is_log_type(logType)

    def update(self, **kwargs):
        """Update logger general parameters using key value pairs.
        Updatable parameters are name, flush, stdout, logToStdout, logFileRoll,
        logToFile, logFileMaxSize, stdoutMinLevel, stdoutMaxLevel, fileMinLevel,
        fileMaxLevel and logFileFirstNumber.
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


    @property
    def parameters(self):
        """get a dictionary of logger general parameters. The same dictionary
        can be used to update another logger instance using update method.

        The returned dict includes a ``userSinks`` key whose value is a dict
        mapping each user-added sink name to its current configuration snapshot
        (enabled, minLevel, maxLevel, logTypeFlags). Built-in sinks are not
        included there; they are described by the surrounding keys.
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
                "flush":self.__flush,
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
                "userSinks":userSinks}


    def custom_init(self, *args, **kwargs):
        """
        Custom initialize abstract method. This method is called at the end of
        initialization. Override it to perform application-specific setup on
        Logger instances.

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
        """
        if not isinstance(name, basestring):
            raise TypeError("name must be a string")
        self.__name = name

    def set_flush(self, flush):
        """
        Set the logger flush flag.

        :Parameters:
           #. flush (boolean): Whether to always flush the logging streams.
        """
        if not isinstance(flush, bool):
            raise TypeError("flush must be boolean")
        self.__flush = flush

    def set_stdout(self, stream=None):
        """
        Set the logger standard output stream.

        :Parameters:
           #. stream (None, stream): The standard output stream. If None, system standard
              output will be set automatically. Otherwise any object with read and write
              methods can be passed.
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
            self.__sinks[_SINK_STDOUT].handler = self.__stdout

    def set_log_to_stdout_flag(self, logToStdout):
        """
        Set the logging to the defined standard output flag. When set to False,
        no logging to  standard output will happen regardless of a logType
        standard output flag.

        :Parameters:
           #. logToStdout (boolean): Whether to log to the standard output stream.
        """
        if not isinstance(logToStdout, bool):
            raise TypeError("logToStdout must be boolean")
        self.__logToStdout = logToStdout
        if _SINK_STDOUT in self.__sinks:
            self.__sinks[_SINK_STDOUT].enabled = logToStdout
            self.__rebuild_active_sinks()

    def set_log_to_file_flag(self, logToFile):
        """
        Set the logging to a file general flag. When set to False, no logging
        to file will happen regardless of a logType file flag.

        :Parameters:
           #. logToFile (boolean): Whether to log to to file.
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
           #. fileFlag (boolean): Whether to log to to file.
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
        """
        if logFileRoll is not None:
            if not isinstance(logFileRoll, int):
                raise TypeError("logFileRoll must be None or integer")
            if logFileRoll<=0:
                raise ValueError("integer logFileRoll must be >0")
        self.__logFileRoll = logFileRoll

    def set_log_file(self, logfile):
        """
        Set the log file full path including directory path basename and extension.

        :Parameters:
           #. logFile (string): the full log file path including basename and
              extension. If this is given, all of logFileBasename and logFileExtension
              will be discarded. logfile is equivalent to logFileBasename.logFileExtension
        """
        if not isinstance(logfile, basestring):
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
        """
        if not isinstance(logFileExtension, basestring):
            raise TypeError("logFileExtension must be a basestring")
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
        # set log file name
        self.__set_log_file_name()

    def set_log_file_basename(self, logFileBasename):
        """
        Set the log file basename.

        :Parameters:
           #. logFileBasename (string): Logging file directory path and file basename.
              A logging file full name is set as logFileBasename.logFileExtension
        """
        self.__set_log_file_basename(logFileBasename)
        # set log file name
        self.__set_log_file_name()

    def __set_log_file_basename(self, logFileBasename):
        if not isinstance(logFileBasename, basestring):
            raise TypeError("logFileBasename must be a basestring")
        self.__logFileBasename = _normalize_path(logFileBasename)#logFileBasename

    def __set_log_file_name(self):
        """Automatically set logFileName attribute"""
        with self.__rotationLock:
            # ensure directory exists
            logDir, _ = os.path.split(self.__logFileBasename)
            if len(logDir) and not os.path.exists(logDir):
                os.makedirs(logDir)
            # get existing logfiles
            numsLUT  = {}
            filesLUT = {}
            ordered  = []
            if not len(logDir) or os.path.isdir(logDir):
                listDir = os.listdir(logDir) if len(logDir) else os.listdir('.')
                for f in listDir:
                    p = os.path.join(logDir,f)
                    if not os.path.isfile(p):
                        continue
                    if re.match(r"^{bsn}(_\d+)?\.{ext}$".format(bsn=re.escape(self.__logFileBasename), ext=re.escape(self.__logFileExtension)), p) is None:
                        continue
                    n = p.split(self.__logFileBasename)[1].split('.%s'%self.__logFileExtension)[0]
                    n = int(n[1:]) if len(n) else ''
                    if n in numsLUT:
                        raise RuntimeError("filelog number is found in LUT shouldn't have happened. PLEASE REPORT BUG")
                    numsLUT[n]  = p
                    filesLUT[p] = n
                ordered = ([''] if '' in numsLUT else []) + sorted([n for n in numsLUT if isinstance(n, int)])
                ordered = [numsLUT[n] for n in ordered]
            # get last file number
            if len(ordered):
                number = filesLUT[ordered[-1]]
            else:
                number = self.__logFileFirstNumber
            # limit number of log files to logFileRoll
            if self.__logFileRoll is not None:
                while len(ordered)>self.__logFileRoll:
                    path = ordered.pop(0)
                    try:
                        os.remove(path)
                    except (FileNotFoundError, OSError):
                        pass
                if len(ordered) == self.__logFileRoll and self.__logFileMaxSize is not None:
                    try:
                        fileSizeMB = os.stat(ordered[-1]).st_size / (1024.**2)
                    except (FileNotFoundError, OSError):
                        fileSizeMB = 0.0
                    if fileSizeMB >= self.__logFileMaxSize:
                        path = ordered.pop(0)
                        try:
                            os.remove(path)
                        except (FileNotFoundError, OSError):
                            pass
                        if isinstance(number, int):
                            number = number + 1
            # temporarily set self.__logFileName
            if not isinstance(number, int):
                self.__logFileName = self.__logFileBasename+"."+self.__logFileExtension
                number = -1
            else:
                self.__logFileName = self.__logFileBasename+"_"+str(number)+"."+self.__logFileExtension
            # check temporarily set logFileName file size
            if self.__logFileMaxSize is not None:
                while os.path.isfile(self.__logFileName):
                    if os.stat(self.__logFileName).st_size/(1024.**2) < self.__logFileMaxSize:
                        break
                    number += 1
                    self.__logFileName = self.__logFileBasename+"_"+str(number)+"."+self.__logFileExtension
            # create log file stream
            if self.__logFileStream is not None:
                try:
                    self.__logFileStream.close()
                except OSError:
                    pass
            self.__logFileStream = None

    def set_log_file_maximum_size(self, logFileMaxSize):
        """
        Set the log file maximum size in megabytes

        :Parameters:
           #. logFileMaxSize (None, number): The maximum size in Megabytes
              of a logging file. Once exceeded, another logging file as
              logFileBasename_N.logFileExtension will be created.
              Where N is an automatically incremented number. If None or a
              negative number is given, the logging file will grow
              indefinitely
        """
        if logFileMaxSize is not None:
            if not _is_number(logFileMaxSize):
                raise TypeError("logFileMaxSize must be a number")
            logFileMaxSize = float(logFileMaxSize)
            if logFileMaxSize <=0:
                logFileMaxSize = None
        #assert logFileMaxSize>=1, "logFileMaxSize minimum size is 1 megabytes"
        self.__logFileMaxSize = logFileMaxSize

    def set_maximum_message_size(self, maxMessageSize):
        """Set the maximum number of characters allowed in a single log message.

        :Parameters:
            #. maxMessageSize (None, integer): Maximum character count for the
               message string. If None, no limit is applied. Messages exceeding
               this limit are truncated and '[truncated]' is appended. Must be
               a positive integer when given.
        """
        if maxMessageSize is not None:
            if not isinstance(maxMessageSize, int) or maxMessageSize <= 0:
                raise TypeError("maxMessageSize must be None or a positive integer")
        self.__maxMessageSize = maxMessageSize

    def set_maximum_data_size(self, maxDataSize):
        """Set the maximum number of characters allowed in the string
        representation of the data argument passed to log() or force_log().

        :Parameters:
            #. maxDataSize (None, integer): Maximum character count for the
               string representation of data. If None, no limit is applied.
               Data strings exceeding this limit are truncated and '[truncated]'
               is appended. Must be a positive integer when given.
        """
        if maxDataSize is not None:
            if not isinstance(maxDataSize, int) or maxDataSize <= 0:
                raise TypeError("maxDataSize must be None or a positive integer")
        self.__maxDataSize = maxDataSize

    def set_log_file_first_number(self, logFileFirstNumber):
        """
        Set log file first number

        :Parameters:
            #. logFileFirstNumber (None, integer): first log file number 'N' in
               logFileBasename_N.logFileExtension. If None is given then
               first log file will be logFileBasename.logFileExtension and once
               logFileMaxSize is reached second log file will be
               logFileBasename_0.logFileExtension and so on and so forth.
               If number is given it must be an integer >=0
        """
        if logFileFirstNumber is not None:
            if not isinstance(logFileFirstNumber, int):
                raise TypeError("logFileFirstNumber must be None or an integer")
            if logFileFirstNumber<0:
                raise ValueError("logFileFirstNumber integer must be >=0")
        self.__logFileFirstNumber = logFileFirstNumber

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
                if not isinstance(sinkName, basestring):
                    raise TypeError("each entry in sinks must be a string sink name")
                if sinkName not in self.__sinks:
                    raise ValueError("sink '%s' is not registered" % sinkName)
                if self.__sinks[sinkName].sinkType != 'user':
                    raise ValueError("sink '%s' is a built-in sink; use stdoutFlag/fileFlag for built-ins" % sinkName)
        if not (stdoutFlag or fileFlag or sinks):
            return
        # check level
        if level is not None:
            if isinstance(level, basestring):
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
                if not isinstance(sinkName, basestring):
                    raise TypeError("each entry in sinks must be a string sink name")
                if sinkName not in self.__sinks:
                    raise ValueError("sink '%s' is not registered" % sinkName)
                if self.__sinks[sinkName].sinkType != 'user':
                    raise ValueError("sink '%s' is a built-in sink; use stdoutFlag/fileFlag for built-ins" % sinkName)
        if not (stdoutFlag or fileFlag or sinks):
            return
        # check level
        if level is not None:
            if isinstance(level, basestring):
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
        stdoutkeys = list(self.__forcedStdoutLevels)
        for logType, l in self.__logTypeLevels.items():
            if logType not in stdoutkeys:
                minOk = (self.__stdoutMinLevel is None) or (l >= self.__stdoutMinLevel)
                maxOk = (self.__stdoutMaxLevel is None) or (l <= self.__stdoutMaxLevel)
                self.__logTypeStdoutFlags[logType] = minOk and maxOk
        if _SINK_STDOUT in self.__sinks:
            self.__rebuild_active_sinks()

    def __update_file_flags(self):
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
                if not sink.logTypeFlags.get(logType, True):
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

    def add_sink(self, name, handler, enabled=True,
                 minLevel=None, maxLevel=None, logTypeFlags=None):
        """Add a user-supplied output sink to the logger.

        The sink receives every log record whose type passes the routing
        rules (enabled flag, per-type flags, and optional level bounds).
        The handler is called as ``handler.write(record + "\\n")`` where
        *record* is the fully-formatted log line (same plain text that
        goes to the log file, without ANSI colour codes). The caller
        owns the handler's lifecycle -- the logger never closes it.

        :Parameters:
            #. name (str): Unique string key for this sink. Must not
               clash with any existing name or reserved integer keys.
            #. handler (file-like): Any object with a write(str) method.
               An optional flush() method is called when Logger.flush
               is True.
            #. enabled (bool): Master switch for this sink. Default True.
            #. minLevel (number, None): Records whose level is strictly
               below this value are suppressed. None means no floor.
            #. maxLevel (number, None): Records whose level is strictly
               above this value are suppressed. None means no ceiling.
            #. logTypeFlags (dict, None): Per-type override map
               {logType (str): bool}. Missing keys default to True.
               None means all types enabled.
        """
        if not isinstance(name, basestring):
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
        if logTypeFlags is not None:
            if not isinstance(logTypeFlags, dict):
                raise TypeError("logTypeFlags must be a dict or None")
            for k, v in logTypeFlags.items():
                if not isinstance(k, basestring):
                    raise TypeError("logTypeFlags keys must be strings")
                if not isinstance(v, bool):
                    raise TypeError("logTypeFlags values must be booleans")
        self.__sinks[name] = _Sink(
            handler      = handler,
            enabled      = enabled,
            logTypeFlags = dict(logTypeFlags) if logTypeFlags is not None else {},
            minLevel     = float(minLevel) if minLevel is not None else None,
            maxLevel     = float(maxLevel) if maxLevel is not None else None,
            sinkType     = 'user',
        )
        self.__rebuild_active_sinks()

    def remove_sink(self, name):
        """Remove a user-added sink by its registered name.

        :Parameters:
            #. name (str): The key used when the sink was registered
               with add_sink().
        """
        if not isinstance(name, basestring):
            raise TypeError("sink name must be a string")
        if name not in self.__sinks:
            raise ValueError("sink '%s' is not registered" % name)
        del self.__sinks[name]
        self.__rebuild_active_sinks()

    def clear_sinks(self):
        """Remove all user-added sinks.

        The two built-in sinks (_SINK_STDOUT and _SINK_FILE) are
        always preserved. This is a no-op if no user sinks are
        registered.
        """
        userKeys = [k for k in self.__sinks if isinstance(k, basestring)]
        for k in userKeys:
            del self.__sinks[k]
        if userKeys:
            self.__rebuild_active_sinks()

    def force_log_type_stdout_flag(self, logType, flag):
        """
        Force a logtype standard output logging flag despite minimum and maximum logging level boundaries.

        :Parameters:
           #. logType (string): A defined logging type.
           #. flag (None boolean): The standard output logging flag.
              If None, logtype existing forced flag is released.
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
        """
        self.force_log_type_stdout_flag(logType, stdoutFlag)
        self.force_log_type_file_flag(logType, fileFlag)

    def set_log_type_name(self, logType, name):
        """
        Set a logtype name.

        :Parameters:
           #. logType (string): A defined logging type.
           #. name (string): The logtype new name.
        """
        if logType not in self.__logTypeStdoutFlags:
            raise ValueError("logType '%s' not defined" %logType)
        if not isinstance(name, basestring):
            raise TypeError("name must be a string")
        name = str(name)
        self.__logTypeNames[logType] = name

    def set_log_type_level(self, logType, level):
        """
        Set a logtype logging level.

        :Parameters:
           #. logType (string): A defined logging type.
           #. level (number): The level of logging.
        """
        if not _is_number(level):
            raise TypeError("level must be a number")
        self.__logTypeLevels[logType] = float(level)

    def remove_log_type(self, logType, _assert=False):
        """
        Remove a logtype.

        :Parameters:
           #. logType (string): The logtype.
           #. _assert (boolean): Raise a ValueError if logType is not defined.
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
        """
        # check logType
        if not isinstance(logType, basestring):
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
        if not isinstance(name, basestring):
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
        elif isinstance(attributes, basestring):
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
        update a logtype.

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

    def _format_message(self, logType, message, data, tback, callerStr=''):
        """Build the complete formatted log record string.

        Called by both log() and force_log() immediately before dispatch.
        Subclasses may override this method to change the overall record
        layout while keeping the built-in routing, level filtering, and
        sink dispatch unchanged.

        :Parameters:
            #. logType (string): A registered log type name.
            #. message (string): The sanitized message text.
            #. data (None, object): Optional data payload; appended after
               the message on a new line when not None.
            #. tback (None, str, list): Optional traceback. A string is
               appended as-is; a list of (filename, lineno, name, line)
               tuples is formatted like a standard Python traceback.
            #. callerStr (string): Pre-formatted caller tag produced by
               _get_caller_str(), or an empty string when callerInfo is False.

        :Returns:
            #. result (string): The fully formatted log record ready for
               dispatch to all active sinks.
        """
        message  = _sanitize_message(message)
        if self.__maxMessageSize is not None and len(message) > self.__maxMessageSize:
            message = message[:self.__maxMessageSize] + '[truncated]'
        header   = self._get_header(logType, message)
        footer = self._get_footer(logType, message)
        dataStr  = ''
        tbackStr = ''
        if data is not None:
            dataStr = '\n%s'%(data,)
            if self.__maxDataSize is not None and len(dataStr) > self.__maxDataSize:
                dataStr = dataStr[:self.__maxDataSize] + '[truncated]'
        if tback is not None:
            if isinstance(tback, str):
                tbackStr = '\n%s'%(tback,)
            else:
                try:
                    tbackStr = []
                    for filename, lineno, name, line in tback:
                        tbackStr.append( '\n  File "%s", line %d, in %s'%(filename,lineno,name) )
                        if line:
                            tbackStr.append( '\n    %s'%(line.strip(),) )
                    tbackStr = ''.join(tbackStr)
                except Exception:
                    tbackStr = '\n%s'%(str(tback),)
        return "%s%s%s%s%s%s" %(header, callerStr, message, footer, dataStr, tbackStr)

    def _get_datetimestamp(self, format='%Y-%m-%d %H:%M:%S'):
        """Return the current date-time as a formatted string.

        Override this method in a subclass to change the timestamp format
        or source (e.g. to use UTC regardless of the instance timezone).

        :Parameters:
            #. format (string): A strftime-compatible format string.
               Default is '%Y-%m-%d %H:%M:%S'.

        :Returns:
            #. result (string): The formatted datetime stamp.
        """
        return datetime.strftime(datetime.now(self.__timezone), format)

    def _get_header(self, logType, message):
        """Return the header string prepended to each log record.

        The default format is ``'YYYY-MM-DD HH:MM:SS - loggerName <LOGTYPE> '``.
        Override in a subclass to produce a custom header layout.

        :Parameters:
            #. logType (string): A registered log type name.
            #. message (string): The message text (available for context
               but not included in the default header).

        :Returns:
            #. result (string): The header string including a trailing space.
        """
        dateTime = self._get_datetimestamp()
        return "%s - %s <%s> "%(dateTime, self.__name, self.__logTypeNames[logType])

    def _get_footer(self, logType, message):
        """Return the footer string appended to each log record.

        Returns an empty string by default. Override in a subclass to append
        structured metadata, record separators, or any fixed suffix.

        :Parameters:
            #. logType (string): A registered log type name.
            #. message (string): The message text.

        :Returns:
            #. result (string): The footer string, or an empty string for no footer.
        """
        return ""

    def __enqueue_worker(self):
        """Background thread: drain the log queue and perform all I/O.

        Items are one of two formats:
          - 3-tuple (log, logType, sinks) from normal log() calls;
            sinks is a snapshot list of _Sink objects from __activeSinks.
          - 4-tuple (log, logType, toStdout, toFile) from force_log();
            toStdout/toFile are caller-supplied booleans that bypass routing.
        The sentinel _QUEUE_STOP signals clean shutdown.
        task_done() is called after every item so flush() can join().
        """
        while True:
            item = self.__logQueue.get()
            try:
                if item is _QUEUE_STOP:
                    return
                if len(item) == 3:
                    # normal log() path — 3-tuple (log, logType, sinks)
                    log, logType, sinks = item
                    for sink in sinks:
                        if sink.sinkType == 'file':
                            self.__log_to_file("%s\n" % log)
                            if self.__flush:
                                self.__flush_stream(self.__logFileStream)
                        elif sink.sinkType == 'user':
                            try:
                                sink.handler.write("%s\n" % log)
                                if self.__flush:
                                    self.__flush_stream(sink.handler)
                            except Exception:
                                # catch any error a user-supplied handler raises:
                                # we must never let a custom sink crash the worker
                                pass
                        else:  # stdout
                            self.__log_to_stdout(self.__format_stdout_line(logType, log))
                            if self.__flush:
                                self.__flush_stream(sink.handler)
                else:
                    # force_log() path — 4-tuple (log, logType, toStdout, toFile)
                    # bypasses routing; toStdout/toFile are caller-supplied booleans
                    log, logType, toStdout, toFile = item
                    if toStdout:
                        self.__log_to_stdout(self.__format_stdout_line(logType, log))
                        if self.__flush:
                            self.__flush_stream(self.__stdout)
                    if toFile:
                        self.__log_to_file("%s\n" % log)
                        if self.__flush:
                            self.__flush_stream(self.__logFileStream)
            finally:
                self.__logQueue.task_done()

    def __put_to_queue(self, item):
        """Put one log record onto the queue, honouring the backpressure policy.

        Called by log() and force_log() whenever enqueue mode is active.
        The policy is read fresh on every call so runtime changes via
        set_queue_full_policy() take effect immediately.

        When maxQueueSize is None the queue is unbounded and put() always
        succeeds instantly -- no policy check is needed.

        Backpressure policies when the queue is at capacity:

        ``block``  -- park the calling thread on the queue's internal
        condition variable (zero CPU while waiting). If queueBlockTimeout
        is None the park has no deadline -- the thread waits until the
        worker drains a slot, however long that takes. If queueBlockTimeout
        is set and expires, the record is dropped, droppedMessages is
        incremented, and one warning is emitted to stderr.

        ``drop``   -- discard the record silently and increment
        droppedMessages. Zero latency impact on the caller.

        ``warn``   -- same as drop but also writes a one-line warning to
        sys.stderr so the loss is visible in terminal output.

        ``raise``  -- call put_nowait() and let queue.Full propagate to
        the caller. The caller is responsible for handling it.

        :Parameters:
            #. item (tuple): The log record tuple — either a 3-tuple
               (log, logType, sinks) from log() or a 4-tuple
               (log, logType, toStdout, toFile) from force_log().
        """
        # unbounded queue — fast path, no policy needed
        if self.__maxQueueSize is None:
            self.__logQueue.put(item)
            return
        policy = self.__queueFullPolicy
        if policy == 'block':
            timeout = self.__queueBlockTimeout
            if timeout is None:
                # park indefinitely — true backpressure, never drops
                self.__logQueue.put(item)
            else:
                # bounded park — drop + warn if deadline expires
                try:
                    self.__logQueue.put(item, timeout=timeout)
                except _queue_module.Full:
                    with self.__droppedLock:
                        self.__droppedMessages += 1
                        dropped = self.__droppedMessages
                    sys.stderr.write(
                        'pysimplelog WARNING: queue still full after %.1fs, '
                        'record dropped (%d total dropped)\n'
                        % (timeout, dropped)
                    )
        elif policy == 'drop':
            try:
                self.__logQueue.put_nowait(item)
            except _queue_module.Full:
                with self.__droppedLock:
                    self.__droppedMessages += 1
        elif policy == 'warn':
            try:
                self.__logQueue.put_nowait(item)
            except _queue_module.Full:
                with self.__droppedLock:
                    self.__droppedMessages += 1
                    dropped = self.__droppedMessages
                sys.stderr.write(
                    'pysimplelog WARNING: queue full, record dropped '
                    '(%d total dropped)\n' % dropped
                )
        elif policy == 'raise':
            # put_nowait raises queue.Full immediately if full —
            # caller is responsible for catching it
            self.__logQueue.put_nowait(item)

    def __log_to_file(self, message):
        # __rotationLock is always acquired on every call to this method, so
        # keeping write() inside the lock adds no extra acquisition cost.
        # It eliminates the race where another thread could close the stream
        # between the stream-capture and the write on a shared Logger instance.
        with self.__rotationLock:
            if self.__logFileStream is None:
                self.__logFileStream = open(self.__logFileName, 'a')
            elif self.__logFileMaxSize is not None:
                if self.__logFileStream.tell()/(1024.**2) >= self.__logFileMaxSize:
                    self.__set_log_file_name()   # re-entrant: RLock allows this
                    self.__logFileStream = open(self.__logFileName, 'a')
            self.__logFileStream.write(message)

    def __log_to_stdout(self, message):
        try:
            self.__stdout.write(message)
        except OSError:
            # for the rare case when stdout buffer no more exits.
            # this can happen when main thread dies and all remaining threads
            # turn to daemon threads. Try and catch add absolutely no
            # overhead unless when an error occurs.
            pass

    def __flush_stream(self, stream):
        """
        Flush and fsync a stream, silently ignoring I/O errors.
        Safe to call from any thread; errors are swallowed so the
        logger never raises on a flush failure.

        Custom handler objects (user sinks) may not implement fileno() at
        all — AttributeError is caught alongside OSError so that the worker
        thread never crashes on such objects.

        :Parameters:
            #. stream (file-like): The stream to flush and fsync.
        """
        try:
            stream.flush()
        except (OSError, AttributeError):
            pass
        try:
            # fileno() may raise AttributeError (missing method) or
            # io.UnsupportedOperation (in-memory streams) — both are benign
            os.fsync(stream.fileno())
        except (OSError, AttributeError):
            pass

    def __format_stdout_line(self, logType, log):
        """Format a log line for stdout with ANSI wrap codes applied.

        :Parameters:
            #. logType (string): A defined logging type.
            #. log (string): The already-formatted log message body.

        :Returns:
            result (str): The line ready to write to the stdout stream.
        """
        fmt = self.__logTypeFormat[logType]
        return "%s%s%s\n" % (fmt[0], log, fmt[1])

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


    def log(self, logType, message, data=None, tback=None, countConstraint=None):
        """
        Log a message of the specified log type.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. countConstraint (None, number): maximum number of time to log
              the given message
           #. data (None,  object): Any type of data to print and/or write to log file
              after log message
           #. tback (None, str, list): Stack traceback to print and/or write to
              log file. In general, this should be traceback.extract_stack

        :Returns:
            #. message (string): the logged message
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
        if countConstraint is not None:
            self.__logMessagesCounter.setdefault(message, -1)
            self.__logMessagesCounter[message] += 1
            if countConstraint<=self.__logMessagesCounter[message]:
                return message
        # format on caller thread so timestamp is captured at call time
        # capture caller frame BEFORE any internal calls so the stack depth
        # is minimal and the user frame is as close to the top as possible
        callerStr = _get_caller_str() if self.__callerInfo else ''
        log = self._format_message(logType=logType, message=message, data=data, tback=tback, callerStr=callerStr)
        # routing: read from the pre-computed active-sink cache (O(1) lookup)
        # the list contains only sinks whose enabled flag and logTypeFlags
        # both pass for this logType — no per-call boolean arithmetic needed
        activeSinks = self.__activeSinks.get(logType, [])
        if self.__enqueue:
            # snapshot so the worker sees a stable list even if config
            # changes between put() and the item being processed
            self.__put_to_queue((log, logType, list(activeSinks)))
        else:
            for sink in activeSinks:
                if sink.sinkType == 'file':
                    self.__log_to_file("%s\n" % log)
                    if self.__flush:
                        self.__flush_stream(self.__logFileStream)
                elif sink.sinkType == 'user':
                    try:
                        sink.handler.write("%s\n" % log)
                        if self.__flush:
                            self.__flush_stream(sink.handler)
                    except OSError:
                        pass
                else:  # stdout
                    self.__log_to_stdout(self.__format_stdout_line(logType, log))
                    if self.__flush:
                        self.__flush_stream(sink.handler)
        # set last logged message (on caller thread for immediate visibility)
        self.__lastLogged[logType] = log
        self.__lastLogged[-1]      = log
        # always return logged message
        return message

    def force_log(self, logType, message, data=None, tback=None, stdout=True, file=True):
        """
        Force logging a message of a certain logtype whether logtype level is allowed or not.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. data (None, object): Optional data payload to append after the
              log message on a new line.
           #. tback (None, str, list): Stack traceback to print and/or write to
              log file. In general, this should be traceback.extract_stack.
           #. stdout (boolean): Whether to force logging to standard output.
           #. file (boolean): Whether to force logging to file.

        :Returns:
            #. message (string): the logged message
        """
        # reject callables — same policy as log()
        if callable(message):
            raise TypeError(
                "force_log() message must be a string or string-coercible value, "
                "not a callable. To defer expensive message construction "
                "guard the call with is_enabled('%s') instead." % logType
            )
        # format on caller thread so timestamp is captured at call time
        callerStr = _get_caller_str() if self.__callerInfo else ''
        log = self._format_message(logType=logType, message=message, data=data, tback=tback, callerStr=callerStr)
        if self.__enqueue:
            self.__put_to_queue((log, logType, stdout, file))
        else:
            if stdout:
                self.__log_to_stdout(self.__format_stdout_line(logType, log))
                if self.__flush:
                    self.__flush_stream(self.__stdout)
            if file:
                self.__log_to_file("%s\n" % log)
                if self.__flush:
                    self.__flush_stream(self.__logFileStream)
        # set last logged message (on caller thread for immediate visibility)
        self.__lastLogged[logType] = log
        self.__lastLogged[-1]      = log
        # always return logged message
        return message

    def catch(self, func=None, logType='error', reraise=False,
              message='An exception was caught'):
        """Decorator and context manager that catches and logs exceptions.

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
            result: A _CatchContext usable as decorator or context
            manager, or the wrapped callable for bare-decorator use.
        """
        ctx = _CatchContext(self, logType=logType,
                            reraise=reraise, message=message)
        if func is not None:
            return ctx(func)
        return ctx

    def bind(self, **context):
        """Return a _BoundLogger that prepends context to every message.

        The bound logger delegates all I/O to this Logger unchanged.
        It holds no state of its own beyond the context dict and the
        reference to this parent. It is immutable and thread-safe.

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
               key is accepted. Values are coerced to str at log time.

        :Returns:
            #. result (_BoundLogger): An immutable context-aware wrapper
            around this Logger.
        """
        return _BoundLogger(self, context)

    def flush(self):
        """Flush all streams.

        When enqueue mode is active, blocks until all queued log
        records have been written before flushing the streams.
        """
        if self.__enqueue and self.__logQueue is not None:
            self.__logQueue.join()
        # flush every registered sink — track ids to avoid double-flush
        # when two sinks share the same handler object
        seen = set()
        for sink in self.__sinks.values():
            if sink.sinkType == 'file':
                if self.__logFileStream is not None:
                    self.__flush_stream(self.__logFileStream)
            elif sink.handler is not None:
                sid = id(sink.handler)
                if sid not in seen:
                    seen.add(sid)
                    self.__flush_stream(sink.handler)

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
        same_logger = AppLogger()
        assert same_logger is logger
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
    l=Logger("log test")
    l.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
    l.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
    l.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold","blink"])
    print(l, '\n')
    # print available logs and logging time.
    for logType in l.logTypes:
        tic = time.time()
        l.log(logType, "this is '%s' level log message."%logType)
        print("%s seconds\n"%str(time.time()-tic))
