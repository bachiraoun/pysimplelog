"""
Turns pysimplelog records into the OpenTelemetry OTLP/JSON layout of a logs export request, with no third-party package.

Only the encoding lives here, it sends nothing. The names of the attributes follow the OpenTelemetry semantic conventions, and
the layout follows the OTLP/JSON rules: the keys are written in lowerCamelCase, a 64 bit integer is written as text, enums are
integers, and the trace and span identifiers are lower case hexadecimal text and not base64.

What a record becomes:

========================  ==============================================================================================
OTLP                      pysimplelog
========================  ==============================================================================================
``timeUnixNano``          ``timestamp``, exact to the microsecond
``observedTimeUnixNano``  the moment given to the encoder, left out when none is given
``severityNumber``        from the log type, see :class:`OtlpSeverityMap`
``severityText``          ``severity``, the display name of the log type
``body``                  ``message``
``traceId`` / ``spanId``  ``trace``, left out when the record has none
``flags``                 the trace flags of ``trace``
``log.record.uid``        the field named *eventIdField*, the stable identifier a receiver can drop repeats by
``process.pid``           ``processId``
``thread.id``             ``threadId``
``thread.name``           ``threadName``
``code.file.path``        ``caller.fileName``
``code.function.name``    ``caller.moduleName`` and ``caller.function``, joined by a dot
``code.line.number``      ``caller.line``
``exception.type``        ``exception.typeName``
``exception.message``     ``exception.message``
``exception.stacktrace``  ``exception.stacktrace``
other attributes          the context, then the fields: a field wins over a context value of the same name
scope name                ``logger``
========================  ==============================================================================================

A field or context value whose name is one of the attributes above is kept under ``fields.<name>`` or ``context.<name>``, so
that nothing is lost and nothing overrides what the encoder writes.
"""

import base64
import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

try:
    from ..__pkginfo__ import __version__
    from ..formatters import _safe_repr, safe_str
except ImportError:
    from __pkginfo__ import __version__
    from formatters import _safe_repr, safe_str

# Nesting deeper than this is replaced, which also stops a structure that contains itself
MAX_DEPTH = 20
INT64_MIN, INT64_MAX = -2 ** 63, 2 ** 63 - 1
UINT64_MAX = 2 ** 64 - 1
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)

# The names the encoder writes itself: a field or a context value with one of them is kept under a prefix
RESERVED_ATTRIBUTES = frozenset({
    'log.record.uid', 'process.pid', 'thread.id', 'thread.name', 'code.file.path', 'code.function.name', 'code.line.number',
    'exception.type', 'exception.message', 'exception.stacktrace'})


class OtlpSeverityMap:
    """
    Maps the name of a log type to an OTLP severity number.

    The answer comes from the name only, as in the SIEM sink: there is no guessing from the numeric level. A log type that is not
    in the table is ``INFO`` (9). Give *overrides* for a log type of your own.

    :Parameters:
        #. overrides (dict, None): Extra or changed ``{name: number}`` entries. The name is compared in lower case and the
           number is an integer from 1 to 24.

    :Raises:
        #. TypeError: If *overrides* is not a dictionary, a name is not text, or a number is not an integer.
        #. ValueError: If a number is not from 1 to 24.
    """

    NUMBERS = {'trace': 1, 'debug': 5, 'info': 9, 'important': 9, 'notice': 10, 'warn': 13, 'warning': 13, 'error': 17,
               'critical': 21, 'super critical': 22, 'supercritical': 22, 'alert': 22, 'emergency': 23}

    def __init__(self, overrides=None):
        self.__numbers = dict(self.NUMBERS)
        if overrides is not None:
            if not isinstance(overrides, dict):
                raise TypeError("overrides must be a dictionary")
            for name, number in overrides.items():
                if not isinstance(name, str):
                    raise TypeError("an override name must be text")
                if not isinstance(number, int) or isinstance(number, bool):
                    raise TypeError("an override number must be an integer")
                if not 1 <= number <= 24:
                    raise ValueError(f"an override number must be from 1 to 24, got {number}")
                self.__numbers[name.strip().lower()] = number

    def resolve(self, logType):
        """
        Returns the severity number of a log type.

        :Parameters:
            #. logType (str): The name of the log type.

        :Returns:
            #. number (int): From 1 to 24, 9 (``INFO``) for a name that is not known.
        """
        return self.__numbers.get(str(logType).strip().lower(), 9)


