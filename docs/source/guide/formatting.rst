Formatting
==========

Two things are called formatting: how the message is built, and how a record is written. The first is done by the log call,
the second by each output.

Building the message
--------------------

.. code-block:: python

    from pysimplelog import logger

    logger.info("User {} logged in from {}", "ann", "10.0.0.7")      ## in order
    logger.info("{1} then {0}", "a", "b")                            ## by position
    logger.info("Order {order_id} created", order_id=123)            ## by name

The rules are few:

* ``{}`` and ``{0}`` take the positional values, ``{name}`` takes a keyword value. Keyword values are also kept as fields.
* A value is written with ``str``, and ``{:>8}``, ``{:.2f}`` and ``{!r}`` work as in Python.
* A message with no values is never formatted, so braces in it are text.
* A placeholder cannot read inside a value: ``{0.name}`` and ``{0[key]}`` are refused, and the message is written unchanged.
* A missing value, a wrong index or a value that cannot be printed never raises. The text is left as it was, or the value is
  replaced by ``<unprintable TypeName: ErrorClass>``.

Secrets given as values are in the text. See :doc:`../getting_started` for ``redact_patterns`` and ``Secret``.

Do the work only when it is needed
----------------------------------

``opt(lazy=True)`` calls the functions you pass only if a sink will write the record:

.. code-block:: python

    def slow_summary():
        return "the report took a long time to build"

    logger.opt(lazy=True).debug("Report: {}", slow_summary)

If no sink wants ``debug``, ``slow_summary`` is not called. Filters and processors read the finished record, so a record they
drop has been computed already.

Wrappers and the caller
-----------------------

When you log from a helper, the file and line shown are the helper's. ``depth`` skips frames:

.. code-block:: python

    logger.set_caller_info(True)

    def log_audit(message):
        logger.opt(depth=1).info(message)       ## shows the caller of log_audit

    log_audit("exported")

Writing the record
------------------

Each output turns a record into text with a formatter. These keywords are always available:

========================  ==============================================================================
Keyword                   Result
========================  ==============================================================================
``"pretty"``              The console layout, with columns and optional colour.
``"text"``                ``time - logger <SEVERITY> message key=value``, the default for files.
``"json"`` / ``"jsonl"``  One line of JSON for each record.
``None``                  JSON.
========================  ==============================================================================

A string with braces is a template:

.. code-block:: python

    from pysimplelog import logger, CONSOLE_SINK

    logger.set_sink_formatter(CONSOLE_SINK, "{timestamp:%H:%M:%S} {severity:<8} {message} user={user_id:05d}")
    logger.info("login", user_id=7)
    logger.info("no user here")

.. code-block:: text

    18:54:58 INFO     login user=00007
    18:54:58 INFO     no user here user=

The names a template can use are ``timestamp``, ``timestamp_utc``, ``severity``, ``log_type``, ``level``, ``logger``,
``message``, ``fields``, ``context``, ``exception`` (the traceback text), ``caller``, ``file``, ``line``, ``function``, ``module``,
``process``, ``thread``, ``thread_name`` and every field and context value. A name the record does not have is empty, whatever
its format. ``timestamp`` is ISO text unless you give a ``strftime`` format. A field called ``line`` is yours, and is not
replaced by the line number.

A function is the most general formatter. It gets the record and returns text:

.. code-block:: python

    logger.set_sink_formatter(CONSOLE_SINK, lambda record: f"{record.severity}: {record.message}")
    logger.info("Done")

.. code-block:: text

    INFO: Done

If a formatter raises, the record is lost for that output only, and the failure is counted in ``sink_stats``.

Control characters
------------------

A value written on a ``key=value`` line cannot start a new line or paint your terminal. The text, pretty and template layouts
write a line break in a value, or in a name, as ``\n``, and an escape character as ``\x1b``:

.. code-block:: python

    logger.set_sink_formatter(CONSOLE_SINK, "pretty")
    logger.info("login", agent="Mozilla\n2026-01-01 | CRITICAL | forged line")

.. code-block:: text

    2026-10-08 18:54:58.449 | INFO     | pysimplelog | login agent=Mozilla\n2026-01-01 | CRITICAL | forged line

JSON escapes them as it always did. Messages keep their line breaks. The ``data`` field is written on its own line as it is.

Next: :doc:`structured_fields`.
