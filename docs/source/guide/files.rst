File logging
============

``add`` attaches an output to a logger in one call. A path makes a log file:

.. code-block:: python

    from pysimplelog import logger

    name = logger.add("logs/app.log")
    logger.info("Written to the console and to logs/app.log")
    logger.remove(name)

``add`` returns the name of the new output, ``sink-1``, ``sink-2`` and so on. Give ``remove`` that name when you do not need
the output any more. To choose the name, pass ``name="app"``. The folder is made if it does not exist, and the path needs an
extension.

A file that does not rotate keeps the name you gave it, and grows until you stop it. For a long running program, rotate it.

Rotation, retention and compression
-----------------------------------

.. code-block:: python

    logger.add("logs/app.log", rotation="500 MB", retention="30 days", compression="gz")

* ``rotation`` is the size at which a new file starts: ``"500 MB"``, ``"10 KB"``, ``"1 GB"`` or a number of megabytes.
* ``retention`` as text, such as ``"30 days"`` or ``"12 hours"``, deletes rotated files that old. As a whole number, such as
  ``retention=5``, it keeps that many files.
* ``compression="gz"`` compresses a file when a new one starts.

A relative path such as ``logs/app.log`` is fixed when you call ``add``. If the program changes its working folder later, the log
stays where it started.

The files of a rotation are numbered, and the newest has the highest number:

.. code-block:: text

    app_0.log.gz   app_1.log.gz   app_2.log.gz   app_3.log

Time units are ``seconds``, ``minutes``, ``hours``, ``days`` and ``weeks``. Rotation at a time of day, such as ``"00:00"``, or on a
weekday name is not supported, and gives a ``ValueError``. ``retention`` without ``rotation`` is refused too, because nothing would
ever be rotated, so there would be nothing to delete:

.. code-block:: text

    ValueError: retention needs rotation: without it the file is never rotated, so there is nothing to delete

A count shows how retention works:

.. code-block:: python

    logger.add("logs/keep.log", rotation="1 KB", retention=3, name="keep")
    ## after many lines, only the newest three files are left:
    ## keep_7.log  keep_8.log  keep_9.log

Rotating by time
----------------

.. code-block:: python

    logger.add("logs/app.log", rotation="daily", retention=30, compression="gz")
    logger.add("logs/busy.log", rotation=("daily", "500 MB"))      ## a new file at midnight, or at 500 MB, whichever comes first

``rotation`` takes ``"hourly"``, ``"daily"``, ``"weekly"`` or ``"monthly"``. The periods follow the calendar in the **local time** of
the machine, and the files are named by date:

.. code-block:: text

    app_2026-10-10.log.gz   app_2026-10-11.log          ## daily
    app_2026-10-11T05.log                                ## hourly
    app_2026-W41.log                                     ## weekly, the ISO week
    app_2026-10.log                                      ## monthly

* With a size as well, a split inside a period adds a number: ``app_2026-10-11.log``, ``app_2026-10-11_1.log``, ``app_2026-10-11_2.log``.
  The next day starts again without a number.
* ``retention`` and ``compression`` work as for numbered files. A whole number keeps that many files, split files included.
* A new file starts when the first record of a new period arrives, not at the exact moment. A program that logs nothing for a day
  creates no file for it.
* A record that is late, because another thread stamped it just before midnight, is written to the current file. Files never go back
  to an earlier period.
* Files of another kind, such as numbered files or files of another period, are left alone, and are not counted for ``retention``.

Choose what goes in the file
----------------------------

.. code-block:: python

    from pysimplelog import match_logger

    ## only errors and above, as one JSON line each
    logger.add("logs/errors.jsonl", format="json", level="ERROR")

    ## only the records of one part of the application
    logger.add("logs/db.log", filter=match_logger("app.db"))

``level`` is the name of a log type (``"ERROR"`` or ``"error"``) or a number. ``format`` is ``"text"`` (the default for a
file), ``"json"``, a template, or a function, as in :doc:`formatting`. ``filter`` is a function that gets each record and
returns whether the output wants it, see :doc:`../getting_started` for the filters that come with the package.

The result of the JSON example, one line for each record:

.. code-block:: text

    {"schema":1,"timestamp":"2026-10-08T18:54:58.458-05:00","severity":"ERROR","log_type":"error","level":30.0,"logger":"pysimplelog","message":"boom","process":{"id":14066},"thread":{"id":140704461343744,"name":"MainThread"},"fields":{"code":7}}

Other things ``add`` takes
--------------------------

* A stream, such as ``sys.stderr`` or an open file, writes to it. You close what you open.
* A function ``f(text, record)`` is called for every record, with the text already formatted.
* ``threaded=True`` writes the file from a thread of its own, see :doc:`../getting_started`.
* Any other argument of ``add_sink``, such as ``enabled`` or ``logTypeFlags``.

A ``Logger`` you make yourself can also write the built-in log file with ``Logger("app", logToFile=True)``. ``add`` is the
simpler way, and it can be used any number of times.

Next: :doc:`formatting`.
