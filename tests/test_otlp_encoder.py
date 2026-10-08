"""Tests of the OTLP/JSON encoder: the mapping of a record, the values, the names, the times, and a cross-check with the official encoder.

The cross-check is skipped when the packages ``opentelemetry-exporter-otlp-proto-common`` and ``opentelemetry-sdk`` are not installed.

Run from the repo root::

    python3 -m unittest tests.test_otlp_encoder -v
"""
import base64
import calendar
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from contrib.otlp_encoder import OtlpLogEncoder, OtlpSeverityMap, RESERVED_ATTRIBUTES  # noqa: E402
from __pkginfo__ import __version__  # noqa: E402
from record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo  # noqa: E402

TRACE = TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1)
STACKTRACE = 'Traceback (most recent call last):\n  File "db.py", line 9, in connect\nConnectionError: timed out'
OBSERVED = 1791311513000000000
RESOURCE = {'service.name': 'orders', 'deployment.environment': 'production'}


def full_record(**changes):
    values = dict(
        timestamp=datetime(2026, 10, 6, 13, 31, 52, 123456, tzinfo=timezone(timedelta(hours=-5))), severity='ERROR', logType='error',
        level=30.0, logger='orders', message='Database connection failed', processId=4321, threadId=140234, threadName='worker-3',
        fields={'order_id': 123, 'retries': 3, 'ratio': float('nan'), 'event_id': 'slot-7'},
        context={'service': 'checkout', 'request_id': 'r-77'}, exception=ExceptionInfo('ConnectionError', 'timed out', STACKTRACE),
        caller=CallerInfo('db.py', 9, 'connect', 'orders.db'), trace=TRACE)
    values.update(changes)
    return LogRecord.create(**values)


def plain_record(**changes):
    values = dict(timestamp=datetime(2026, 10, 6, 18, 31, 52, 5000, tzinfo=timezone.utc), severity='INFO', logType='info', level=10.0,
                  logger='orders', message='Order created', processId=1, threadId=2, threadName='main')
    values.update(changes)
    return LogRecord.create(**values)


def attributes_of(logRecord):
    """The attributes of an OTLP log record as a dictionary from the name to the AnyValue."""
    return {item['key']: item['value'] for item in logRecord['attributes']}


def encode_one(record, **settings):
    return OtlpLogEncoder(**settings).encode_record(record)


def value_of(item):
    """Returns the AnyValue of one attribute that holds a single value, from the field of a record."""
    return encode_one(plain_record(fields={'x': item}))['attributes'][3]['value']


SDK_ATTRIBUTES = {'telemetry.sdk.name': 'pysimplelog', 'telemetry.sdk.language': 'python', 'telemetry.sdk.version': __version__}


class TestSeverityMap(unittest.TestCase):

    def test_the_built_in_log_types(self):
        severity = OtlpSeverityMap()
        self.assertEqual([severity.resolve(name) for name in ('debug', 'info', 'warn', 'error', 'critical')], [5, 9, 13, 17, 21])

    def test_the_other_names_of_the_table(self):
        severity = OtlpSeverityMap()
        self.assertEqual([severity.resolve(name) for name in ('trace', 'notice', 'warning', 'super critical', 'alert', 'emergency')],
                         [1, 10, 13, 22, 22, 23])

    def test_the_name_is_compared_in_lower_case_and_without_outer_spaces(self):
        severity = OtlpSeverityMap()
        self.assertEqual((severity.resolve('ERROR'), severity.resolve(' Warn '), severity.resolve('Super Critical')), (17, 13, 22))

    def test_a_name_that_is_not_known_is_info_and_the_level_is_not_guessed(self):
        severity = OtlpSeverityMap()
        for name in ('audit', 'billing', '', 'errors'):
            self.assertEqual(severity.resolve(name), 9)

    def test_overrides_add_and_change(self):
        severity = OtlpSeverityMap({'audit': 12, 'ERROR': 18})
        self.assertEqual((severity.resolve('audit'), severity.resolve('error'), severity.resolve('info')), (12, 18, 9))

    def test_the_table_of_the_class_is_not_changed_by_an_instance(self):
        OtlpSeverityMap({'info': 12})
        self.assertEqual(OtlpSeverityMap().resolve('info'), 9)

    def test_wrong_overrides_are_refused(self):
        for bad in ([('a', 1)], 'a', 5):
            with self.assertRaises(TypeError):
                OtlpSeverityMap(bad)
        for bad in ({1: 5}, {'a': '5'}, {'a': 5.0}, {'a': True}):
            with self.assertRaises(TypeError):
                OtlpSeverityMap(bad)
        for bad in (0, 25, -1):
            with self.assertRaises(ValueError):
                OtlpSeverityMap({'a': bad})

    def test_every_number_of_the_table_is_valid(self):
        self.assertTrue(all(1 <= number <= 24 for number in OtlpSeverityMap.NUMBERS.values()))


