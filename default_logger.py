"""
The default logger, made on first use so that importing the package does nothing.
"""

import threading

try:
    from .simple_log import Logger
except ImportError:
    from simple_log import Logger


class _DefaultLogger:
    """
    A stand-in for the shared default logger, which is made when the first attribute is read.

    Every module that imports it shares the same logger, so a library should make its own
    :class:`Logger` instead of configuring this one.

    .. code-block:: python

        from pysimplelog import logger

        logger.info("Application started")
    """

    def __init__(self):
        self.__instance = None
        self.__lock = threading.Lock()

    @property
    def instance(self):
        """The real :class:`Logger`, made on first access. It writes to the console and not to a file."""
        with self.__lock:
            if self.__instance is None:
                self.__instance = Logger(name="pysimplelog", logToFile=False)
            return self.__instance

    def __getattr__(self, attributeName):
        """Forwards every public attribute to the real logger."""
        # Private names are refused so that copy and pickle cannot loop before __init__ has run
        if attributeName.startswith('_'):
            raise AttributeError(attributeName)
        return getattr(self.instance, attributeName)


logger = _DefaultLogger()
