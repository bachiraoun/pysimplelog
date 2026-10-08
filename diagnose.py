"""
Writes a traceback with the values of the variables that each frame uses, for development.
"""

import re
import traceback
import linecache
import types
from collections import defaultdict, deque

try:
    from .processors import DEFAULT_SENSITIVE_NAMES, _normalize_name
except ImportError:
    from processors import DEFAULT_SENSITIVE_NAMES, _normalize_name

DIAGNOSE_MODES = ('summary', 'full')
MAX_VALUE_LENGTH = 200
REDACTED_TEXT = '<redacted>'

# A name after a dot is an attribute, not a variable of the frame
_VARIABLE_NAME_RE = re.compile(r'(?<![\w.])[A-Za-z_]\w*')
_FRAME_LINE_RE = re.compile(r'^  File "(.*)", line (\d+), in (.*)$')
_PLAIN_TYPES = (str, int, float, bool, type(None), bytes)
_NOT_SHOWN_TYPES = (types.ModuleType, types.FunctionType, types.BuiltinFunctionType, types.MethodType, type)


def format_exception_with_values(excType, excValue, excTraceback, mode, extraNames=()):
    """
    Formats an exception like Python does, with the variables of each frame under its source line.

    Only the variables named on the source line of a frame are shown. A variable whose name contains a
    sensitive name, such as ``password``, shows ``<redacted>`` instead of its value.

    :Parameters:
        #. excType (type): The exception class.
        #. excValue (BaseException): The exception.
        #. excTraceback (traceback, None): The traceback of the exception.
        #. mode (str): 'summary' shows plain values in full and containers and objects by type and length.
           'full' shows the ``repr`` of every value.
        #. extraNames (tuple): Sensitive names added to the default ones.

    :Returns:
        #. text (str): The traceback text without a trailing newline. It is the plain Python traceback when
           the variables cannot be collected.
    """
    text = ''.join(traceback.format_exception(excType, excValue, excTraceback)).rstrip('\n')
    try:
        sensitiveNames = tuple(_normalize_name(name) for name in DEFAULT_SENSITIVE_NAMES + tuple(extraNames))
        variableLines = _collect_variable_lines(excValue, excTraceback, mode, sensitiveNames)
        return _insert_variable_lines(text, variableLines)
    except Exception:
        # A value that breaks the collection must not lose the traceback
        return text


def _chain_tracebacks(excValue, excTraceback, seen):
    """Yields the tracebacks of an exception chain in the order Python prints them."""
    if excValue is None or id(excValue) in seen:
        return
    seen.add(id(excValue))
    if excValue.__cause__ is not None:
        yield from _chain_tracebacks(excValue.__cause__, excValue.__cause__.__traceback__, seen)
    elif excValue.__context__ is not None and not excValue.__suppress_context__:
        yield from _chain_tracebacks(excValue.__context__, excValue.__context__.__traceback__, seen)
    yield excTraceback


def _collect_variable_lines(excValue, excTraceback, mode, sensitiveNames):
    """Returns ``{(file, line, function): deque of variable line lists}``, in the order the frames print."""
    collected = defaultdict(deque)
    for chainTraceback in _chain_tracebacks(excValue, excTraceback, set()):
        for frame, lineNumber in traceback.walk_tb(chainTraceback):
            key = (frame.f_code.co_filename, str(lineNumber), frame.f_code.co_name)
            collected[key].append(_frame_variable_lines(frame, lineNumber, mode, sensitiveNames))
    return collected


def _frame_variable_lines(frame, lineNumber, mode, sensitiveNames):
    """Returns the ``name = value`` lines of the variables used on one source line of a frame."""
    sourceLine = linecache.getline(frame.f_code.co_filename, lineNumber, frame.f_globals)
    lines = []
    shownNames = set()
    for name in _VARIABLE_NAME_RE.findall(sourceLine):
        if name in shownNames or name not in frame.f_locals:
            continue
        shownNames.add(name)
        value = frame.f_locals[name]
        if isinstance(value, _NOT_SHOWN_TYPES):
            continue
        isSensitive = any(sensitive in _normalize_name(name) for sensitive in sensitiveNames)
        shownValue = REDACTED_TEXT if isSensitive else _describe_value(value, mode)
        lines.append(f"        {name} = {shownValue}")
    return lines


def _describe_value(value, mode):
    """Returns the text of a value, cut to the maximum length, that never raises."""
    try:
        if mode == 'summary' and type(value) not in _PLAIN_TYPES:
            try:
                return f"<{type(value).__name__} len={len(value)}>"
            except Exception:
                return f"<{type(value).__name__}>"
        text = repr(value)
    except Exception as error:
        return f"<repr failed: {type(error).__name__}>"
    if len(text) > MAX_VALUE_LENGTH:
        text = text[:MAX_VALUE_LENGTH] + '...'
    return text


def _insert_variable_lines(text, variableLines):
    """Puts the variable lines after the source lines of each frame of a traceback text."""
    output = []
    pending = []
    for line in text.split('\n'):
        # A line that is not indented by four spaces ends the source lines of the frame before it
        if not line.startswith('    '):
            output.extend(pending)
            pending = []
        match = _FRAME_LINE_RE.match(line)
        if match is not None:
            frameLines = variableLines.get(match.groups())
            if frameLines:
                pending = frameLines.popleft()
        output.append(line)
    output.extend(pending)
    return '\n'.join(output)
