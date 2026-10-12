"""Formatters turn a record into the text that an output writes: a tidy console line, a plain text line, one line of JSON, or your own template or function. Pick one for an output with ``set_sink_formatter`` or ``add(..., format=...)``."""

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
    """Returns, for the second a timestamp falls in, the texts that do not change within that second (ISO date and time, readable date and time, UTC offset). They are remembered, because most records of a busy program share a second."""
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
    """Writes a timestamp as ISO 8601 text with milliseconds, such as ``2026-10-08T21:30:00.100-05:00``."""
    parts = _second_parts(timestamp)
    return f"{parts[1]}.{timestamp.microsecond // 1000:03d}{parts[3]}"


def _format_timestamp_text(timestamp):
    """Writes a timestamp as ``YYYY-MM-DD HH:MM:SS`` text."""
    return _second_parts(timestamp)[2]


def _readable_timestamp(timestamp, isUtc, hasMilliseconds):
    """Writes a timestamp as ``YYYY-MM-DD HH:MM:SS``, with ``.mmm`` added when asked, and in UTC with a trailing ``Z`` when asked."""
    if isUtc:
        timestamp = timestamp.astimezone(timezone.utc)
    text = _format_timestamp_text(timestamp)
    if hasMilliseconds:
        text += f".{timestamp.microsecond // 1000:03d}"
    return text + 'Z' if isUtc else text


def _format_caller(caller):
    """Writes the caller of a log call as ``file:line in function``."""
    return f"{caller.fileName}:{caller.line} in {caller.function}"


def safe_str(value):
    """
    Turns a value into text without ever failing. An object whose own ``__str__`` crashes gives a placeholder that names its type
    and the kind of error.

    A value can raise from its own ``__str__``. The placeholder names the type and the class of the error, never
    the error message, because that message can hold sensitive text.

    .. code-block:: python

        safe_str(42)                  ## '42'
        safe_str(BrokenObject())      ## '<unprintable BrokenObject: RuntimeError>'

    :Parameters:
        #. value (object): Any value.

    :Returns:
        #. text (str): ``str(value)``, or ``<unprintable TypeName: ErrorClass>``.
    """
    try:
        return str(value)
    except Exception as error:
        return f"<unprintable {type(value).__name__}: {type(error).__name__}>"


# Everything but the tab: the line breaks of any kind, the escape character that starts colour codes, and the other controls,
# including the ones from 0x80 to 0x9f, which some terminals read as commands
_CONTROL_RE = re.compile('[\\x00-\\x08\\x0a-\\x1f\\x7f-\\x9f\\u2028\\u2029]')
_CONTROL_NAMES = {'\n': '\\n', '\r': '\\r'}


def _escape_control(match):
    """Writes one control character as a visible escape, such as ``\\n`` for a line break or ``\\x1b`` for the escape character."""
    character = match.group()
    name = _CONTROL_NAMES.get(character)
    if name is not None:
        return name
    code = ord(character)
    return f"\\x{code:02x}" if code <= 0xff else f"\\u{code:04x}"


def escape_control_characters(text):
    """
    Makes a text safe to put on one line: line breaks, the escape character and other control characters are written as
    visible escapes, and everything else is left alone.

    A value written on one ``key=value`` line must not be able to start a new line or paint the terminal. The
    tab is kept.

    .. code-block:: python

        escape_control_characters("a\\nb")             ## 'a\\\\nb'
        escape_control_characters("plain text")       ## 'plain text'

    :Parameters:
        #. text (str): Any text.

    :Returns:
        #. escapedText (str): The text, unchanged when it has no control character.
    """
    if text.isprintable():
        return text
    return _CONTROL_RE.sub(_escape_control, text)


def indent_continuation_lines(text):
    """
    Makes a multi-line text safe to write under a log line: every line after the first is indented by four spaces.

    A line that starts at the left edge looks like a new log record, so text that came from outside must not be able to
    start one. Every kind of line break becomes a plain one, because the tools that read a log split on more than ``\\n``.

    .. code-block:: python

        indent_continuation_lines("a\\nb")             ## 'a\\n    b'
        indent_continuation_lines("one line")        ## 'one line'

    :Parameters:
        #. text (str): Any text.

    :Returns:
        #. indentedText (str): The text, unchanged when it is on one line.
    """
    lines = text.splitlines()
    if len(lines) < 2:
        return text
    return '\n    '.join(lines)


