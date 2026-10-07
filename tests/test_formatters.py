"""Tests of the text and template formatters, formatter keywords, and values that cannot be printed.

The JSON layout has its own file, test_json_schema.py.

Run from the repo root::

    python3 -m unittest tests.test_formatters -v
"""
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import (JsonFormatter, TextFormatter, TemplateFormatter, register_formatter, resolve_formatter,  # noqa: E402
                        safe_str, FORMATTERS)
from record import LogRecord, ExceptionInfo, CallerInfo  # noqa: E402
from sinks import StreamSink  # noqa: E402

ZONE = timezone(timedelta(hours=-5))
TRACE = 'Traceback (most recent call last):\n  File "db.py", line 9, in connect\nConnectionError: timed out'


def make_record(**changes):
    values = dict(timestamp=datetime(2026, 10, 6, 13, 31, 52, 123456, tzinfo=ZONE), severity='ERROR', logType='error',
                  level=30.0, logger='orders', message='Database connection failed', processId=4321, threadId=140234,
                  threadName='worker-3')
    values.update(changes)
    return LogRecord.create(**values)


FULL = dict(fields={'order_id': 123, 'retries': 3}, context={'service': 'checkout', 'request_id': 'r-77'},
            exception=ExceptionInfo('ConnectionError', 'timed out', TRACE), caller=CallerInfo('db.py', 9, 'connect', 'orders.db'))


class Unprintable:
    def __repr__(self):
        raise RuntimeError('secret-in-error-message')

    __str__ = __repr__


class TestTextFormatter(unittest.TestCase):

    def test_the_layout_of_a_full_record(self):
        self.assertEqual(TextFormatter()(make_record(**FULL)),
                         '2026-10-06 13:31:52 - orders <ERROR> [db.py:9 in connect] [service=checkout request_id=r-77] '
                         f'Database connection failed order_id=123 retries=3\n{TRACE}')

    def test_the_layout_of_a_bare_record(self):
        self.assertEqual(TextFormatter()(make_record()), '2026-10-06 13:31:52 - orders <ERROR> Database connection failed')

    def test_the_time_is_in_the_zone_of_the_record(self):
        late = make_record(timestamp=datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone.utc))
        self.assertTrue(TextFormatter()(late).startswith('2026-01-01 23:59:59 - '))

    def test_there_is_no_trailing_newline(self):
        self.assertFalse(TextFormatter()(make_record(**FULL)).endswith('\n'))
        self.assertFalse(TextFormatter()(make_record()).endswith('\n'))

    def test_the_data_field_goes_on_its_own_line(self):
        text = TextFormatter()(make_record(fields={'data': {'a': 1}, 'k': 'v'}))
        self.assertEqual(text.split('\n'), ['2026-10-06 13:31:52 - orders <ERROR> Database connection failed k=v', "{'a': 1}"])

    def test_the_traceback_comes_after_the_data(self):
        text = TextFormatter()(make_record(fields={'data': 'D'}, exception=ExceptionInfo('E', 'm', 'TRACE')))
        self.assertTrue(text.endswith('\nD\nTRACE'))

    def test_a_message_with_several_lines_is_kept(self):
        self.assertIn('first\nsecond', TextFormatter()(make_record(message='first\nsecond')))

    def test_non_text_values(self):
        text = TextFormatter()(make_record(fields={'none': None, 'flag': True, 'items': [1, 2], 'pi': 3.5}))
        self.assertTrue(text.endswith('none=None flag=True items=[1, 2] pi=3.5'))

    def test_a_value_that_cannot_be_printed_does_not_lose_the_record(self):
        text = TextFormatter()(make_record(fields={'bad': Unprintable(), 'good': 1}))
        self.assertIn('Database connection failed', text)
        self.assertIn('good=1', text)
        self.assertIn('<unprintable Unprintable: RuntimeError>', text)
        self.assertNotIn('secret-in-error-message', text)

    def test_what_is_not_a_record_is_refused(self):
        for bad in (None, 'text', {}):
            with self.assertRaises(TypeError):
                TextFormatter()(bad)

    def test_unicode_is_kept(self):
        self.assertIn('café ☃', TextFormatter()(make_record(message='café ☃')))


