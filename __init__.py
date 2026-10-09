"""
A pythonic, simple yet complete system logger supporting simultaneous output to stdout,
a rotating log file, and any number of user-supplied sinks.

pysimplelog supports ANSI text colouring and formatting attributes when the output
stream allows it.  For singleton use, import ``SingleLogger`` in place of ``Logger``.

Installation guide
==================
pysimplelog requires Python 3.10 or later and has no mandatory third-party dependencies
(``pytz`` is optional and only needed when a timezone name is passed to the constructor).
Get the package from pysimplelog's `GitHub repository
<https://github.com/bachiraoun/pysimplelog/>`_ and copy it to Python's site-packages directory,
or to any folder on ``PYTHONPATH``.
"""

try:
    from .__pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__
    from .simple_log import Logger, SingleLogger, CONSOLE_SINK, FILE_SINK
    from .default_logger import logger
    from .record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo, validate_record
    from .formatters import JsonFormatter, TextFormatter, TemplateFormatter, ConsoleFormatter, stream_supports_color, register_formatter, resolve_formatter
    from .sinks import Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode
    from .processors import add_context, redact_fields, redact_text, redact_patterns, hash_secrets, DEFAULT_SENSITIVE_NAMES
    from .secret import Secret
    from .filters import sample, match_logger, match_module, match_field
    from .log_context import context, current_context, keep_context
    from .queues import QueueFull, validate_queue_policy
    from .spool import SpoolConfig, SpoolError, SpoolBusyError, SpoolMismatchError
    from .namespaces import disable, enable
except ImportError:
    from __pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__
    from simple_log import Logger, SingleLogger, CONSOLE_SINK, FILE_SINK
    from default_logger import logger
    from record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo, validate_record
    from formatters import JsonFormatter, TextFormatter, TemplateFormatter, ConsoleFormatter, stream_supports_color, register_formatter, resolve_formatter
    from sinks import Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode
    from processors import add_context, redact_fields, redact_text, redact_patterns, hash_secrets, DEFAULT_SENSITIVE_NAMES
    from secret import Secret
    from filters import sample, match_logger, match_module, match_field
    from log_context import context, current_context, keep_context
    from queues import QueueFull, validate_queue_policy
    from spool import SpoolConfig, SpoolError, SpoolBusyError, SpoolMismatchError
    from namespaces import disable, enable

__all__ = [
    'Logger', 'SingleLogger', 'CONSOLE_SINK', 'FILE_SINK', 'logger',
    'LogRecord', 'ExceptionInfo', 'CallerInfo', 'TraceInfo', 'validate_record',
    'JsonFormatter', 'TextFormatter', 'TemplateFormatter', 'ConsoleFormatter', 'stream_supports_color',
    'register_formatter', 'resolve_formatter',
    'Sink', 'StreamSink', 'ConsoleSink', 'FileSink', 'CallbackSink', 'validate_flush_mode',
    'add_context', 'redact_fields', 'redact_text', 'redact_patterns', 'hash_secrets', 'Secret', 'DEFAULT_SENSITIVE_NAMES',
    'sample', 'match_logger', 'match_module', 'match_field',
    'context', 'current_context', 'keep_context',
    'QueueFull', 'validate_queue_policy',
    'SpoolConfig', 'SpoolError', 'SpoolBusyError', 'SpoolMismatchError',
    'StandardLoggingHandler', 'redirect_standard_logging', 'restore_standard_logging',
    'disable', 'enable',
    'get_version', 'get_author', 'get_email', 'get_doc', 'get_repository',
]


_STANDARD_LOGGING_NAMES = ('StandardLoggingHandler', 'redirect_standard_logging', 'restore_standard_logging')


def __getattr__(name):
    """Loads the standard logging bridge the first time one of its names is asked for, so importing the package does not import ``logging``."""
    if name in _STANDARD_LOGGING_NAMES:
        try:
            from . import standard_logging
        except ImportError:
            import standard_logging
        value = getattr(standard_logging, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
