"""Turns an immutable LogRecord into the text that one sink writes."""

import json
import math
import os
import re
import traceback
from datetime import timezone
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

# Nesting deeper than this is written as a placeholder, which also stops a structure that contains itself
MAX_JSON_DEPTH = 20

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


def safe_str(value):
    """
    Returns the text of a value, or a placeholder when the value cannot be turned into text.

    A value can raise from its own ``__str__``. The placeholder names the type and the class of the error, never
    the error message, because that message can hold sensitive text.

    :Parameters:
        #. value (object): Any value.

    :Returns:
        #. text (str): ``str(value)``, or ``<unprintable TypeName: ErrorClass>``.
    """
    try:
        return str(value)
    except Exception as error:
        return f"<unprintable {type(value).__name__}: {type(error).__name__}>"


# Everything but the tab: the line breaks of any kind, the escape character that starts colour codes, and the other controls
_CONTROL_RE = re.compile('[\\x00-\\x08\\x0a-\\x1f\\x7f\\x85\\u2028\\u2029]')
_CONTROL_NAMES = {'\n': '\\n', '\r': '\\r'}


def _escape_control(match):
    """Returns the escaped text of one control character."""
    character = match.group()
    name = _CONTROL_NAMES.get(character)
    if name is not None:
        return name
    code = ord(character)
    return f"\\x{code:02x}" if code <= 0xff else f"\\u{code:04x}"


def escape_control_characters(text):
    """
    Writes the line breaks and the other control characters of a text as visible escapes such as ``\\n`` and ``\\x1b``.

    A value written on one ``key=value`` line must not be able to start a new line or paint the terminal. The
    tab is kept.

    :Parameters:
        #. text (str): Any text.

    :Returns:
        #. escapedText (str): The text, unchanged when it has no control character.
    """
    if _CONTROL_RE.search(text) is None:
        return text
    return _CONTROL_RE.sub(_escape_control, text)


def describe_error(error):
    """
    Describes an error by its class and the place it was raised, never by its message.

    The message of an error can hold sensitive text, such as a password in a connection string, so it must not be written to
    the standard error stream. The details stay in the error object, for example in ``sink_stats``.

    :Parameters:
        #. error (BaseException): The error.

    :Returns:
        #. description (str): ``ClassName at file.py:12 in function``, or the class name when the error has no traceback.
    """
    name = type(error).__name__
    if error.__traceback__ is None:
        return name
    frame = traceback.extract_tb(error.__traceback__)[-1]
    return f"{name} at {os.path.basename(frame.filename)}:{frame.lineno} in {frame.name}"


def _pair_text(key, value, convert):
    """Returns ``key=value`` for one line: control characters in the key or in the value are written as escapes."""
    return f"{escape_control_characters(str(key))}={escape_control_characters(convert(value))}"


def _safe_repr(value):
    """Returns ``repr(value)``, or the placeholder of safe_str when the value cannot give one. JSON uses it for unknown types."""
    try:
        return repr(value)
    except Exception as error:
        return f"<unprintable {type(value).__name__}: {type(error).__name__}>"


def _non_finite_text(value):
    """Returns the text a number that JSON cannot hold is written as: ``NaN``, ``Infinity`` or ``-Infinity``."""
    if value != value:
        return 'NaN'
    return 'Infinity' if value > 0 else '-Infinity'


def _to_jsonable(value, depth):
    """
    Returns a copy of a value that json can always write: keys become text, and a structure nested too deep,
    or containing itself, is replaced by a placeholder.
    """
    if depth > MAX_JSON_DEPTH:
        return '<too deep>'
    if isinstance(value, dict):
        return {key if isinstance(key, str) else safe_str(key): _to_jsonable(item, depth + 1)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item, depth + 1) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        # JSON has no NaN or infinity, a bare NaN makes a strict parser refuse the whole line
        return _non_finite_text(value)
    return value


def _dumps(value):
    """Returns the JSON text of a value, using repr for what JSON cannot represent, and never raising for a bad value."""
    try:
        return json.dumps(value, default=_safe_repr, separators=JSON_SEPARATORS, allow_nan=False)
    except (TypeError, ValueError):
        # A key that is not text, a number that is not finite, or a structure that contains itself: rewrite it, then write it
        return json.dumps(_to_jsonable(value, 0), default=_safe_repr, separators=JSON_SEPARATORS, allow_nan=False)


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
        text = _dumps(value)
    return text


def _mapping_to_json(mapping):
    """Returns the JSON object text of a mapping, writing plain values by hand because that is faster."""
    entries = []
    for key, value in mapping.items():
        text = _json_scalar(value)
        if text is None:
            # One encoder call for the whole mapping is cheaper than one call per complex value
            return _dumps(dict(mapping))
        entries.append(f"{encode_basestring_ascii(key)}:{text}")
    return '{' + ','.join(entries) + '}'