class TestValues(unittest.TestCase):

    def test_text(self):
        self.assertEqual(value_of('café ☃ "q" \\ \n'), {'stringValue': 'café ☃ "q" \\ \n'})
        self.assertEqual(value_of(''), {'stringValue': ''})

    def test_a_boolean_is_not_taken_for_an_integer(self):
        self.assertEqual((value_of(True), value_of(False)), ({'boolValue': True}, {'boolValue': False}))

    def test_integers_are_written_as_text(self):
        self.assertEqual((value_of(0), value_of(-5), value_of(2 ** 63 - 1), value_of(-2 ** 63)),
                         ({'intValue': '0'}, {'intValue': '-5'}, {'intValue': '9223372036854775807'},
                          {'intValue': '-9223372036854775808'}))

    def test_an_integer_that_does_not_fit_in_64_bits_becomes_text(self):
        self.assertEqual((value_of(2 ** 63), value_of(-2 ** 63 - 1), value_of(10 ** 40)),
                         ({'stringValue': str(2 ** 63)}, {'stringValue': str(-2 ** 63 - 1)}, {'stringValue': str(10 ** 40)}))

    def test_floats(self):
        self.assertEqual((value_of(1.5), value_of(-0.0), value_of(1e300)), ({'doubleValue': 1.5}, {'doubleValue': -0.0},
                                                                          {'doubleValue': 1e300}))

    def test_floats_that_json_cannot_hold_are_written_as_the_text_proto_json_uses(self):
        self.assertEqual((value_of(float('nan')), value_of(float('inf')), value_of(-float('inf'))),
                         ({'doubleValue': 'NaN'}, {'doubleValue': 'Infinity'}, {'doubleValue': '-Infinity'}))

    def test_bytes_are_base64(self):
        self.assertEqual((value_of(b'ab'), value_of(bytearray(b'\x00\xff')), value_of(b'')),
                         ({'bytesValue': 'YWI='}, {'bytesValue': 'AP8='}, {'bytesValue': ''}))

    def test_lists_and_tuples_are_arrays(self):
        self.assertEqual(value_of([1, 'a', [True]]), {'arrayValue': {'values': [{'intValue': '1'}, {'stringValue': 'a'},
                                                                              {'arrayValue': {'values': [{'boolValue': True}]}}]}})
        self.assertEqual(value_of((1, 2)), {'arrayValue': {'values': [{'intValue': '1'}, {'intValue': '2'}]}})
        self.assertEqual(value_of([]), {'arrayValue': {'values': []}})

    def test_dictionaries_are_key_value_lists_and_a_key_that_is_not_text_becomes_text(self):
        self.assertEqual(value_of({'a': 1, 2: 'b', (1, 2): None}), {'kvlistValue': {'values': [
            {'key': 'a', 'value': {'intValue': '1'}}, {'key': '2', 'value': {'stringValue': 'b'}}, {'key': '(1, 2)', 'value': {}}]}})
        self.assertEqual(value_of({}), {'kvlistValue': {'values': []}})

    def test_none_is_left_out_at_the_top_and_empty_inside(self):
        attributes = attributes_of(encode_one(plain_record(fields={'gone': None, 'kept': 1})))
        self.assertNotIn('gone', attributes)
        self.assertIn('kept', attributes)
        self.assertEqual(value_of([None]), {'arrayValue': {'values': [{}]}})

    def test_any_other_value_is_its_repr(self):
        self.assertEqual(value_of({1, 2}), {'stringValue': '{1, 2}'})
        self.assertEqual(value_of(range(3)), {'stringValue': 'range(0, 3)'})
        self.assertEqual(value_of(1 + 2j), {'stringValue': '(1+2j)'})

    def test_an_object_that_cannot_be_printed_gives_a_placeholder_without_its_error_text(self):
        class Unprintable:
            def __repr__(self):
                raise RuntimeError('secret-in-error-message')
        value = value_of(Unprintable())
        self.assertEqual(value, {'stringValue': '<unprintable Unprintable: RuntimeError>'})

    def test_subclasses_of_the_basic_types(self):
        class Name(str):
            def __str__(self):
                raise RuntimeError('no')

        class Count(int):
            pass

        class Weight(float):
            pass
        self.assertEqual((value_of(Name('x')), value_of(Count(7)), value_of(Weight(2.5))),
                         ({'stringValue': 'x'}, {'intValue': '7'}, {'doubleValue': 2.5}))

    def test_a_structure_that_contains_itself_is_cut(self):
        loop = {}
        loop['again'] = loop
        text = json.dumps(value_of(loop))
        self.assertIn('<too deep>', text)
        self.assertLess(len(text), 20000)
        items = []
        items.append(items)
        self.assertIn('<too deep>', json.dumps(value_of(items)))

    def test_the_nesting_limit_is_exact(self):
        def nested(levels):
            value = 'leaf'
            for _ in range(levels):
                value = [value]
            return json.dumps(value_of(value))
        self.assertNotIn('<too deep>', nested(20))
        self.assertIn('<too deep>', nested(21))

    def test_a_mapping_that_fails_while_it_is_read_becomes_a_placeholder(self):
        from collections.abc import Mapping

        class Broken(Mapping):
            def __getitem__(self, key):
                raise KeyError(key)

            def __iter__(self):
                raise RuntimeError('secret-in-error-message')

            def __len__(self):
                return 1
        text = json.dumps(value_of(Broken()))
        self.assertIn('<unencodable Broken>', text)
        self.assertNotIn('secret', text)

    def test_a_dictionary_that_changes_while_it_is_read(self):
        class Changing(dict):
            def items(self):
                raise RuntimeError('dictionary changed size during iteration')
        self.assertEqual(value_of(Changing(a=1)), {'stringValue': '<unencodable Changing>'})

    def test_a_list_that_fails_while_it_is_read_becomes_a_placeholder(self):
        class Broken(list):
            def __iter__(self):
                raise RuntimeError('no')
        self.assertEqual(value_of(Broken([1])), {'stringValue': '<unencodable Broken>'})

    def test_the_result_is_always_strict_json(self):
        record = plain_record(fields={'a': float('nan'), 'b': [float('inf'), {'c': -float('inf')}], 'd': {1, 2}, 'e': b'x', 'f': object})
        json.loads(OtlpLogEncoder().encode([record]), parse_constant=lambda constant: self.fail(f"not valid JSON: {constant}"))


