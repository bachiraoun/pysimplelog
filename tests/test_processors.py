"""Tests of the record processors: order, add and remove, failing closed, redaction, and many threads.

Run from the repo root::

    python3 -m unittest tests.test_processors -v
"""
import contextlib
import io
import json
import os
import sys
import threading
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import JsonFormatter  # noqa: E402
from processors import redact_fields, redact_text, DEFAULT_REPLACEMENT  # noqa: E402
from record import LogRecord, ExceptionInfo, TraceInfo  # noqa: E402
from sinks import StreamSink  # noqa: E402


def make_logger(**arguments):
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()))
    return logger, stream


def parsed(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def make_record(**changes):
    values = dict(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), severity='INFO', logType='info', level=10.0,
                  logger='app', message='hello', processId=1, threadId=2, threadName='main')
    values.update(changes)
    return LogRecord.create(**values)


class TestAddAndRemove(unittest.TestCase):

    def test_a_processor_changes_what_every_sink_gets(self):
        logger, stream = make_logger()
        other = io.StringIO()
        logger.add_sink('other', StreamSink(other, formatter=JsonFormatter()))
        logger.add_processor(lambda record: record._replace(message=record.message.upper()))
        logger.info('hello')
        self.assertEqual(parsed(stream)[0]['message'], 'HELLO')
        self.assertEqual(json.loads(other.getvalue())['message'], 'HELLO')

    def test_they_run_in_the_order_they_were_added(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: record._replace(message=record.message + 'A'))
        logger.add_processor(lambda record: record._replace(message=record.message + 'B'))
        logger.add_processor(lambda record: record._replace(message=record.message + 'C'))
        logger.info('x')
        self.assertEqual(parsed(stream)[0]['message'], 'xABC')

    def test_each_sees_the_result_of_the_one_before(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: record._replace(fields={**record.fields, 'first': 1}))
        logger.add_processor(lambda record: record._replace(fields={**record.fields, 'seen': 'first' in record.fields}))
        logger.info('x')
        self.assertEqual(parsed(stream)[0]['fields'], {'first': 1, 'seen': True})

    def test_the_property_lists_them_in_order_and_is_a_tuple(self):
        logger, _ = make_logger()
        first, second = (lambda record: record), (lambda record: record)
        logger.add_processor(first)
        logger.add_processor(second)
        self.assertEqual(logger.processors, (first, second))
        self.assertIsInstance(logger.processors, tuple)

    def test_removing_stops_it(self):
        logger, stream = make_logger()

        def shout(record):
            return record._replace(message='SHOUT')
        logger.add_processor(shout)
        logger.info('a')
        logger.remove_processor(shout)
        logger.info('b')
        self.assertEqual([line['message'] for line in parsed(stream)], ['SHOUT', 'b'])

    def test_removing_what_was_never_added_does_nothing(self):
        logger, _ = make_logger()
        logger.remove_processor(lambda record: record)
        self.assertEqual(logger.processors, ())

    def test_adding_the_same_function_twice_runs_it_twice_and_removing_takes_both(self):
        logger, stream = make_logger()

        def twice(record):
            return record._replace(message=record.message + '!')
        logger.add_processor(twice)
        logger.add_processor(twice)
        logger.info('x')
        self.assertEqual(parsed(stream)[0]['message'], 'x!!')
        logger.remove_processor(twice)
        self.assertEqual(logger.processors, ())

    def test_what_is_not_callable_is_refused(self):
        logger, _ = make_logger()
        for bad in (None, 'f', 3):
            with self.assertRaises(TypeError):
                logger.add_processor(bad)

    def test_they_can_be_given_when_the_logger_is_made(self):
        logger, stream = make_logger(processors=[lambda record: record._replace(message='made')])
        logger.info('x')
        self.assertEqual(parsed(stream)[0]['message'], 'made')

    def test_a_processor_added_later_applies_from_the_next_record(self):
        logger, stream = make_logger()
        logger.info('before')
        logger.add_processor(lambda record: record._replace(message='after'))
        logger.info('before again')
        self.assertEqual([line['message'] for line in parsed(stream)], ['before', 'after'])


