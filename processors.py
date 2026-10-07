"""Ready-made record processors: values added to every record, redaction of sensitive values, and a bridge for text functions."""

import re
import sys
from collections.abc import Mapping
from types import MappingProxyType

DEFAULT_SENSITIVE_NAMES = ('password', 'token', 'authorization', 'api_key', 'ssn', 'credit_card', 'secret')
DEFAULT_REPLACEMENT = '[REDACTED]'

# Nesting deeper than this is replaced, which also stops a structure that contains itself
MAX_DEPTH = 20

# Values of these types cannot hold a mapping or a string to change, so they are passed by without
# the slower checks against abstract classes
_PLAIN_TYPES = frozenset({int, float, bool, type(None), bytes})

# Keys are the same from one log call to the next, so the answer for a key is kept. The cache stops
# growing at this size, for the case of keys made of identifiers that never repeat
MAX_CACHED_KEYS = 2048


def _normalize_name(name):
    """Returns a name in lower case with hyphens and spaces as underscores, so ``API-Key`` matches ``api_key``."""
    return str(name).lower().replace('-', '_').replace(' ', '_')


def _redact_mapping(mapping, isSensitive, replacement, depth):
    """Returns ``(mapping, changed)``: the mapping with the value of every sensitive key replaced, at any depth."""
    if depth > MAX_DEPTH:
        return replacement, True
    entries = {}
    changed = False
    for key, value in mapping.items():
        if isSensitive(key):
            entries[key] = replacement
            changed = True
        else:
            entries[key], valueChanged = _redact_value(value, isSensitive, replacement, depth + 1)
            changed = changed or valueChanged
    if not changed:
        return mapping, False
    return entries, True


def _redact_value(value, isSensitive, replacement, depth):
    """Returns ``(value, changed)`` for a value that can hold mappings: a mapping, a list or a tuple."""
    if type(value) in _PLAIN_TYPES or type(value) is str:
        return value, False
    if isinstance(value, Mapping):
        return _redact_mapping(value, isSensitive, replacement, depth)
    if isinstance(value, (list, tuple)):
        if depth > MAX_DEPTH:
            return replacement, True
        items = []
        changed = False
        for item in value:
            newItem, itemChanged = _redact_value(item, isSensitive, replacement, depth + 1)
            items.append(newItem)
            changed = changed or itemChanged
        if not changed:
            return value, False
        return (items if isinstance(value, list) else tuple(items)), True
    return value, False


def redact_fields(names=DEFAULT_SENSITIVE_NAMES, replacement=DEFAULT_REPLACEMENT):
    """
    Makes a record processor that replaces the value of every sensitive key in the fields and the context.

    A key is sensitive when its name, in lower case with hyphens and spaces turned into underscores,
    contains one of *names*. So ``token`` also hides ``access_token`` and ``API-Token``. Keys are looked
    for at any depth inside dictionaries, lists and tuples. The value is replaced whatever its type. Nesting
    deeper than 20 levels is replaced as a whole, which also stops a structure that contains itself.

    Only keys are looked at. A secret inside free text, such as the message or a traceback, is not found,
    use :func:`redact_text` with a function that knows the format of the secret.

    :Parameters:
        #. names (list, tuple, set): The sensitive names. The default is ``password``, ``token``,
           ``authorization``, ``api_key``, ``ssn``, ``credit_card`` and ``secret``.
        #. replacement (str): The text written in place of a sensitive value.

    :Returns:
        #. processor (callable): ``f(record) -> record``, to give to ``Logger.add_processor``.

    :Raises:
        #. TypeError: If names is a single string or holds something that is not a string, or replacement
           is not a string.
        #. ValueError: If a name is empty, because it would match every key.

    .. code-block:: python

        logger.add_processor(redact_fields())
        ## One more name, kept with the defaults
        logger.add_processor(redact_fields(DEFAULT_SENSITIVE_NAMES + ('session_id',)))
    """
    if isinstance(names, str) or not all(isinstance(name, str) for name in names):
        raise TypeError("names must be a list of strings")
    if not isinstance(replacement, str):
        raise TypeError("replacement must be a string")
    sensitiveNames = tuple(_normalize_name(name) for name in names)
    if any(len(name) == 0 for name in sensitiveNames):
        raise ValueError("a sensitive name must not be empty")
    pattern = re.compile('|'.join(re.escape(name) for name in sensitiveNames))
    answers = {}

    def is_sensitive(key):
        answer = answers.get(key)
        if answer is None:
            answer = pattern.search(_normalize_name(key)) is not None
            if len(answers) < MAX_CACHED_KEYS:
                answers[key] = answer
        return answer

    def processor(record):
        fields, fieldsChanged = record.fields, False
        context, contextChanged = record.context, False
        if len(fields) > 0:
            fields, fieldsChanged = _redact_mapping(fields, is_sensitive, replacement, 0)
        if len(context) > 0:
            context, contextChanged = _redact_mapping(context, is_sensitive, replacement, 0)
        if not fieldsChanged and not contextChanged:
            return record
        return record._replace(fields=MappingProxyType(fields) if fieldsChanged else record.fields,
                               context=MappingProxyType(context) if contextChanged else record.context)
    return processor


