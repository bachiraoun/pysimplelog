"""Defines the immutable structured record that represents one log event."""

from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, NamedTuple

EMPTY_MAPPING = MappingProxyType({})


class ExceptionInfo(NamedTuple):
    """
    Describes the exception attached to a log record.

    :Parameters:
        #. typeName (str, None): Exception class name. None when only the traceback text is known.
        #. message (str, None): Exception message. None when only the traceback text is known.
        #. stacktrace (str): Formatted traceback text.
    """

    typeName: str | None
    message: str | None
    stacktrace: str


class CallerInfo(NamedTuple):
    """
    Describes the place in user code that produced a log record.

    :Parameters:
        #. fileName (str): Base name of the source file.
        #. line (int): Line number of the log call.
        #. function (str): Name of the function that made the log call.
        #. moduleName (str): Name of the module that made the log call.
    """

    fileName: str
    line: int
    function: str
    moduleName: str


class LogRecord(NamedTuple):
    """
    Represents one log event as immutable structured data.

    Formatting is not part of the record: every sink renders the same record with its own
    formatter. A record is built by :meth:`create`, which wraps *fields* and *context* in
    read-only views. The views are not copies, so the dictionaries given to
    :meth:`create` must not be changed afterwards.

    Nothing is type checked when a record is built, because the logger builds records from
    values it has already checked. Call :func:`validate_record` on a record built anywhere else.

    :Parameters:
        #. timestamp (datetime.datetime): Time of the log call, timezone aware.
        #. severity (str): Display name of the log type, such as ``INFO``.
        #. logType (str): Name of the log type as it is registered in the logger, such as ``info``. Several log
           types can share a display name, this is the one that tells them apart.
        #. level (float, None): Numeric level of the log type. None when it has none.
        #. logger (str): Name of the logger that produced the record.
        #. message (str): The log message.
        #. processId (int): Operating system process identifier.
        #. threadId (int): Identifier of the thread that made the log call.
        #. threadName (str): Name of the thread that made the log call.
        #. fields (Mapping): Structured values given with this log call, with string keys.
        #. context (Mapping): Ambient values, such as a request identifier, with string keys.
        #. exception (ExceptionInfo, None): The attached exception, if any.
        #. caller (CallerInfo, None): The log call location, if it was captured.

    .. code-block:: python

        ## Build a record by hand, normally the logger does this
        from datetime import datetime, timezone
        record = LogRecord.create(timestamp=datetime.now(timezone.utc), severity='INFO', logType='info',
                                  level=20, logger='orders', message='Order created',
                                  processId=1, threadId=1, threadName='MainThread',
                                  fields={'order_id': 123})
        ## A record that comes from outside the logger must be checked
        validate_record(record)
    """

    timestamp: datetime
    severity: str
    logType: str
    level: float | None
    logger: str
    message: str
    processId: int
    threadId: int
    threadName: str
    fields: Mapping[str, Any] = EMPTY_MAPPING
    context: Mapping[str, Any] = EMPTY_MAPPING
    exception: ExceptionInfo | None = None
    caller: CallerInfo | None = None

    def __reduce__(self):
        """Makes the record picklable and deep-copyable: the read-only views are saved as plain dictionaries."""
        values = list(self)
        values[9] = dict(self.fields)
        values[10] = dict(self.context)
        return (_rebuild_record, (tuple(values),))

    @classmethod
    def create(cls, timestamp, severity, logType, level, logger, message, processId, threadId, threadName,
               fields=None, context=None, exception=None, caller=None):
        """
        Builds a record whose fields and context are read-only views.

        :Parameters:
            #. timestamp (datetime.datetime): Time of the log call, timezone aware.
            #. severity (str): Display name of the log type.
            #. logType (str): Registered name of the log type.
            #. level (float, None): Numeric level of the log type.
            #. logger (str): Name of the logger.
            #. message (str): The log message.
            #. processId (int): Operating system process identifier.
            #. threadId (int): Identifier of the calling thread.
            #. threadName (str): Name of the calling thread.
            #. fields (dict, None): Structured values. None means no fields.
            #. context (dict, None): Ambient values. None means no context.
            #. exception (ExceptionInfo, None): The attached exception, if any.
            #. caller (CallerInfo, None): The log call location, if captured.

        :Returns:
            #. record (LogRecord): The new record.
        """
        return cls(timestamp, severity, logType, level, logger, message, processId, threadId, threadName,
                   EMPTY_MAPPING if fields is None else MappingProxyType(fields),
                   EMPTY_MAPPING if context is None else MappingProxyType(context),
                   exception, caller)