class TestOneRecord(unittest.TestCase):

    def test_the_fixed_parts(self):
        logRecord = encode_one(full_record())
        self.assertEqual(logRecord['severityNumber'], 17)
        self.assertEqual(logRecord['severityText'], 'ERROR')
        self.assertEqual(logRecord['body'], {'stringValue': 'Database connection failed'})

    def test_the_trace(self):
        logRecord = encode_one(full_record())
        self.assertEqual((logRecord['traceId'], logRecord['spanId'], logRecord['flags']), (TRACE.traceId, TRACE.spanId, 1))
        self.assertEqual(len(logRecord['traceId']), 32)

    def test_without_a_trace_there_are_no_trace_keys(self):
        logRecord = encode_one(plain_record())
        for key in ('traceId', 'spanId', 'flags'):
            self.assertNotIn(key, logRecord)

    def test_trace_flags(self):
        for flags in (0, 1, 255):
            self.assertEqual(encode_one(plain_record(trace=TraceInfo(TRACE.traceId, TRACE.spanId, flags)))['flags'], flags)

    def test_the_process_and_the_thread(self):
        attributes = attributes_of(encode_one(plain_record(processId=4321, threadId=140234, threadName='worker-3')))
        self.assertEqual((attributes['process.pid'], attributes['thread.id'], attributes['thread.name']),
                         ({'intValue': '4321'}, {'intValue': '140234'}, {'stringValue': 'worker-3'}))

    def test_a_thread_identifier_beyond_64_bits_does_not_break_the_record(self):
        attributes = attributes_of(encode_one(plain_record(threadId=2 ** 64 - 1)))
        self.assertEqual(attributes['thread.id'], {'stringValue': str(2 ** 64 - 1)})

    def test_the_caller(self):
        attributes = attributes_of(encode_one(full_record()))
        self.assertEqual((attributes['code.file.path'], attributes['code.function.name'], attributes['code.line.number']),
                         ({'stringValue': 'db.py'}, {'stringValue': 'orders.db.connect'}, {'intValue': '9'}))

    def test_a_caller_without_a_module_gives_the_function_alone(self):
        attributes = attributes_of(encode_one(plain_record(caller=CallerInfo('a.py', 3, 'run', ''))))
        self.assertEqual(attributes['code.function.name'], {'stringValue': 'run'})

    def test_without_a_caller_there_are_no_code_attributes(self):
        self.assertFalse([key for key in attributes_of(encode_one(plain_record())) if key.startswith('code.')])

    def test_the_exception(self):
        attributes = attributes_of(encode_one(full_record()))
        self.assertEqual((attributes['exception.type'], attributes['exception.message'], attributes['exception.stacktrace']),
                         ({'stringValue': 'ConnectionError'}, {'stringValue': 'timed out'}, {'stringValue': STACKTRACE}))

    def test_an_exception_known_only_by_its_text(self):
        attributes = attributes_of(encode_one(plain_record(exception=ExceptionInfo(None, None, 'only the text'))))
        self.assertEqual(attributes['exception.stacktrace'], {'stringValue': 'only the text'})
        self.assertNotIn('exception.type', attributes)
        self.assertNotIn('exception.message', attributes)

    def test_without_an_exception_there_are_no_exception_attributes(self):
        self.assertFalse([key for key in attributes_of(encode_one(plain_record())) if key.startswith('exception.')])

    def test_the_context_and_the_fields_are_attributes(self):
        attributes = attributes_of(encode_one(full_record()))
        self.assertEqual((attributes['service'], attributes['request_id'], attributes['order_id']),
                         ({'stringValue': 'checkout'}, {'stringValue': 'r-77'}, {'intValue': '123'}))

    def test_the_context_comes_before_the_fields(self):
        keys = [item['key'] for item in encode_one(plain_record(fields={'f': 1}, context={'c': 1}))['attributes']]
        self.assertLess(keys.index('c'), keys.index('f'))

    def test_a_field_wins_over_a_context_value_of_the_same_name(self):
        attributes = attributes_of(encode_one(plain_record(fields={'who': 'field'}, context={'who': 'context'})))
        self.assertEqual(attributes['who'], {'stringValue': 'field'})
        keys = [item['key'] for item in encode_one(plain_record(fields={'who': 'field'}, context={'who': 'context'}))['attributes']]
        self.assertEqual(keys.count('who'), 1)

    def test_an_attribute_name_is_never_written_twice(self):
        keys = [item['key'] for item in encode_one(full_record())['attributes']]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_stable_identifier_is_the_record_uid_and_nothing_else(self):
        logRecord = encode_one(full_record())
        attributes = attributes_of(logRecord)
        self.assertEqual(attributes['log.record.uid'], {'stringValue': 'slot-7'})
        self.assertNotIn('event_id', attributes)

    def test_the_identifier_field_can_have_another_name_or_none(self):
        record = plain_record(fields={'eventId': 'abc', 'event_id': 'other'})
        attributes = attributes_of(encode_one(record, eventIdField='eventId'))
        self.assertEqual(attributes['log.record.uid'], {'stringValue': 'abc'})
        self.assertEqual(attributes['event_id'], {'stringValue': 'other'})
        attributes = attributes_of(encode_one(record, eventIdField=None))
        self.assertNotIn('log.record.uid', attributes)
        self.assertIn('eventId', attributes)

    def test_an_identifier_that_is_not_text_becomes_text_and_none_gives_no_attribute(self):
        self.assertEqual(attributes_of(encode_one(plain_record(fields={'event_id': 55})))['log.record.uid'], {'stringValue': '55'})
        attributes = attributes_of(encode_one(plain_record(fields={'event_id': None})))
        self.assertNotIn('log.record.uid', attributes)
        self.assertNotIn('event_id', attributes)

    def test_without_an_identifier_there_is_no_record_uid(self):
        self.assertNotIn('log.record.uid', attributes_of(encode_one(plain_record())))

    def test_the_observed_time_is_written_only_when_given(self):
        self.assertNotIn('observedTimeUnixNano', encode_one(plain_record()))
        self.assertEqual(OtlpLogEncoder().encode_record(plain_record(), OBSERVED)['observedTimeUnixNano'], str(OBSERVED))

    def test_the_observed_time_must_be_an_integer(self):
        for bad in (1.5, '1', True):
            with self.assertRaises(TypeError):
                OtlpLogEncoder().encode_record(plain_record(), bad)

    def test_the_log_type_gives_the_severity_not_the_display_name_or_the_level(self):
        record = plain_record(severity='SOMETHING', logType='warn', level=99.0)
        logRecord = encode_one(record)
        self.assertEqual((logRecord['severityNumber'], logRecord['severityText']), (13, 'SOMETHING'))

    def test_a_custom_log_type_with_an_override(self):
        record = plain_record(severity='AUDIT', logType='audit')
        self.assertEqual(encode_one(record)['severityNumber'], 9)
        self.assertEqual(encode_one(record, severityMap=OtlpSeverityMap({'audit': 11}))['severityNumber'], 11)

    def test_the_keys_of_the_log_record_follow_the_order_of_the_protocol(self):
        keys = list(encode_one(full_record()))
        self.assertEqual(keys, ['timeUnixNano', 'severityNumber', 'severityText', 'body', 'attributes', 'flags', 'traceId', 'spanId'])
        keys = list(OtlpLogEncoder().encode_record(full_record(), OBSERVED))
        self.assertEqual(keys[-1], 'observedTimeUnixNano')

    def test_the_record_is_not_changed(self):
        record = full_record()
        before = (record, dict(record.fields), dict(record.context))
        OtlpLogEncoder().encode([record])
        self.assertEqual((record, dict(record.fields), dict(record.context)), before)

    def test_the_same_record_gives_the_same_text(self):
        record = full_record()
        encoder = OtlpLogEncoder(resource=RESOURCE)
        self.assertEqual(encoder.encode([record], OBSERVED), encoder.encode([record], OBSERVED))


class TestReservedNames(unittest.TestCase):

    def test_every_reserved_name_a_field_uses_is_kept_under_a_prefix(self):
        fields = {name: f'field {name}' for name in RESERVED_ATTRIBUTES}
        attributes = attributes_of(encode_one(full_record(fields=fields), eventIdField=None))
        for name in RESERVED_ATTRIBUTES:
            self.assertEqual(attributes[f'fields.{name}'], {'stringValue': f'field {name}'}, name)

    def test_the_value_the_encoder_writes_is_not_replaced(self):
        attributes = attributes_of(encode_one(full_record(fields={'process.pid': 'mine', 'exception.type': 'mine'}), eventIdField=None))
        self.assertEqual(attributes['process.pid'], {'intValue': '4321'})
        self.assertEqual(attributes['exception.type'], {'stringValue': 'ConnectionError'})

    def test_a_context_value_with_a_reserved_name_is_kept_under_its_own_prefix(self):
        attributes = attributes_of(encode_one(plain_record(context={'thread.name': 'mine'})))
        self.assertEqual(attributes['context.thread.name'], {'stringValue': 'mine'})
        self.assertEqual(attributes['thread.name'], {'stringValue': 'main'})

    def test_the_identifier_field_is_not_a_reserved_name_when_no_record_uid_is_written(self):
        attributes = attributes_of(encode_one(plain_record(fields={'log.record.uid': 'mine'}), eventIdField=None))
        self.assertEqual(attributes['fields.log.record.uid'], {'stringValue': 'mine'})

    def test_a_reserved_name_in_the_context_and_in_the_fields_keeps_both_values(self):
        attributes = attributes_of(encode_one(plain_record(fields={'thread.name': 'from fields'}, context={'thread.name': 'from context'})))
        self.assertEqual(attributes['fields.thread.name'], {'stringValue': 'from fields'})
        self.assertEqual(attributes['context.thread.name'], {'stringValue': 'from context'})
        self.assertEqual(attributes['thread.name'], {'stringValue': 'main'})

    def test_a_name_that_only_looks_like_a_reserved_one_is_kept(self):
        attributes = attributes_of(encode_one(plain_record(fields={'process.pids': 1, 'Process.pid': 2})))
        self.assertIn('process.pids', attributes)
        self.assertIn('Process.pid', attributes)

    def test_a_field_with_a_dotted_name_is_a_plain_attribute(self):
        self.assertIn('http.method', attributes_of(encode_one(plain_record(fields={'http.method': 'GET'}))))


