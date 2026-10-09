Multiple sinks
==============

A **sink** is an output: the console, a file, a function, a network collector. One log call goes to every sink that wants it, and
each sink decides what to write and how.

Several outputs at once
-----------------------

.. code-block:: python

    from pysimplelog import logger, match_logger

    logger.add("logs/app.log", rotation="10 MB", retention=5)                 ## everything, as text
    logger.add("logs/errors.jsonl", format="json", level="ERROR")             ## errors only, as JSON
    logger.add("logs/db.log", filter=match_logger("app.db"))                  ## one part of the application
    logger.add(lambda text, record: print("ALERT", text.strip()), level="CRITICAL")

    logger.info("goes to the console and app.log")
    logger.critical("goes everywhere, and calls the function")

The console is a sink too, and is always there on the shared ``logger``. Each ``add`` returns the sink's name:

.. code-block:: python

    name = logger.add("logs/audit.log")
    logger.remove(name)                    ## stops it and closes the file

What a sink wants
-----------------

A sink takes a record when it passes, in this order:

1. The sink is switched on, and its log types are allowed (``level=``, or ``logTypeFlags``).
2. Your global filters (``add_filter``) keep the record.
3. The sink's own filter (``filter=``, or ``set_sink_filter``) keeps it.

Filters are described in :doc:`processors_and_filters`.

See what each sink did
----------------------

.. code-block:: python

    name = logger.add("logs/stats.log", threaded=True)
    logger.info("something to count")
    logger.flush()

    print(logger.sink_stats(name)["delivery"])    ## processed, failed, last_error, latency_mean, latency_max
    print(logger.sink_stats(name)["queue"])       ## the queue of a threaded sink, or None for the others
    print(list(logger.sink_stats()))              ## every sink by name, and the two built-in ones, -1 (CONSOLE_SINK) and 0 (FILE_SINK)

A sink that raises loses that one record, and only for itself: the others still get it. The failure is counted in ``failed``
and written once to the error stream, with the kind of error and where it came from, but not its message, because a message can
hold secrets. The full error is in ``last_error``.

Silence a library
-----------------

A library that logs with pysimplelog gives its loggers dotted names, such as ``payments.stripe``. You can switch off a whole
branch without touching the library:

.. code-block:: python

    import pysimplelog

    pysimplelog.disable("payments")        ## payments, payments.stripe, payments.db ... are dropped
    pysimplelog.enable("payments")         ## back on

This applies to every logger of the program, and to records that come from the standard ``logging`` package under that name.
``force_log`` is not affected, see the next section.

To cover other processes as well, set the variable before they start, or let the call set it for you:

.. code-block:: python

    pysimplelog.disable("urllib3", env=True)       ## also adds urllib3 to PYSIMPLELOG_NAMESPACE_DISABLE

.. code-block:: console

    PYSIMPLELOG_NAMESPACE_DISABLE="payments,urllib3" python app.py

The variable is read once when the program starts. A child made with ``spawn`` has no list of its own, so it needs the variable.

Messages that must always appear
--------------------------------

Some messages must be written whatever the settings are, such as "the program is stopping". ``force_log`` ignores the level,
the log types that are switched off, the filters and ``disable()``. It goes to every output that is switched on:

.. code-block:: python

    logger.add("logs/audit.log", name="audit", level="CRITICAL")

    logger.info("not written to the audit file")
    logger.force_log("info", "Shutting down")                          ## written to every output that is on
    logger.force_log("error", "Audit trail broken", sinks=["audit"])   ## written only to the output named audit

Processors still run, so a password is hidden in a forced message too. An output that is switched off, such as the log file of a
logger made with ``logToFile=False``, stays silent. ``opt()`` and ``bind()`` work with it:

.. code-block:: python

    logger.opt(depth=1).force_log("info", "Stopped by {}", "ann")

Your own sink
-------------

Any function ``f(text, record)`` is a sink. For more control, subclass ``Sink`` and write ``write(self, text, record)``:

.. code-block:: python

    from pysimplelog import Sink

    class Counter(Sink):
        def __init__(self):
            super().__init__(formatter="text")
            self.count = 0

        def write(self, text, record):
            self.count += 1

    counter = Counter()
    logger.add(counter, level="WARNING")
    logger.warning("one")
    logger.warning("two")

Next: :doc:`async_logging`.
