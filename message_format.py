"""Fills the ``{}`` and ``{name}`` places of a message with the values of a log call, safely: a message that does not fit its values is written as it is, and never raises."""

import functools
import re
from string import Formatter

try:
    from .formatters import escape_control_characters, safe_str
except ImportError:
    from formatters import escape_control_characters, safe_str

# These print on one line already, so they are passed as they are
_UNCHANGED_TYPES = (int, float, bool, type(None))


class _OneLineValue:
    """A value whose text is always on one line: its line breaks and other control characters are written as visible escapes."""

    __slots__ = ('__value',)

    def __init__(self, value):
        self.__value = value

    def __str__(self):
        return escape_control_characters(safe_str(self.__value))

    def __repr__(self):
        return escape_control_characters(repr(self.__value))

    def __format__(self, formatSpec):
        return escape_control_characters(format(self.__value, formatSpec))


def _make_one_line(value):
    """
    Makes a value safe to put in a message, so that it cannot start a new line in the log.

    :Parameters:
        #. value (object): A value that fills a place of a message.

    :Returns:
        #. safeValue (object): The text with its control characters escaped when *value* is a string, *value* itself when it is a
           number, a boolean or None, and a wrapper that escapes the text of any other object.
    """
    if isinstance(value, str):
        return escape_control_characters(value)
    if type(value) in _UNCHANGED_TYPES:
        return value
    return _OneLineValue(value)


class _SafeFormatter(Formatter):
    """A formatter that fills places with values and never reaches inside them."""

    def get_field(self, fieldName, args, kwargs):
        """
        Refuses ``{0.name}`` and ``{0[key]}``, so a message cannot read the parts of a value.

        :Parameters:
            #. fieldName (str): The name inside the braces, such as ``0`` or ``order``.
            #. args (tuple): The positional values of the call.
            #. kwargs (dict): The named values of the call.
        """
        if '.' in fieldName or '[' in fieldName:
            raise ValueError("a placeholder names a value, it cannot reach inside it")
        return super().get_field(fieldName, args, kwargs)

    def convert_field(self, value, conversion):
        """
        Applies ``!s``, ``!r`` or ``!a``, with a placeholder for a value that cannot be turned into text.

        :Parameters:
            #. value (object): The value to convert.
            #. conversion (None, str): The letter after ``!``: ``s``, ``r`` or ``a``. None means no
               conversion.
        """
        try:
            return super().convert_field(value, conversion)
        except Exception:
            return safe_str(value)

    def format_field(self, value, formatSpec):
        """
        Applies the format, such as ``:.2f``, and falls back to the plain text of the value when the format does not fit it.

        :Parameters:
            #. value (object): The value to write.
            #. formatSpec (str): The text after ``:``, such as ``.2f``. It can be empty.
        """
        # A width or precision of 10000 or more would build a huge text before any size limit can cut it
        if _HUGE_NUMBER_RE.search(formatSpec) is not None:
            return safe_str(value)
        try:
            return super().format_field(value, formatSpec)
        except Exception:
            return safe_str(value)


_FORMATTER = _SafeFormatter()

# Five digits or more in a format, such as the width in ``{x:>200000000}``
_HUGE_NUMBER_RE = re.compile(r'\d{5,}')

# Braces holding only a name, a number or nothing: no attribute, no index, no conversion and no format spec
_PLAIN_TEMPLATE_RE = re.compile(r'(?:[^{}]|\{\{|\}\}|\{[A-Za-z0-9_]*\})*')


@functools.lru_cache(maxsize=512)
def _is_plain_template(template):
    """Says whether every place of a message is a plain name or number, so Python's quick formatting can be used. The answer is remembered, because a program has few distinct messages."""
    return _PLAIN_TEMPLATE_RE.fullmatch(template) is not None


def render_message(template, args, fields):
    """
    Fills the ``{}`` and ``{name}`` places of a message with the values of the call.

    Returns the message with its placeholders filled.

    Nothing is formatted when the call has no positional arguments and no fields, so a message that
    holds braces on its own is written as it is. Any failure, such as a missing name or a bad index,
    gives back the template unchanged: a log call must never fail the program.

    .. code-block:: python

        render_message("User {} logged in", ("ann",), {})            ## 'User ann logged in'
        render_message("Order {order_id}", (), {"order_id": 7})       ## 'Order 7'
        render_message('{"a": 1}', (), {})                           ## '{"a": 1}'

    :Parameters:
        #. template (object): The message given by the caller. Only a string is formatted.
        #. args (tuple): The positional arguments of the call, they fill ``{}`` and ``{0}``.
        #. fields (dict): The named values of the call, they fill ``{name}``.

    :Returns:
        #. message (object): The formatted string, or *template* itself when nothing was formatted.
    """
    if not isinstance(template, str) or (len(args) == 0 and len(fields) == 0):
        return template
    if '{' not in template and '}' not in template:
        return template
    # Only the values are changed. The template is the developer's own text, so its line breaks are kept
    args = tuple(_make_one_line(value) for value in args)
    fields = {name: _make_one_line(value) for name, value in fields.items()}
    try:
        if _is_plain_template(template):
            return template.format(*args, **fields)
    except Exception:
        # A value that cannot be printed, or a name or index that is missing: the safe formatter decides what to write
        pass
    try:
        return _FORMATTER.vformat(template, args, fields)
    except Exception:
        return template
