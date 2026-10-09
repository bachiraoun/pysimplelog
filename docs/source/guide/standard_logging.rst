Standard logging
================

Most libraries you use, such as ``requests`` or ``urllib3``, log with Python's built-in ``logging`` package. You can send all of
that through pysimplelog, so that it goes to the same sinks, passes the same redaction, and looks the same.

Nothing happens until you ask
-----------------------------

.. code-block:: python

    import logging
    from pysimplelog import Logger, redirect_standard_logging, restore_standard_logging

    log = Logger("app", logToFile=False, consoleFormatter="pretty")
    handler = redirect_standard_logging(log, loggerLevel=logging.INFO)

    logging.getLogger("urllib3.connectionpool").info("Starting new HTTPS connection")
    logging.getLogger("my-lib").warning("disk almost full: %s%%", 93, extra={"disk": "/data"})

    restore_standard_logging(handler)

.. code-block:: text

    ... | INFO     | app | Starting new HTTPS connection logger_name=urllib3.connectionpool
    ... | WARNING  | app | disk almost full: 93% logger_name=my-lib disk=/data

* The name of the standard logger is kept in the field ``logger_name``, and ``extra={...}`` becomes fields.
* Exceptions keep their traceback, and the original time, process, thread and (with ``callerInfo``) file and line are kept.
* ``restore_standard_logging(handler)`` undoes it all.

The standard root logger drops anything below ``WARNING`` before a handler sees it. ``loggerLevel=logging.INFO`` lowers that for
the time of the redirect.

Take only one library
---------------------

.. code-block:: python

    handler = redirect_standard_logging(log, name="urllib3", loggerLevel=logging.DEBUG)

``replace=True`` removes the handlers that the standard logger already had, so its records reach only pysimplelog.

Silence a noisy library
-----------------------

.. code-block:: python

    import pysimplelog

    pysimplelog.disable("urllib3")           ## its records are dropped, by the name it logs under

or by filter, see :doc:`processors_and_filters`.

A sink that logs must not feed itself
-------------------------------------

An HTTP library may log through the standard package while a pysimplelog sink is sending over HTTP. Without care, that record would
come back into the same sink, and be sent again, forever. pysimplelog stops it: a standard record made while a record is being
delivered is dropped and counted.

.. code-block:: python

    handler.droppedRecords                   ## how many were dropped for that reason

The first one also writes a line to the error stream. If you see it, silence the library that logs from inside the sink with
``pysimplelog.disable(name)``.

What does not carry over
------------------------

* A level number that standard logging defines, such as 25, is mapped to the highest log type it reaches. ``levelMap`` changes
  that.
* A bad ``%`` format in the standard call, such as ``logging.warning("%d", "text")``, is reported by Python's own error
  handling and the record is lost, as it is with any standard handler.

Next: :doc:`processors_and_filters`.
