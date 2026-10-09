Structured fields
=================

Every log call builds one record, and the keyword values you pass are its fields. The message says what happened, the fields
say the details, so that a person can read the first and a program can filter on the second:

.. code-block:: python

    from pysimplelog import logger

    logger.info("Order created", order_id=123, amount=12.5, items=[1, 2], customer={"name": "ann"})

.. code-block:: text

    2026-10-08 18:54:58.449 | INFO     | pysimplelog | Order created order_id=123 amount=12.5 items=[1, 2] customer={'name': 'ann'}

The same record as JSON keeps the types:

.. code-block:: python

    from pysimplelog import CONSOLE_SINK

    logger.set_sink_formatter(CONSOLE_SINK, "json")
    logger.info("Order created", order_id=123, amount=12.5)

.. code-block:: text

    {"schema":1,"timestamp":"2026-10-08T18:54:58.449-05:00","severity":"INFO","log_type":"info","level":10.0,"logger":"pysimplelog","message":"Order created","process":{"id":14066},"thread":{"id":140704461343744,"name":"MainThread"},"fields":{"order_id":123,"amount":12.5}}

Big or multi-line values
------------------------

A field called ``data`` is not written as ``key=value``. It goes on its own line after the message, as it is, which suits a
payload or a table:

.. code-block:: python

    logger.set_sink_formatter(CONSOLE_SINK, "pretty")
    logger.info("Response received", status=200, data='{"ok": true}')

.. code-block:: text

    2026-10-08 18:54:58.449 | INFO     | pysimplelog | Response received status=200
    {"ok": true}

``maxDataSize`` on a ``Logger`` cuts ``data`` when it is too long, and ``maxMessageSize`` does the same for the message.

Using fields later
------------------

Fields are what filters, processors and templates read. A template shows one by name, ``{order_id}``, and a filter chooses on it:

.. code-block:: python

    from pysimplelog import match_field

    logger.add("logs/big_orders.log", filter=match_field("order_id", 123))

``match_field`` keeps the records whose field has one of the values you give. See :doc:`../getting_started` for the other
filters, and for the processors that change records.

Names to avoid
--------------

``exc_info`` and ``countConstraint`` are arguments of the log call, not fields. ``fields`` and ``tback`` are refused, because
they were arguments of older versions and a call written for them would otherwise log the wrong thing. Everything else is a
valid field name. In JSON the fields are kept inside ``fields``, so a field can never overwrite a fixed key such as
``message``.

Values that are the same for a whole request or a whole program are better as context.

Next: :doc:`context`.