def indent_block(text):
    """
    Indents every line of a text by four spaces, so that no line of it starts at the left edge of the log.

    :Parameters:
        #. text (str): Any text.

    :Returns:
        #. indentedText (str): The text with each line indented.
    """
    return '    ' + indent_continuation_lines(text)


def describe_error(error):
    """
    Describes an error in one short phrase without its message, so a secret hidden in the message cannot reach the error stream.

    The message of an error can hold sensitive text, such as a password in a connection string, so it must not be written to
    the standard error stream. The details stay in the error object, for example in ``sink_stats``.

    .. code-block:: python

        try:
            connect("password=hunter2")
        except Exception as error:
            describe_error(error)          ## 'ConnectionError at db.py:12 in connect'

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
    """Writes ``key=value`` for one line, with control characters in the key or the value written as visible escapes."""
    return f"{escape_control_characters(str(key))}={escape_control_characters(convert(value))}"


def _safe_repr(value):
    """Returns ``repr(value)``, or a placeholder when the value cannot give one. JSON uses it for values it does not know."""
    try:
        return repr(value)
    except Exception as error:
        return f"<unprintable {type(value).__name__}: {type(error).__name__}>"


def _non_finite_text(value):
    """Returns the text for a number JSON cannot hold: ``NaN``, ``Infinity`` or ``-Infinity``."""
    if value != value:
        return 'NaN'
    return 'Infinity' if value > 0 else '-Infinity'


def _to_jsonable(value, depth):
    """Returns a copy of a value that JSON can always write: keys become text, and a structure that is too deep or contains itself is replaced by a placeholder."""
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
    """Returns the JSON text of a value. What JSON cannot represent is written with ``repr``, and a bad value never raises."""
    try:
        return json.dumps(value, default=_safe_repr, separators=JSON_SEPARATORS, allow_nan=False)
    except (TypeError, ValueError):
        # A key that is not text, a number that is not finite, or a structure that contains itself: rewrite it, then write it
        return json.dumps(_to_jsonable(value, 0), default=_safe_repr, separators=JSON_SEPARATORS, allow_nan=False)


def _require_record(record):
    """Raises a clear error when the thing given to a formatter is not a record."""
    if not isinstance(record, LogRecord):
        raise TypeError(f"formatter needs a LogRecord, got {type(record).__name__}")


# Texts that repeat from one record to the next. Each cache holds this many entries at most, and starts again when full,
# so a program with an endless variety of names cannot make it grow
MAX_CACHED_TEXTS = 512
_IDENTITY_TEXTS = {}
_ORIGIN_TEXTS = {}
_KEY_TEXTS = {}


def _remember(cache, key, text):
    """Keeps a text in a small memory, which starts again when it is full."""
    if len(cache) >= MAX_CACHED_TEXTS:
        cache.clear()
    cache[key] = text


def _json_scalar(value):
    """Returns the JSON text of a plain text, whole number, decimal, true/false or None, and None for anything else."""
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
    """Returns the JSON text of any value, using ``repr`` for what JSON cannot represent."""
    text = _json_scalar(value)
    if text is None:
        text = _dumps(value)
    return text


def _mapping_to_json(mapping):
    """Returns the JSON object text of a dictionary, writing plain values by hand because that is faster."""
    entries = []
    for key, value in mapping.items():
        text = _json_scalar(value)
        if text is None:
            # One encoder call for the whole mapping is cheaper than one call per complex value
            return _dumps(dict(mapping))
        keyText = _KEY_TEXTS.get(key)
        if keyText is None:
            keyText = encode_basestring_ascii(key)
            _remember(_KEY_TEXTS, key, keyText)
        entries.append(f"{keyText}:{text}")
    return '{' + ','.join(entries) + '}'


class JsonFormatter:
    """
    Writes a record as one line of JSON that a program can read back.

    The line has no trailing newline. The keys ``schema``, ``timestamp``,
    ``severity``, ``log_type``, ``level``, ``logger``, ``message``, ``process`` and ``thread``
    are always present. ``exception``, ``caller``, ``context`` and ``fields``
    are present only when they have content. Values that JSON cannot represent
    are written with ``repr``. A key that is not text is written as its text, and a value that cannot give
    a ``repr`` is written as ``<unprintable TypeName: ErrorClass>``, so a bad value never loses the record.

    .. code-block:: python

        from pysimplelog import logger, CONSOLE_SINK, JsonFormatter

        logger.set_sink_formatter(CONSOLE_SINK, JsonFormatter(utc=True))
        logger.info("Order created", order_id=123)
        ## {"schema":1,"timestamp":"...Z","severity":"INFO",...,"message":"Order created",...,"fields":{"order_id":123}}

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
        timestamp = record.timestamp.astimezone(timezone.utc) if self.__utc else record.timestamp
        if self.__flatten or record.exception is not None or record.caller is not None:
            items = self._fixed_items(record, timestamp)
            if self.__flatten:
                items.extend(self._flat_items(record))
            else:
                if len(record.context) > 0:
                    items.append(f'"context":{_mapping_to_json(record.context)}')
                if len(record.fields) > 0:
                    items.append(f'"fields":{_mapping_to_json(record.fields)}')
            return '{' + ','.join(items) + '}'
        # The usual record: what names the log type and the logger, and what names the process and the thread, repeats
        identityKey = (record.severity, record.logType, record.level, record.logger)
        identity = _IDENTITY_TEXTS.get(identityKey)
        if identity is None:
            level = 'null' if record.level is None else _json_value(record.level)
            identity = (f'"severity":{encode_basestring_ascii(record.severity)},'
                        f'"log_type":{encode_basestring_ascii(record.logType)},"level":{level},'
                        f'"logger":{encode_basestring_ascii(record.logger)}')
            _remember(_IDENTITY_TEXTS, identityKey, identity)
        originKey = (record.processId, record.threadId, record.threadName)
        origin = _ORIGIN_TEXTS.get(originKey)
        if origin is None:
            origin = (f'"process":{{"id":{record.processId}}},'
                      f'"thread":{{"id":{record.threadId},"name":{encode_basestring_ascii(record.threadName)}}}')
            _remember(_ORIGIN_TEXTS, originKey, origin)
        text = (f'{{"schema":{SCHEMA_VERSION},"timestamp":"{_format_timestamp(timestamp)}",{identity},'
                f'"message":{encode_basestring_ascii(record.message)},{origin}')
        if len(record.context) > 0:
            text += f',"context":{_mapping_to_json(record.context)}'
        if len(record.fields) > 0:
            text += f',"fields":{_mapping_to_json(record.fields)}'
        return text + '}'

    @staticmethod
    def _fixed_items(record, timestamp):
        """Returns the entries of the JSON document that every layout has: schema, time, severity, message, exception, caller, process and thread."""
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
        """Returns the context and field entries as top-level JSON entries, renaming a name that clashes with a fixed key."""
        merged = {}
        for prefix, source in (('context', record.context), ('fields', record.fields)):
            for key, value in source.items():
                name = f"{prefix}.{key}" if key in RESERVED_KEYS else key
                merged[name] = value
        return [f"{encode_basestring_ascii(name)}:{_json_value(value)}" for name, value in merged.items()]


