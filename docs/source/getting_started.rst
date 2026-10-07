Getting Started
===============

Installation
------------

Install pysimplelog from PyPI using pip:

.. code-block:: console

    pip install pysimplelog

pysimplelog requires **Python 3.10 or later** and has no mandatory third-party
dependencies.  ``pytz`` is optional and only needed when a timezone name is
passed to the ``Logger`` constructor.

Basic Usage
-----------

.. code-block:: python

    from pysimplelog import Logger

    ## create a logger — logs to stdout and to simplelog.log by default
    l = Logger("my-app")

    ## built-in log levels
    l.debug("starting up")
    l.info("application ready")
    l.warn("disk usage above 80%")
    l.error("connection refused")
    l.critical("out of memory")

    ## add a custom log type with colour
    l.add_log_type("trace", name="TRACE", level=5, color="cyan")
    l.log("trace", "entering request handler")

Structured Logging with bind()
-------------------------------

Use ``bind()`` to attach context key-value pairs to every record without
modifying the underlying logger. They are written in the ``context`` of the record, apart from
its fields:

.. code-block:: python

    def handle_request(request_id, user):
        log = l.bind(requestId=request_id, user=user)
        log.info("request received")   ## [requestId=x user=y] request received
        log.error("authorisation failed")

``context()`` attaches values to every record made inside a ``with`` block, whatever logger makes
them. The values follow the flow of the program through ``contextvars``: they reach every function the
block calls, and each asynchronous task keeps its own. Blocks nest, an inner value replaces an outer
one with the same name until its block ends:

.. code-block:: python

    with l.context(request_id=request_id, user_id=user_id):
        l.info("Order created")          ## carries request_id and user_id
        with l.context(step="payment"):
            l.info("Charging")           ## carries request_id, user_id and step

The values reach what ``asyncio.to_thread`` and executors run, because those copy the context. A plain
``threading.Thread`` starts empty: run its function with ``contextvars.copy_context().run`` to hand it the values.
Records that come from the standard ``logging`` package carry them too.

Exception Capture with catch()
-------------------------------

``catch()`` works as both a decorator and a context manager:

.. code-block:: python

    ## as a decorator
    @l.catch(logType="error", reraise=False)
    def risky():
        raise ValueError("something went wrong")

    ## as a context manager
    with l.catch():
        risky_code()

Add a processor to scrub the exception message and full traceback -- useful
for stripping local filesystem paths or other infrastructure detail that must
never reach a log file or a downstream sink such as a SIEM collector. A
processor is a ``f(record) -> record`` function run on every record before
it reaches any sink; ``redact_text`` turns a plain text function into one:

.. code-block:: python

    from pysimplelog import redact_text

    def hide_paths(text):
        return text.replace("/opt/myapp/venv/lib/pysimplelog", "<redacted>")

    l.add_processor(redact_text(hide_paths))

    @l.catch(logType="error")
    def load_plugin(path):
        raise ImportError("/opt/myapp/venv/lib/pysimplelog/plugins.py not found")

Processors
----------

A processor is a function ``f(record) -> record`` that rewrites each log record
before it reaches any sink (terminal, file, SIEM, ...). It receives the whole
:class:`~pysimplelog.record.LogRecord` -- message, fields and traceback included --
so one function can hide local paths or secrets everywhere. Processors run for every
record, in the order they were added. To treat some records differently, test
``record.logType`` inside the function:

.. code-block:: python

    from pysimplelog import Logger, redact_text, redact_fields

    def hide_paths(text):
        return text.replace("/opt/myapp", "...")

    ## at creation
    l = Logger("my-app", processors=[redact_text(hide_paths)])

    ## or later
    l.add_processor(redact_fields())    ## hides password, token, api_key, ... values
    l.processors                        ## (<function>, <function>)

    l.remove_processor(hide_paths)      ## nothing happens if it was never added

A function that raises, or returns something that is not a record, makes the logger
drop the record rather than let it through unredacted. One warning per function is
written to stderr and ``processorFailures`` counts them, so a broken processor is
never silent. A processor must not log.

Structured fields and exceptions
--------------------------------

Every keyword argument of a log call is a field of the record. ``exc_info`` records an exception:

.. code-block:: python

    l.info("Order created", order_id=123, customer_id=456)   ## order_id=123 customer_id=456 after the message

    try:
        connect()
    except ConnectionError as error:
        l.error("Database connection failed", exc_info=error)   ## type, message and traceback
        ## or l.error("...", exc_info=True) inside the except block

The names ``logType``, ``message``, ``exc_info`` and ``countConstraint`` belong to the method, so they
cannot be field names.

Standard logging
----------------

Libraries log with Python's standard ``logging`` package. ``redirect_standard_logging`` sends those records
through the same processors, filters and sinks. Nothing changes until you call it:

.. code-block:: python

    import logging
    from pysimplelog import Logger, redirect_standard_logging, restore_standard_logging

    l = Logger("my-app", consoleFormatter=None)
    handler = redirect_standard_logging(l, loggerLevel=logging.INFO)   ## the root logger, INFO and above

    logging.getLogger("urllib3.connectionpool").info("Starting new HTTPS connection")
    logging.getLogger("my-lib").warning("disk almost full: %s%%", 93, extra={"disk": "/data"})
    ## the field logger_name is the standard logger, and extra={...} becomes fields

    restore_standard_logging(handler)

The standard levels map to the log types ``debug``, ``info``, ``warn``, ``error`` and ``critical``, and
``levelMap`` overrides that. ``name='urllib3'`` takes only one library, and ``replace=True`` removes the handlers
the standard logger had, so the records reach only pysimplelog. ``StandardLoggingHandler(l)`` can also be added to
any standard logger by hand.

Formatters
----------

Every sink turns a record into text with its own formatter. ``None`` gives JSON, one object per
line, ``'text'`` gives the readable line, a string with ``{name}`` placeholders is a template, and
a function ``f(record) -> str`` is used as it is:

.. code-block:: python

    from pysimplelog import Logger, FILE_SINK, CONSOLE_SINK

    l = Logger("my-app", fileFormatter=None)          ## JSON lines in the log file
    l.set_sink_formatter(CONSOLE_SINK, "{timestamp} {severity} {message}")
    l.add_sink("audit", open("audit.log", "a"))        ## a file-like object gets the readable text
    l.set_sink_formatter("audit", None)                ## ... or JSON

Filters
-------

A filter is a function ``f(record) -> bool`` run after the processors. ``False`` drops the
record for every sink. A filter that raises keeps the record and is counted in
``filterFailures``. ``set_sink_filter()`` gives one sink its own filter:

.. code-block:: python

    from pysimplelog import sample

    l.add_filter(lambda record: record.fields.get("path") != "/health")
    l.add_filter(sample(0.1))                       ## keep about one record in ten
    l.set_sink_filter("audit", lambda record: record.logType == "audit")
    l.set_sink_filter("audit", None)                ## back to everything the sink's routing allows

Unknown Log Types
-----------------

By default logging with an undefined log type raises ``KeyError``. Choose a
fallback instead, so a misspelled type never crashes the caller and stays visible:

.. code-block:: python

    l = Logger("my-app", unknownLogTypePolicy="fallback", fallbackLogType="error")
    l.log("typo", "hello")    ## logged as an error: Unknown log type 'typo': hello

Non-blocking Enqueue Mode
--------------------------

Set ``enqueue=True`` to push all I/O to a background daemon thread.  Call
``flush()`` before exit to guarantee all records are written:

.. code-block:: python

    l = Logger("my-app", enqueue=True)
    l.info("this returns immediately")
    l.flush()   ## blocks until the queue is empty

What a full queue does is explicit. With ``maxQueueSize`` set, ``queueFullPolicy`` is one of
``"block"`` (the caller waits, for ``queueBlockTimeout`` seconds at most), ``"drop_newest"``,
``"drop_oldest"`` or ``"reject"`` (the log call raises ``QueueFull``). A sink that does slow work gets its own
queue and thread with ``add_sink(..., threaded=True, threadQueueSize=1000, threadQueuePolicy="drop_oldest")``.
Nothing is lost without being counted:

.. code-block:: python

    l.queueStats          ## policy, capacity, depth, queued, dropped, rejected of the enqueue mode
    l.sink_stats("siem")  ## queue counters, filtered, and processed, failed, latency_mean, latency_max
    l.sink_stats()        ## the same for every sink

Singleton Usage
---------------

For application-wide shared logging, use ``SingleLogger``:

.. code-block:: python

    from pysimplelog import SingleLogger as Logger

    Logger("my-app")          ## first call — creates and initialises
    Logger().info("hello")    ## subsequent calls — returns same instance

SIEM / Syslog Forwarding
-------------------------

``pysimplelog.contrib`` ships an optional, zero-mandatory-dependency add-on
that forwards log records to a SIEM (Security Information and Event
Management) or syslog collector as RFC 5424 structured syslog over TCP+TLS,
UDP, or HTTP(S). It is pure ``add_sink()`` usage under the hood -- nothing
in the core ``Logger`` is touched:

.. code-block:: python

    from pysimplelog.contrib import siem_sink, siem_transport

    transport = siem_transport.TCPSyslogTransport("siem.example.com", 6514, useTls=True)

    ## opt-in routing: only 'warn'/'error'/'critical' reach the collector
    sink = siem_sink.attach(l, transport,
                             logTypeFlags={"warn": True, "error": True, "critical": True},
                             defaultFlag=False)

    l.error("payment gateway timeout")

    ## at shutdown
    siem_sink.detach(l, sink)

See :doc:`api_reference` for the full ``contrib`` API (UDP and HTTP/Splunk-HEC
transports, retry/backoff tuning, circuit breaker, drop/error callbacks), and
the ``examples/`` directory in the source distribution for runnable scripts.

Forked processes
----------------

