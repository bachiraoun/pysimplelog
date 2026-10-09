Examples
========

The ``examples`` folder of the repository holds short scripts you can run and change. Each one starts with a comment that says what
it shows. Run one from the folder that holds the ``pysimplelog`` folder, or with it on ``PYTHONPATH``:

.. code-block:: console

    python3 pysimplelog/examples/13_hello_world.py

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Script
     - What it shows
   * - ``01_basic_logging.py``
     - The log types, a custom log type, a file and a sink of your own.
   * - ``02_siem_console.py`` to ``05_siem_http.py``
     - Sending records to a SIEM: printed, UDP, TCP and HTTP.
   * - ``06_admin_error_catch_siem.py``
     - Catching errors and sending them to a SIEM.
   * - ``07_processors.py``
     - Processors that hide or change values.
   * - ``08_standard_logging.py``
     - Records of Python's ``logging`` package going through pysimplelog.
   * - ``09_context.py``
     - ``bind()`` and ``context()``, also across asynchronous tasks.
   * - ``10_durable_delivery.py``
     - A disk spool that keeps records through an outage.
   * - ``11_opentelemetry_logs.py``, ``12_real_collector_check.py``
     - Sending records to an OpenTelemetry collector.
   * - ``13_hello_world.py``
     - The shared ``logger``, ``{}`` formatting and fields.
   * - ``14_files_and_rotation.py``
     - ``add()`` with rotation, retention and the JSON layout.
   * - ``15_opt_lazy_depth.py``
     - ``opt()``: lazy values, the caller depth and the exception.
   * - ``16_exceptions_and_diagnose.py``
     - A chained exception with ``diagnose``, and a password hidden.
   * - ``17_redaction.py``
     - Hiding secrets by name, by shape and with ``Secret``.
   * - ``18_namespaces_and_environment.py``
     - Silencing a library, and setting the console from the environment.
   * - ``19_force_log.py``
     - A message that must appear, and where it goes.
   * - ``20_many_processes.py``
     - Several processes writing one file, each with its own logger.

The scripts ``01``, ``02``, ``08``, ``09`` and ``13`` to ``20`` are run by ``tests/test_examples.py``, so they stay correct when the
library changes.

Next: :doc:`hello_world` if you have not read the guide yet.
