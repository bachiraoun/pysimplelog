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