class TextFormatter:
    """
    Writes a record as one readable line, the way the log file does by default.

    Renders a record as one human-readable line, followed by the traceback when there is one.

    The layout is ``timestamp - logger <SEVERITY> [caller] [context] message key=value``. A field named
    ``data`` is not written as ``key=value`` but on its own line after the message, and the traceback
    comes last. The text has no trailing newline.

    .. code-block:: python

        ## 2026-10-06 19:21:49 - orders <INFO> [request_id=r1] Order created order_id=123
        formatter = TextFormatter()

    :Parameters:
        #. utc (bool): Writes the time in UTC with a trailing Z.
        #. milliseconds (bool): Writes .mmm after the seconds.

    :Raises:
        #. TypeError: If utc or milliseconds is not a boolean.
    """

    def __init__(self, utc=False, milliseconds=False):
        if not isinstance(utc, bool) or not isinstance(milliseconds, bool):
            raise TypeError("utc and milliseconds must be booleans")
        self.__utc = utc
        self.__milliseconds = milliseconds

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

    def _render(self, record, convert):
        """Builds the line for a record, turning every field and context value into text with *convert*."""
        parts = [f"{_readable_timestamp(record.timestamp, self.__utc, self.__milliseconds)} - {record.logger} <{record.severity}> "]
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
            parts.append(f"\n{indent_continuation_lines(convert(record.fields['data']))}")
        if record.exception is not None:
            parts.append(f"\n{indent_block(record.exception.stacktrace)}")
        return ''.join(parts)


