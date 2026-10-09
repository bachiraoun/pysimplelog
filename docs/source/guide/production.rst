Production setup
================

A setup that has worked well for services, in one place. Take what fits, and read the page it links to for the reasons.

A starting point
----------------

.. code-block:: python

    import os
    import socket
    from pysimplelog import Logger, add_context, redact_fields, redact_patterns

    LOG_FOLDER = os.environ.get("LOG_FOLDER", "logs")

    log = Logger("billing", logToFile=False, consoleFormatter="pretty", env=True, shutdownTimeout=10)

    ## 1. secrets and shared values, before any output sees a record
    log.add_processor(redact_fields())
    log.add_processor(redact_patterns())
    log.add_processor(add_context(service="billing", environment=os.environ.get("ENV", "dev"), host=socket.gethostname()))

    ## 2. everything, as JSON, rotated, compressed, written by a thread of its own
    log.add(os.path.join(LOG_FOLDER, "billing.jsonl"), format="json", rotation="100 MB", retention="14 days",
            compression="gz", threaded=True)

    ## 3. errors apart, readable, for a person looking at the files
    log.add(os.path.join(LOG_FOLDER, "errors.log"), level="ERROR", rotation="50 MB", retention=10)

    log.info("Service started", port=8080)

    ## at the end of the program, if it can end normally
    log.flush(timeout=10)

The checklist
-------------

**Output**

* JSON for anything a program reads (:doc:`json`), pretty text for people.
* Rotate every file and say how many or how old to keep (:doc:`files`). A file that is never rotated grows until the disk is full.
* Give a slow output its own thread with ``threaded=True`` (:doc:`async_logging`).

**Safety**

* Add ``redact_fields`` and ``redact_patterns`` first (:doc:`processors_and_filters`). A secret in the message text itself is only
  caught by the patterns, so keep secrets out of messages.
* Leave ``diagnose`` off. It writes variable values to every output (:doc:`exceptions`).
* Use ``Secret(...)`` for values that must never be printed.

**Not losing records**

* Choose a queue policy on purpose (:doc:`queue_policies`). The default for a threaded sink is ``drop_oldest`` with 1000 places,
  so a burst can lose records, and the loss is counted.
* Call ``log.flush(timeout=...)`` before the program ends, and check what it returns.
* For records that must survive a crash or an outage, use a spool (:doc:`durable_delivery`).
* Watch ``log.sink_stats()`` and ``log.droppedMessages``. Nothing is lost silently, but you have to look.

**Environment**

* ``PYSIMPLELOG_LEVEL``, ``PYSIMPLELOG_FORMAT`` and ``PYSIMPLELOG_COLOR`` change the console without editing code, for the shared
  ``logger`` and for a ``Logger(..., env=True)`` (:doc:`console`).
* ``PYSIMPLELOG_NAMESPACE_DISABLE`` silences libraries in every process (:doc:`multiple_sinks`).
* Colours are only used on a terminal, so a log collector reading the console sees plain text.

**Libraries**

* A library should make its own ``Logger("mylib")`` and leave the shared ``logger`` to the application.
* The application can then silence, redirect or redact it.

**Processes**

* Each process should make its own logger after it starts. With ``fork``, the child writes its records itself; with ``spawn``,
  it starts empty.
* Context and the list of silenced libraries do not cross into other processes by themselves.

Concurrency guarantees
----------------------

This is what the tests prove, and nothing more. Each row names the test file that proves it (all in ``tests/``).

.. list-table::
   :header-rows: 1
   :widths: 24 46 30

   * - Situation
     - What you can rely on
     - Proved by
   * - Many threads, one process
     - No record is lost or doubled. The records of one thread keep their order. There is no order between threads.
     - ``test_concurrency``
   * - Many processes, each with its own logger, one file (Linux and macOS)
     - No line is torn and none is lost, with ``fork``, ``spawn`` and ``forkserver`` (where the system has it). Order is kept
       inside one thread of one process only.
     - ``test_concurrency_matrix``
   * - Many processes, each with its own logger and a file of its own (every system, Windows included)
     - Counts are exact, and the order inside each thread is kept.
     - ``test_concurrency_matrix``
   * - asyncio tasks and threads
     - Each task sees its own context and never the context of another task. A plain thread does not inherit a task's context.
       Counts are exact.
     - ``test_concurrency_matrix``
   * - A process killed while logging
     - The file keeps only complete lines. The other processes and the parent go on. What the killed process had not yet
       written is lost, unless the sink has a spool.
     - ``test_concurrency_matrix``
   * - A full queue
     - The result is the same every time for the same input: ``drop_newest`` keeps the first records, ``drop_oldest`` the last
       ones, ``reject`` raises ``QueueFull`` for the ones that do not fit, ``block`` waits and loses nothing. The counters say
       how many were dropped.
     - ``test_concurrency_matrix``
   * - The program ends with records waiting
     - It waits up to ``shutdownTimeout`` seconds, then ends and says on the error stream that records were left behind.
     - ``test_concurrency_matrix``, ``test_concurrency``
   * - A sink that fails
     - Only that sink loses the record. The failure is counted. The other sinks get every record.
     - ``test_concurrency_matrix``
   * - A sink thread that ends
     - Logging does not hang, and the other sinks still get every record.
     - ``test_concurrency_matrix``
   * - A spool and processes that died
     - Each process has its own slot, and another process takes them over. Delivery is at least once: a record may arrive twice,
       never zero times. The order of one process is kept.
     - ``test_concurrency_matrix``, ``test_durable``
   * - A forked child
     - It delivers in the thread that logs, and does not wait for threads it does not have.
     - ``test_fork``

Several processes sharing one file is safe only where the operating system makes an append atomic: Linux and macOS. On Windows
two processes can overwrite each other's bytes, so give each process a file of its own (see ``examples/20_many_processes.py``), or
send the records to one place with a network sink. Python's own ``logging`` module has the same limit.

What is not promised: an order between different threads or processes, a delivery that is exactly once, and the survival of a
record that was only in memory when the process was killed.

Next: :doc:`performance`.
