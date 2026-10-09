Console logging
===============

The shared ``logger`` writes to the console in a tidy layout:

.. code-block:: text

    2026-10-08 18:54:58.449 | WARNING  | pysimplelog | shown

The columns are the time with milliseconds, the severity, the logger name and the message. Values passed as keywords follow
the message as ``key=value``. The severity is coloured only when the console is a terminal.

Show less
---------

.. code-block:: python

    from pysimplelog import logger

    logger.set_minimum_level("warn")     ## only warning, error and critical
    logger.info("hidden")
    logger.warning("shown")
    logger.set_minimum_level(None)       ## everything again

The level applies to the console and to the log file of a logger that has one. The shared ``logger`` has no log file, add
one with :doc:`files`.

Change the layout
-----------------

``set_sink_formatter`` changes how the console writes a record. It takes effect on the next call:

.. code-block:: python

    from pysimplelog import logger, CONSOLE_SINK, ConsoleFormatter

    ## a template
    logger.set_sink_formatter(CONSOLE_SINK, "{timestamp:%H:%M:%S} [{severity}] {message}")
    logger.info("Order {} created", 7)

    ## the default layout, with the time in UTC and no milliseconds
    logger.set_sink_formatter(CONSOLE_SINK, ConsoleFormatter(utc=True, milliseconds=False))
    logger.info("Order {} created", 7)

    ## one line of JSON for each record
    logger.set_sink_formatter(CONSOLE_SINK, None)

    ## back to the default
    logger.set_sink_formatter(CONSOLE_SINK, "pretty")

.. code-block:: text

    18:54:58 [INFO] Order 7 created
    2026-10-08 23:54:58Z | INFO     | pysimplelog | Order 7 created

A template can use ``timestamp`` (with a ``strftime`` format such as ``{timestamp:%H:%M:%S}``), ``timestamp_utc``,
``severity``, ``logger``, ``message``, ``caller``, ``fields``, ``context`` and any field you passed. See :doc:`formatting`
for the full list. ``ConsoleFormatter`` takes these options:

====================  ======================================================================================
Option                What it does
====================  ======================================================================================
``colors``            ``True`` writes colour codes. The logger decides this itself from the terminal.
``severityColors``    ``{"INFO": "\x1b[34m"}`` replaces the colour of a severity.
``traceback``         ``'full'`` (default) or ``'compact'``, which drops the source lines of a traceback.
``utc``               ``True`` writes the time in UTC, with a trailing ``Z``.
``milliseconds``      ``True`` (default) writes ``.mmm`` after the seconds.
``colorOf``           A function ``f(record)`` that returns a colour code for a record.
====================  ======================================================================================

Colours
-------

Colours are on when the console is a terminal and the ``NO_COLOR`` variable is not set. To decide yourself, give a logger
you make ``consoleColor='always'``, ``'never'`` or ``'auto'``:

.. code-block:: python

    from pysimplelog import Logger

    log = Logger("api.users", logToFile=False, consoleColor="never")
    log.info("plain, never coloured")

A log type you colour yourself is shown in that colour in the severity column:

.. code-block:: python

    logger.add_log_type("audit", name="AUDIT", level=15, color="magenta")
    logger.log("audit", "user exported the report", user="ann")

.. code-block:: text

    2026-10-08 18:54:58.450 | AUDIT    | pysimplelog | user exported the report user=ann

The five built-in log types keep their default colours unless you give them one.

Show where the call came from
-----------------------------

.. code-block:: python

    logger.set_caller_info(True)
    logger.info("with caller")

.. code-block:: text

    2026-10-08 18:54:58.450 | INFO     | pysimplelog | <stdin>:15 in <module> | with caller

It costs a little for every call, so it is off by default.

Set it from the environment
---------------------------

Three variables set up the shared ``logger`` before your code runs. They are useful for a deployment or a one-off run
without editing code:

=========================  =========================================================================================
Variable                   Meaning
=========================  =========================================================================================
``PYSIMPLELOG_LEVEL``      ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL`` or a number: the lowest level
                           written to the console.
``PYSIMPLELOG_FORMAT``     ``pretty``, ``text``, ``json`` or a template such as ``{timestamp} {message}``.
``PYSIMPLELOG_COLOR``      ``auto``, ``always`` or ``never``.
=========================  =========================================================================================

.. code-block:: console

    PYSIMPLELOG_LEVEL=WARNING PYSIMPLELOG_FORMAT=json python app.py

The order is: what your code asks for, then the variable, then the default. A logger you make yourself ignores the variables
unless you give it ``env=True``. A wrong value raises a ``ValueError`` that names the variable, the first time the logger is
used. The variables are read once, so changing them while the program runs has no effect.

Next: :doc:`files`.
