JSON
====

People read the console. Programs read JSON: a log collector, a search tool, a script. pysimplelog writes **one JSON object per line**
(JSON Lines), the same record that the other layouts show.

Write JSON
----------

.. code-block:: python

    from pysimplelog import logger, CONSOLE_SINK

    logger.set_sink_formatter(CONSOLE_SINK, "json")                     ## the console
    logger.add("logs/events.jsonl", format="json")                      ## a file
    logger.info("Order created", order_id=123, amount=12.5)

One line, shown here on several for reading:

.. code-block:: text

    {"schema":1,
     "timestamp":"2026-10-08T21:30:00.100-05:00",
     "severity":"INFO", "log_type":"info", "level":10.0,
     "logger":"pysimplelog",
     "message":"Order created",
     "process":{"id":14066},
     "thread":{"id":140704461343744,"name":"MainThread"},
     "fields":{"order_id":123,"amount":12.5}}

* ``schema`` is the version of this layout, so a reader knows what to expect.
* ``timestamp`` has milliseconds and the UTC offset.
* ``context``, ``caller`` (with ``callerInfo`` on) and ``exception`` appear when the record has them.
* Values keep their type: numbers stay numbers. Something JSON cannot hold, such as a set, is written with its ``repr``, and
  ``NaN`` is written as a text, so one bad value never loses the record.

The full list of keys is in :doc:`../getting_started`, under "JSON schema".

Options
-------

.. code-block:: python

    from pysimplelog import JsonFormatter

    logger.set_sink_formatter(CONSOLE_SINK, JsonFormatter(utc=True))        ## times in UTC, with a Z
    logger.set_sink_formatter(CONSOLE_SINK, JsonFormatter(flatten=True))    ## context and fields at the top level

With ``flatten=True`` a field called ``message`` would clash with the real key, so it is written as ``fields.message``.

Read it back
------------

.. code-block:: python

    import json

    with open("logs/events.jsonl") as stream:
        records = [json.loads(line) for line in stream]
    errors = [record for record in records if record["severity"] == "ERROR"]

From a shell, ``jq`` reads it the same way:

.. code-block:: console

    jq -r 'select(.severity=="ERROR") | .message' logs/events.jsonl

An exception in JSON
--------------------

.. code-block:: python

    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("Division failed")

The record gets an ``exception`` object with ``type``, ``message`` and ``stacktrace``, so a program does not have to cut the
traceback out of the message.

Why a line can be longer than another library's
-----------------------------------------------

Each record is about 260 characters because it carries the schema version, the log type and level, the process and the thread.
The other libraries write less by default, which makes their lines shorter and a little faster to produce. If you need a leaner
line for one sink, a function formatter can write exactly what you want:

.. code-block:: python

    import json
    logger.set_sink_formatter(CONSOLE_SINK, lambda record: json.dumps({"t": record.timestamp.isoformat(), "m": record.message}))

Next: :doc:`multiple_sinks`.
