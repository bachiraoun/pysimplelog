Getting Started
===============

New to pysimplelog? Start with the :doc:`user guide <guide/index>`, which follows what you do with a logger. This page
is the detailed reference for each subject.

Installation
------------

Get pysimplelog from its `GitHub repository <https://github.com/bachiraoun/pysimplelog/>`_, into a folder named
``pysimplelog``:

.. code-block:: console

    git clone https://github.com/bachiraoun/pysimplelog.git

Then put that folder where Python can import it: in your ``site-packages`` folder, or in any folder that is on
``PYTHONPATH``.

pysimplelog requires **Python 3.10 or later** and has no mandatory third-party
dependencies.  ``pytz`` is optional and only needed when a timezone name is
passed to the ``Logger`` constructor.

Basic Usage
-----------

The quickest way in is the shared logger, which needs no setup:

.. code-block:: python

    from pysimplelog import logger

    logger.info("Application started")
    logger.info("User {} logged in", "ann")
    logger.add("logs/app.log", rotation="500 MB", retention="30 days")

For a library, or for a logger with its own settings, make a ``Logger``:

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

Everyday conveniences
---------------------

The calls below are the ones most programs use. Each has a page in the :doc:`user guide <guide/index>` that goes further: :doc:`guide/formatting`, :doc:`guide/files`,
:doc:`guide/exceptions` and :doc:`guide/multiple_sinks`.

.. code-block:: python

    from pysimplelog import logger
    import pysimplelog

    ## {} fills the message, keywords stay on the record as fields
    logger.info("User {} logged in", 7, service="auth")

    ## One call for a file, with rotation and retention
    logger.add("logs/app.log", rotation="500 MB", retention="30 days", compression="gz")
    logger.add("logs/errors.jsonl", format="json", level="ERROR")

    ## Options behind one call: lazy values, the exception, the caller depth
    logger.opt(lazy=True).debug("Result: {}", lambda: sum(range(1000)))
    logger.opt(depth=1).info("Reported for the caller of my wrapper")

    ## A message that must appear whatever the levels and filters say
    logger.force_log("info", "Shutting down")

    ## Silence a noisy library by name
    pysimplelog.disable("urllib3")
    pysimplelog.enable("urllib3")

The console, the level and the colours can be set from the environment, without changing the code. The variables are
``PYSIMPLELOG_LEVEL``, ``PYSIMPLELOG_FORMAT`` and ``PYSIMPLELOG_COLOR``, and ``PYSIMPLELOG_NAMESPACE_DISABLE`` silences libraries.
An argument you pass always wins over the environment, and the environment wins over the defaults (:doc:`guide/console`).

To see the values of the variables in a traceback, make the logger with ``diagnose=True``. A variable whose name contains
``password``, ``token``, ``cookie`` or ``credential`` always shows ``<redacted>``. A ``Secret(value)`` prints as ``[REDACTED]``
everywhere it is used (:doc:`guide/exceptions`, :doc:`guide/processors_and_filters`).

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

Adding the same values to every record
--------------------------------------

``add_context()`` makes a processor that puts named values in the context of every record, for what describes the whole
program: the service, the environment, the host. A value that is a function is called for every record, so it can say what is
true now. A name that the call already has in its context is left as it is, a function that raises is reported once and the record is
never lost. It also reaches the records of the standard ``logging`` bridge, which ``bind()`` does not:

.. code-block:: python

    import socket
    from pysimplelog import Logger, add_context

    l = Logger("orders", processors=[add_context(service="checkout", environment="production", host=socket.gethostname(),
                                                 request_id=lambda: current_request_id())])

The process and thread identifiers are already in every record, so there is nothing to add for them.

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

Log files: rotation, retention, compression and housekeeping
------------------------------------------------------------

A log file that is never limited grows for ever. A ``FileSink`` limits it with three rules:

* ``maxSize`` (megabytes): when the file reaches it, a new file is started, ``app_0.log``, ``app_1.log`` and so on.
* ``roll``: at most that many files are kept, the older ones are deleted.
* ``maxAge`` (seconds): a rotated file older than that, counted from its last change, is deleted. The file being written never is.
* ``compress='gz'``: a file that has been rotated out becomes ``app_3.log.gz``. It needs ``maxSize``.

.. code-block:: python

    from pysimplelog import Logger, FileSink

    logger = Logger("app", logToFile=False)          ## no file of the logger itself
    logger.add_sink("file", FileSink("logs/app", maxSize=10, roll=14, maxAge=14 * 86400, compress="gz"))

