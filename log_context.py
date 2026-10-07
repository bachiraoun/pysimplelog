"""Context values that follow the flow of the program and are attached to every record."""

import contextvars
from types import MappingProxyType

try:
    from .record import EMPTY_MAPPING
except ImportError:
    from record import EMPTY_MAPPING

# The values attached to every record made in the current thread or asynchronous task. The dictionary
# held here is never changed, a scope puts a new one, so a record can share it without a copy
CURRENT_CONTEXT = contextvars.ContextVar('pysimplelog_context', default=EMPTY_MAPPING)


class ContextScope:
    """
    A context manager that attaches values to every record made inside its ``with`` block.

    Make one with :func:`context`. Each ``with`` needs its own scope.

    :Parameters:
        #. values (dict): The values to attach, with string keys.
    """

    def __init__(self, values):
        self.__values = values
        self.__token = None
        self.__previous = None

    def __enter__(self):
        if self.__token is not None:
            raise RuntimeError("this context scope is already active, make another one with context()")
        previous = CURRENT_CONTEXT.get()
        merged = {**previous, **self.__values} if len(previous) > 0 else dict(self.__values)
        self.__previous = previous
        self.__token = CURRENT_CONTEXT.set(merged)
        return self

    def __exit__(self, excType, excValue, excTraceback):
        token, self.__token = self.__token, None
        try:
            CURRENT_CONTEXT.reset(token)
        except ValueError:
            # The block ended in another context than it began, as an asynchronous generator can do
            CURRENT_CONTEXT.set(self.__previous)
        return False


def context(**values):
    """
    Attaches values to every record made inside a ``with`` block, whatever logger makes it.

    The values are kept in a ``contextvars`` variable, so they follow the flow of the program: they reach
    every function the block calls, and every asynchronous task started inside it, each task keeping its
    own values. They also reach what ``asyncio.to_thread`` and executors run, because those copy the context.
    A plain ``threading.Thread`` starts empty, run its function with ``contextvars.copy_context().run`` to
    hand it the values.

    Blocks nest. An inner value replaces an outer one with the same name until the inner block ends, and
    the outer value is back after it, also when the block ends by an exception. The values are written
    in the ``context`` of the record, apart from its fields.

    :Parameters:
        #. values: The values to attach, any number of keyword arguments.

    :Returns:
        #. scope (ContextScope): The context manager.

    .. code-block:: python

        with context(request_id=request_id, user_id=user_id):
            logger.info("Order created")      ## carries request_id and user_id
            with context(step='payment'):
                logger.info("Charging")       ## carries request_id, user_id and step
    """
    return ContextScope(values)


def current_context():
    """
    Returns the values attached by the blocks the program is in right now.

    :Returns:
        #. values (Mapping): A read-only view of the values, empty outside every block.
    """
    return MappingProxyType(CURRENT_CONTEXT.get())
