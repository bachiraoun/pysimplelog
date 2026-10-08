"""The JSON layout is a contract: these tests fix it, line by line, and keep the documentation equal to it.

Run from the repo root::

    python3 -m unittest tests.test_json_schema -v

A log shipper or a parser written against the layout must not break when the library changes. So the exact text for reference
records is written in this file, and a change to the layout fails here first. The page of the documentation that shows the layout is
checked against the same text. A change that is wanted is made here, in the documentation, and in the schema number, together.
"""
import io
import json
import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formatters import JsonFormatter, resolve_formatter  # noqa: E402
from record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo  # noqa: E402
from simple_log import Logger  # noqa: E402
from sinks import StreamSink  # noqa: E402

DOCUMENTATION = os.path.join(os.path.dirname(__file__), '..', 'docs', 'source', 'getting_started.rst')

NESTED = ('{"schema":1,"timestamp":"2026-10-06T13:31:52.123-05:00","severity":"ERROR","log_type":"error","level":30.0,'
          '"logger":"orders","message":"Database connection failed","exception":{"type":"ConnectionError","message":"timed out",'
          '"stacktrace":"Traceback (most recent call last):\\n  File \\"db.py\\", line 9, in connect\\nConnectionError: timed out"},'
          '"caller":{"file":"db.py","line":9,"function":"connect","module":"orders.db"},"process":{"id":4321},'
          '"thread":{"id":140234,"name":"worker-3"},"context":{"service":"checkout","request_id":"r-77"},'
          '"fields":{"order_id":123,"retries":3,"ratio":"NaN"}}')
FLAT = ('{"schema":1,"timestamp":"2026-10-06T13:31:52.123-05:00","severity":"ERROR","log_type":"error","level":30.0,'
        '"logger":"orders","message":"Database connection failed","exception":{"type":"ConnectionError","message":"timed out",'
        '"stacktrace":"Traceback (most recent call last):\\n  File \\"db.py\\", line 9, in connect\\nConnectionError: timed out"},'
        '"caller":{"file":"db.py","line":9,"function":"connect","module":"orders.db"},"process":{"id":4321},'
        '"thread":{"id":140234,"name":"worker-3"},"service":"checkout","request_id":"r-77","order_id":123,"retries":3,"ratio":"NaN"}')
UTC = NESTED.replace('2026-10-06T13:31:52.123-05:00', '2026-10-06T18:31:52.123Z')
MINIMAL = ('{"schema":1,"timestamp":"2026-10-06T18:31:52.005Z","severity":"INFO","log_type":"info","level":10.0,"logger":"orders",'
           '"message":"Order created","process":{"id":1},"thread":{"id":2,"name":"main"}}')


def reference_record():
    """The record every reference line above was made from: every part of a record is in it."""
    return LogRecord.create(
        timestamp=datetime(2026, 10, 6, 13, 31, 52, 123456, tzinfo=timezone(timedelta(hours=-5))), severity='ERROR',
        logType='error', level=30.0, logger='orders', message='Database connection failed', processId=4321, threadId=140234,
        threadName='worker-3', fields={'order_id': 123, 'retries': 3, 'ratio': float('nan')},
        context={'service': 'checkout', 'request_id': 'r-77'},
        exception=ExceptionInfo('ConnectionError', 'timed out',
                                'Traceback (most recent call last):\n  File "db.py", line 9, in connect\nConnectionError: timed out'),
        caller=CallerInfo('db.py', 9, 'connect', 'orders.db'))


def minimal_record():
    return LogRecord.create(datetime(2026, 10, 6, 18, 31, 52, 5000, tzinfo=timezone.utc), 'INFO', 'info', 10.0, 'orders',
                            'Order created', 1, 2, 'main')


def strict_loads(text):
    """Parses JSON the way a strict parser does: NaN and Infinity are refused, as Elasticsearch, Go and browsers refuse them."""
    def refuse(constant):
        raise ValueError(f"not valid JSON: {constant}")
    return json.loads(text, parse_constant=refuse)


