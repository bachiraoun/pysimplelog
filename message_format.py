"""
Fills the placeholders of a log message with the arguments and the fields of the call.
"""

import functools
import re
from string import Formatter

try:
    from .formatters import safe_str
except ImportError:
    from formatters import safe_str


class _SafeFormatter(Formatter):
    """A formatter that fills placeholders with values and never reaches inside them."""

    def get_field(self, fieldName, args, kwargs):
        """Refuses ``{0.name}`` and ``{0[key]}``, so a template cannot read attributes or items of a value."""
        if '.' in fieldName or '[' in fieldName:
            raise ValueError("a placeholder names a value, it cannot reach inside it")
        return super().get_field(fieldName, args, kwargs)

    def convert_field(self, value, conversion):
        """Applies ``!s``, ``!r`` or ``!a``, with a placeholder for a value that cannot be printed."""
        try:
            return super().convert_field(value, conversion)
        except Exception:
            return safe_str(value)

    def format_field(self, value, formatSpec):
        """Applies the format spec, with the plain text of the value when the spec does not fit it."""
        try:
            return super().format_field(value, formatSpec)
        except Exception:
            return safe_str(value)


_FORMATTER = _SafeFormatter()

# Braces holding only a name, a number or nothing: no attribute, no index, no conversion and no format spec
_PLAIN_TEMPLATE_RE = re.compile(r'(?:[^{}]|\{\{|\}\}|\{[A-Za-z0-9_]*\})*')


@functools.lru_cache(maxsize=512)
def _is_plain_template(template):
    """Says whether every placeholder of a template is a plain name or number, cached because the same few templates repeat."""
    return _PLAIN_TEMPLATE_RE.fullmatch(template) is not None


def render_message(template, args, fields):
    """
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
