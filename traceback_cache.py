"""Writing a traceback is slow because Python reads the source files. When the same line fails again and again, this remembers the text instead."""

import builtins
import traceback

MAX_CACHED_STACKS = 512

# Python 3.10 has no exception groups, and an empty tuple matches nothing in isinstance
_GROUP_TYPES = (getattr(builtins, 'BaseExceptionGroup', None),) if hasattr(builtins, 'BaseExceptionGroup') else ()
_CAUSE_MESSAGE = "\nThe above exception was the direct cause of the following exception:\n\n"
_CONTEXT_MESSAGE = "\nDuring handling of the above exception, another exception occurred:\n\n"

# The frames of a traceback, by the code objects and the instruction of each one. A module that is loaded again has new
# code objects, so an edited file never gives the text of its old version
_STACKS = {}


def _stack_text(traceback_):
    """Returns the frames of a traceback as Python writes them, from memory when the same places were written before."""
    key = []
    entry = traceback_
    while entry is not None:
        key.append((entry.tb_frame.f_code, entry.tb_lasti))
        entry = entry.tb_next
    key = tuple(key)
    text = _STACKS.get(key)
    if text is None:
        text = ''.join(traceback.format_tb(traceback_))
        if len(_STACKS) >= MAX_CACHED_STACKS:
            _STACKS.clear()
        _STACKS[key] = text
    return text


def _append_segments(value, traceback_, seen, parts):
    """Adds the text of an exception, and before it the text of the exceptions chained to it, in the order Python writes them."""
    cause, context = value.__cause__, value.__context__
    if cause is not None:
        chained, message = cause, _CAUSE_MESSAGE
    elif context is not None and not value.__suppress_context__:
        chained, message = context, _CONTEXT_MESSAGE
    else:
        chained, message = None, ''
    if chained is not None and id(chained) not in seen:
        seen.add(id(chained))
        _append_segments(chained, chained.__traceback__, seen, parts)
        parts.append(message)
    if traceback_ is not None:
        parts.append("Traceback (most recent call last):\n")
        parts.append(_stack_text(traceback_))
    parts.extend(traceback.format_exception_only(type(value), value))


def format_exception_text(excType, excValue, excTraceback):
    """
    Writes an exception and its traceback exactly as Python's ``traceback.format_exception`` does, but faster when the same place fails again.

    The text of the frames is kept, so an exception raised again at the same place, as in a loop of failures, costs a
    fraction of the first one. An exception group, or something that is not an exception, is formatted by Python itself.

    .. code-block:: python

        try:
            1 / 0
        except ZeroDivisionError as error:
            text = format_exception_text(type(error), error, error.__traceback__)

    :Parameters:
        #. excType (type): The exception class.
        #. excValue (BaseException): The exception.
        #. excTraceback (traceback, None): The traceback of the exception.

    :Returns:
        #. text (str): The traceback text without a trailing line break.
    """
    if not isinstance(excValue, BaseException) or isinstance(excValue, _GROUP_TYPES):
        return ''.join(traceback.format_exception(excType, excValue, excTraceback)).rstrip('\n')
    parts = []
    _append_segments(excValue, excTraceback, {id(excValue)}, parts)
    return ''.join(parts).rstrip('\n')
