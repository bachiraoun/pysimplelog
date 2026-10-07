"""Turns an immutable LogRecord into the text that one sink writes."""

import json
import math
from json.encoder import encode_basestring_ascii
from string import Formatter

try:
    from .record import LogRecord
except ImportError:
    from record import LogRecord

SCHEMA_VERSION = 1
JSON_SEPARATORS = (',', ':')

# Keys of the JSON document. A user field with one of these names never overwrites it
RESERVED_KEYS = frozenset({'schema', 'timestamp', 'severity', 'log_type', 'level', 'logger', 'message',
                           'fields', 'context', 'exception', 'caller', 'process', 'thread'})

# (second and utc offset, ISO date-time text, readable date-time text, offset text) of the last
# timestamp. Rebuilt only when the second changes. It is replaced as one tuple, never edited, so
# threads can share it without a lock.
_SECOND_CACHE = (None, '', '', '')


def _second_parts(timestamp):
    """Returns the cached (key, ISO text, readable text, offset text) tuple for the second of timestamp."""
    global _SECOND_CACHE
    key = (int(timestamp.timestamp()), timestamp.utcoffset())
    cache = _SECOND_CACHE
    if cache[0] != key:
        isoText = timestamp.isoformat(timespec='seconds')
        # Coordinated Universal Time (UTC) is written as Z, the form log shippers expect
        offsetText = 'Z' if isoText.endswith('+00:00') else isoText[19:]
        cache = (key, isoText[:19], f"{isoText[:10]} {isoText[11:19]}", offsetText)
        _SECOND_CACHE = cache
    return cache


def _format_timestamp(timestamp):
    """Returns the timestamp as International Organization for Standardization (ISO) 8601 text with milliseconds."""
    parts = _second_parts(timestamp)
    return f"{parts[1]}.{timestamp.microsecond // 1000:03d}{parts[3]}"


def _format_timestamp_text(timestamp):
    """Returns the timestamp as ``YYYY-MM-DD HH:MM:SS`` text."""
    return _second_parts(timestamp)[2]


def _format_caller(caller):
    """Returns the caller as ``file:line in function`` text."""
    return f"{caller.fileName}:{caller.line} in {caller.function}"


def _require_record(record):
    """Raises TypeError with a clear message when record is not a LogRecord."""
    if not isinstance(record, LogRecord):
        raise TypeError(f"formatter needs a LogRecord, got {type(record).__name__}")


def _json_scalar(value):
    """Returns the JSON text of a plain str, int, float, bool or None, and None for any other value."""
    kind = type(value)
    if kind is str:
        return encode_basestring_ascii(value)
    if kind is int:
        return str(value)
    if kind is bool:
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    if kind is float and math.isfinite(value):
        return repr(value)
    return None


def _json_value(value):
    """Returns the JSON text of any value, using repr for what JSON cannot represent."""
    text = _json_scalar(value)
    if text is None:
        text = json.dumps(value, default=repr, separators=JSON_SEPARATORS)
    return text


def _mapping_to_json(mapping):
    """Returns the JSON object text of a mapping, writing plain values by hand because that is faster."""
    entries = []
    for key, value in mapping.items():
        text = _json_scalar(value)
        if text is None:
            # One encoder call for the whole mapping is cheaper than one call per complex value
            return json.dumps(dict(mapping), default=repr, separators=JSON_SEPARATORS)
        entries.append(f"{encode_basestring_ascii(key)}:{text}")
    return '{' + ','.join(entries) + '}'