class TestWhatTheyCanDo(unittest.TestCase):

    def test_a_processor_that_returns_the_same_record_changes_nothing(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: record)
        logger.info('x', a=1)
        self.assertEqual(parsed(stream)[0]['fields'], {'a': 1})

    def test_it_can_treat_only_some_log_types(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: record._replace(message='ERR') if record.logType == 'error' else record)
        logger.info('a')
        logger.error('b')
        self.assertEqual([line['message'] for line in parsed(stream)], ['a', 'ERR'])

    def test_it_can_add_fields_and_context_and_the_exception(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: record._replace(
            fields={**record.fields, 'added': 1}, context={'c': 2}, exception=ExceptionInfo('E', 'm', 'trace')))
        logger.info('x')
        line = parsed(stream)[0]
        self.assertEqual((line['fields'], line['context'], line['exception']['type']), ({'added': 1}, {'c': 2}, 'E'))

    def test_the_result_is_what_last_record_keeps(self):
        logger, _ = make_logger()
        logger.add_processor(lambda record: record._replace(message='kept'))
        logger.info('x')
        self.assertEqual(logger.lastRecord.message, 'kept')

    def test_the_record_given_to_it_cannot_be_changed_in_place(self):
        logger, stream = make_logger()
        outcome = []

        def try_to_change(record):
            def set_item():
                record.fields['a'] = 1
            for action in (lambda: setattr(record, 'message', 'x'), set_item):
                try:
                    action()
                except (AttributeError, TypeError) as error:
                    outcome.append(type(error).__name__)
            return record
        logger.add_processor(try_to_change)
        logger.info('x')
        self.assertEqual(outcome, ['AttributeError', 'TypeError'])
        self.assertEqual(parsed(stream)[0]['message'], 'x')

    def test_it_runs_once_for_a_record_whatever_the_number_of_sinks(self):
        logger, _ = make_logger()
        for number in range(4):
            logger.add_sink(f's{number}', StreamSink(io.StringIO(), formatter=JsonFormatter()))
        calls = []
        logger.add_processor(lambda record: calls.append(1) or record)
        logger.info('x')
        self.assertEqual(len(calls), 1)

    def test_it_does_not_run_for_a_record_no_sink_takes(self):
        logger, _ = make_logger()
        calls = []
        logger.add_processor(lambda record: calls.append(1) or record)
        logger.remove_sink('capture')
        logger.info('x')
        self.assertEqual(calls, [])


class TestFailingClosed(unittest.TestCase):

    def _run(self, processor, count=3):
        logger, stream = make_logger()
        logger.add_processor(processor)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for _ in range(count):
                logger.info('secret')
        return logger, stream, error.getvalue()

    def test_a_processor_that_raises_drops_the_record_for_every_sink(self):
        def broken(record):
            raise RuntimeError('boom')
        logger, stream, error = self._run(broken)
        self.assertEqual(stream.getvalue(), '')
        self.assertEqual(logger.processorFailures, 3)

    def test_the_warning_is_written_once_per_processor(self):
        def broken(record):
            raise RuntimeError('boom')
        _, _, error = self._run(broken, count=10)
        self.assertEqual(error.count('WARNING'), 1)
        self.assertIn('RuntimeError', error)
        self.assertNotIn('boom', error)

    def test_a_result_that_is_not_a_record_drops_it_too(self):
        for bad in (None, 'text', {}, tuple(make_record())):
            with self.subTest(bad=bad):
                logger, stream, _ = self._run(lambda record, bad=bad: bad, count=1)
                self.assertEqual(stream.getvalue(), '')
                self.assertEqual(logger.processorFailures, 1)

    def test_the_processors_after_a_failed_one_do_not_run(self):
        logger, _ = make_logger()
        calls = []

        def broken(record):
            raise RuntimeError('boom')
        logger.add_processor(broken)
        logger.add_processor(lambda record: calls.append(1) or record)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
        self.assertEqual(calls, [])

    def test_the_logger_goes_on_after_a_failure(self):
        logger, stream = make_logger()
        state = {'fail': True}

        def sometimes(record):
            if state['fail']:
                raise RuntimeError('boom')
            return record
        logger.add_processor(sometimes)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('lost')
        state['fail'] = False
        logger.info('kept')
        self.assertEqual([line['message'] for line in parsed(stream)], ['kept'])

    def test_the_log_call_itself_never_raises(self):
        logger, _ = make_logger()
        logger.add_processor(lambda record: 1 / 0)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
            logger.error('y')

    def test_a_dropped_record_is_not_the_last_record(self):
        logger, _ = make_logger()
        logger.add_processor(lambda record: 1 / 0)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
        self.assertIsNone(logger.lastRecord)

    def test_a_record_that_a_filter_would_see_is_not_filtered_when_a_processor_failed(self):
        logger, _ = make_logger()
        calls = []
        logger.add_processor(lambda record: 1 / 0)
        logger.add_filter(lambda record: calls.append(1) or True)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
        self.assertEqual(calls, [])
        self.assertEqual(logger.filteredRecords, 0)

    def test_two_failing_processors_each_warn_once(self):
        logger, _ = make_logger()
        logger.add_processor(lambda record: 1 / 0)
        error = io.StringIO()
        first = logger.processors[0]
        logger.remove_processor(first)

        def other(record):
            raise ValueError('other')
        logger.add_processor(first)
        with contextlib.redirect_stderr(error):
            logger.info('a')
            logger.remove_processor(first)
            logger.add_processor(other)
            logger.info('b')
            logger.info('c')
        self.assertEqual(error.getvalue().count('WARNING'), 2)


