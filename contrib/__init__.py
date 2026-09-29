"""Optional, zero-mandatory-dependency integrations for pysimplelog.

Nothing under ``pysimplelog.contrib`` is imported by the core package and
nothing here modifies ``SimpleLog.py``. Everything is a pure consumer of
the public ``Logger.add_sink()`` API, so importing this sub-package has
zero effect on Logger behaviour unless you explicitly wire it up.

Currently available:
    #. ``siem_transport`` -- stdlib-only network transports (TCP+TLS,
       UDP, HTTP) used to ship bytes to a collector.
    #. ``siem_sink`` -- RFC 5424 structured-syslog formatter, a
       non-blocking forwarding sink, and ``attach()``/``detach()``
       helpers that wire it into a pysimplelog ``Logger``.

Quick start -- the fastest way to forward logs to a SIEM (Security
Information and Event Management) collector is ``siem_sink.quick_attach()``.
It picks the right transport for you from a plain protocol string. See its
docstring for an example covering every supported protocol (plain TCP,
TCP+TLS, TCP with mutual TLS, UDP, HTTPS webhooks, and Splunk's HTTP Event
Collector).
"""
