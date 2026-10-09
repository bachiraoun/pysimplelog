OpenTelemetry
=============

**OpenTelemetry** is a common standard for sending logs, traces and metrics to observability tools. Its log protocol is called
**OTLP**. pysimplelog can send its records to an OpenTelemetry Collector, or to any service that takes OTLP over HTTP, using only
the standard library. Like SIEM, it is optional and lives in ``pysimplelog.contrib``.

Send logs to a collector
------------------------

.. code-block:: python

    ## not run: needs a collector
    from pysimplelog import Logger
    from pysimplelog.contrib.otlp_sink import attach

    log = Logger("orders")
    attach(log, "https://collector.example.org:4318",
           headers={"Authorization": "Bearer <token>"},
           resource={"service.name": "orders", "deployment.environment": "production"},
           compress=True)
    log.error("Payment failed", order_id=123)

``attach`` adds a sink that runs in its own thread, so a log call never waits for the network. Records are sent in groups: up to
512, or what has arrived after one second, whichever comes first, as the OpenTelemetry SDKs do. ``log.flush()`` and leaving the
program send what is waiting.

What is sent
------------

Each record becomes one OTLP log record, with the standard names:

* the time, with microsecond precision, and the time it was sent;
* the severity, as a number and as text (``debug`` 5, ``info`` 9, ``warn`` 13, ``error`` 17, ``critical`` 21);
* the message as the body;
* your fields and context as attributes, with their types;
* the exception, the caller and the process and thread as attributes named by the OpenTelemetry conventions;
* the trace and span of the active OpenTelemetry span, if the ``opentelemetry-api`` package is installed and a span is active.

The table of every name is in :doc:`../getting_started`, under "OpenTelemetry logs (OTLP)".

Keep the records through an outage
----------------------------------

.. code-block:: python

    ## not run: needs a collector
    MB = 1024 ** 2
    attach(log, "https://collector.example.org:4318", resource={"service.name": "orders"},
           spool={"path": "/var/spool/orders/otel", "id": "orders-otel", "maxBytes": 50 * MB, "totalMaxBytes": 200 * MB})

With a spool, a record is on disk before the log call returns and is deleted once the collector has it, see
:doc:`durable_delivery`.

Good to know
------------

* The records carry the identifier ``log.record.uid`` (the ``event_id`` a spool adds), so a receiver can drop a repeat after a
  crash.
* A receiver that is not available gets retried with a growing wait. A response that says the request is wrong is not retried.
* It does not send metrics or traces, and it does not use gRPC or protobuf.
* The package ``opentelemetry-api`` is only needed if you want trace and span identifiers on the records. Nothing else is
  required.

Next: :doc:`standard_logging`.
