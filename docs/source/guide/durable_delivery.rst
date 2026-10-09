Durable delivery
================

A record in a queue is in memory. If the program crashes, or the collector it sends to is down for an hour, it is gone. A
**spool** keeps the records of a sink **on disk** until the sink has delivered them. It is off unless you ask for it.

A sink that can be spooled
--------------------------

A sink that sends records somewhere (a collector, an API) can be spooled. A console, a stream or a file cannot, because there is
nothing to wait for. The sink says where it sends, so a spool is only ever taken over by a sink for the same destination:

.. code-block:: python

    import os, tempfile
    from pysimplelog import Logger, Sink

    class Collector(Sink):
        """Stands in for a collector. write() returns False when it cannot deliver."""
        SPOOL_DESTINATION = ("host",)        ## the attributes that say where this sink sends

        def __init__(self):
            super().__init__(formatter=lambda record: record.message)
            self.host = "collector.example.org"
            self.isUp = True
            self.received = []

        def write(self, text, record):
            if not self.isUp:
                return False                 ## "keep it, I could not deliver"
            self.received.append((record.fields["event_id"], text))

    folder = os.path.join(tempfile.mkdtemp(), "spool")
    collector = Collector()
    log = Logger("billing", logToFile=False, logToStdout=False)
    log.add_sink("collector", collector, threaded=True,
                 spool={"path": folder,             ## fixed in your application, the same in every run
                        "id": "billing",            ## the label of this spool
                        "maxBytes": 10 * 1024 ** 2,         ## the most this process keeps
                        "totalMaxBytes": 50 * 1024 ** 2})   ## the most all processes keep

    collector.isUp = False
    log.error("payment failed", order_id=123)       ## on disk before this call returns
    print(log.sink_stats("collector")["spool"]["depth"])    ## 1: waiting
    collector.isUp = True                                   ## the collector is back
    log.flush(timeout=10)
    print(log.sink_stats("collector")["spool"]["depth"])    ## 0: delivered, and the file is deleted
    log.clear_sinks()

What you get
------------

* The record is written to disk by the thread that logs it, **after** the processors and filters, so what is on disk is already
  redacted.
* A worker thread of the sink sends the records in order. A send that fails is tried again after a growing wait, and nothing
  after it is sent first.
* Delivery is **at least once**: after a crash a few records can arrive twice. Each carries the same ``event_id`` field every
  time, so the receiver can tell.
* A clean shutdown leaves no file behind.
* Each process writes to a slot of its own, so processes never share files. If a process dies, another one sends what it left
  behind, either when it is idle (``"adoptOrphans": True``) or when you call ``log.adopt_orphans(name)``. Only a sink made for the
  same ``id``, class and destination will do it.
* For a sink that has no destination attributes, give a ``"target"`` text in the settings instead.

What you can set
----------------

``flush`` (``none``, ``flush``, ``fsync``, ``fullsync``) says how sure a record is to be on the disk. ``policy`` says what a full
spool does (``drop_oldest``, ``drop_newest``, ``block``, ``reject``). Others set the age limit, the file size, how often the
position is saved, the wait between tries, and when to give up. See ``SpoolConfig`` in the API reference, and
:doc:`../getting_started` for the long form.

The cost
--------

Writing to disk costs the logging thread about 30 to 90 microseconds more than a threaded sink without a spool, and more with
``fsync``. That is the price of surviving a crash.

Next: :doc:`siem`.
