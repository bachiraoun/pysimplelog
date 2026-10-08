"""
A wrapper that keeps a value out of every text the logging system writes.
"""

REDACTED_TEXT = '[REDACTED]'


class Secret:
    """
    Holds a value that must never be written. Every text made from it is ``[REDACTED]``, in every format.

    The record keeps the wrapper, so a processor or a trusted sink can still call :meth:`reveal`. It cannot be
    pickled, so it cannot be sent to another process by accident.

    .. code-block:: python

        config = {"user": "admin", "password": Secret(password)}
        logger.info("connecting", config=config)    ## password shows as [REDACTED]

    :Parameters:
        #. value (object): The value to hide.
    """

    __slots__ = ('__value',)

    def __init__(self, value):
        self.__value = value

    def reveal(self):
        """Returns the hidden value."""
        return self.__value

    def __str__(self):
        return REDACTED_TEXT

    def __repr__(self):
        return REDACTED_TEXT

    def __format__(self, spec):
        return format(REDACTED_TEXT, spec)

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        raise TypeError("a Secret cannot be pickled")
