"""Bridge from Python's standard logging package into a pysimplelog Logger."""

import logging
import os

try:
    from .record import CallerInfo
    from .SimpleLog import Logger
except ImportError:
    from record import CallerInfo
    from SimpleLog import Logger

# Names of the attributes every standard record has. Any other attribute of a record was added by the
# ``extra`` argument of the logging call, and becomes a field
_STANDARD_ATTRIBUTES = frozenset(logging.LogRecord('', 0, '', 0, '', (), None).__dict__) | {'message', 'asctime'}

# Lowest standard level of each pysimplelog log type, highest first
_DEFAULT_LEVELS = ((logging.CRITICAL, 'critical'), (logging.ERROR, 'error'), (logging.WARNING, 'warn'),
                   (logging.INFO, 'info'))


class StandardLoggingHandler(logging.Handler):
    """
    Gives the records of Python's standard logging package to a pysimplelog Logger.

    Every standard record goes through the whole pipeline of the logger: the routing by log type, the
    processors, the filters and the sinks. It keeps the original time, process, thread and, when the logger has
    ``callerInfo`` on, the original file, line and function.

    The level of the record picks the log type: below ``INFO`` is ``debug``, ``INFO`` is ``info``, ``WARNING`` is
    ``warn``, ``ERROR`` is ``error`` and ``CRITICAL`` and above is ``critical``. A custom level, such as 25, counts
    as the highest of these levels that it reaches. Give *levelMap* to choose differently.

    The record becomes:

    * the message, with the arguments of the logging call already put in,
    * the field ``logger_name``, the name of the standard logger, such as ``urllib3.connectionpool``,
    * one field for each key of the ``extra`` argument of the logging call,
    * the field ``stack`` when the call asked for ``stack_info``,
    * the exception, with its type, message and traceback, when the call has ``exc_info`` or is
      ``logging.exception``.

    This handler takes no lock of its own, because a pysimplelog Logger is already safe to use from many
    threads. If the logger cannot take a record, the handler reports it as the standard library does for any handler,
    see ``logging.raiseExceptions``.

    :Parameters:
        #. logger (Logger): The pysimplelog Logger that receives the records.
        #. level (int): Lowest standard level this handler takes. The level of the standard logger it is
           attached to still applies first.
        #. levelMap (None, dict): Overrides of the mapping from standard levels to log types of *logger*. A key is a
           level number such as ``25`` or a level name such as ``'NOTICE'``, a value is a log type name.

    :Raises:
        #. TypeError: If *logger* is not a pysimplelog Logger or *levelMap* is not a dictionary.
        #. ValueError: If a value of *levelMap* is not a log type of *logger*.

    .. code-block:: python

        import logging
        handler = StandardLoggingHandler(logger)
        logging.getLogger('myapp').addHandler(handler)
        logging.getLogger('myapp').warning('disk almost full: %s%%', 93)
    """

    def __init__(self, logger, level=logging.NOTSET, levelMap=None):
        super().__init__(level)
        if not isinstance(logger, Logger):
            raise TypeError("logger must be a pysimplelog Logger")
        if levelMap is not None and not isinstance(levelMap, dict):
            raise TypeError("levelMap must be None or a dictionary")
        self.__logger = logger
        self.__levelMap = dict(levelMap) if levelMap is not None else {}
        for logType in self.__levelMap.values():
            if not logger.is_log_type(logType):
                raise ValueError(f"levelMap log type {logType!r} is not a log type of the logger")
        self.__logTypes = {}
        # Set by redirect_standard_logging, so restore_standard_logging can undo it
        self.targetLogger = None
        self.replacedHandlers = []
        self.previousLevel = None

    @property
    def logger(self):
        """The pysimplelog Logger that receives the records."""
        return self.__logger

    def createLock(self):
        """Gives the handler no lock, a pysimplelog Logger is already safe to use from many threads."""
        self.lock = None

    def emit(self, record):
        """
        Gives one standard record to the pysimplelog Logger.

        :Parameters:
            #. record (logging.LogRecord): The standard record.
        """
        try:
            caller = None
            if self.__logger.callerInfo:
                caller = CallerInfo(os.path.basename(record.pathname), record.lineno, record.funcName, record.module)
            self.__logger.log_external(self._log_type_of(record), record.getMessage(), created=record.created,
                                       processId=record.process, threadId=record.thread,
                                       threadName=record.threadName, caller=caller,
                                       exc_info=record.exc_info if record.exc_info else None,
                                       fields=self._fields_of(record))
        except Exception:
            self.handleError(record)

    def _log_type_of(self, record):
        """Returns the log type for the level of a standard record."""
        key = (record.levelno, record.levelname)
        logType = self.__logTypes.get(key)
        if logType is None:
            logType = self.__levelMap.get(record.levelno) or self.__levelMap.get(record.levelname)
            if logType is None:
                logType = 'debug'
                for level, name in _DEFAULT_LEVELS:
                    if record.levelno >= level:
                        logType = name
                        break
            self.__logTypes[key] = logType
        return logType

    @staticmethod
    def _fields_of(record):
        """Returns the fields of a standard record: its logger name, its stack, and what ``extra`` added."""
        fields = {'logger_name': record.name}
        if record.stack_info:
            fields['stack'] = record.stack_info
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRIBUTES:
                fields[key] = value
        return fields