``roll`` and ``maxAge`` both apply: a file goes when there are too many or it is too old, compressed or not. Compression is done
by a thread of its own, so the thread that logs never waits for it. The original is deleted only after the compressed file is
complete and has the modification time of the original, so its age does not start again. A crash leaves the original, and the
compression is made at the next start. Closing the sink waits for the one in progress.

**When is the age tested?** There is no timer and no thread for it. It is tested when a file is rotated out, when the sink starts,
when a record is written (at most once a minute), and when you call ``sink.enforce_retention()`` or ``logger.maintain()``. A
program that logs nothing keeps its old files until one of those, which does not matter for the size of the folder, since nothing
is being added. If files must go on time whatever happens, call ``logger.maintain()`` from your scheduler, or from a thread of
your own:

.. code-block:: python

    import threading

    def keep_tidy(logger, everySeconds=3600):
        stop = threading.Event()
        def run():
            while not stop.wait(everySeconds):
                logger.maintain()
        threading.Thread(target=run, daemon=True).start()
        return stop                                  ## stop.set() ends it

``logger.maintain()`` does the housekeeping of every sink: it enforces ``roll`` and ``maxAge`` of the file sinks (also the file of
the logger itself), and a spool drops its segments older than ``maxAge`` and tries again to delete files that were in use. It
sends nothing, it is safe from any thread, and it reports for each sink what it did. ``flush()`` is the call that pushes data out.

Limits to know:

* A tool such as ``logrotate`` that renames the file being written is not noticed: the sink goes on writing to the renamed file until
  its own limit. Use the rotation of the sink, or close the sink after the other tool has moved the file.
* Two processes writing the same rotating file each count their own size, so they rotate independently. Give each its own files.
* Compressing a file replaces ``app_3.log`` by ``app_3.log.gz``: a program that follows the plain file does not see the compressed one.
* A forked child does not compress. The files stay plain until a process starts the sink and compresses them.

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

JSON schema
-----------

``JsonFormatter`` (the keyword ``'json'`` or ``'jsonl'``, and the default of every new sink) writes one object on one line. The
layout is documented, and a test compares this page with what the formatter writes, so it cannot drift. The schema number is
in every line. A later release may add keys, and never changes or removes one without changing that number.

.. code-block:: json

    {"schema":1,"timestamp":"2026-10-06T13:31:52.123-05:00","severity":"ERROR","log_type":"error","level":30.0,"logger":"orders","message":"Database connection failed","exception":{"type":"ConnectionError","message":"timed out","stacktrace":"Traceback (most recent call last):\n  File \"db.py\", line 9, in connect\nConnectionError: timed out"},"caller":{"file":"db.py","line":9,"function":"connect","module":"orders.db"},"process":{"id":4321},"thread":{"id":140234,"name":"worker-3"},"context":{"service":"checkout","request_id":"r-77"},"fields":{"order_id":123,"retries":3,"ratio":"NaN"}}

======================  ============================  ===========================================================================
Key                     Type                          Meaning
======================  ============================  ===========================================================================
``schema``              integer                       The version of this layout, 1.
``timestamp``           text                          ISO 8601 with milliseconds and the offset of the time zone, ``Z`` for UTC.
``severity``            text                          The display name of the log type, ``ERROR``.
``log_type``            text                          The name of the log type, ``error``.
``level``               number or null                The numeric level of the log type.
``logger``              text                          The name of the logger.
``message``             text                          The message.
``exception``           object, when there is one     ``type``, ``message`` (null when only the traceback is known), ``stacktrace``.
``caller``              object, when recorded         ``file``, ``line``, ``function``, ``module``, with ``callerInfo=True``.
``process``             object                        ``id``.
``thread``              object                        ``id`` and ``name``.
``context``             object, when not empty        Ambient values: ``bind()``, ``context()``, ``add_context()``.
``fields``              object, when not empty        The values given with the log call.
======================  ============================  ===========================================================================

``JsonFormatter(flatten=True)`` writes the entries of ``context`` and ``fields`` at the top level instead, in this order, and a
field wins over a context value of the same name. A name that is one of the keys above is written as ``fields.<name>`` or
``context.<name>`` and never replaces the key:

.. code-block:: json

    {"schema":1,"timestamp":"2026-10-06T13:31:52.123-05:00","severity":"ERROR","log_type":"error","level":30.0,"logger":"orders","message":"Database connection failed","exception":{"type":"ConnectionError","message":"timed out","stacktrace":"Traceback (most recent call last):\n  File \"db.py\", line 9, in connect\nConnectionError: timed out"},"caller":{"file":"db.py","line":9,"function":"connect","module":"orders.db"},"process":{"id":4321},"thread":{"id":140234,"name":"worker-3"},"service":"checkout","request_id":"r-77","order_id":123,"retries":3,"ratio":"NaN"}