class TestTheLayoutIsFixed(unittest.TestCase):

    def test_the_nested_layout(self):
        self.assertEqual(JsonFormatter()(reference_record()), NESTED)

    def test_the_flat_layout(self):
        self.assertEqual(JsonFormatter(flatten=True)(reference_record()), FLAT)

    def test_a_record_with_nothing_optional_has_only_the_keys_that_are_always_there(self):
        self.assertEqual(JsonFormatter()(minimal_record()), MINIMAL)

    def test_the_keys_come_in_this_order(self):
        self.assertEqual(list(strict_loads(NESTED)), ['schema', 'timestamp', 'severity', 'log_type', 'level', 'logger', 'message',
                                                      'exception', 'caller', 'process', 'thread', 'context', 'fields'])

    def test_the_schema_number_is_one(self):
        self.assertEqual(strict_loads(JsonFormatter()(minimal_record()))['schema'], 1)

    def test_a_trace_changes_nothing_in_any_layout(self):
        # Trace identifiers are for the sinks that send to a tracing backend. Schema 1 does not write them
        traced = reference_record()._replace(trace=TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1))
        self.assertEqual(JsonFormatter()(traced), NESTED)
        self.assertEqual(JsonFormatter(flatten=True)(traced), FLAT)
        self.assertEqual(JsonFormatter(utc=True)(traced), UTC)
        self.assertEqual(JsonFormatter()(minimal_record()._replace(trace=TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1))), MINIMAL)

    def test_the_keywords_give_the_same_layout(self):
        for keyword in ('json', 'jsonl'):
            self.assertEqual(resolve_formatter(keyword)(reference_record()), NESTED)

    def test_a_line_is_one_line(self):
        self.assertNotIn('\n', JsonFormatter()(reference_record()))
        self.assertNotIn('\n', JsonFormatter()(minimal_record()._replace(message='two\nlines')))

    def test_a_name_that_is_a_key_does_not_replace_the_key_when_flat(self):
        record = minimal_record()._replace(fields={'message': 'mine', 'logger': 'other'}, context={'schema': 7})
        flat = strict_loads(JsonFormatter(flatten=True)(record))
        self.assertEqual((flat['message'], flat['logger'], flat['schema']), ('Order created', 'orders', 1))
        self.assertEqual((flat['fields.message'], flat['fields.logger'], flat['context.schema']), ('mine', 'other', 7))

    def test_a_field_wins_over_a_context_value_of_the_same_name_when_flat(self):
        record = minimal_record()._replace(fields={'who': 'field'}, context={'who': 'context'})
        self.assertEqual(strict_loads(JsonFormatter(flatten=True)(record))['who'], 'field')


class TestTimestamps(unittest.TestCase):

    def test_by_default_the_offset_of_the_time_zone_is_written(self):
        self.assertIn('"timestamp":"2026-10-06T13:31:52.123-05:00"', JsonFormatter()(reference_record()))

    def test_utc_converts_the_instant_and_writes_a_z(self):
        self.assertEqual(JsonFormatter(utc=True)(reference_record()), UTC)

    def test_utc_keeps_the_instant(self):
        local = strict_loads(JsonFormatter()(reference_record()))['timestamp']
        converted = strict_loads(JsonFormatter(utc=True)(reference_record()))['timestamp']
        self.assertEqual(datetime.fromisoformat(local.replace('Z', '+00:00')),
                         datetime.fromisoformat(converted.replace('Z', '+00:00')))

    def test_utc_works_for_a_record_that_is_in_utc_already_and_for_the_flat_layout(self):
        self.assertEqual(JsonFormatter(utc=True)(minimal_record()), MINIMAL)
        self.assertIn('"timestamp":"2026-10-06T18:31:52.123Z"', JsonFormatter(flatten=True, utc=True)(reference_record()))

    def test_utc_must_be_a_boolean(self):
        for bad in (1, 'yes', None):
            with self.assertRaises(TypeError):
                JsonFormatter(utc=bad)

    def test_every_second_of_a_minute_and_both_signs_of_the_offset(self):
        for hours in (-12, -5, 0, 5.5, 14):
            zone = timezone(timedelta(hours=hours))
            for second in (0, 1, 59):
                record = minimal_record()._replace(timestamp=datetime(2026, 12, 31, 23, 59, second, 999000, tzinfo=zone))
                written = strict_loads(JsonFormatter(utc=True)(record))['timestamp']
                self.assertEqual(datetime.fromisoformat(written.replace('Z', '+00:00')), record.timestamp)


