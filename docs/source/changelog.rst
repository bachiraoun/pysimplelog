Changelog
=========

5.x
---

* Added non-blocking enqueue mode (``enqueue=True``).
* Added ``bind()`` for structured context logging.
* Added ``catch()`` decorator and context manager for exception capture.
* Added ``add_sink()`` / ``remove_sink()`` for unlimited user-defined output sinks.
* Added ``callerInfo`` option to tag log lines with file, line number, and function name.
* Added ``maxMessageSize`` and ``maxDataSize`` truncation limits.
* Added queue backpressure controls: ``maxQueueSize``, ``queueFullPolicy``, ``queueBlockTimeout``.
* Added ``is_log_type()`` as the canonical snake_case replacement for ``is_logType()`` (deprecated).
* Added ``is_enabled()``, ``is_enabled_for_stdout()``, ``is_enabled_for_file()`` query methods.
* Unified sink registry (``sinks``, ``activeSinks`` properties).
* Dropped Python 2.7 support. Minimum supported version is Python 3.6.

3.x
---

* Rotating log file support.
* Custom log type colours, highlights, and text attributes.
* Timezone support via ``pytz``.
* ``set_minimum_level()`` / ``set_maximum_level()`` for level-range filtering.
