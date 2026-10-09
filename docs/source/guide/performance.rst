Performance
===========

A log call should cost little when the record is written, almost nothing when it is not, and never surprise you. This page says
what is cheap and what is not, and how to measure it on your own machine. It has no figures on purpose: they belong to one machine,
one Python and one moment, and a page of figures is wrong a month later.

What costs little
-----------------

* A call that no sink wants (a debug call when the level is info) returns after a quick check. A message you build yourself,
  such as an f-string, is built before the call, so pass the work as a function to run only if needed:

  .. code-block:: python

      logger.opt(lazy=True).debug("Report: {}", build_report)     ## build_report() runs only if a sink wants debug

* ``{}`` in a message with plain placeholders is filled by Python's own formatting, the fast way.
* Structured fields cost less than the same information written into the message by hand.
* A file with a sink of its own, a thread, or a queue costs the calling thread very little, see :doc:`async_logging`.

What costs more
---------------

* ``logger.exception`` and tracebacks: Python builds a traceback by reading source lines. The text of the frames is remembered, so
  the same place raising again is much cheaper than the first time.
* ``callerInfo=True`` looks at the call stack for every call.
* ``diagnose`` reads the values of variables. Use it in development.
* A spool writes to disk before the call returns, see :doc:`durable_delivery`.
* Flushing a file after every line is safer and slower than letting the operating system buffer it. pysimplelog flushes by default;
  some libraries do not, so compare like with like.
* Importing the package and making a ``Logger`` cost some milliseconds and some tens of microseconds. Make loggers once, at the
  start, not in a loop.

Measure it yourself
-------------------

The package comes with a benchmark that compares pysimplelog with the standard ``logging`` module, Loguru and structlog,
whichever are installed. From the folder that holds the package:

.. code-block:: console

    python3 pysimplelog/benchmarks/bench_compare.py --list
    python3 pysimplelog/benchmarks/bench_compare.py --all
    python3 pysimplelog/benchmarks/bench_compare.py --pysimplelog --loguru --scenario disabled,structured,json
    python3 pysimplelog/benchmarks/bench_compare.py --pysimplelog --components

It measures, for each scenario: calls per second, the time of a call (mean, p50, p95 and p99), processor time, and for background
work the time to finish and the records left waiting. The results are saved in ``benchmarks/results`` as text and JSON.

Read the results with care:

* Close other programs first. The script prints the load of the machine, and warns when it is busy.
* Differences under about 10%, or with overlapping ranges, are noise. The table shows the lowest and highest p50 of the repeats.
* The libraries do not write the same thing. pysimplelog writes a richer JSON record than structlog and a longer text line than
  Loguru, and the ``bytes`` column shows it.
* For a background thread, read the end-to-end figure, not only the time to hand a record over.

Where pysimplelog is ahead and behind
-------------------------------------

On the machine it was developed on, pysimplelog was ahead in the common cases: calls with fields, files, several sinks, context,
background writing and exceptions. It was behind in a few: a call that no sink wants, JSON writing compared with structlog (which
writes a smaller record), import time, and making a logger. Run the benchmark for the numbers of your machine.

Next: :doc:`coming_from`.
