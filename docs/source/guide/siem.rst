SIEM and syslog
===============

A **SIEM** (Security Information and Event Management) system collects the logs of many machines so that a security team can
search them and raise alerts. Most of them accept **syslog** messages. pysimplelog can send its records to one, using the
standard syslog format (RFC 5424). This lives in the optional ``pysimplelog.contrib`` package, and the core does not need it.

Try it without a server
-----------------------

The ``console`` mode prints the messages instead of sending them, so you can see what a collector would receive:

.. code-block:: python

    from pysimplelog import Logger
    from pysimplelog.contrib import siem_sink

    log = Logger("auth", logToFile=False, logToStdout=False)
    sink = siem_sink.quick_attach(log, protocol="console")

    log.info("user bob logged in")
    log.error("failed login attempt", user="mallory")
    log.flush(timeout=2.0)
    siem_sink.detach(log, sink)

Each line is a syslog message: a priority, the time, the host, the program, then the message and the fields.

Send to a real collector
------------------------

Change the protocol and give the address. The rest of the program stays the same:

.. code-block:: python

    ## not run: needs a collector
    sink = siem_sink.quick_attach(log, protocol="tcps", host="siem.example.org", port=6514)   ## TCP with TLS
    sink = siem_sink.quick_attach(log, protocol="udp", host="siem.example.org", port=514)     ## UDP
    sink = siem_sink.quick_attach(log, protocol="https", url="https://siem.example.org/hec")  ## HTTP, such as Splunk

Choose what it gets, so that only the serious records leave the machine:

.. code-block:: python

    ## not run: needs a collector
    from pysimplelog.contrib import siem_transport

    transport = siem_transport.TCPSyslogTransport("siem.example.org", 6514, useTls=True)
    sink = siem_sink.attach(log, transport, logTypeFlags={"warn": True, "error": True, "critical": True}, defaultFlag=False)

Good to know
------------

* The sink runs in a thread of its own, so a slow or unreachable collector never slows the program.
* A sink that keeps failing is stopped for a while by a **circuit breaker**, and tried again later, so it does not use up the
  program's time.
* To keep the records through an outage or a crash, give it a spool, see :doc:`durable_delivery`.
* Secrets: processors run before any sink, so remove them there, see :doc:`processors_and_filters`.
* The long form, with retries, callbacks for dropped records, and the transports' options, is in :doc:`../getting_started`
  and in the API reference, and the ``examples`` folder has runnable scripts.

Next: :doc:`otlp`.