SGR_RESET = '\x1b[0m'
SGR_DIM = '\x1b[2m'
TRACEBACK_STYLES = ('full', 'compact')
DEFAULT_SEVERITY_COLORS = {'DEBUG': '\x1b[36m', 'INFO': '\x1b[32m', 'WARNING': '\x1b[33m',
                           'ERROR': '\x1b[31m', 'CRITICAL': '\x1b[1;31m'}


def stream_supports_color(stream):
    """
    Says whether colour codes belong in a stream: true for a terminal, unless the ``NO_COLOR`` variable is set or the terminal is
    ``dumb``.

    They do when the stream is a terminal, the user did not refuse colour with the ``NO_COLOR`` variable, and the
    terminal is not ``dumb``. A pipe, a file or a CI log is not a terminal, so it stays plain.

    .. code-block:: python

        import sys
        stream_supports_color(sys.stdout)         ## True in a terminal, False when piped to a file

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


# The styles a message can use between tags, such as ``<red>`` and ``<bold>``
MARKUP_STYLES = {'bold': '\x1b[1m', 'dim': '\x1b[2m', 'underline': '\x1b[4m',
                 'red': '\x1b[31m', 'green': '\x1b[32m', 'yellow': '\x1b[33m', 'blue': '\x1b[34m',
                 'magenta': '\x1b[35m', 'cyan': '\x1b[36m', 'white': '\x1b[37m'}
# A tag is a name in angle brackets, an opening ``<red>`` or a closing ``</red>``, or ``</>`` for the last one opened. A backslash
# in front of it, ``\\<red>``, keeps it as text. Only lowercase names, so an ordinary ``<Name>`` is never taken for a tag
_MARKUP_TAG_RE = re.compile(r'(\\)?<(/)?([a-z]*)>')


def render_markup(text, colors):
    """
    Turns the colour tags of a message into colour codes, or removes them.

    A tag such as ``<red>`` starts a style and ``</red>`` ends it, ``</>`` ends the last one started. Styles can be nested,
    ``<bold><red>`` and ``</red>`` leaves the bold on. The styles are ``bold``, ``dim``, ``underline`` and the colours
    ``red``, ``green``, ``yellow``, ``blue``, ``magenta``, ``cyan`` and ``white``. Anything that is not a tag
    of these is kept as written, such as ``a < b``, ``<unknown>`` or a closing tag that closes nothing. A backslash before a tag, ``\\<red>``,
    keeps the tag as text. A style that is never closed ends with the message, and at the end of each line when the message has
    several, so a colour never reaches the text that follows.

    .. code-block:: python

        render_markup("<red>failed</red> to connect", True)       ## the word failed in red
        render_markup("<red>failed</red> to connect", False)      ## failed to connect

    :Parameters:
        #. text (str): The message.
        #. colors (bool): True writes the colour codes, False removes the tags and writes the plain text.

    :Returns:
        #. rendered (str): The message with the tags turned into codes, or removed.

    :Raises:
        #. TypeError: If *text* is not a string.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    # Most messages have no tag, and they must cost nothing
    if '<' not in text:
        return text
    pieces = []
    openStyles = []
    position = 0
    for match in _MARKUP_TAG_RE.finditer(text):
        backslash, slash, name = match.groups()
        isStyle = name in MARKUP_STYLES
        isOpening = slash is None and isStyle
        isClosing = slash is not None and (isStyle or name == '')
        if not (isOpening or isClosing):
            # Not a tag of ours, so it stays in the text exactly as written, with its backslash
            continue
        pieces.append(_markup_text(text[position:match.start()], openStyles, colors))
        position = match.end()
        if backslash is not None:
            pieces.append(match.group()[1:])
        elif isOpening:
            openStyles.append(name)
            if colors:
                pieces.append(MARKUP_STYLES[name])
        elif len(openStyles) > 0 and (name == '' or name in openStyles):
            if name == '':
                openStyles.pop()
            else:
                # The last one opened with this name, the styles opened after it stay on
                for index in range(len(openStyles) - 1, -1, -1):
                    if openStyles[index] == name:
                        del openStyles[index]
                        break
            if colors:
                pieces.append(SGR_RESET + ''.join(MARKUP_STYLES[style] for style in openStyles))
        else:
            # A closing tag with nothing to close is text
            pieces.append(match.group())
    pieces.append(_markup_text(text[position:], openStyles, colors))
    if colors and len(openStyles) > 0:
        pieces.append(SGR_RESET)
    return ''.join(pieces)