class JsonFormatter:
    """
    Renders a record as one line of JSON, with a fixed and documented schema.

    The line has no trailing newline. The keys ``schema``, ``timestamp``,
    ``severity``, ``log_type``, ``level``, ``logger``, ``message``, ``process`` and ``thread``
    are always present. ``exception``, ``caller``, ``context`` and ``fields``
    are present only when they have content. Values that JSON cannot represent
    are written with ``repr``. A key that is not text is written as its text, and a value that cannot give
    a ``repr`` is written as ``<unprintable TypeName: ErrorClass>``, so a bad value never loses the record.

    :Parameters:
        #. flatten (bool): When True, ``fields`` and ``context`` entries are written at the top level
           instead of inside their own objects. An entry whose name is a fixed key is written as
           ``fields.<name>`` or ``context.<name>`` and never overwrites the fixed key. When a name is in
           both, the field wins. Flattened output is a little slower to build.
        #. utc (bool): When True, the timestamp is converted to Coordinated Universal Time and written with a ``Z``, whatever the
           time zone of the logger. The instant is the same. The default writes the offset of the time zone of the logger.

    .. code-block:: python

        ## Default nested layout
        formatter = JsonFormatter()
        ## Entries at the top level
        formatter = JsonFormatter(flatten=True)
    """

    def __init__(self, flatten=False, utc=False):
        if not isinstance(flatten, bool):
            raise TypeError("flatten must be a boolean")
        if not isinstance(utc, bool):
            raise TypeError("utc must be a boolean")
        self.__flatten = flatten
        self.__utc = utc

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
        items = self._fixed_items(record, record.timestamp.astimezone(timezone.utc) if self.__utc else record.timestamp)
        if self.__flatten:
            items.extend(self._flat_items(record))
        else:
            if len(record.context) > 0:
                items.append(f'"context":{_mapping_to_json(record.context)}')
            if len(record.fields) > 0:
                items.append(f'"fields":{_mapping_to_json(record.fields)}')
        return '{' + ','.join(items) + '}'

    @staticmethod
    def _fixed_items(record, timestamp):
        """Returns the JSON entries that every layout shares, as a list of ``"key":value`` texts."""
        level = 'null' if record.level is None else _json_value(record.level)
        items = [f'"schema":{SCHEMA_VERSION}',
                 f'"timestamp":"{_format_timestamp(timestamp)}"',
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
        try:
            return self._render(record, str)
        except Exception:
            # A value that cannot become text must not lose the record, so it is rendered again with a placeholder
            return self._render(record, safe_str)

    @staticmethod
    def _render(record, convert):
        """Builds the text of a record, turning every field and context value into text with *convert*."""
        parts = [f"{_format_timestamp_text(record.timestamp)} - {record.logger} <{record.severity}> "]
        if record.caller is not None:
            parts.append(f"[{_format_caller(record.caller)}] ")
        if len(record.context) > 0:
            pairs = ' '.join(_pair_text(key, value, convert) for key, value in record.context.items())
            parts.append(f"[{pairs}] ")
        parts.append(record.message)
        for key, value in record.fields.items():
            if key != 'data':
                parts.append(' ' + _pair_text(key, value, convert))
        if 'data' in record.fields:
            parts.append(f"\n{convert(record.fields['data'])}")
        if record.exception is not None:
            parts.append(f"\n{record.exception.stacktrace}")
        return ''.join(parts)


SGR_RESET = '\x1b[0m'
SGR_DIM = '\x1b[2m'
TRACEBACK_STYLES = ('full', 'compact')
DEFAULT_SEVERITY_COLORS = {'DEBUG': '\x1b[36m', 'INFO': '\x1b[32m', 'WARNING': '\x1b[33m',
                           'ERROR': '\x1b[31m', 'CRITICAL': '\x1b[1;31m'}


def stream_supports_color(stream):
    """
    Says whether colour codes belong in a stream.

    They do when the stream is a terminal, the user did not refuse colour with the ``NO_COLOR`` variable, and the
    terminal is not ``dumb``. A pipe, a file or a CI log is not a terminal, so it stays plain.

    :Parameters:
        #. stream (file-like): The stream the text will be written to.

    :Returns:
        #. isColored (bool): True when colour codes can be written to the stream.
    """
    if os.environ.get('NO_COLOR', '') != '' or os.environ.get('TERM') == 'dumb':
        return False
    isTerminal = getattr(stream, 'isatty', None)
    if isTerminal is None:
        return False
    try:
        return isTerminal() is True
    except Exception:
        return False


class ConsoleFormatter:
    """
    Renders a record as a tidy line of columns for a console, in colour when it is asked to.

    The layout is ``timestamp | SEVERITY | logger | message``, with a ``file:line in function`` column before
    the message when the record has a caller. The context and the fields follow the message as ``key=value``,
    a field named ``data`` goes on its own line, and the traceback comes last. The text has no trailing newline.

    .. code-block:: python

        ## 2026-10-08 08:42:17 | INFO     | api.users | User authenticated user_id=7
        formatter = ConsoleFormatter()
        ## The same with colours, only for a terminal
        formatter = ConsoleFormatter(colors=stream_supports_color(sys.stdout))

    :Parameters:
        #. colors (bool): Whether to write colour codes. The default False never does.
        #. severityColors (None, dict): ``{SEVERITY: escape code}`` that replaces the colour of a severity, for
           example ``{'INFO': '\\x1b[34m'}``. None keeps the defaults.
        #. traceback (str): 'full' writes Python's traceback as it is. 'compact' drops the source lines and the
           'Traceback (most recent call last):' line, and dims the rest, so only the file, line and function of
           each frame and the exception line remain.

    :Raises:
        #. TypeError: If *colors* is not a boolean, or *severityColors* is not a dictionary of strings.
        #. ValueError: If *traceback* is not 'full' or 'compact'.
    """

    def __init__(self, colors=False, severityColors=None, traceback='full'):
        if not isinstance(colors, bool):
            raise TypeError("colors must be a boolean")
        if traceback not in TRACEBACK_STYLES:
            raise ValueError(f"traceback must be one of {TRACEBACK_STYLES}")
        self.__traceback = traceback
        colorMap = dict(DEFAULT_SEVERITY_COLORS)
        if severityColors is not None:
            if not isinstance(severityColors, dict) or not all(
                    isinstance(key, str) and isinstance(value, str) for key, value in severityColors.items()):
                raise TypeError("severityColors must be a dictionary of strings")
            colorMap.update(severityColors)
        self.__colors = colors
        self.__severityColors = colorMap

    def __call__(self, record):
        """
        Renders a record as columns of text.

        :Parameters:
            #. record (LogRecord): The record to render.

        :Returns:
            #. text (str): The text without a trailing newline.

        :Raises:
            #. TypeError: If record is not a LogRecord.
        """
        _require_record(record)
        try:
            return self._render(record, str)
        except Exception:
            # A value that cannot become text must not lose the record, so it is rendered again with a placeholder
            return self._render(record, safe_str)

    def _render(self, record, convert):
        """Builds the text of a record, turning every field and context value into text with *convert*."""
        columns = [self._dim(_format_timestamp_text(record.timestamp)),
                   self._paint(f"{record.severity:<8}", record.severity),
                   record.logger]
        if record.caller is not None:
            columns.append(_format_caller(record.caller))
        parts = [' | '.join(columns), ' | ', record.message]
        pairs = [_pair_text(key, value, convert) for key, value in record.context.items()]
        pairs.extend(_pair_text(key, value, convert) for key, value in record.fields.items() if key != 'data')
        if len(pairs) > 0:
            parts.append(' ' + self._dim(' '.join(pairs)))
        if 'data' in record.fields:
            parts.append(f"\n{convert(record.fields['data'])}")
        if record.exception is not None:
            parts.append(f"\n{self._traceback_text(record.exception)}")
        return ''.join(parts)

    def _traceback_text(self, exception):
        """Returns the traceback as the formatter was asked to write it."""
        if self.__traceback == 'full' or exception.typeName is None:
            # A text made elsewhere has no known layout, so it is never cut
            return exception.stacktrace
        kept = []
        for line in exception.stacktrace.splitlines():
            isFrame = line.startswith('  File "')
            isSourceLine = line.startswith(' ')
            if line.startswith('Traceback (most recent call last):') or (isSourceLine and not isFrame):
                continue
            kept.append(self._dim(line) if isFrame else line)
        return '\n'.join(kept)

    def _dim(self, text):
        """Returns the text dimmed when colours are on."""
        return f"{SGR_DIM}{text}{SGR_RESET}" if self.__colors else text

    def _paint(self, text, severity):
        """Returns the text in the colour of a severity when colours are on and the severity has one."""
        code = self.__severityColors.get(severity)
        if not self.__colors or code is None:
            return text
        return f"{code}{text}{SGR_RESET}"


class _SafeValue:
    """Wraps a value so that formatting it never raises: a value that cannot be formatted gives the placeholder."""

    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def __format__(self, spec):
        try:
            return format(self.value, spec)
        except Exception:
            text = safe_str(self.value) if not isinstance(self.value, str) else self.value
        try:
            return format(text, spec)
        except Exception:
            # The spec does not fit the value, such as ``d`` on text. The value without the spec is better than no record
            return text


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
        view = self._build_view(record)
        try:
            return self.__template.format_map(view)
        except Exception:
            # A value that cannot be formatted must not lose the record, so it is rendered again with a placeholder
            return self.__template.format_map(_TemplateView({key: _SafeValue(value) for key, value in view.items()}))

    @staticmethod
    def _build_view(record):
        """Returns the names a template can use, with the value of each for this record."""
        view = _TemplateView()
        # Like the text layouts, a text value must not start a new line, and data is meant to be multi-line
        for source in (record.context, record.fields):
            view.update({key: escape_control_characters(value) if isinstance(value, str) and key != 'data' else value
                         for key, value in source.items()})
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
        return view


# Keyword to formatter factory. Add more with register_formatter
FORMATTERS = {'json': JsonFormatter, 'jsonl': JsonFormatter, 'text': TextFormatter, 'pretty': ConsoleFormatter}


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
