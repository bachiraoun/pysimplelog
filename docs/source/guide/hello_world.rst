Hello world
===========

Import the shared logger and use it. There is nothing to set up:

.. code-block:: python

    from pysimplelog import logger

    logger.info("Application started")
    logger.warning("Disk almost full")
    logger.error("Could not reach the database")

In a terminal the severity word is coloured. The lines look like this:

.. code-block:: text

    2026-10-08 18:45:02.761 | INFO     | pysimplelog | Application started
    2026-10-08 18:45:02.761 | WARNING  | pysimplelog | Disk almost full
    2026-10-08 18:45:02.762 | ERROR    | pysimplelog | Could not reach the database

The levels are ``debug``, ``info``, ``warning`` (or ``warn``), ``error`` and ``critical``. ``logger`` is made the first
time you use it, so importing the package does nothing. Every module that imports it shares the same logger.

Putting values in the message
-----------------------------

``{}`` is filled with the values you pass, in order. A ``{name}`` is filled from a keyword value, and that value is also
kept as a field of the record:

.. code-block:: python

    logger.info("User {} logged in from {}", "ann", "10.0.0.7")
    logger.info("Order {order_id} created", order_id=123)

.. code-block:: text

    2026-10-08 18:45:02.762 | INFO     | pysimplelog | User ann logged in from 10.0.0.7
    2026-10-08 18:45:02.762 | INFO     | pysimplelog | Order 123 created order_id=123

A message with braces but no values is written as it is, so ``logger.info('{"a": 1}')`` prints the braces. A log call never
raises because of its message: a missing value leaves the text unchanged.

A library should not use this logger
------------------------------------

The shared ``logger`` belongs to the application. A library that logs should make its own, so that the application decides
what to do with its records:

.. code-block:: python

    from pysimplelog import Logger

    log = Logger("mylib.db", logToFile=False)
    log.info("Connected")

A ``Logger`` you make writes the plain text layout, ``time - name <INFO> message``, unless you give it
``consoleFormatter='pretty'``. The application can silence or redirect it. See :doc:`console`.

Next: :doc:`console`.
