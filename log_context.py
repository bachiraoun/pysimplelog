"""Context is information that describes where a log call happens, such as the request or the user. You set it once, and every record made afterwards carries it."""

import contextvars
import functools
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
    What ``context(...)`` returns. It works in a ``with`` block, in ``async with`` and as a function decorator.

    A context manager that attaches values to every record made inside its ``with`` block.

    Make one with :func:`context`. Each ``with`` needs its own scope.

    .. code-block:: python

        with context(request_id="r-1"):
            logger.info("inside")

        @context(job="nightly")
        def run():
            logger.info("inside the job")

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

    async def __aenter__(self):
        """Opens the scope in asynchronous code, it does not wait for anything."""
        return self.__enter__()

    async def __aexit__(self, excType, excValue, excTraceback):
        """Closes the scope in asynchronous code."""
        return self.__exit__(excType, excValue, excTraceback)

    def __call__(self, function):
        """
        Makes a function run inside a new scope with these values on every call, so ``@context(step="x")`` works.

        :Parameters:
            #. function (callable): A function or a coroutine function.

        :Returns:
            #. wrapper (callable): The function, run inside the scope.

        :Raises:
            #. TypeError: If *function* is a generator function, because the scope would end when the generator
               is made and not when it is used up.
        """
        import inspect
        if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
            raise TypeError("context cannot decorate a generator function: use a with block inside it")
        values = self.__values
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def wrapper(*args, **kwargs):
                with ContextScope(values):
                    return await function(*args, **kwargs)
        else:
            @functools.wraps(function)
            def wrapper(*args, **kwargs):
                with ContextScope(values):
                    return function(*args, **kwargs)
        return wrapper


def context(**values):
    """
    Adds values to every record made inside a ``with`` block, without passing them to each call.

    The values are kept in a ``contextvars`` variable, so they follow the flow of the program: they reach
    every function the block calls, and every asynchronous task started inside it, each task keeping its
    own values. They also reach what ``asyncio.to_thread`` and executors run, because those copy the context.
    A plain ``threading.Thread`` starts empty, wrap its function with :func:`keep_context` to hand it the
    values. A scope also works as a decorator, ``@context(step="x")``, and in ``async with``. The values are
    held, not copied: a list put in the context and changed later is written changed, which a threaded sink
    can show after the call has returned.

    Blocks nest. An inner value replaces an outer one with the same name until the inner block ends, and
    the outer value is back after it, also when the block ends by an exception. The values are written
    in the ``context`` of the record, apart from its fields.

    .. code-block:: python

        with context(request_id="r-42"):
            logger.info("inside")          ## ... inside request_id=r-42

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
    Shows the context values that are active right now.

    .. code-block:: python

        with context(request_id="r-42"):
            dict(current_context())        ## {'request_id': 'r-42'}

    :Returns:
        #. values (Mapping): A read-only view of the values, empty outside every block.
    """
    return MappingProxyType(CURRENT_CONTEXT.get())


def keep_context(function):
    """
    Makes a function run with the context values of the moment this is called, in any thread.

    A plain ``threading.Thread`` starts with no context values. Wrap its function to hand it the values of the code
    that starts it. A new copy is used for every call, so one wrapped function can run in many threads at once.

    :Parameters:
        #. function (callable): The function to run.

    :Returns:
        #. wrapper (callable): The function, run with the values that were current when it was wrapped.

    .. code-block:: python

        with context(request_id=request_id):
            threading.Thread(target=keep_context(work)).start()    ## work's records carry request_id
            executor.submit(keep_context(work))
    """
    snapshot = contextvars.copy_context()

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        """
        Runs the wrapped function with a copy of the context values saved when it was wrapped.

        :Parameters:
            #. args (tuple): The positional arguments of the wrapped function, passed on unchanged.
            #. kwargs (dict): The keyword arguments of the wrapped function, passed on unchanged.
        """
        return snapshot.copy().run(function, *args, **kwargs)
    return wrapper