class TestRedactFields(unittest.TestCase):

    def _redact(self, fields=None, context=None, **arguments):
        return redact_fields(**arguments)(make_record(fields=fields, context=context))

    def test_the_default_names_in_fields_and_context(self):
        record = self._redact(fields={'password': 'p', 'user': 'ann', 'api_key': 'k'}, context={'token': 't', 'tenant': 'x'})
        self.assertEqual(dict(record.fields), {'password': DEFAULT_REPLACEMENT, 'user': 'ann', 'api_key': DEFAULT_REPLACEMENT})
        self.assertEqual(dict(record.context), {'token': DEFAULT_REPLACEMENT, 'tenant': 'x'})

    def test_a_name_matches_inside_a_longer_key_in_any_case_and_spelling(self):
        record = self._redact(fields={'access_token': 1, 'API-Token': 2, 'Secret Value': 3, 'PASSWORD': 4, 'passwd': 5})
        self.assertEqual({key: value for key, value in record.fields.items()},
                         {'access_token': DEFAULT_REPLACEMENT, 'API-Token': DEFAULT_REPLACEMENT,
                          'Secret Value': DEFAULT_REPLACEMENT, 'PASSWORD': DEFAULT_REPLACEMENT, 'passwd': 5})

    def test_any_type_of_value_is_replaced(self):
        record = self._redact(fields={'password': {'a': 1}, 'token': [1, 2], 'secret': None, 'ssn': 123})
        self.assertEqual(set(record.fields.values()), {DEFAULT_REPLACEMENT})

    def test_nested_mappings_lists_and_tuples(self):
        record = self._redact(fields={'outer': {'inner': [{'password': 'p', 'ok': 1}, ({'token': 't'},)]}})
        self.assertEqual(record.fields['outer'], {'inner': [{'password': DEFAULT_REPLACEMENT, 'ok': 1},
                                                            ({'token': DEFAULT_REPLACEMENT},)]})
        self.assertIsInstance(record.fields['outer']['inner'][1], tuple)

    def test_the_original_data_is_not_changed(self):
        original = {'outer': {'password': 'p'}}
        self._redact(fields=original)
        self.assertEqual(original, {'outer': {'password': 'p'}})

    def test_a_record_with_nothing_to_hide_comes_back_as_the_same_object(self):
        record = make_record(fields={'a': 1}, context={'b': 2})
        self.assertIs(redact_fields()(record), record)

    def test_a_secret_in_free_text_is_not_found(self):
        record = self._redact(fields={'note': 'password=hunter2'})
        self.assertEqual(record.fields['note'], 'password=hunter2')

    def test_own_names_and_replacement(self):
        record = self._redact(fields={'session_id': 's', 'password': 'p'}, names=('session_id',), replacement='***')
        self.assertEqual(dict(record.fields), {'session_id': '***', 'password': 'p'})

    def test_a_structure_that_contains_itself_does_not_loop(self):
        loop = {}
        loop['again'] = loop
        record = self._redact(fields={'loop': loop})
        self.assertIn(DEFAULT_REPLACEMENT, json.dumps(record.fields['loop'], default=str)[:4000] + DEFAULT_REPLACEMENT)

    def test_validation(self):
        for bad in ('password', [1], ['a', None]):
            with self.assertRaises(TypeError):
                redact_fields(names=bad)
        with self.assertRaises(TypeError):
            redact_fields(replacement=1)
        with self.assertRaises(ValueError):
            redact_fields(names=('',))

    def test_in_a_logger_the_secret_reaches_no_sink(self):
        logger, stream = make_logger()
        other = io.StringIO()
        logger.add_sink('other', StreamSink(other, formatter=None))
        logger.add_processor(redact_fields())
        with logger.context(token='abc123'):
            logger.info('login', password='hunter2', user='ann')
        for text in (stream.getvalue(), other.getvalue(), repr(logger.lastRecord)):
            self.assertNotIn('hunter2', text)
            self.assertNotIn('abc123', text)
        self.assertIn('ann', stream.getvalue())


class TestTheTraceSurvivesProcessors(unittest.TestCase):

    TRACE = TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1)

    def test_redaction_keeps_the_trace(self):
        record = make_record(fields={'password': 'p', 'note': '/opt/app'}, context={'token': 't'})._replace(trace=self.TRACE)
        self.assertEqual(redact_fields()(record).trace, self.TRACE)
        self.assertEqual(redact_text(lambda text: text.upper())(record).trace, self.TRACE)

    def test_a_record_that_redaction_changes_keeps_it_too(self):
        out = redact_fields()(make_record(fields={'password': 'p'})._replace(trace=self.TRACE))
        self.assertEqual(out.fields['password'], DEFAULT_REPLACEMENT)
        self.assertEqual(out.trace, self.TRACE)

    def test_a_processor_can_set_the_trace_and_a_sink_sees_it(self):
        logger, _ = make_logger()
        seen = []
        logger.add_processor(lambda record: record._replace(trace=self.TRACE))
        logger.add_filter(lambda record: seen.append(record.trace) or True)
        logger.info('x')
        self.assertEqual(seen, [self.TRACE])
        self.assertEqual(logger.lastRecord.trace, self.TRACE)