def _rebuild_record(values):
    """Rebuilds a record from the plain values that ``LogRecord.__reduce__`` saved, wrapping fields and context in read-only views."""
    fields, context = values[9], values[10]
    return LogRecord(*values[:9], EMPTY_MAPPING if len(fields) == 0 else MappingProxyType(fields),
                     EMPTY_MAPPING if len(context) == 0 else MappingProxyType(context), *values[11:])


def _is_number(value):
    """Returns True for an int or float, False for anything else including a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value):
    """Returns True for an int, False for anything else including a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_mapping(name, mapping):
    """Raises TypeError when mapping is not a mapping with string keys."""
    if not isinstance(mapping, Mapping):
        raise TypeError(f"{name} must be a mapping")
    for key in mapping:
        if not isinstance(key, str):
            raise TypeError(f"{name} keys must be strings, got {type(key).__name__}")


def validate_record(record):
    """
    Checks that a record has the documented types, for records built outside the logger.

    The logger does not call this on its own records, which keeps the logging path fast.
    Use it where a record comes from elsewhere: built by hand, received from the standard
    logging bridge, or read back from a disk spool.

    :Parameters:
        #. record (LogRecord): The record to check.

    :Raises:
        #. TypeError: If record is not a LogRecord, or any attribute, including those of the
           nested exception and caller, does not have its documented type.
    """
    if not isinstance(record, LogRecord):
        raise TypeError(f"record must be a LogRecord, got {type(record).__name__}")
    if not isinstance(record.timestamp, datetime) or record.timestamp.tzinfo is None:
        raise TypeError("timestamp must be a timezone aware datetime")
    if not isinstance(record.severity, str) or not isinstance(record.logType, str):
        raise TypeError("severity and logType must be strings")
    if record.level is not None and not _is_number(record.level):
        raise TypeError("level must be a number or None")
    if not isinstance(record.logger, str):
        raise TypeError("logger must be a string")
    if not isinstance(record.message, str):
        raise TypeError("message must be a string")
    if not _is_int(record.processId) or not _is_int(record.threadId):
        raise TypeError("processId and threadId must be integers")
    if not isinstance(record.threadName, str):
        raise TypeError("threadName must be a string")
    _validate_mapping('fields', record.fields)
    _validate_mapping('context', record.context)
    exception = record.exception
    if exception is not None:
        if not isinstance(exception, ExceptionInfo):
            raise TypeError("exception must be an ExceptionInfo or None")
        if exception.typeName is not None and not isinstance(exception.typeName, str):
            raise TypeError("exception typeName must be a string or None")
        if exception.message is not None and not isinstance(exception.message, str):
            raise TypeError("exception message must be a string or None")
        if not isinstance(exception.stacktrace, str):
            raise TypeError("exception stacktrace must be a string")
    caller = record.caller
    if caller is not None:
        if not isinstance(caller, CallerInfo):
            raise TypeError("caller must be a CallerInfo or None")
        if not isinstance(caller.fileName, str) or not isinstance(caller.function, str) \
                or not isinstance(caller.moduleName, str):
            raise TypeError("caller fileName, function and moduleName must be strings")
        if not _is_int(caller.line):
            raise TypeError("caller line must be an integer")
