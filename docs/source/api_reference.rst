API Reference
=============

Core
----

.. automodule:: pysimplelog.simple_log
    :members:
    :undoc-members:
    :show-inheritance:

Records, Formatters and Sinks
-----------------------------

.. automodule:: pysimplelog.record
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.formatters
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.sinks
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.processors
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.filters
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.standard_logging
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.log_context
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.queues
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.namespaces
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.environment
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.secret
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.diagnose
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.sink_options
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.message_format
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.default_logger
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.spool
    :members:
    :show-inheritance:

SIEM / Syslog Forwarding (pysimplelog.contrib)
-----------------------------------------------

Optional, zero-mandatory-dependency add-on for forwarding log records to a
SIEM (Security Information and Event Management) or syslog collector. See
:doc:`getting_started` for a quick example, or the ``examples/`` directory
in the source distribution for runnable end-to-end scripts covering
console, UDP, TCP, and HTTP collectors.

.. automodule:: pysimplelog.contrib.siem_sink
    :members:
    :undoc-members:
    :show-inheritance:

.. automodule:: pysimplelog.contrib.siem_transport
    :members:
    :undoc-members:
    :show-inheritance:

OpenTelemetry Logs (pysimplelog.contrib)
----------------------------------------

Optional, zero-mandatory-dependency add-on for sending log records to an OpenTelemetry Collector, or to any backend that accepts OTLP
over HTTP. See :doc:`getting_started` for the example, the mapping of a record, and what happens when the receiver does not take a
group, or ``examples/11_opentelemetry_logs.py`` for a script that runs as it is.

.. automodule:: pysimplelog.contrib.otlp_sink
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.contrib.otlp_encoder
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.contrib.otlp_transport
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.tracing
    :members:
    :show-inheritance:

Internals
---------

These modules do the work behind the scenes. You do not call them, but their behaviour is described here.

.. automodule:: pysimplelog.durable
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.delivery_guard
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.forking
    :members:
    :show-inheritance:

.. automodule:: pysimplelog.traceback_cache
    :members:
    :show-inheritance:
