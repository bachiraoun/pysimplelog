Exceptions
==========

When something fails you want the message, the traceback, and ideally the values that caused it. pysimplelog gives all three,
and each is a small step from the one before.

Log the error you are handling
------------------------------

``logger.exception`` logs at error level and attaches the traceback of the exception being handled:

.. code-block:: python

    from pysimplelog import logger

    def charge(price, quantity):
        return price * quantity

    try:
        charge(19.9, None)
    except TypeError:
        logger.exception("Payment of {} failed", 7)

.. code-block:: text

    2026-10-08 21:30:00.100 | ERROR    | pysimplelog | Payment of 7 failed
    Traceback (most recent call last):
      File "pay.py", line 7, in <module>
        charge(19.9, None)
      File "pay.py", line 4, in charge
        return price * quantity
               ~~~~~~^~~~~~~~~
    TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'

Give ``logType="critical"`` to log at another level. Chained errors (``raise ... from ...``) are written the way Python
writes them, with the cause first.

Other ways to attach an exception
---------------------------------

.. code-block:: python

    try:
        charge(19.9, None)
    except TypeError as error:
        logger.error("Payment failed", exc_info=error)             ## the exception you hold
        logger.opt(exception=True).error("Payment failed")         ## the one being handled, with the other options

Let a function or a block catch the errors
------------------------------------------

``catch`` logs an error and carries on, so one failing step does not stop the program:

.. code-block:: python

    @logger.catch
    def risky():
        raise ValueError("something went wrong")

    risky()                          ## logged, and the program continues

    with logger.catch(reraise=False):
        charge(19.9, None)

``catch(logType="critical", reraise=True)`` logs and then raises the error again.

A shorter traceback
-------------------

The console can write a shorter traceback: the files, lines and functions, and the error, without the source lines:

.. code-block:: python

    from pysimplelog import CONSOLE_SINK, ConsoleFormatter

    logger.set_sink_formatter(CONSOLE_SINK, ConsoleFormatter(traceback="compact"))

The log file and JSON keep the full text.

See the values that caused it
-----------------------------

``diagnose`` adds the variables used on each line of the traceback. It is meant for development, and it is off by default:

.. code-block:: python

    from pysimplelog import Logger

    log = Logger("shop", logToFile=False, diagnose="summary")

    def charge(price, user_password):
        return price * user_password

    try:
        charge(19.9, None)
    except TypeError:
        log.exception("Payment failed")

.. code-block:: text

      File "pay.py", line 20, in charge
        return price * user_password
               ~~~~~~^~~~~~~~~~~~~~~
            price = 19.9
            user_password = <redacted>

* ``"summary"`` shows numbers, text, ``None`` and booleans in full, and shows lists, dictionaries and objects only by type and
  length, such as ``<dict len=3>``. ``"full"`` shows the ``repr`` of everything.
* A variable whose name contains ``password``, ``token``, ``authorization``, ``api_key``, ``ssn``, ``credit_card``, ``secret``, ``cookie`` or ``credential``
  always shows ``<redacted>``. Add names with ``Logger(..., diagnoseRedact=("card",))``.
* The values are in the record, so **every** output gets them, files and network sinks included. Use it in development, not in
  production.
* The values come from the source lines of your files, so it shows nothing for code typed into an interactive prompt.
* To change it on a running logger: ``logger.set_diagnose("summary")`` and ``logger.set_diagnose(False)``.

Hiding secrets in a traceback
-----------------------------

The message and the traceback pass through your processors like everything else, so ``redact_text`` and ``redact_patterns``
clean them, see :doc:`processors_and_filters`.

Next: :doc:`json`.