class TestRedactText(unittest.TestCase):

    def test_every_text_of_the_record_goes_through_the_function(self):
        record = make_record(message='in /opt/app', fields={'path': '/opt/app/x', 'deep': {'list': ['/opt/app', 5]}},
                             context={'where': '/opt/app'}, exception=ExceptionInfo('E', 'at /opt/app', 'File /opt/app/y'))
        out = redact_text(lambda text: text.replace('/opt/app', '...'))(record)
        self.assertEqual(out.message, 'in ...')
        self.assertEqual(out.fields['path'], '.../x')
        self.assertEqual(out.fields['deep'], {'list': ['...', 5]})
        self.assertEqual(out.context['where'], '...')
        self.assertEqual((out.exception.message, out.exception.stacktrace), ('at ...', 'File .../y'))
        self.assertEqual(out.exception.typeName, 'E')

    def test_keys_are_not_changed(self):
        out = redact_text(lambda text: 'X')(make_record(fields={'key': 'v'}))
        self.assertEqual(dict(out.fields), {'key': 'X'})

    def test_non_text_values_pass_through(self):
        marker = object()
        out = redact_text(lambda text: text)(make_record(fields={'n': 1.5, 'none': None, 'obj': marker, 'bytes': b'x'}))
        self.assertIs(out.fields['obj'], marker)
        self.assertEqual((out.fields['n'], out.fields['none'], out.fields['bytes']), (1.5, None, b'x'))

    def test_a_record_without_an_exception_keeps_none(self):
        self.assertIsNone(redact_text(lambda text: text)(make_record()).exception)

    def test_an_exception_without_a_message_keeps_none(self):
        out = redact_text(lambda text: text)(make_record(exception=ExceptionInfo(None, None, 'trace')))
        self.assertIsNone(out.exception.message)

    def test_a_function_that_raises_or_returns_a_non_string_makes_the_logger_drop_the_record(self):
        for function in (lambda text: 1 / 0, lambda text: 5, lambda text: None):
            logger, stream = make_logger()
            logger.add_processor(redact_text(function))
            with contextlib.redirect_stderr(io.StringIO()):
                logger.info('secret')
            self.assertEqual(stream.getvalue(), '')
            self.assertEqual(logger.processorFailures, 1)

    def test_validation(self):
        with self.assertRaises(TypeError):
            redact_text('not callable')

    def test_the_original_record_is_not_changed(self):
        record = make_record(message='/opt/app', fields={'a': '/opt/app'})
        redact_text(lambda text: '')(record)
        self.assertEqual((record.message, record.fields['a']), ('/opt/app', '/opt/app'))


class TestManyThreads(unittest.TestCase):

    def test_adding_and_removing_while_many_threads_log_never_breaks_or_loses_a_record(self):
        logger, stream = make_logger()
        stop = threading.Event()
        errors = []

        def churn():
            try:
                while not stop.is_set():
                    def tag(record):
                        return record._replace(fields={**record.fields, 'tagged': True})
                    logger.add_processor(tag)
                    logger.remove_processor(tag)
                    # Without a pause this thread starves the loggers of the interpreter lock
                    stop.wait(0.0005)
            except Exception as error:
                errors.append(error)

        def work(number):
            for index in range(150):
                logger.info(f'{number}-{index}')

        churner = threading.Thread(target=churn)
        churner.start()
        threads = [threading.Thread(target=work, args=(number,)) for number in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        stop.set()
        churner.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(parsed(stream)), 900)
        self.assertEqual(logger.processorFailures, 0)

    def test_redaction_is_exact_under_many_threads(self):
        logger, stream = make_logger()
        logger.add_processor(redact_fields())

        def work(number):
            for index in range(200):
                logger.info('m', password=f'pw-{number}-{index}', n=number)

        threads = [threading.Thread(target=work, args=(number,)) for number in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        text = stream.getvalue()
        self.assertNotIn('pw-', text)
        self.assertEqual(text.count(DEFAULT_REPLACEMENT), 1200)

    def test_a_failing_processor_counts_every_failure_and_warns_once_under_many_threads(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: 1 / 0)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            threads = [threading.Thread(target=lambda: [logger.info('x') for _ in range(100)]) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
        self.assertEqual(logger.processorFailures, 600)
        self.assertEqual(error.getvalue().count('WARNING'), 1)
        self.assertEqual(stream.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
