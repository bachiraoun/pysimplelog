Coming from another library
===========================

If you already know Loguru, the standard ``logging`` module or structlog, this page shows how the same things look here.

From Loguru
-----------

.. code-block:: python

    ## Loguru
    from loguru import logger
    logger.add("app.log", rotation="500 MB", retention="30 days", level="INFO")
    logger.info("User {} logged in", user_id)
    logger.bind(request_id=rid).info("Handled")
    logger.opt(lazy=True).debug("Result: {}", lambda: slow())
    logger.exception("Failed")

    ## pysimplelog
    from pysimplelog import logger
    logger.add("app.log", rotation="500 MB", retention="30 days", level="INFO")
    logger.info("User {} logged in", user_id)
    logger.bind(request_id=rid).info("Handled")
    logger.opt(lazy=True).debug("Result: {}", slow)
    logger.exception("Failed")

========================================  ==========================================================
Loguru                                    pysimplelog
========================================  ==========================================================
``logger.remove(id)``                     ``logger.remove(name)``
``serialize=True``                        ``format="json"``
``enqueue=True`` on a sink                ``threaded=True`` on ``add``, or ``Logger(enqueue=True)``
``logger.contextualize(...)``             ``with context(...):``
``logger.disable("lib")``                 ``pysimplelog.disable("lib")``
``backtrace`` and ``diagnose``            ``diagnose="summary"`` on the logger
``logger.level("NAME", no=...)``          ``logger.add_log_type("name", name="NAME", level=...)``
``@logger.catch``                         ``@logger.catch``
========================================  ==========================================================

Differences to know:

* The shared ``logger`` writes to the **standard output** in its own layout, not to the error stream.
* ``format`` is a template with ``{timestamp}``, ``{severity}``, ``{message}`` and your fields, not Loguru's ``{time}``, ``{level}``.
* Fields are passed as keyword arguments and kept as separate values, where Loguru uses ``bind`` for them.
* Beyond Loguru: processors and filters that run in front of every sink, per-sink queues with explicit policies, a disk spool, SIEM and
  OpenTelemetry outputs, and counters for everything that is dropped.

From the standard ``logging`` module
------------------------------------

.. code-block:: python

    ## logging
    import logging
    log = logging.getLogger("app")
    logging.basicConfig(level=logging.INFO)
    log.info("order %s created", order_id, extra={"customer": name})
    log.exception("Failed")

    ## pysimplelog
    from pysimplelog import Logger
    log = Logger("app", consoleFormatter="pretty", logToFile=False)
    log.info("order {} created", order_id, customer=name)
    log.exception("Failed")

* ``%s`` becomes ``{}``, and ``extra={...}`` becomes keyword arguments.
* There are no handlers and formatters to wire together: ``log.add(...)`` makes the output and ``format=`` sets its layout.
* To keep libraries that use ``logging``, send them in with ``redirect_standard_logging``, see :doc:`standard_logging`.

From structlog
--------------

.. code-block:: python

    ## structlog
    import structlog
    log = structlog.get_logger().bind(service="orders")
    log.info("order_created", order_id=123)

    ## pysimplelog
    from pysimplelog import logger
    log = logger.bind(service="orders")
    log.info("order created", order_id=123)

* A structlog processor chain becomes ``add_processor`` for changes and ``add_filter`` for dropping, with ``redact_fields`` and
  ``redact_patterns`` ready-made.
* ``JSONRenderer`` becomes ``format="json"``, and ``ConsoleRenderer`` becomes the ``"pretty"`` layout.
* ``structlog.contextvars`` becomes ``context(...)``, and it also works across ``asyncio`` tasks.
* Output goes to sinks you can add, remove and give a level and a filter, instead of one logger factory.