class TestTemplateFormatter(unittest.TestCase):

    def test_every_documented_name(self):
        template = ('{timestamp}|{severity}|{log_type}|{level}|{logger}|{message}|{caller}|{process}|{thread}|{thread_name}'
                    '|{order_id}|{service}')
        self.assertEqual(TemplateFormatter(template)(make_record(**FULL)),
                         '2026-10-06T13:31:52.123-05:00|ERROR|error|30.0|orders|Database connection failed|db.py:9 in connect'
                         '|4321|140234|worker-3|123|checkout')

    def test_exception_fields_and_context_names(self):
        record = make_record(**FULL)
        self.assertEqual(TemplateFormatter('{exception}')(record), TRACE)
        self.assertEqual(TemplateFormatter('{fields}')(record), "{'order_id': 123, 'retries': 3}")
        self.assertEqual(TemplateFormatter('{context}')(record), "{'service': 'checkout', 'request_id': 'r-77'}")

    def test_a_name_the_record_does_not_have_is_empty(self):
        self.assertEqual(TemplateFormatter('[{nothing}][{caller}][{exception}]')(make_record()), '[][][]')

    def test_a_field_never_replaces_a_fixed_name(self):
        record = make_record(fields={'message': 'mine', 'severity': 'mine', 'extra': 'ok'})
        self.assertEqual(TemplateFormatter('{message}/{severity}/{extra}')(record),
                         'Database connection failed/ERROR/ok')

    def test_a_field_wins_over_a_context_value_of_the_same_name(self):
        record = make_record(fields={'who': 'field'}, context={'who': 'context'})
        self.assertEqual(TemplateFormatter('{who}')(record), 'field')

    def test_format_specs_work(self):
        self.assertEqual(TemplateFormatter('{message:>30}|{level:.1f}|{process:06d}')(make_record()),
                         '    Database connection failed|30.0|004321')

    def test_literal_braces(self):
        self.assertEqual(TemplateFormatter('{{{severity}}}')(make_record()), '{ERROR}')

    def test_no_placeholders_is_a_fixed_text(self):
        self.assertEqual(TemplateFormatter('fixed')(make_record()), 'fixed')

    def test_a_template_cannot_reach_inside_a_value(self):
        for template in ('{message.upper}', '{fields[order_id]}', '{message.__class__}', '{0}', '{ message}'):
            with self.subTest(template=template):
                with self.assertRaises(ValueError):
                    TemplateFormatter(template)

    def test_a_template_must_be_a_string(self):
        for bad in (None, 1, b'{message}'):
            with self.assertRaises(TypeError):
                TemplateFormatter(bad)

    def test_a_value_that_cannot_be_formatted_does_not_lose_the_record(self):
        text = TemplateFormatter('{message} {bad} {good}')(make_record(fields={'bad': Unprintable(), 'good': 1}))
        self.assertEqual(text, 'Database connection failed <unprintable Unprintable: RuntimeError> 1')
        self.assertNotIn('secret-in-error-message', text)

    def test_a_format_spec_that_does_not_fit_the_value_gives_the_value_without_it(self):
        self.assertEqual(TemplateFormatter('{message:d}')(make_record()), 'Database connection failed')
        self.assertEqual(TemplateFormatter('{message:%%%}')(make_record()), 'Database connection failed')

    def test_a_bad_spec_on_one_placeholder_leaves_the_others_formatted(self):
        self.assertEqual(TemplateFormatter('{level:.1f} {message:d} {process:06d}')(make_record()),
                         '30.0 Database connection failed 004321')

    def test_a_bad_spec_on_a_value_that_cannot_be_printed_gives_the_placeholder(self):
        text = TemplateFormatter('{bad:d}')(make_record(fields={'bad': Unprintable()}))
        self.assertEqual(text, '<unprintable Unprintable: RuntimeError>')

    def test_what_is_not_a_record_is_refused(self):
        with self.assertRaises(TypeError):
            TemplateFormatter('{message}')('record')