class TestValuesAreAlwaysValidJson(unittest.TestCase):

    def _line(self, **fields):
        return JsonFormatter()(minimal_record()._replace(fields=fields))

    def test_not_a_number_and_infinity_are_written_as_text(self):
        line = self._line(a=float('nan'), b=float('inf'), c=-float('inf'), d=1.5, e=0.0, f=-0.0)
        parsed = strict_loads(line)['fields']
        self.assertEqual(parsed, {'a': 'NaN', 'b': 'Infinity', 'c': '-Infinity', 'd': 1.5, 'e': 0.0, 'f': -0.0})

    def test_they_are_written_as_text_deep_inside_a_structure_too(self):
        parsed = strict_loads(self._line(data={'rows': [[1.0, float('nan')], (float('inf'),)], 'nested': {'x': -float('inf')}}))
        self.assertEqual(parsed['fields']['data'], {'rows': [[1.0, 'NaN'], ['Infinity']], 'nested': {'x': '-Infinity'}})

    def test_a_level_that_is_not_finite_is_written_as_text_too(self):
        record = minimal_record()._replace(level=float('inf'))
        self.assertEqual(strict_loads(JsonFormatter()(record))['level'], 'Infinity')
        self.assertEqual(strict_loads(JsonFormatter(flatten=True)(record))['level'], 'Infinity')

    def test_the_flat_layout_is_valid_too(self):
        record = minimal_record()._replace(fields={'a': float('nan')}, context={'b': float('inf')})
        parsed = strict_loads(JsonFormatter(flatten=True)(record))
        self.assertEqual((parsed['a'], parsed['b']), ('NaN', 'Infinity'))

    def test_every_other_value_gives_a_line_a_strict_parser_accepts(self):
        class Plain:
            pass

        class Unprintable:
            def __repr__(self):
                raise RuntimeError('secret-in-error-message')

        cycle = {}
        cycle['self'] = cycle
        values = dict(text='café ☃ "quoted" \\ \t', zero=0, big=10 ** 40, none=None, yes=True, raw=b'bytes', items={1, 2},
                      pair=(1, 2), tuple_key={(1, 2): 3}, object_key={Plain(): 1}, cycle=cycle, plain=Plain(), bad=Unprintable(),
                      deep=[[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]])
        line = self._line(**values)
        parsed = strict_loads(line)['fields']
        self.assertEqual(parsed['text'], values['text'])
        self.assertEqual(parsed['big'], 10 ** 40)
        self.assertEqual(parsed['tuple_key'], {'(1, 2)': 3})
        self.assertIn('<too deep>', json.dumps(parsed['cycle']))
        self.assertEqual(parsed['bad'], '<unprintable Unprintable: RuntimeError>')
        self.assertNotIn('secret-in-error-message', line)

    def test_the_result_is_ascii_so_any_transport_carries_it(self):
        line = self._line(text='é☃\U0001F600')
        line.encode('ascii')
        self.assertEqual(strict_loads(line)['fields']['text'], 'é☃\U0001F600')

    def test_a_logger_writing_json_to_a_stream_stays_valid_with_not_a_number_in_a_field(self):
        stream = io.StringIO()
        logger = Logger('orders', logToFile=False, logToStdout=False)
        logger.add_sink('s', StreamSink(stream, formatter=None))
        logger.info('error of the fit', error=float('nan'), values=[1.0, float('inf')])
        parsed = strict_loads(stream.getvalue().strip())
        self.assertEqual((parsed['fields']['error'], parsed['fields']['values']), ('NaN', [1.0, 'Infinity']))
        self.assertTrue(math.isnan(float(parsed['fields']['error'])))


@unittest.skipUnless(os.path.isfile(DOCUMENTATION), 'the documentation is not installed')
class TestTheDocumentationShowsTheSameText(unittest.TestCase):

    def test_the_page_contains_the_lines_the_formatter_writes(self):
        with open(DOCUMENTATION, encoding='utf-8') as stream:
            text = stream.read()
        for name, expected in (('nested', NESTED), ('flat', FLAT), ('utc', UTC)):
            with self.subTest(layout=name):
                self.assertIn(expected, text, 'the documentation of the JSON layout is not what the formatter writes')

    def test_every_key_of_the_layout_is_described_on_the_page(self):
        with open(DOCUMENTATION, encoding='utf-8') as stream:
            text = stream.read()
        for key in strict_loads(NESTED):
            self.assertIn(f'``{key}``', text, key)


if __name__ == '__main__':
    unittest.main()