def _any_value(value, depth):
    """
    Returns the OTLP ``AnyValue`` of a value: a dictionary with one key that says the type.

    It never raises. A record that cannot be encoded can never be delivered, and a sink would try it again for ever, so a
    structure that fails while it is read, a mapping that changes size under another thread for example, becomes a
    placeholder that names its type and never its error.
    """
    if depth > MAX_DEPTH:
        return {'stringValue': '<too deep>'}
    if isinstance(value, str):
        return {'stringValue': str.__str__(value)}
    if isinstance(value, bool):
        return {'boolValue': bool(value)}
    if isinstance(value, int):
        number = int(value)
        if INT64_MIN <= number <= INT64_MAX:
            # OTLP/JSON writes a 64 bit integer as text, because many JSON readers keep only 53 bits
            return {'intValue': str(number)}
        return {'stringValue': str(number)}
    if isinstance(value, float):
        number = float(value)
        if number != number:
            return {'doubleValue': 'NaN'}
        if number in (float('inf'), float('-inf')):
            return {'doubleValue': 'Infinity' if number > 0 else '-Infinity'}
        return {'doubleValue': number}
    if value is None:
        return {}
    if isinstance(value, (bytes, bytearray)):
        return {'bytesValue': base64.b64encode(bytes(value)).decode('ascii')}
    try:
        if isinstance(value, Mapping):
            return {'kvlistValue': {'values': [{'key': key if isinstance(key, str) else safe_str(key),
                                                'value': _any_value(item, depth + 1)} for key, item in value.items()]}}
        if isinstance(value, (list, tuple)):
            return {'arrayValue': {'values': [_any_value(item, depth + 1) for item in value]}}
    except Exception:
        return {'stringValue': f"<unencodable {type(value).__name__}>"}
    return {'stringValue': _safe_repr(value)}


def _key_values(attributes):
    """Returns the OTLP ``KeyValue`` list of a dictionary, in its order."""
    return [{'key': key, 'value': _any_value(value, 0)} for key, value in attributes.items()]