def _markup_text(text, openStyles, colors):
    """Returns a piece of text between tags: when styles are on, each line break ends them and the next line starts them again."""
    if not colors or len(openStyles) == 0 or '\n' not in text:
        return text
    return text.replace('\n', SGR_RESET + '\n' + ''.join(MARKUP_STYLES[style] for style in openStyles))


class ConsoleFormatter:
    """
    Writes a record as a tidy line of columns for the console, in colour when you ask for it. It is what the ``"pretty"`` layout uses.

    The layout is ``timestamp.mmm | SEVERITY | logger | message``, with a ``file:line in function`` column before
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
        #. utc (bool): Writes the time in UTC with a trailing Z.
        #. milliseconds (bool): Writes .mmm after the seconds. True by default.
        #. colorOf (None, callable): ``f(record) -> escape code``, tried before *severityColors*. None, or an empty
           answer, falls back to the colour of the severity.
        #. markup (bool): True reads the colour tags of the message, such as ``<red>failed</red>``, see :func:`render_markup`. The
           tags become colour codes when *colors* is True, and are removed when it is False. The default False leaves the
           message as it is.

    :Raises:
        #. TypeError: If *colors* is not a boolean, *severityColors* is not a dictionary of strings, *utc*, *milliseconds* or
           *markup* is not a boolean, or *colorOf* is not callable.
        #. ValueError: If *traceback* is not 'full' or 'compact'.
    """

    def __init__(self, colors=False, severityColors=None, traceback='full', utc=False, milliseconds=True,
                 colorOf=None, markup=False):
        if not isinstance(colors, bool):
            raise TypeError("colors must be a boolean")
        if not isinstance(utc, bool) or not isinstance(milliseconds, bool):
            raise TypeError("utc and milliseconds must be booleans")
        if not isinstance(markup, bool):
            raise TypeError("markup must be a boolean")
        self.__markup = markup
        if colorOf is not None and not callable(colorOf):
            raise TypeError("colorOf must be callable or None")
        self.__utc = utc
        self.__milliseconds = milliseconds
        self.__colorOf = colorOf
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
        """Builds the line for a record, turning every field and context value into text with *convert*."""
        columns = [self._dim(_readable_timestamp(record.timestamp, self.__utc, self.__milliseconds)),
                   self._paint(f"{record.severity:<8}", record),
                   record.logger]
        if record.caller is not None:
            columns.append(_format_caller(record.caller))
        message = render_markup(record.message, self.__colors) if self.__markup else record.message
        parts = [' | '.join(columns), ' | ', message]
        pairs = [_pair_text(key, value, convert) for key, value in record.context.items()]
        pairs.extend(_pair_text(key, value, convert) for key, value in record.fields.items() if key != 'data')
        if len(pairs) > 0:
            parts.append(' ' + self._dim(' '.join(pairs)))
        if 'data' in record.fields:
            parts.append(f"\n{indent_continuation_lines(convert(record.fields['data']))}")
        if record.exception is not None:
            parts.append(f"\n{indent_block(self._traceback_text(record.exception))}")
        return ''.join(parts)

    def _traceback_text(self, exception):
        """Returns the traceback the way the formatter was asked to write it: in full or shortened."""
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
        """Returns the text in a dim style when colours are on."""
        return f"{SGR_DIM}{text}{SGR_RESET}" if self.__colors else text

    def _paint(self, text, record):
        """Returns the text in the colour of a record when colours are on and the record has one."""
        if not self.__colors:
            return text
        code = self._color_code(record)
        if code is None:
            return text
        return f"{code}{text}{SGR_RESET}"

    def _color_code(self, record):
        """Returns the colour code of a record: the one *colorOf* gives, else the one of its severity, else None."""
        if self.__colorOf is not None:
            try:
                code = self.__colorOf(record)
            except Exception:
                # A colour is a decoration, a function that fails must not lose the record
                code = None
            if code:
                return code
        return self.__severityColors.get(record.severity)


class _SafeValue:
    """Wraps a value so that formatting it never fails: a value that cannot be formatted gives a placeholder."""

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


class _TimestampView:
    """A timestamp for templates: ISO text by default, ``strftime`` when the format has a ``%``, and plain text alignment otherwise."""

    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return _format_timestamp(self.value)

    def __format__(self, spec):
        if '%' in spec:
            return self.value.strftime(spec)
        return format(_format_timestamp(self.value), spec)


