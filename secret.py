"""Some values, such as passwords and keys, must never reach a log. ``Secret`` wraps one so that every text made from it says ``[REDACTED]``."""

REDACTED_TEXT = '[REDACTED]'


class Secret:
    """
    A value that prints as ``[REDACTED]`` everywhere: in the console, in files, in JSON. Wrap a password or a key in it once, where it is created.

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
        """
        Returns the hidden value, for the code that is allowed to use it.

        .. code-block:: python

            password = Secret("hunter2")
            str(password)             ## '[REDACTED]'
            password.reveal()         ## 'hunter2'
        """
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