class JsonFormatter:
    """
    Renders a record as one line of JSON, with a fixed and documented schema.

    The line has no trailing newline. The keys ``schema``, ``timestamp``,
    ``severity``, ``log_type``, ``level``, ``logger``, ``message``, ``process`` and ``thread``
    are always present. ``exception``, ``caller``, ``context`` and ``fields``
    are present only when they have content. Values that JSON cannot represent
    are written with ``repr``.

    :Parameters:
        #. flatten (bool): When True, ``fields`` and ``context`` entries are written at the top level
           instead of inside their own objects. An entry whose name is a fixed key is written as
           ``fields.<name>`` or ``context.<name>`` and never overwrites the fixed key. When a name is in
           both, the field wins. Flattened output is a little slower to build.

    .. code-block:: python

        ## Default nested layout
        formatter = JsonFormatter()
        ## Entries at the top level
        formatter = JsonFormatter(flatten=True)
    """

    def __init__(self, flatten=False):
        if not isinstance(flatten, bool):
            raise TypeError("flatten must be a boolean")
        self.__flatten = flatten

    def __call__(self, record):
        """
        Renders a record as one line of JSON.

        :Parameters:
            #. record (LogRecord): The record to render.

        :Returns:
            #. line (str): The JSON text without a trailing newline.

        :Raises:
            #. TypeError: If record is not a LogRecord.
        """
        _require_record(record)
        items = self._fixed_items(record)
        if self.__flatten:
            items.extend(self._flat_items(record))
        else:
            if len(record.context) > 0:
                items.append(f'"context":{_mapping_to_json(record.context)}')
            if len(record.fields) > 0:
                items.append(f'"fields":{_mapping_to_json(record.fields)}')
        return '{' + ','.join(items) + '}'

    @staticmethod
    def _fixed_items(record):
        """Returns the JSON entries that every layout shares, as a list of ``"key":value`` texts."""
        level = 'null' if record.level is None else _json_value(record.level)
        items = [f'"schema":{SCHEMA_VERSION}',
                 f'"timestamp":"{_format_timestamp(record.timestamp)}"',
                 f'"severity":{encode_basestring_ascii(record.severity)}',
                 f'"log_type":{encode_basestring_ascii(record.logType)}',
                 f'"level":{level}',
                 f'"logger":{encode_basestring_ascii(record.logger)}',
                 f'"message":{encode_basestring_ascii(record.message)}']
        exception = record.exception
        if exception is not None:
            items.append('"exception":{'
                         f'"type":{_json_value(exception.typeName)},'
                         f'"message":{_json_value(exception.message)},'
                         f'"stacktrace":{encode_basestring_ascii(exception.stacktrace)}'
                         '}')
        caller = record.caller
        if caller is not None:
            items.append('"caller":{'
                         f'"file":{encode_basestring_ascii(caller.fileName)},'
                         f'"line":{caller.line},'
                         f'"function":{encode_basestring_ascii(caller.function)},'
                         f'"module":{encode_basestring_ascii(caller.moduleName)}'
                         '}')
        items.append(f'"process":{{"id":{record.processId}}}')
        items.append(f'"thread":{{"id":{record.threadId},"name":{encode_basestring_ascii(record.threadName)}}}')
        return items

    @staticmethod
    def _flat_items(record):
        """Returns the context and field entries as top-level JSON entries, renaming names that clash with a fixed key."""
        merged = {}
        for prefix, source in (('context', record.context), ('fields', record.fields)):
            for key, value in source.items():
                name = f"{prefix}.{key}" if key in RESERVED_KEYS else key
                merged[name] = value
        return [f"{encode_basestring_ascii(name)}:{_json_value(value)}" for name, value in merged.items()]


class TextFormatter:
    """
    Renders a record as one human-readable line, followed by the traceback when there is one.

    The layout is ``timestamp - logger <SEVERITY> [caller] [context] message key=value``. A field named
    ``data`` is not written as ``key=value`` but on its own line after the message, and the traceback
    comes last. The text has no trailing newline.

    .. code-block:: python

        ## 2026-10-06 19:21:49 - orders <INFO> [request_id=r1] Order created order_id=123
        formatter = TextFormatter()
    """

    def __call__(self, record):
        """
        Renders a record as readable text.

        :Parameters:
            #. record (LogRecord): The record to render.

        :Returns:
            #. text (str): The text without a trailing newline.

        :Raises:
            #. TypeError: If record is not a LogRecord.
        """
        _require_record(record)
        parts = [f"{_format_timestamp_text(record.timestamp)} - {record.logger} <{record.severity}> "]
        if record.caller is not None:
            parts.append(f"[{_format_caller(record.caller)}] ")
        if len(record.context) > 0:
            pairs = ' '.join(f"{key}={value}" for key, value in record.context.items())
            parts.append(f"[{pairs}] ")
        parts.append(record.message)
        for key, value in record.fields.items():
            if key != 'data':
                parts.append(f" {key}={value}")
        if 'data' in record.fields:
            parts.append(f"\n{record.fields['data']}")
        if record.exception is not None:
            parts.append(f"\n{record.exception.stacktrace}")
        return ''.join(parts)