``JsonFormatter(utc=True)`` converts the timestamp to UTC and writes it with a ``Z``, whatever the time zone of the logger. The instant is
the same:

.. code-block:: json

    {"schema":1,"timestamp":"2026-10-06T18:31:52.123Z","severity":"ERROR","log_type":"error","level":30.0,"logger":"orders","message":"Database connection failed","exception":{"type":"ConnectionError","message":"timed out","stacktrace":"Traceback (most recent call last):\n  File \"db.py\", line 9, in connect\nConnectionError: timed out"},"caller":{"file":"db.py","line":9,"function":"connect","module":"orders.db"},"process":{"id":4321},"thread":{"id":140234,"name":"worker-3"},"context":{"service":"checkout","request_id":"r-77"},"fields":{"order_id":123,"retries":3,"ratio":"NaN"}}

What a value becomes, so that a line is always valid JSON and a record is never lost for one value:

* Text, integers, booleans and null are written as they are. A float that is finite is written as a number.
* ``NaN``, ``Infinity`` and ``-Infinity`` are written as the **text** ``"NaN"``, ``"Infinity"`` and ``"-Infinity"``, because JSON has no
  such numbers and a strict parser refuses the whole line when it meets one. The example above has one in ``ratio``.
* Dictionaries, lists and tuples are written as objects and arrays. A key that is not text is written as its text, and a structure
  nested more than 20 levels, or one that contains itself, is cut with the text ``"<too deep>"``.
* Any other value, a set, bytes or an object, is written as its ``repr`` text. A value whose ``repr`` raises is written as
  ``"<unprintable TypeName: ErrorClass>"``, never with the message of the error.

A record can also carry the identifiers of the distributed trace it was made in (``record.trace``), for the sinks that send records to
a tracing backend. They are **not** part of schema 1: the JSON, text and template formats never write them, so asking for them in one
sink changes the output of no other.

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

Three ready-made filters choose by the structure of the record, not by its text. ``match_logger()`` keeps the records of the loggers
that are named, or inside them (``urllib3`` also matches ``urllib3.connectionpool`` and not ``urllib3x``), which is what the
standard ``logging`` bridge needs. ``match_module()`` keeps the records of the modules that are named, when the logger records
the caller (``callerInfo=True``), and keeps what it cannot judge. ``match_field()`` keeps the records whose field or context
value is one of the values given. Each takes ``exclude=True`` to drop the matches instead:

.. code-block:: python

    from pysimplelog import match_logger, match_field

    l.add_filter(match_logger("urllib3", "asyncio", exclude=True))                 ## silence two noisy libraries
    l.add_filter(match_field("environment", "test", exclude=True))                ## nothing from the test environment
    l.set_sink_filter("audit", match_field("category", "security", "billing"))    ## the audit sink gets two categories only

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

Sending records in groups
-------------------------

A destination that takes many records in one request, an HTTP endpoint for example, is far cheaper to feed in groups. A sink
asks for this with ``batchSize`` and implements ``write_batch`` instead of ``write``:

.. code-block:: python

    from pysimplelog import Sink
    from pysimplelog.sinks import SPLIT

    class BulkSink(Sink):
        def __init__(self, url):
            super().__init__(formatter="json", batchSize=500, batchInterval=1.0)
            self.url = url

        def write_batch(self, items):            ## items: [(text, record), ...], oldest first
            status = post(self.url, [text for text, record in items])
            if status == 400:
                return SPLIT                     ## refused as a whole, without saying which record is at fault
            if status != 200:
                return False                     ## try the whole group again later
            ## returning nothing says every record was delivered

    logger.add_sink("bulk", BulkSink("https://bulk.example.org/ingest"), threaded=True)

The worker of a ``threaded`` sink waits for the first record, then up to ``batchInterval`` seconds, counted from that first record,
for the group to fill to ``batchSize``, and sends what it has. A group that is already full, which is what a backlog
makes, goes at once, and so do ``logger.flush()``, removing the sink and leaving the program: none of them waits for the
interval. A sink that is not threaded gets one record at a time through ``write_batch``, because there is nothing to group.

With a spool, the same happens, and the records stay on disk until the group is delivered:

* A group that fails is sent again whole, after the growing wait, and nothing after it is sent first. With ``maxAttempts`` set,
  the records of a group that failed that many times go to the ``dead`` file.
* ``SPLIT`` makes the worker send the group in two halves, the first half first, and so on, until the one record the
  destination refuses is alone. That record goes to the ``dead`` file and all the others are delivered, in order.
