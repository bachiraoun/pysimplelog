Getting Started
===============

Installation
------------

Install pysimplelog from PyPI using pip:

.. code-block:: console

    pip install pysimplelog

pysimplelog requires **Python 3.6 or later** and has no mandatory third-party
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

Use ``bind()`` to attach context key-value pairs to every message without
modifying the underlying logger:

.. code-block:: python

    def handle_request(request_id, user):
        log = l.bind(requestId=request_id, user=user)
        log.info("request received")   ## [requestId=x user=y] request received
        log.error("authorisation failed")

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
processor is a ``f(text) -> text`` function run on every finished record before
it reaches any sink; ``logTypes`` limits it to some log types, ``None`` means all:

.. code-block:: python

    def hide_paths(text):
        return text.replace("/opt/myapp/venv/lib/pysimplelog", "<redacted>")

    l.add_processor(hide_paths)                      ## every log type
    l.add_processor(str.upper, logTypes=["critical"])  ## only critical records

    @l.catch(logType="error")
    def load_plugin(path):
        raise ImportError("/opt/myapp/venv/lib/pysimplelog/plugins.py not found")

Processors
----------

A processor is a function ``f(text) -> text`` that rewrites each finished log
record before it reaches any sink (terminal, file, SIEM, ...). It receives the
whole record -- message, data and traceback included -- so one function can hide
local paths or secrets everywhere. ``processors`` is a dictionary: the key ``None``
holds the functions run for every log type, every other key is a log type holding
the functions run only for that type. Functions run in the order they were added,
those for every log type first:

.. code-block:: python

    def hide_paths(text):
        return text.replace("/opt/myapp", "...")

    ## at creation
    l = Logger("my-app", processors={None: [hide_paths], "critical": [str.upper]})

    ## or later
    l.add_processor(hide_paths)                          ## every log type
    l.add_processor(str.upper, logTypes=["critical"])    ## only critical records
    l.processors                                         ## {None: [...], "critical": [...]}

    l.remove_processor(hide_paths)    ## removed from every list it is in

A function that raises is skipped and the record goes on with the text it had; one
warning per function is written to stderr, so a broken processor is never silent.
A function that does not return a string is ignored. A processor must not log.

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