class _TemplateView(dict):
    """A dictionary that gives an empty string for a placeholder the record does not have."""

    def __missing__(self, key):
        return ''


class TemplateFormatter:
    """
    Renders a record from a template with ``{name}`` placeholders.

    Available names: ``timestamp``, ``severity``, ``log_type``, ``level``, ``logger``, ``message``,
    ``fields``, ``context``, ``exception`` (the traceback text), ``caller`` (``file:line in function``),
    ``process``, ``thread``, ``thread_name`` and every key of the record fields and context.
    A name the record does not have renders as an empty string. A field never overrides a
    fixed name. Only plain names are allowed: ``{message.upper}`` and ``{fields[x]}`` are rejected,
    so a template cannot reach attributes of the values.

    :Parameters:
        #. template (str): The template text, for example ``"{timestamp} {severity} {message} {order_id}"``.

    :Raises:
        #. TypeError: If template is not a string.
        #. ValueError: If a placeholder is not a plain name.
    """

    def __init__(self, template):
        if not isinstance(template, str):
            raise TypeError("template must be a string")
        for literalText, fieldName, formatSpec, conversion in Formatter().parse(template):
            if fieldName is not None and not fieldName.isidentifier():
                raise ValueError(f"Template placeholder {fieldName!r} must be a plain name")
        self.__template = template

    def __call__(self, record):
        """
        Renders a record from the template.

        :Parameters:
            #. record (LogRecord): The record to render.

        :Returns:
            #. text (str): The text without a trailing newline.

        :Raises:
            #. TypeError: If record is not a LogRecord.
        """
        _require_record(record)
        view = _TemplateView()
        view.update(record.context)
        view.update(record.fields)
        view.update({'timestamp': _format_timestamp(record.timestamp),
                     'severity': record.severity,
                     'log_type': record.logType,
                     'level': record.level,
                     'logger': record.logger,
                     'message': record.message,
                     'fields': dict(record.fields),
                     'context': dict(record.context),
                     'exception': '' if record.exception is None else record.exception.stacktrace,
                     'caller': '' if record.caller is None else _format_caller(record.caller),
                     'process': record.processId,
                     'thread': record.threadId,
                     'thread_name': record.threadName})
        return self.__template.format_map(view)


# Keyword to formatter factory. Add more with register_formatter
FORMATTERS = {'json': JsonFormatter, 'jsonl': JsonFormatter, 'text': TextFormatter}


def register_formatter(name, factory):
    """
    Registers a keyword that resolve_formatter turns into a formatter.

    :Parameters:
        #. name (str): The new keyword. It must not contain ``{`` and must not be registered already.
        #. factory (callable): Called with no arguments, returns a callable ``f(record) -> str``.

    :Raises:
        #. TypeError: If name is not a string or factory is not callable.
        #. ValueError: If name is empty, contains ``{``, or is already registered.
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if len(name) == 0 or '{' in name:
        raise ValueError("name must be non-empty and must not contain '{'")
    if name in FORMATTERS:
        raise ValueError(f"formatter {name!r} is already registered")
    if not callable(factory):
        raise TypeError("factory must be callable")
    FORMATTERS[name] = factory


def resolve_formatter(formatter):
    """
    Turns any accepted formatter value into a callable ``f(record) -> str``.

    :Parameters:
        #. formatter (None, str, callable): None gives JSON. A string is a registered keyword
           (``json``, ``jsonl``, ``text``, or one added with register_formatter), or a template
           containing ``{name}`` placeholders. A callable is used as it is.

    :Returns:
        #. renderer (callable): A callable that takes a LogRecord and returns a string.

    :Raises:
        #. ValueError: If a string is neither a registered keyword nor a template.
        #. TypeError: If formatter is none of the accepted types.
    """
    if formatter is None:
        return JsonFormatter()
    if isinstance(formatter, str):
        if formatter in FORMATTERS:
            return FORMATTERS[formatter]()
        if '{' in formatter:
            return TemplateFormatter(formatter)
        raise ValueError(f"Unknown formatter {formatter!r}. Use one of {sorted(FORMATTERS)} "
                         "or a template with {name} placeholders")
    if callable(formatter):
        return formatter
    raise TypeError("formatter must be None, a string or a callable")
