Queue policies and delivery guarantees
======================================

A queue has a size. When the program logs faster than a sink can write, the queue fills up, and you must say what happens next.
pysimplelog makes you choose, and never loses a record without counting it.

The four policies
-----------------

========================  =======================================================================================
Policy                    What a full queue does with a new record
========================  =======================================================================================
``"block"``               The log call waits for a free place. With a timeout, it gives up and drops the new record.
``"drop_newest"``         The new record is thrown away.
``"drop_oldest"``         The record that has waited longest is thrown away, and the new one is kept.
``"reject"``              The log call raises ``QueueFull``. The other sinks have the record first.
========================  =======================================================================================

For the queue of ``enqueue``:

.. code-block:: python

    from pysimplelog import Logger, QueueFull

    log = Logger("app", logToFile=False, enqueue=True, maxQueueSize=1000, queueFullPolicy="drop_oldest")

    log = Logger("app", logToFile=False, enqueue=True, maxQueueSize=1000,
                 queueFullPolicy="block", queueBlockTimeout=0.5)       ## wait 0.5 seconds, then drop

For the queue of one sink (``threadQueueSize`` is 1000 and the policy is ``drop_oldest`` unless you say otherwise):

.. code-block:: python

    log.add("logs/app.log", threaded=True, threadQueueSize=10000, threadQueuePolicy="block")

``drop_oldest`` is a good default for logs, because the newest records are the most useful, but it does mean that a burst can lose
records. If you must not lose any, use ``"block"`` and accept that the program waits, or use a spool.

Catch the refusal
-----------------

.. code-block:: python

    log = Logger("app", logToFile=False, enqueue=True, maxQueueSize=10, queueFullPolicy="reject")
    try:
        log.info("maybe too many")
    except QueueFull:
        pass                          ## the record was refused, the caller decides what to do

Count what was lost
-------------------

Nothing is lost without being counted:

.. code-block:: python

    log = Logger("app", logToFile=False, enqueue=True, maxQueueSize=1000)
    name = log.add("logs/app.log", threaded=True)

    print(log.queueStats)                       ## the enqueue queue: policy, capacity, depth, queued, dropped, rejected
    print(log.droppedMessages)                  ## records thrown away from it so far
    print(log.sink_stats(name)["queue"])        ## the same for the queue of one sink

A run of losses also writes one line to the error stream, so a full queue is visible without looking at the counters.

The delivery guarantees
-----------------------

* By default a log call writes to the sinks before it returns. Nothing is kept in memory by pysimplelog.
* The records of one thread reach each sink in the order that thread logged them. Different sinks are independent of each
  other. There is no order between a threaded sink and the others.
* ``enqueue=True`` and ``threaded=True`` keep records in memory until a thread writes them.
* A record is never lost without being counted.
* At the normal end of the program the queues are written for up to ``shutdownTimeout`` seconds. What is left is lost and
  reported. ``flush()`` returns ``False`` when its timeout ended first.
* If the program is killed, or ends with ``os._exit``, what is in memory is lost.
* A sink that raises loses that record for itself only. A processor that raises drops the record for every sink, because it
  cannot be sure the secret was removed. A filter that raises keeps the record.
* A sink with a spool keeps its records on disk until they are delivered, in order, and survives a crash. Delivery is at least
  once, so a record can arrive twice, with the same ``event_id`` each time.
* A child made with ``fork`` writes its own records, in the calling thread. No queue is shared between processes.

Next: :doc:`durable_delivery`.