* A record the formatter cannot render goes to the ``dead`` file on its own, and the rest of its group is sent.
* A crash can make the records of the last group arrive twice, and each record keeps its ``event_id``.

``logger.sink_stats(name)["delivery"]`` counts ``processed`` records, ``failed`` attempts (a group that fails counts once),
and the latency of a delivery call, which is one call for a whole group.

OpenTelemetry logs (OTLP)
-------------------------

``pysimplelog.contrib.otlp_sink`` sends records to an OpenTelemetry Collector, or to any backend that accepts OTLP over HTTP, with
the standard library only. It is optional: nothing in the core imports it.

.. code-block:: python

    from pysimplelog import Logger
    from pysimplelog.contrib.otlp_sink import attach

    logger = Logger("orders")
    attach(logger, "https://collector.example.org:4318",
           headers={"Authorization": "Bearer <token>"},
           resource={"service.name": "orders", "deployment.environment": "production"},
           compress=True)
    logger.error("Payment failed", order_id=123)

``attach`` adds one sink and makes it ``threaded``, so a log call never waits for the network. It is the same as
``logger.add_sink(name, OtlpLogSink(...), threaded=True)``. To keep the records through a collector that is down, or a crash, give it
a spool, as for any sink:

.. code-block:: python

    MB = 1024 ** 2
    attach(logger, "https://collector.example.org:4318", resource={"service.name": "orders"},
           spool={"path": "/var/spool/orders/otel",   ## fixed in the application, the same in every run
                  "id": "orders-otel", "maxBytes": 50 * MB, "totalMaxBytes": 200 * MB})

What is sent
~~~~~~~~~~~~

Records are sent in groups: up to ``batchSize`` (512) records, or what has arrived after ``batchInterval`` (1 second), whichever comes
first. These are the defaults of the OpenTelemetry SDKs. ``logger.flush()``, removing the sink and leaving the program send what is
waiting at once. Each record becomes one OTLP log record, with the names of the OpenTelemetry semantic conventions:

=========================  ================================================================================================
OTLP                       From the record
=========================  ================================================================================================
``timeUnixNano``           ``timestamp``, exact to the microsecond
``observedTimeUnixNano``   the moment the group is sent
``severityNumber``         the log type: debug 5, info 9, warn 13, error 17, critical 21; any other name 9, or what you give
``severityText``           ``severity``, the display name of the log type
``body``                   the message
``traceId``, ``spanId``    the active span, see below
``log.record.uid``         the field ``event_id``, the identifier a spool adds, by which a receiver can drop a repeat
``process.pid``            the process
``thread.id``, ``name``    the thread
``code.file.path`` ...     the caller, when the logger has ``callerInfo=True``
``exception.*``            the exception: type, message and stack trace
other attributes           the context, then the fields (a field replaces a context value of the same name)
scope name                 the logger name
resource                   the ``resource`` you give, and ``telemetry.sdk.name``, ``.language`` and ``.version``
=========================  ================================================================================================

A field named like one of the attributes above is kept under ``fields.<name>``, and a context value under ``context.<name>``, so
nothing is lost and nothing replaces what the encoder writes. Values are converted as for JSON: integers as text when OTLP says so,
``NaN`` and ``Infinity`` as text, bytes as base64, nested dictionaries and lists as OTLP values, anything else as its ``repr``.
Without a ``service.name`` in *resource* the receiver shows ``unknown_service``. This is the request for one record:

.. otlp-example-start

