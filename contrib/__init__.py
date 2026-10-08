"""Optional, zero-mandatory-dependency integrations for pysimplelog.

Nothing under ``pysimplelog.contrib`` is imported by the core package and
nothing here modifies ``simple_log.py``. Everything is a pure consumer of
the public ``Logger.add_sink()`` API, so importing this sub-package has
zero effect on Logger behaviour unless you explicitly wire it up.

Currently available:
    #. ``siem_transport`` -- stdlib-only network transports (TCP+TLS,
       UDP, HTTP) used to ship bytes to a collector.
    #. ``otlp_encoder`` -- turns records into the OpenTelemetry OTLP/JSON
       layout of a logs export request, with no third-party package.
    #. ``otlp_transport`` -- posts that body to an OTLP/HTTP receiver over a
       kept-alive connection and says how the receiver answered.
    #. ``otlp_sink`` -- the sink that joins them to the group delivery and the
       spool, and ``attach()`` to add it to a ``Logger``.
    #. ``siem_sink`` -- RFC 5424 structured-syslog formatter, a
       non-blocking forwarding sink, and ``attach()``/``detach()``
       helpers that wire it into a pysimplelog ``Logger``.

Quick start -- the fastest way to forward logs to a SIEM (Security
Information and Event Management) collector is ``siem_sink.quick_attach()``.
It picks the right transport for you from a plain protocol string. See its
docstring for an example covering every supported protocol (plain TCP,
TCP+TLS, TCP with mutual TLS, UDP, HTTPS webhooks, and Splunk's HTTP Event
Collector).

Quick start -- the fastest way to send logs to an OpenTelemetry Collector is
``otlp_sink.attach()``. It adds one threaded sink that sends the records in
groups over OTLP/HTTP, with the standard library only::

    from pysimplelog import Logger
    from pysimplelog.contrib.otlp_sink import attach

    logger = Logger("orders")
    attach(logger, "https://collector.example.org:4318",
           resource={"service.name": "orders"}, compress=True)

Give it ``spool=`` to keep the records on disk through an outage or a
crash. See its docstring and the documentation for what is sent and what
happens when the receiver does not take a group.
"""