A process made by ``os.fork``, or by ``multiprocessing`` where it forks, gets a copy of the logger, but not of its threads.
So that it works, and does not wait for a thread that is not there:

* A threaded sink, and the ``enqueue`` mode, deliver in the thread that logs, in the child. Nothing is queued for a worker
  that does not exist, and ``flush`` and the exit of the child do not wait for one.
* The locks of the package are replaced by new ones in the child. A fork copies a lock as it is, and one that another thread
  held at that moment would stay held for ever in the copy.
* A TCP connection to a SIEM is not shared: the child opens its own, because two processes writing into one stream would mix
  their messages.
* A sink with a spool sends its records at once without it, see *Durable delivery*.

The parent is not affected. Processes that are started by spawning, the default on macOS and Windows, import the code
again and make their own logger, so none of this applies to them.

Durable delivery
----------------

A sink can keep its records on disk until it has delivered them, so a collector that is down for an hour, or a
program that crashes, does not lose them. This is a spool. It is off unless you give the sink ``spool=``, which is a
``SpoolConfig`` or a dictionary with the same names:

.. code-block:: python

    from pysimplelog import Logger
    from pysimplelog.contrib import siem_sink

    MB = 1024 ** 2
    logger = Logger("billing")
    siem_sink.quick_attach(
        logger, "tcps", host="siem.example.org", port=6514,
        spool={"path": "/var/spool/billing/siem",   ## fixed in the application, the same in every run
               "id": "billing-siem",                ## the label of this spool, fixed too
               "maxBytes": 100 * MB,                ## largest size of this process's files, required
               "totalMaxBytes": 500 * MB,           ## largest size of all the processes' files, required
               "adoptOrphans": True})               ## also send what a crashed process left behind

    logger.error("payment failed", order_id=123)    ## on disk before this call returns

A record is written to the spool in the thread that logs it, after the processors and filters, so what is on disk is
already redacted. A worker thread of the sink then delivers the records in order. A send that fails is tried again after a
growing wait, and nothing after it is sent first. A record the formatter cannot render goes to a ``dead`` file at once.
Records are delivered at-least-once: a crash can make the last few arrive twice, and each record carries the same
``event_id`` field every time it is sent, so a receiver can tell. Delivered records are deleted, and a clean shutdown
leaves no file behind.

Each process writes to a slot of its own under the base folder, so processes never share files. A slot whose process died
is sent by another one, when it is idle (``adoptOrphans=True``) or when you call ``logger.adopt_orphans(name)``, but only
by a sink made for the same ``id``, sink class and destination: records meant for one receiver never go to another. A
sink says where it sends with ``SPOOL_DESTINATION``, the SIEM sink takes it from its transport, and any other sink gives
a ``target`` text in the settings. A stream, console or file sink cannot be spooled.

What you can set: ``flush`` (``none``, ``flush``, ``fsync``, ``fullsync``), what a full spool does (``policy``:
``drop_oldest``, ``drop_newest``, ``block``, ``reject``), ``maxAge``, ``segmentBytes``, how often the position is saved
(``ackEvery``, ``ackInterval``), the wait between tries (``retryBackoffBase``, ``retryBackoffMax``), when to give up
(``maxAttempts``, never by default) and how orphans are adopted. See ``SpoolConfig``. ``logger.sink_stats(name)["spool"]``
says what the spool holds and what it lost.

Things to know:

* The record is written by the thread that logs, which costs it about 30 to 90 microseconds more than a threaded sink
  without a spool (it is the system call of ``flush``, and the worker thread competing for the interpreter), and more with
  ``fsync`` or ``fullsync``. ``python3 pysimplelog/benchmarks/bench_logging.py`` measures it on your machine, next to the
  standard ``logging`` module, Loguru and structlog when they are installed. On macOS ``fsync`` does not survive a power cut and ``fullsync`` does,
  at about 19 milliseconds a record.
* Do not use ``enqueue=True`` when you need the guarantee: that queue is in memory, and a record in it is lost in a crash.
* Order is kept for each process. Between processes it is only by timestamp.
* UDP gives no confirmation, so a spool over UDP only proves that a datagram left.
* A process made by ``fork`` does not own the spool of its parent. Its records are sent at once, by the thread that logs and
  without the spool, and counted as ``unspooled``. Make the logger in the new process to give it a spool of its own.
* On Windows the lock is ``msvcrt.locking``, and the permission bits given to the spool folder are ignored, so the folder is
  as private as its parent: put it where only the account that runs the program can read. A file that Windows will not
  delete because another program has it open, a virus scanner for example, is deleted at a later acknowledgement and does
  not stop the sink. The author could only run the Windows path through the continuous integration of the repository
  (``.github/workflows/tests.yml``), see its results before relying on it.

API stability
-------------

From 6.0 the names in ``pysimplelog.__all__``, the public methods and properties of ``Logger``, and the
arguments of ``Logger()`` and ``add_sink()`` are stable. Later 6.x releases only add to them. A removal
or a change of meaning waits for 7.0.