class TestTimes(unittest.TestCase):

    @staticmethod
    def nanoseconds(timestamp):
        """The expected value, from the calendar and not from the encoder's own arithmetic."""
        return calendar.timegm(timestamp.utctimetuple()) * 10 ** 9 + timestamp.microsecond * 1000

    def test_the_time_is_exact_to_the_microsecond(self):
        for microsecond in (0, 1, 999999, 123456):
            timestamp = datetime(2026, 10, 6, 18, 31, 52, microsecond, tzinfo=timezone.utc)
            self.assertEqual(encode_one(plain_record(timestamp=timestamp))['timeUnixNano'], str(self.nanoseconds(timestamp)))

    def test_the_value_is_text(self):
        self.assertIsInstance(encode_one(plain_record())['timeUnixNano'], str)

    def test_one_moment_in_every_time_zone_gives_one_value(self):
        moment = datetime(2026, 10, 6, 18, 31, 52, 123456, tzinfo=timezone.utc)
        values = {encode_one(plain_record(timestamp=moment.astimezone(timezone(timedelta(hours=hours)))))['timeUnixNano']
                  for hours in (-12, -5, 0, 5.5, 14)}
        self.assertEqual(values, {str(self.nanoseconds(moment))})

    def test_a_value_beyond_what_a_float_holds_exactly_is_still_exact(self):
        timestamp = datetime(2026, 10, 6, 18, 31, 52, 1, tzinfo=timezone.utc)
        self.assertTrue(encode_one(plain_record(timestamp=timestamp))['timeUnixNano'].endswith('000001000'))

    def test_a_moment_before_1970_is_brought_to_zero_because_the_field_is_unsigned(self):
        timestamp = datetime(1969, 12, 31, 23, 59, 59, 500000, tzinfo=timezone.utc)
        self.assertEqual(encode_one(plain_record(timestamp=timestamp))['timeUnixNano'], '0')

    def test_the_epoch_itself(self):
        self.assertEqual(encode_one(plain_record(timestamp=datetime(1970, 1, 1, tzinfo=timezone.utc)))['timeUnixNano'], '0')

    def test_a_moment_beyond_the_largest_value_is_brought_to_it(self):
        self.assertEqual(encode_one(plain_record(timestamp=datetime(9999, 1, 1, tzinfo=timezone.utc)))['timeUnixNano'],
                         str(2 ** 64 - 1))