class TestKeywords(unittest.TestCase):

    def test_none_is_json_and_keywords_resolve(self):
        self.assertIsInstance(resolve_formatter(None), JsonFormatter)
        self.assertIsInstance(resolve_formatter('json'), JsonFormatter)
        self.assertIsInstance(resolve_formatter('jsonl'), JsonFormatter)
        self.assertIsInstance(resolve_formatter('text'), TextFormatter)

    def test_a_string_with_braces_is_a_template(self):
        self.assertIsInstance(resolve_formatter('{message}'), TemplateFormatter)

    def test_a_callable_is_used_as_it_is(self):
        def function(record):
            return record.message.upper()
        self.assertIs(resolve_formatter(function), function)

    def test_each_resolve_gives_a_new_formatter(self):
        self.assertIsNot(resolve_formatter('text'), resolve_formatter('text'))

    def test_bad_values(self):
        for bad in ('', 'plain words', 'Text'):
            with self.assertRaises(ValueError):
                resolve_formatter(bad)
        for bad in (3, 1.5, b'text', ['text']):
            with self.assertRaises(TypeError):
                resolve_formatter(bad)

    def test_register_a_keyword(self):
        name = 'test_shout_formatter'
        self.addCleanup(FORMATTERS.pop, name, None)
        register_formatter(name, lambda: (lambda record: record.message.upper()))
        self.assertEqual(resolve_formatter(name)(make_record(message='quiet')), 'QUIET')

    def test_register_validation(self):
        name = 'test_other_formatter'
        self.addCleanup(FORMATTERS.pop, name, None)
        for bad in (1, None):
            with self.assertRaises(TypeError):
                register_formatter(bad, lambda: None)
        for bad in ('', 'has{brace'):
            with self.assertRaises(ValueError):
                register_formatter(bad, lambda: None)
        with self.assertRaises(TypeError):
            register_formatter(name, 'not callable')
        with self.assertRaises(ValueError):
            register_formatter('text', lambda: None)
        register_formatter(name, lambda: None)
        with self.assertRaises(ValueError):
            register_formatter(name, lambda: None)


class TestInASink(unittest.TestCase):

    def _logger(self, formatter):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add_sink('s', StreamSink(stream, formatter=formatter))
        return logger, stream

    def test_each_sink_formats_the_same_record_its_own_way(self):
        logger, first = self._logger('text')
        second = io.StringIO()
        third = io.StringIO()
        logger.add_sink('second', StreamSink(second, formatter='{severity}:{message}'))
        logger.add_sink('third', StreamSink(third, formatter=lambda record: record.message[::-1]))
        logger.info('abc')
        self.assertIn('<INFO> abc', first.getvalue())
        self.assertEqual(second.getvalue().strip(), 'INFO:abc')
        self.assertEqual(third.getvalue().strip(), 'cba')

    def test_the_formatter_of_a_sink_can_change_while_running(self):
        logger, stream = self._logger('{message}')
        logger.info('one')
        logger.set_sink_formatter('s', '{message}!')
        logger.info('two')
        self.assertEqual(stream.getvalue().splitlines(), ['one', 'two!'])

    def test_a_bad_new_formatter_keeps_the_old_one(self):
        logger, stream = self._logger('{message}')
        with self.assertRaises(ValueError):
            logger.set_sink_formatter('s', 'not a keyword')
        logger.info('still')
        self.assertEqual(stream.getvalue().strip(), 'still')

    def test_a_template_with_a_spec_that_does_not_fit_still_writes_the_record(self):
        logger, stream = self._logger('{message:d}|{severity}')
        logger.info('x')
        self.assertEqual(stream.getvalue().strip(), 'x|INFO')

    def test_a_formatter_that_raises_does_not_break_the_logger(self):
        import contextlib
        logger, stream = self._logger(lambda record: 1 / 0)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
        other = io.StringIO()
        logger.add_sink('ok', StreamSink(other, formatter='{message}'))
        logger.info('y')
        self.assertEqual(other.getvalue().strip(), 'y')


class TestSafeStr(unittest.TestCase):

    def test_normal_values(self):
        self.assertEqual((safe_str(1), safe_str('a'), safe_str(None), safe_str([1])), ('1', 'a', 'None', '[1]'))

    def test_an_unprintable_value_gives_a_placeholder_without_its_error_text(self):
        self.assertEqual(safe_str(Unprintable()), '<unprintable Unprintable: RuntimeError>')


if __name__ == '__main__':
    unittest.main()