def _apply_text(function, value, depth):
    """Returns the value with the text function applied to every string in it, inside mappings, lists and tuples too."""
    if isinstance(value, str):
        result = function(value)
        if not isinstance(result, str):
            raise TypeError(f"a text function must return a string, got {type(result).__name__}")
        return result
    if type(value) in _PLAIN_TYPES:
        return value
    if depth > MAX_DEPTH:
        return value
    if isinstance(value, Mapping):
        return {key: _apply_text(function, item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_apply_text(function, item, depth + 1) for item in value]
        return items if isinstance(value, list) else tuple(items)
    return value


def redact_text(function):
    """
    Turns a text function into a record processor.

    The function is applied to the message, the exception message and traceback, and every string inside the
    fields and the context, including strings in nested dictionaries, lists and tuples. Keys are not changed.
    Use it for a function that hides or replaces parts of a text, such as the path of an installation. A
    function that adds text is applied to every part.

    If the function raises, or returns something that is not a string, so does the processor: the logger
    drops the record for its Sink objects rather than let the original text through.

    :Parameters:
        #. function (callable): ``f(text) -> text``.

    :Returns:
        #. processor (callable): ``f(record) -> record``, to give to ``Logger.add_processor``.

    :Raises:
        #. TypeError: If function is not callable.

    .. code-block:: python

        def hide_paths(text):
            return text.replace('/opt/myapp', '...')

        logger.add_processor(redact_text(hide_paths))
    """
    if not callable(function):
        raise TypeError("function must be callable")

    def processor(record):
        exception = record.exception
        if exception is not None:
            exception = exception._replace(
                message=None if exception.message is None else _apply_text(function, exception.message, 0),
                stacktrace=_apply_text(function, exception.stacktrace, 0))
        fields, context = record.fields, record.context
        if len(fields) > 0:
            fields = MappingProxyType(_apply_text(function, fields, 0))
        if len(context) > 0:
            context = MappingProxyType(_apply_text(function, context, 0))
        return record._replace(message=_apply_text(function, record.message, 0), fields=fields,
                               context=context, exception=exception)
    return processor


def add_context(**values):
    """
    Makes a processor that adds the same named values to the context of every record.

    Use it for what describes the whole program and not one call: the service, the environment, the host, the version. The values
    are in the context of the record, next to a request identifier, so every sink and every format shows them. They reach
    the records of the standard ``logging`` bridge too, which ``bind()`` does not.

    A value that is a function is called for every record, so it can say what is true now, for example the current request. A
    function that returns None adds nothing for that record, and a function that raises adds nothing and is reported once,
    the record itself is never lost. A name that the record already has in its context is left as it is: what the call
    said is more precise than what the program says.

    :Parameters:
        #. values: The names and values, any number of keyword arguments. A value is a string, a number or anything the
           formats can write, or a function of no argument that returns one.

    :Returns:
        #. processor (callable): ``f(record) -> record``, to give to ``Logger.add_processor`` or to ``Logger(processors=[...])``.

    :Raises:
        #. ValueError: If no value is given.

    .. code-block:: python

        import socket

        logger.add_processor(add_context(service="orders", environment="production", host=socket.gethostname()))
        ## The current request, known only while one is handled
        logger.add_processor(add_context(request_id=lambda: current_request_id()))
    """
    if len(values) == 0:
        raise ValueError("give at least one value")
    static = {name: value for name, value in values.items() if not callable(value)}
    dynamic = {name: value for name, value in values.items() if callable(value)}
    reported = set()

    def processor(record):
        context = record.context
        added = None
        for name, value in static.items():
            if name not in context:
                if added is None:
                    added = {}
                added[name] = value
        for name, function in dynamic.items():
            if name in context:
                continue
            try:
                value = function()
            except Exception as error:
                if name not in reported:
                    reported.add(name)
                    try:
                        sys.stderr.write(f"pysimplelog WARNING: the function for {name!r} in add_context raised "
                                         f"{type(error).__name__}: {error}, the value is left out\n")
                    except (OSError, ValueError):
                        # The error stream is closed or broken, the record goes on without the value
                        pass
                continue
            if value is not None:
                if added is None:
                    added = {}
                added[name] = value
        if added is None:
            return record
        return record._replace(context=MappingProxyType({**context, **added}))

    return processor