class TestRequest(unittest.TestCase):

    def test_the_shape(self):
        request = OtlpLogEncoder(resource=RESOURCE, scopeVersion='6.0.0').encode_request([plain_record()])
        self.assertEqual(list(request), ['resourceLogs'])
        self.assertEqual(len(request['resourceLogs']), 1)
        resourceLogs = request['resourceLogs'][0]
        self.assertEqual(list(resourceLogs), ['resource', 'scopeLogs'])
        self.assertEqual(resourceLogs['scopeLogs'][0]['scope'], {'name': 'orders', 'version': '6.0.0'})
        self.assertEqual(len(resourceLogs['scopeLogs'][0]['logRecords']), 1)

    def test_the_version_of_the_scope_is_left_out_when_not_given(self):
        scope = OtlpLogEncoder().encode_request([plain_record()])['resourceLogs'][0]['scopeLogs'][0]['scope']
        self.assertEqual(scope, {'name': 'orders'})

    def test_records_are_grouped_by_logger_in_the_order_the_names_first_appear(self):
        records = [plain_record(logger='b', message='1'), plain_record(logger='a', message='2'), plain_record(logger='b', message='3'),
                   plain_record(logger='a', message='4'), plain_record(logger='c', message='5')]
        scopes = OtlpLogEncoder().encode_request(records)['resourceLogs'][0]['scopeLogs']
        self.assertEqual([scope['scope']['name'] for scope in scopes], ['b', 'a', 'c'])
        self.assertEqual([[item['body']['stringValue'] for item in scope['logRecords']] for scope in scopes], [['1', '3'], ['2', '4'], ['5']])

    def test_no_records_give_a_request_with_no_scope(self):
        self.assertEqual(OtlpLogEncoder().encode_request([])['resourceLogs'][0]['scopeLogs'], [])

    def test_the_observed_time_is_the_same_for_the_whole_group(self):
        request = OtlpLogEncoder().encode_request([plain_record(), plain_record(logger='x')], OBSERVED)
        times = {item['observedTimeUnixNano'] for scope in request['resourceLogs'][0]['scopeLogs'] for item in scope['logRecords']}
        self.assertEqual(times, {str(OBSERVED)})

    def test_encode_gives_ascii_json_bytes_without_spaces(self):
        body = OtlpLogEncoder().encode([plain_record(message='café ☃ \U0001F600')])
        self.assertIsInstance(body, bytes)
        body.decode('ascii')
        self.assertNotIn(b': ', body)
        self.assertNotIn(b', ', body)
        self.assertEqual(json.loads(body)['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]['body']['stringValue'],
                         'café ☃ \U0001F600')

    def test_encode_is_the_json_of_encode_request(self):
        encoder, records = OtlpLogEncoder(resource=RESOURCE), [full_record(), plain_record()]
        self.assertEqual(json.loads(encoder.encode(records, OBSERVED)), json.loads(json.dumps(encoder.encode_request(records, OBSERVED))))


class TestResource(unittest.TestCase):

    @staticmethod
    def resource_of(**settings):
        request = OtlpLogEncoder(**settings).encode_request([plain_record()])
        return {item['key']: item['value'] for item in request['resourceLogs'][0]['resource']['attributes']}

    def test_the_sdk_attributes_are_always_there(self):
        resource = self.resource_of()
        self.assertEqual(resource, {key: {'stringValue': value} for key, value in SDK_ATTRIBUTES.items()})

    def test_the_settings_follow_them_in_order(self):
        request = OtlpLogEncoder(resource=RESOURCE).encode_request([plain_record()])
        keys = [item['key'] for item in request['resourceLogs'][0]['resource']['attributes']]
        self.assertEqual(keys, ['telemetry.sdk.name', 'telemetry.sdk.language', 'telemetry.sdk.version', 'service.name',
                                'deployment.environment'])

    def test_a_setting_replaces_a_sdk_attribute_of_the_same_name(self):
        resource = self.resource_of(resource={'telemetry.sdk.language': 'custom'})
        self.assertEqual(resource['telemetry.sdk.language'], {'stringValue': 'custom'})

    def test_values_of_other_types(self):
        resource = self.resource_of(resource={'a': 5, 'b': True, 'c': 1.5, 'd': ['x', 'y'], 'e': None})
        self.assertEqual((resource['a'], resource['b'], resource['c']), ({'intValue': '5'}, {'boolValue': True}, {'doubleValue': 1.5}))
        self.assertEqual(resource['d'], {'arrayValue': {'values': [{'stringValue': 'x'}, {'stringValue': 'y'}]}})
        self.assertNotIn('e', resource)

    def test_the_dictionary_given_is_not_kept(self):
        settings = {'service.name': 'orders'}
        encoder = OtlpLogEncoder(resource=settings)
        settings['service.name'] = 'changed'
        request = encoder.encode_request([plain_record()])
        names = {item['key']: item['value'] for item in request['resourceLogs'][0]['resource']['attributes']}
        self.assertEqual(names['service.name'], {'stringValue': 'orders'})

    def test_the_resource_is_the_same_in_every_request(self):
        encoder = OtlpLogEncoder(resource=RESOURCE)
        first = encoder.encode_request([plain_record()])['resourceLogs'][0]['resource']
        second = encoder.encode_request([plain_record(), plain_record()])['resourceLogs'][0]['resource']
        self.assertEqual(first, second)

    def test_wrong_settings_are_refused(self):
        for settings in ({'resource': [('a', 'b')]}, {'resource': {1: 'a'}}, {'severityMap': {'a': 1}}, {'eventIdField': 5},
                         {'eventIdField': b'x'}, {'scopeVersion': 1}):
            with self.subTest(settings=settings):
                with self.assertRaises(TypeError):
                    OtlpLogEncoder(**settings)
        for settings in ({'resource': {'': 'a'}}, {'eventIdField': ''}):
            with self.subTest(settings=settings):
                with self.assertRaises((ValueError, TypeError)):
                    OtlpLogEncoder(**settings)


class TestGolden(unittest.TestCase):
    """The exact text for reference records: a change of the layout fails here first."""

    def test_the_full_record(self):
        encoder = OtlpLogEncoder(resource=RESOURCE, scopeVersion='6.0.0')
        self.assertEqual(encoder.encode([full_record()], OBSERVED).decode('ascii'), GOLDEN_FULL.replace('__VERSION__', __version__))

    def test_the_plain_record(self):
        self.assertEqual(OtlpLogEncoder().encode([plain_record()]).decode('ascii'), GOLDEN_PLAIN.replace('__VERSION__', __version__))

    def test_two_loggers(self):
        records = [plain_record(logger='b', message='1'), plain_record(logger='a', message='2')]
        self.assertEqual(OtlpLogEncoder().encode(records).decode('ascii'), GOLDEN_TWO.replace('__VERSION__', __version__))


try:
    from google.protobuf import json_format
    from opentelemetry._logs import LogRecord as SdkLogRecord, SeverityNumber
    from opentelemetry.exporter.otlp.proto.common._log_encoder import encode_logs
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    from opentelemetry.sdk._logs import ReadableLogRecord
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope
    HAS_OFFICIAL_ENCODER = True
except ImportError:
    HAS_OFFICIAL_ENCODER = False


@unittest.skipUnless(HAS_OFFICIAL_ENCODER, 'the packages opentelemetry-sdk and opentelemetry-exporter-otlp-proto-common are not installed')
class TestOfficialEncoder(unittest.TestCase):
    """
    The same records are encoded by the official OpenTelemetry encoder, which makes protobuf, and the JSON of this encoder is read by
    the official protobuf parser. If the two messages are equal, the names of the keys, the types, the enums, the integers and the
    layout are what the protocol says. The attributes of each record are written out by hand here and not taken from the encoder.
    """

    @staticmethod
    def _hex_to_base64(node):
        """OTLP/JSON writes the identifiers in hexadecimal and the protobuf parser reads base64, the only difference between them."""
        if isinstance(node, dict):
            return {key: (base64.b64encode(bytes.fromhex(value)).decode('ascii') if key in ('traceId', 'spanId') else
                          TestOfficialEncoder._hex_to_base64(value)) for key, value in node.items()}
        if isinstance(node, list):
            return [TestOfficialEncoder._hex_to_base64(item) for item in node]
        return node

    def parsed(self, encoder, records):
        body = json.loads(encoder.encode(records, OBSERVED))
        return json_format.ParseDict(self._hex_to_base64(body), ExportLogsServiceRequest())

    @staticmethod
    def official(entries, resourceAttributes):
        """Makes the message with the official encoder from ``(record, attributes, scopeVersion)`` entries."""
        resource = Resource(resourceAttributes, '')
        batch = []
        for record, attributes, scopeVersion in entries:
            trace = record.trace
            batch.append(ReadableLogRecord(
                log_record=SdkLogRecord(
                    timestamp=int(calendar.timegm(record.timestamp.utctimetuple())) * 10 ** 9 + record.timestamp.microsecond * 1000,
                    observed_timestamp=OBSERVED, trace_id=None if trace is None else int(trace.traceId, 16),
                    span_id=None if trace is None else int(trace.spanId, 16), trace_flags=None if trace is None else trace.flags,
                    severity_text=record.severity, severity_number=SeverityNumber(OtlpSeverityMap().resolve(record.logType)),
                    body=record.message, attributes=attributes),
                resource=resource, instrumentation_scope=InstrumentationScope(record.logger, scopeVersion)))
        return encode_logs(batch)

    def test_a_plain_record(self):
        record = plain_record(fields={'a': 1})
        attributes = {'process.pid': 1, 'thread.id': 2, 'thread.name': 'main', 'a': 1}
        encoder = OtlpLogEncoder()
        self.assertEqual(self.parsed(encoder, [record]), self.official([(record, attributes, None)], SDK_ATTRIBUTES))

    def test_a_record_with_everything(self):
        record = full_record(fields={'order_id': 123, 'retries': 3, 'event_id': 'slot-7'})
        attributes = {'log.record.uid': 'slot-7', 'process.pid': 4321, 'thread.id': 140234, 'thread.name': 'worker-3',
                      'code.file.path': 'db.py', 'code.function.name': 'orders.db.connect', 'code.line.number': 9,
                      'exception.type': 'ConnectionError', 'exception.message': 'timed out', 'exception.stacktrace': STACKTRACE,
                      'service': 'checkout', 'request_id': 'r-77', 'order_id': 123, 'retries': 3}
        encoder = OtlpLogEncoder(resource=RESOURCE, scopeVersion='6.0.0')
        self.assertEqual(self.parsed(encoder, [record]),
                         self.official([(record, attributes, '6.0.0')], {**SDK_ATTRIBUTES, **RESOURCE}))

    def test_every_type_of_value(self):
        fields = {'i': 7, 'big': -2 ** 63, 'b': True, 'f': 1.5, 's': 'caf\u00e9', 'by': b'ab', 'l': [1, 'a', [2.5]],
                  'd': {'k': 'v', 'n': {'z': False}}, 'empty': [], 'emptyd': {}}
        record = plain_record(fields=fields)
        attributes = {'process.pid': 1, 'thread.id': 2, 'thread.name': 'main', **fields}
        self.assertEqual(self.parsed(OtlpLogEncoder(), [record]), self.official([(record, attributes, None)], SDK_ATTRIBUTES))

    def test_two_loggers_and_several_records(self):
        records = [plain_record(logger='b', message='1'), plain_record(logger='a', message='2'), plain_record(logger='b', message='3')]
        attributes = {'process.pid': 1, 'thread.id': 2, 'thread.name': 'main'}
        encoder = OtlpLogEncoder()
        expected = self.official([(records[0], attributes, None), (records[2], attributes, None), (records[1], attributes, None)],
                                 SDK_ATTRIBUTES)
        self.assertEqual(self.parsed(encoder, records), expected)

    def test_the_severity_numbers_are_the_official_enum(self):
        for logType, number in (('debug', 5), ('info', 9), ('warn', 13), ('error', 17), ('critical', 21)):
            self.assertEqual(SeverityNumber(OtlpSeverityMap().resolve(logType)).value, number)
            message = self.parsed(OtlpLogEncoder(), [plain_record(logType=logType)])
            self.assertEqual(message.resource_logs[0].scope_logs[0].log_records[0].severity_number, number)

    def test_the_values_json_cannot_hold_are_read_by_the_official_parser(self):
        message = self.parsed(OtlpLogEncoder(), [plain_record(fields={'nan': float('nan'), 'inf': float('inf'), 'ninf': -float('inf'),
                                                                      'huge': 2 ** 70, 'none': [None]})])
        values = {item.key: item.value for item in message.resource_logs[0].scope_logs[0].log_records[0].attributes}
        self.assertNotEqual(values['nan'].double_value, values['nan'].double_value)
        self.assertEqual((values['inf'].double_value, values['ninf'].double_value), (float('inf'), -float('inf')))
        self.assertEqual(values['huge'].string_value, str(2 ** 70))
        self.assertEqual(values['none'].array_value.values[0].WhichOneof('value'), None)

    def test_the_trace_identifiers_and_the_time_are_read_back(self):
        message = self.parsed(OtlpLogEncoder(), [full_record()])
        logRecord = message.resource_logs[0].scope_logs[0].log_records[0]
        self.assertEqual(logRecord.trace_id.hex(), TRACE.traceId)
        self.assertEqual(logRecord.span_id.hex(), TRACE.spanId)
        self.assertEqual((logRecord.flags, logRecord.time_unix_nano, logRecord.observed_time_unix_nano), (1, 1791311512123456000, OBSERVED))

    def test_a_key_that_the_protocol_does_not_have_would_be_refused_by_the_parser(self):
        body = json.loads(OtlpLogEncoder().encode([plain_record()]))
        body['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]['notAKey'] = 1
        with self.assertRaises(json_format.ParseError):
            json_format.ParseDict(body, ExportLogsServiceRequest())


GOLDEN_FULL = (
    '{"resourceLogs":[{"resource":{"attributes":[{"key":"telemetry.sdk.name","value":{"stringValue":"pysimplelog"}},{"key":"telemetry.sdk.language","value":{"stringValue":"python"}},{"key":"telemetry.sdk.version","value":{"stringValue":"__VERSION__"}},{"key":"service.name","value":{"stringValue":"orders"}},{"key":"deployment.environment","value":{"stringValue":"production"}}]},"scopeLogs":[{"scope":{"name":"orders","version":"__VERSION__"},"logRecords":[{"timeUnixNano":"1791311512123456000","severityNumber":17,"severityText":"ERROR","body":{"stringValue":"Database connection failed"},"attributes":[{"key":"log.record.uid","value":{"stringValue":"slot-7"}},{"key":"process.pid","value":{"intValue":"4321"}},{"key":"thread.id","value":{"intValue":"140234"}},{"key":"thread.name","value":{"stringValue":"worker-3"}},{"key":"code.file.path","value":{"stringValue":"db.py"}},{"key":"code.function.name","value":{"stringValue":"orders.db.connect"}},{"key":"code.line.number","value":{"intValue":"9"}},{"key":"exception.type","value":{"stringValue":"ConnectionError"}},{"key":"exception.message","value":{"stringValue":"timed out"}},{"key":"exception.stacktrace","value":{"stringValue":"Traceback (most recent call last):\\n  File \\"db.py\\", line 9, in connect\\nConnectionError: timed out"}},{"key":"service","value":{"stringValue":"checkout"}},{"key":"request_id","value":{"stringValue":"r-77"}},{"key":"order_id","value":{"intValue":"123"}},{"key":"retries","value":{"intValue":"3"}},{"key":"ratio","value":{"doubleValue":"NaN"}}],"flags":1,"traceId":"0af7651916cd43dd8448eb211c80319c","spanId":"b7ad6b7169203331","observedTimeUnixNano":"1791311513000000000"}]}]}]}')
GOLDEN_PLAIN = (
    '{"resourceLogs":[{"resource":{"attributes":[{"key":"telemetry.sdk.name","value":{"stringValue":"pysimplelog"}},{"key":"telemetry.sdk.language","value":{"stringValue":"python"}},{"key":"telemetry.sdk.version","value":{"stringValue":"__VERSION__"}}]},"scopeLogs":[{"scope":{"name":"orders"},"logRecords":[{"timeUnixNano":"1791311512005000000","severityNumber":9,"severityText":"INFO","body":{"stringValue":"Order created"},"attributes":[{"key":"process.pid","value":{"intValue":"1"}},{"key":"thread.id","value":{"intValue":"2"}},{"key":"thread.name","value":{"stringValue":"main"}}]}]}]}]}')
GOLDEN_TWO = (
    '{"resourceLogs":[{"resource":{"attributes":[{"key":"telemetry.sdk.name","value":{"stringValue":"pysimplelog"}},{"key":"telemetry.sdk.language","value":{"stringValue":"python"}},{"key":"telemetry.sdk.version","value":{"stringValue":"__VERSION__"}}]},"scopeLogs":[{"scope":{"name":"b"},"logRecords":[{"timeUnixNano":"1791311512005000000","severityNumber":9,"severityText":"INFO","body":{"stringValue":"1"},"attributes":[{"key":"process.pid","value":{"intValue":"1"}},{"key":"thread.id","value":{"intValue":"2"}},{"key":"thread.name","value":{"stringValue":"main"}}]}]},{"scope":{"name":"a"},"logRecords":[{"timeUnixNano":"1791311512005000000","severityNumber":9,"severityText":"INFO","body":{"stringValue":"2"},"attributes":[{"key":"process.pid","value":{"intValue":"1"}},{"key":"thread.id","value":{"intValue":"2"}},{"key":"thread.name","value":{"stringValue":"main"}}]}]}]}]}')


if __name__ == '__main__':
    unittest.main()
