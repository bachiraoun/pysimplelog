Asynchronous logging
====================

By default a log call writes to every sink before it returns. That is simple and safe, and it is fast for the console and for
files. It is slow when a sink waits for something: a network, a slow disk. Then you want the log call to hand the record over
and return.

A queue and a thread for everything
-----------------------------------

.. code-block:: python

    from pysimplelog import Logger

    log = Logger("app", logToFile=False, enqueue=True)
    log.info("this returns at once")
    log.flush()                    ## waits until everything queued has been written

With ``enqueue=True`` the records wait in one queue, and a background thread writes them. The records of one thread keep their
order.

A queue and a thread for one slow sink
--------------------------------------

Usually only one sink is slow. Give that one its own thread, and the others stay as they are:

.. code-block:: python

    log = Logger("app", logToFile=False)
    log.add("logs/app.log", threaded=True)                      ## written by a thread of its own
    log.info("the console is written now, the file a moment later")
    log.flush()

A slow or broken sink then cannot hold up the other sinks, or the program.

Wait for the queue, and ask whether it worked
----------------------------------------------

``flush`` waits for the queues, and tells you whether everything was written in time:

.. code-block:: python

    isDrained = log.flush(timeout=5.0)
    if not isDrained:
        print("some records are still waiting")

At the normal end of the program the queues are written for up to ``shutdownTimeout`` seconds (5 by default, set in the
``Logger``). Records still waiting after that are lost, and one line on the error stream says how many. The way to be sure is
to call ``flush()`` before the end.

.. code-block:: python

    Logger("app", enqueue=True, shutdownTimeout=30)             ## wait up to 30 seconds at the end

Good to know
------------

* A program that is killed, or that ends with ``os._exit``, loses what is in memory. If that matters, use a spool, see
  :doc:`durable_delivery`.
* A child process made with ``fork`` has no copy of the thread, so it writes its records itself, in the calling thread.
* What happens when a queue fills up is your choice, see :doc:`queue_policies`.
* The records are formatted by the thread that logs or by the worker, depending on the sink. A processor always runs in the
  calling thread, so a secret is gone before the record is queued.

Next: :doc:`queue_policies`.