.. code-block:: json

    {
      "resourceLogs": [
        {
          "resource": {
            "attributes": [
              {"key": "telemetry.sdk.name", "value": {"stringValue": "pysimplelog"}},
              {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
              {"key": "telemetry.sdk.version", "value": {"stringValue": "6.0.0"}},
              {"key": "service.name", "value": {"stringValue": "orders"}},
              {"key": "deployment.environment", "value": {"stringValue": "production"}}
            ]
          },
          "scopeLogs": [
            {
              "scope": {
                "name": "orders"
              },
              "logRecords": [
                {
                  "timeUnixNano": "1791311512123456000",
                  "severityNumber": 17,
                  "severityText": "ERROR",
                  "body": {
                    "stringValue": "Payment failed"
                  },
                  "attributes": [
                    {"key": "log.record.uid", "value": {"stringValue": "slot-7"}},
                    {"key": "process.pid", "value": {"intValue": "4321"}},
                    {"key": "thread.id", "value": {"intValue": "140234"}},
                    {"key": "thread.name", "value": {"stringValue": "worker-3"}},
                    {"key": "code.file.path", "value": {"stringValue": "billing.py"}},
                    {"key": "code.function.name", "value": {"stringValue": "orders.billing.charge"}},
                    {"key": "code.line.number", "value": {"intValue": "42"}},
                    {"key": "exception.type", "value": {"stringValue": "PaymentError"}},
                    {"key": "exception.message", "value": {"stringValue": "card declined"}},
                    {"key": "exception.stacktrace", "value": {"stringValue": "Traceback (most recent call last):\n  File \"billing.py\", line 42, in charge\nPaymentError: card declined"}},
                    {"key": "request_id", "value": {"stringValue": "r-77"}},
                    {"key": "order_id", "value": {"intValue": "123"}},
                    {"key": "amount", "value": {"doubleValue": 12.5}}
                  ],
                  "flags": 1,
                  "traceId": "0af7651916cd43dd8448eb211c80319c",
                  "spanId": "b7ad6b7169203331",
                  "observedTimeUnixNano": "1790000000000000000"
                }
              ]
            }
          ]
        }
      ]
    }

.. otlp-example-end

Trace correlation
~~~~~~~~~~~~~~~~~

When the package ``opentelemetry-api`` is installed, the sink records the identifiers of the active span in each record, so that the
backend can open the trace from the log line. This is read when the log call is made, in the calling thread, because the thread of
the sink does not know the span. The identifiers are kept with the record, also in the spool, so a record sent after a restart
carries its own trace. No other sink changes: the built-in formats never write them. ``captureTrace=False`` switches it off, and
``captureTrace=True`` asks for it and warns once if the package is missing. The default does it when the package is there and says
nothing when it is not.

When the receiver does not take a group
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The sink follows the OTLP/HTTP specification, with one difference, in the last row:

==========================================  ==========================================================================================
The receiver                                The sink
==========================================  ==========================================================================================
takes it (any 2xx)                          Delivered. A ``partialSuccess`` that names refused records is counted and warned about
                                            once, and the group is not sent again.
is busy or not reachable (429, 502, 503,    Tries again at once, ``maxRetries`` times (2), after the ``Retry-After`` wait or a growing
504, no answer)                             wait with jitter. Then it gives the group back: a spool keeps it and tries again, for
                                            ever unless ``maxAttempts`` is set, and without a spool it is dropped and counted.
refuses the payload (400, 413, 422)         Cuts the group in two, and again, until the record at fault is alone. That one goes to the
                                            ``dead`` file of the spool, and the others are delivered.
anything else (401, 403, 404, 500 ...)      The specification says never to retry. The sink does not retry at once and warns once.
                                            With a spool the records **wait** for you to fix the address or the token, and are not
                                            thrown away.
==========================================  ==========================================================================================

The connection is kept open between requests, a redirect is not followed (it could send your token to another host), and the proxy
settings of the environment are not used. The token in *headers* is never written to a log line, to the spool, or to the identity
that decides which sink may take over a spool.

Watching it
~~~~~~~~~~~

``logger.sink_stats("otlp")["delivery"]`` has ``sent`` (records the receiver took), ``batches``, ``bytes`` (of the JSON bodies, before
compression), ``partial_rejected``, ``retries``, ``refused``, ``errors`` (answers the protocol does not retry) and ``last_status``,
with ``processed``, ``failed`` and the latency of every sink. ``["spool"]`` says what is waiting on disk.

Things to know
~~~~~~~~~~~~~~

* Without ``threaded=True`` every log call waits for the network. ``attach`` sets it for you.
* The spool names its identifier field ``event_id``. If you change ``eventIdField`` in the spool settings, give the sink the same
  ``eventIdField``, or the records go without ``log.record.uid``.
* A formatter set on this sink changes nothing: it makes its own body.
* ``compress=True`` is worth it for a collector that is not on the same machine: the body of 512 records is about 90 times smaller
  for records that look alike. A body of unlike records compresses less.
* The sink delivers logs. It does not export metrics or traces, it does not speak gRPC, and it sends JSON and not protobuf.

The encoder and the transport were compared with the official OpenTelemetry Python encoder (the protobuf messages are equal) and
checked against the OpenTelemetry Collector 0.162.0 in a container: ``examples/12_real_collector_check.py`` does it again. The cost
on this author's machine was 7 microseconds for a log call without a spool and 47 with one, and about 39,000 records a second
without a spool and 19,000 with one to a receiver on the same machine: ``benchmarks/bench_otlp.py`` measures it on yours.

API stability
-------------

From 6.0 the names in ``pysimplelog.__all__``, the public methods and properties of ``Logger``, and the
arguments of ``Logger()`` and ``add_sink()`` are stable. Later 6.x releases only add to them. A removal
or a change of meaning waits for 7.0.