def _unix_nano(timestamp):
    """
    Returns the time as nanoseconds since the epoch, in whole integers so that no float rounds it.

    OTLP holds the time in an unsigned 64 bit number, in which 0 means that no time is set, so a moment before 1970 or after the
    year 2554, which only a broken clock gives, is brought back to the nearest value that can be written.
    """
    return min(max((timestamp - _EPOCH) // _MICROSECOND * 1000, 0), UINT64_MAX)


class OtlpLogEncoder:
    """
    Builds the OTLP/JSON body of a logs export request from records.

    :Parameters:
        #. resource (dict, None): Who is sending: ``service.name``, ``service.version``, ``deployment.environment`` and so on. The
           values can be text, numbers, booleans, lists or dictionaries. The attributes ``telemetry.sdk.name``,
           ``telemetry.sdk.language`` and ``telemetry.sdk.version`` are added, and a key of *resource* with one of these names
           replaces it.
        #. severityMap (OtlpSeverityMap, None): How a log type gets its severity number. None gives the default table.
        #. eventIdField (str, None): The name of the field that holds the stable identifier of a record, the one a spool adds. It is
           written as ``log.record.uid`` and not as an ordinary attribute. None writes no such attribute.
        #. scopeVersion (str, None): The version written in each scope, left out when None.

    :Raises:
        #. TypeError: If an argument has the wrong type, or a key of *resource* is not text.
        #. ValueError: If a key of *resource* is empty.

    .. code-block:: python

        encoder = OtlpLogEncoder(resource={'service.name': 'orders', 'deployment.environment': 'production'})
        body = encoder.encode(records, observedTimeNs=time.time_ns())      ## bytes, ready to POST to /v1/logs
    """

    def __init__(self, resource=None, severityMap=None, eventIdField='event_id', scopeVersion=None):
        if resource is not None and not isinstance(resource, dict):
            raise TypeError("resource must be a dictionary")
        if severityMap is not None and not isinstance(severityMap, OtlpSeverityMap):
            raise TypeError("severityMap must be an OtlpSeverityMap")
        if eventIdField is not None and (not isinstance(eventIdField, str) or len(eventIdField) == 0):
            raise TypeError("eventIdField must be a non-empty string or None")
        if scopeVersion is not None and not isinstance(scopeVersion, str):
            raise TypeError("scopeVersion must be a string or None")
        attributes = {'telemetry.sdk.name': 'pysimplelog', 'telemetry.sdk.language': 'python', 'telemetry.sdk.version': __version__}
        for key, value in (resource or {}).items():
            if not isinstance(key, str):
                raise TypeError("a key of resource must be text")
            if len(key) == 0:
                raise ValueError("a key of resource must not be empty")
            attributes[key] = value
        self.__resource = {'attributes': _key_values({key: value for key, value in attributes.items() if value is not None})}
        self.__severityMap = severityMap or OtlpSeverityMap()
        self.__eventIdField = eventIdField
        self.__scopeVersion = scopeVersion

    def encode_record(self, record, observedTimeNs=None):
        """
        Returns one record as an OTLP ``LogRecord``, a dictionary.

        :Parameters:
            #. record (LogRecord): The record.
            #. observedTimeNs (None, int): The moment the record was observed by the sender, in nanoseconds since the epoch. Left
               out when None.

        :Returns:
            #. logRecord (dict): The OTLP ``LogRecord``.

        :Raises:
            #. TypeError: If *observedTimeNs* is neither None nor an integer.
        """
        if observedTimeNs is not None and (not isinstance(observedTimeNs, int) or isinstance(observedTimeNs, bool)):
            raise TypeError("observedTimeNs must be an integer number of nanoseconds or None")
        attributes = {}
        fields, context = record.fields, record.context
        eventId = None if self.__eventIdField is None else fields.get(self.__eventIdField)
        if eventId is not None:
            attributes['log.record.uid'] = eventId if isinstance(eventId, str) else safe_str(eventId)
        attributes['process.pid'] = record.processId
        attributes['thread.id'] = record.threadId
        attributes['thread.name'] = record.threadName
        caller = record.caller
        if caller is not None:
            attributes['code.file.path'] = caller.fileName
            attributes['code.function.name'] = f"{caller.moduleName}.{caller.function}" if len(caller.moduleName) > 0 else caller.function
            attributes['code.line.number'] = caller.line
        exception = record.exception
        if exception is not None:
            if exception.typeName is not None:
                attributes['exception.type'] = exception.typeName
            if exception.message is not None:
                attributes['exception.message'] = exception.message
            attributes['exception.stacktrace'] = exception.stacktrace
        # The fields come last, so a field replaces a context value of the same name
        for source, prefix in ((context, 'context.'), (fields, 'fields.')):
            for key, value in source.items():
                if source is fields and eventId is not None and key == self.__eventIdField:
                    continue
                if value is None:
                    continue
                attributes[prefix + key if key in RESERVED_ATTRIBUTES else key] = value
        logRecord = {'timeUnixNano': str(_unix_nano(record.timestamp)), 'severityNumber': self.__severityMap.resolve(record.logType),
                     'severityText': record.severity, 'body': {'stringValue': record.message},
                     'attributes': _key_values(attributes)}
        trace = record.trace
        if trace is not None:
            logRecord['flags'] = trace.flags
            logRecord['traceId'] = trace.traceId
            logRecord['spanId'] = trace.spanId
        if observedTimeNs is not None:
            logRecord['observedTimeUnixNano'] = str(observedTimeNs)
        return logRecord

    def encode_request(self, records, observedTimeNs=None):
        """
        Returns the body of a logs export request, as a dictionary. The records are grouped in one scope for each logger name,
        in the order the names first appear, and keep their order inside a scope.

        :Parameters:
            #. records (list): The records.
            #. observedTimeNs (None, int): See :meth:`encode_record`.

        :Returns:
            #. request (dict): The ``ExportLogsServiceRequest``.
        """
        scopes = {}
        for record in records:
            scopes.setdefault(record.logger, []).append(self.encode_record(record, observedTimeNs))
        scopeLogs = []
        for name, logRecords in scopes.items():
            scope = {'name': name}
            if self.__scopeVersion is not None:
                scope['version'] = self.__scopeVersion
            scopeLogs.append({'scope': scope, 'logRecords': logRecords})
        return {'resourceLogs': [{'resource': self.__resource, 'scopeLogs': scopeLogs}]}

    def encode(self, records, observedTimeNs=None):
        """
        Returns the body of a logs export request as JSON bytes, ready to send. The text is ASCII and has no spaces.

        :Parameters:
            #. records (list): The records.
            #. observedTimeNs (None, int): See :meth:`encode_record`.

        :Returns:
            #. body (bytes): The JSON text.
        """
        return json.dumps(self.encode_request(records, observedTimeNs), separators=(',', ':'), allow_nan=False).encode('ascii')