def redirect_standard_logging(logger, level=logging.NOTSET, name=None, loggerLevel=None, levelMap=None, replace=False):
    """
    Sends the records of Python's standard logging package, such as those of the libraries an application
    uses, to a pysimplelog Logger.

    Nothing changes until this is called. It adds a :class:`StandardLoggingHandler` to a standard logger, the
    root logger unless *name* is given, and returns it. Undo it with :func:`restore_standard_logging`.

    The standard root logger drops records below ``WARNING`` before any handler sees them. To receive
    ``INFO`` and ``DEBUG`` records too, give *loggerLevel*.

    :Parameters:
        #. logger (Logger): The pysimplelog Logger that receives the records.
        #. level (int): Lowest standard level the handler takes.
        #. name (None, str): The standard logger to attach to. None is the root logger, so every record that
           propagates reaches it. ``'urllib3'`` takes only that library and what is under it.
        #. loggerLevel (None, int): When given, the level of that standard logger is set to it, and put back by
           :func:`restore_standard_logging`.
        #. levelMap (None, dict): Overrides of the mapping from standard levels to log types, see
           :class:`StandardLoggingHandler`.
        #. replace (bool): When True the handlers the standard logger already has are removed, so the records
           reach only pysimplelog. :func:`restore_standard_logging` puts them back.

    :Returns:
        #. handler (StandardLoggingHandler): The handler that was added.

    :Raises:
        #. ValueError: If the standard logger already sends its records to *logger*, or *levelMap* names a log
           type that *logger* does not have.
        #. TypeError: If *logger* is not a pysimplelog Logger.

    .. code-block:: python

        import logging
        handler = redirect_standard_logging(logger, loggerLevel=logging.INFO)
        logging.getLogger('urllib3').info('Starting new HTTPS connection')
        restore_standard_logging(handler)
    """
    target = logging.getLogger(name)
    for existing in target.handlers:
        if isinstance(existing, StandardLoggingHandler) and existing.logger is logger:
            raise ValueError("the standard logger already sends its records to this logger")
    handler = StandardLoggingHandler(logger, level, levelMap)
    handler.targetLogger = target
    if replace:
        handler.replacedHandlers = list(target.handlers)
        for replaced in handler.replacedHandlers:
            target.removeHandler(replaced)
    if loggerLevel is not None:
        handler.previousLevel = target.level
        target.setLevel(loggerLevel)
    target.addHandler(handler)
    return handler


def restore_standard_logging(handler):
    """
    Undoes :func:`redirect_standard_logging`: removes the handler, puts back the handlers it replaced and the
    level of the standard logger.

    :Parameters:
        #. handler (StandardLoggingHandler): The value returned by :func:`redirect_standard_logging`.

    :Raises:
        #. ValueError: If the handler was not made by :func:`redirect_standard_logging`.
    """
    target = handler.targetLogger
    if target is None:
        raise ValueError("handler was not made by redirect_standard_logging")
    target.removeHandler(handler)
    for replaced in handler.replacedHandlers:
        target.addHandler(replaced)
    if handler.previousLevel is not None:
        target.setLevel(handler.previousLevel)
    handler.targetLogger = None
    handler.replacedHandlers = []
    handler.previousLevel = None
    handler.close()
