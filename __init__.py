"""
A pythonic, simple yet complete system logger supporting simultaneous output to stdout,
a rotating log file, and any number of user-supplied sinks.

pysimplelog supports ANSI text colouring and formatting attributes when the output
stream allows it.  For singleton use, import ``SingleLogger`` in place of ``Logger``.

Installation guide
==================
pysimplelog requires Python 3.10 or later and has no mandatory third-party dependencies
(``pytz`` is optional and only needed when a timezone name is passed to the constructor).
Install from PyPI using pip:

.. code-block:: console

    pip install pysimplelog

Alternatively, fork pysimplelog's `GitHub repository
<https://github.com/bachiraoun/pysimplelog/>`_ and copy the package to
Python's site-packages directory.
"""

try:
    from .__pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from .simple_log import Logger, SingleLogger, CONSOLE_SINK, FILE_SINK
    from .default_logger import logger
    from .record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo, validate_record
    from .formatters import JsonFormatter, TextFormatter, TemplateFormatter, register_formatter, resolve_formatter
    from .sinks import Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode
    from .processors import add_context, redact_fields, redact_text, DEFAULT_SENSITIVE_NAMES
    from .filters import sample, match_logger, match_module, match_field
    from .log_context import context, current_context
    from .queues import QueueFull, validate_queue_policy
    from .spool import SpoolConfig, SpoolError, SpoolBusyError, SpoolMismatchError
    from .standard_logging import StandardLoggingHandler, redirect_standard_logging, restore_standard_logging
except ImportError:
    from __pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from simple_log import Logger, SingleLogger, CONSOLE_SINK, FILE_SINK
    from default_logger import logger
    from record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo, validate_record
    from formatters import JsonFormatter, TextFormatter, TemplateFormatter, register_formatter, resolve_formatter
    from sinks import Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode
    from processors import add_context, redact_fields, redact_text, DEFAULT_SENSITIVE_NAMES
    from filters import sample, match_logger, match_module, match_field
    from log_context import context, current_context
    from queues import QueueFull, validate_queue_policy
    from spool import SpoolConfig, SpoolError, SpoolBusyError, SpoolMismatchError
    from standard_logging import StandardLoggingHandler, redirect_standard_logging, restore_standard_logging

__all__ = [
    'Logger', 'SingleLogger', 'CONSOLE_SINK', 'FILE_SINK', 'logger',
    'LogRecord', 'ExceptionInfo', 'CallerInfo', 'TraceInfo', 'validate_record',
    'JsonFormatter', 'TextFormatter', 'TemplateFormatter', 'register_formatter', 'resolve_formatter',
    'Sink', 'StreamSink', 'ConsoleSink', 'FileSink', 'CallbackSink', 'validate_flush_mode',
    'add_context', 'redact_fields', 'redact_text', 'DEFAULT_SENSITIVE_NAMES',
    'sample', 'match_logger', 'match_module', 'match_field',
    'context', 'current_context',
    'QueueFull', 'validate_queue_policy',
    'SpoolConfig', 'SpoolError', 'SpoolBusyError', 'SpoolMismatchError',
    'StandardLoggingHandler', 'redirect_standard_logging', 'restore_standard_logging',
    'get_version', 'get_author', 'get_email', 'get_doc', 'get_repository', 'get_pypi',
]


def get_version():
    """Get pysimplelog's version number."""
    return __version__

def get_author():
    """Get pysimplelog's author's name."""
    return __author__

def get_email():
    """Get pysimplelog's author's email."""
    return __email__

def get_doc():
    """Get pysimplelog's official online documentation link."""
    return __onlinedoc__

def get_repository():
    """Get pysimplelog's official online repository link."""
    return __repository__

def get_pypi():
    """Get pysimplelog's PyPI link."""
    return __pypi__