class _TemplateView(dict):
    """A dictionary that gives an empty text for a name the record does not have, whatever its format."""

    def __missing__(self, key):
        # A spec such as 05d fails on an empty string, and a record must not be lost for a field it does not have
        return _SafeValue('')


class TemplateFormatter:
    """
    Writes a record from a template with ``{name}`` placeholders, the way you would write an f-string.

    Available names: ``timestamp`` (ISO text, or a ``strftime`` spec such as ``{timestamp:%H:%M:%S}``),
    ``timestamp_utc`` (the same in UTC), ``severity``, ``log_type``, ``level``, ``logger``, ``message``,
    ``fields``, ``context``, ``exception`` (the traceback text), ``caller`` (``file:line in function``),
    ``file``, ``line``, ``function`` and ``module`` of the caller (when the logger has ``callerInfo``, and unless a
    field has the same name), ``process``, ``thread``, ``thread_name`` and every key of the record fields and context.
    A name the record does not have renders as an empty string, whatever its format spec. A field never overrides a
    fixed name. Only plain names are allowed: ``{message.upper}`` and ``{fields[x]}`` are rejected,
    so a template cannot reach attributes of the values.

    .. code-block:: python

        from pysimplelog import logger, CONSOLE_SINK

        logger.set_sink_formatter(CONSOLE_SINK, "{timestamp:%H:%M:%S} [{severity}] {message} user={user_id:05d}")
        logger.info("login", user_id=7)          ## 21:30:00 [INFO] login user=00007

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
        # Like the text layouts, a text value must not start a new line. Data is meant to be multi-line, so its lines are indented instead
        for source in (record.context, record.fields):
            for key, value in source.items():
                if isinstance(value, str):
                    value = indent_continuation_lines(value) if key == 'data' else escape_control_characters(value)
                view[key] = value
        view.update({'timestamp': _TimestampView(record.timestamp),
                     'timestamp_utc': _TimestampView(record.timestamp.astimezone(timezone.utc)),
                     'severity': record.severity,
                     'log_type': record.logType,
                     'level': record.level,
                     'logger': record.logger,
                     'message': record.message,
                     'fields': dict(record.fields),
                     'context': dict(record.context),
                     'exception': '' if record.exception is None else indent_block(record.exception.stacktrace),
                     'caller': '' if record.caller is None else _format_caller(record.caller),
                     'process': record.processId,
                     'thread': record.threadId,
                     'thread_name': record.threadName})
        if record.caller is not None:
            # setdefault: a field named line or file keeps its value, as templates written before these names did
            for name, value in (('file', record.caller.fileName), ('line', record.caller.line),
                                ('function', record.caller.function), ('module', record.caller.moduleName)):
                view.setdefault(name, value)
        return view


# Keyword to formatter factory. Add more with register_formatter
FORMATTERS = {'json': JsonFormatter, 'jsonl': JsonFormatter, 'text': TextFormatter, 'pretty': ConsoleFormatter}


def register_formatter(name, factory):
    """
    Adds your own name for a layout, so ``format="short"`` works like ``format="json"``.

    .. code-block:: python

        register_formatter("short", lambda: (lambda record: f"{record.severity}: {record.message}"))
        logger.add("logs/short.log", format="short")

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
    Turns any way of naming a layout (a keyword, a template, a function, or None) into the function that writes records.

    Turns any accepted formatter value into a callable ``f(record) -> str``.

    .. code-block:: python

        render = resolve_formatter("json")
        text = render(record)

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


def without_markup(formatter):
    """
    Makes a formatter that removes the colour tags of the message first, for an output that is not the console.

    A message written with tags such as ``<red>failed</red>`` is meant for a console that reads them. A file or a
    JSON output would keep the tags as text, and this gives them the plain message.

    .. code-block:: python

        logger.set_sink_formatter(FILE_SINK, without_markup("text"))

    :Parameters:
        #. formatter (None, str, callable): Anything :func:`resolve_formatter` accepts.

    :Returns:
        #. renderer (callable): ``f(record) -> str``, the formatter's text for the record with its message cleaned.

    :Raises:
        #. ValueError: If *formatter* is a string that is neither a keyword nor a template.
        #. TypeError: If *formatter* is none of the accepted types.
    """
    render = resolve_formatter(formatter)

    def render_plain(record):
        """Returns the text of the record with the colour tags of its message removed."""
        _require_record(record)
        return render(record._replace(message=render_markup(record.message, False)))
    return render_plain
