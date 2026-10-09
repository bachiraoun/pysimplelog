"""Fills the ``{}`` and ``{name}`` places of a message with the values of a log call, safely: a message that does not fit its values is written as it is, and never raises."""

import functools
import re
from string import Formatter

try:
    from .formatters import safe_str
except ImportError:
    from formatters import safe_str


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
        try:
            return super().format_field(value, formatSpec)
        except Exception:
            return safe_str(value)


_FORMATTER = _SafeFormatter()

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
