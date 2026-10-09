"""Tests of the filters: global and per sink, fail open, the counters, sample, and many threads.

Run from the repo root::

    python3 -m unittest tests.test_filters -v
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
from filters import sample  # noqa: E402
from formatters import JsonFormatter  # noqa: E402
from record import LogRecord  # noqa: E402
from sinks import StreamSink  # noqa: E402


def make_logger(**arguments):
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()))
    return logger, stream


def messages(stream):
    return [json.loads(line)['message'] for line in stream.getvalue().splitlines()]


def make_record():
    return LogRecord.create(datetime(2026, 1, 1, tzinfo=timezone.utc), 'INFO', 'info', 10.0, 'app', 'm', 1, 2, 'main')


class TestGlobalFilters(unittest.TestCase):

    def test_a_filter_drops_for_every_sink(self):
        logger, stream = make_logger()
        other = io.StringIO()
        logger.add_sink('other', StreamSink(other, formatter=JsonFormatter()))
        logger.add_filter(lambda record: 'drop' not in record.message)
        logger.info('keep')
        logger.info('drop me')
        self.assertEqual(messages(stream), ['keep'])
        self.assertEqual(messages(other), ['keep'])

    def test_all_must_agree_and_the_first_no_ends_the_check(self):
        logger, stream = make_logger()
        calls = []
        logger.add_filter(lambda record: calls.append('first') or False)
        logger.add_filter(lambda record: calls.append('second') or True)
        logger.info('x')
        self.assertEqual(calls, ['first'])
        self.assertEqual(stream.getvalue(), '')

    def test_they_run_in_the_order_they_were_added(self):
        logger, _ = make_logger()
        calls = []
        for name in 'abc':
            logger.add_filter(lambda record, name=name: calls.append(name) or True)
        logger.info('x')
        self.assertEqual(calls, ['a', 'b', 'c'])

    def test_they_see_what_the_processors_left(self):
        logger, stream = make_logger()
        logger.add_processor(lambda record: record._replace(message='changed'))
        logger.add_filter(lambda record: record.message == 'changed')
        logger.info('original')
        self.assertEqual(messages(stream), ['changed'])

    def test_a_dropped_record_is_counted_and_is_not_the_last_record(self):
        logger, _ = make_logger()
        logger.add_filter(lambda record: False)
        for _ in range(4):
            logger.info('x')
        self.assertEqual(logger.filteredRecords, 4)
        self.assertIsNone(logger.lastRecord)

    def test_a_kept_record_is_not_counted(self):
        logger, _ = make_logger()
        logger.add_filter(lambda record: True)
        logger.info('x')
        self.assertEqual((logger.filteredRecords, logger.filterFailures), (0, 0))

    def test_add_and_remove(self):
        logger, stream = make_logger()

        def nothing(record):
            return False
        logger.add_filter(nothing)
        logger.info('a')
        self.assertEqual(logger.filters, (nothing,))
        logger.remove_filter(nothing)
        logger.info('b')
        self.assertEqual(messages(stream), ['b'])
        self.assertEqual(logger.filters, ())

    def test_removing_what_was_never_added_does_nothing(self):
        logger, _ = make_logger()
        logger.remove_filter(lambda record: True)
        self.assertEqual(logger.filters, ())

    def test_what_is_not_callable_is_refused(self):
        logger, _ = make_logger()
        for bad in (None, 'f', 1):
            with self.assertRaises(TypeError):
                logger.add_filter(bad)

    def test_it_can_decide_on_the_log_type(self):
        logger, stream = make_logger()
        logger.add_filter(lambda record: record.logType in ('error', 'critical'))
        for logType in ('debug', 'info', 'warn', 'error', 'critical'):
            logger.log(logType, logType)
        self.assertEqual(messages(stream), ['error', 'critical'])

    def test_it_can_decide_on_fields_and_context(self):
        logger, stream = make_logger()
        logger.add_filter(lambda record: record.fields.get('keep') is True or record.context.get('keep') is True)
        logger.info('no')
        logger.info('field', keep=True)
        logger.bind(keep=True).info('bound')
        self.assertEqual(messages(stream), ['field', 'bound'])

    def test_force_log_is_not_filtered(self):
        logger, stream = make_logger()
        calls = []
        logger.add_filter(lambda record: calls.append(1) or False)
        logger.force_log('info', 'forced')
        self.assertEqual((calls, logger.filteredRecords), ([], 0))
        self.assertEqual(messages(stream), ['forced'])


class TestFailingOpen(unittest.TestCase):

    def _run(self, keep, count=3):
        logger, stream = make_logger()
        logger.add_filter(keep)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for _ in range(count):
                logger.info('x')
        return logger, stream, error.getvalue()

    def test_a_filter_that_raises_keeps_the_record(self):
        logger, stream, error = self._run(lambda record: 1 / 0)
        self.assertEqual(len(messages(stream)), 3)
        self.assertEqual(logger.filterFailures, 3)
        self.assertEqual(logger.filteredRecords, 0)

    def test_the_warning_is_written_once_per_filter(self):
        _, _, error = self._run(lambda record: 1 / 0, count=10)
        self.assertEqual(error.count('WARNING'), 1)

    def test_an_answer_that_is_not_true_or_false_keeps_the_record_and_counts(self):
        for answer in (None, 0, 1, 'yes', []):
            with self.subTest(answer=answer):
                logger, stream, _ = self._run(lambda record, answer=answer: answer, count=2)
                self.assertEqual(len(messages(stream)), 2)
                self.assertEqual(logger.filterFailures, 2)

    def test_a_failing_filter_does_not_stop_the_next_ones(self):
        logger, stream = make_logger()
        logger.add_filter(lambda record: 1 / 0)
        logger.add_filter(lambda record: False)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
        self.assertEqual(stream.getvalue(), '')
        self.assertEqual((logger.filterFailures, logger.filteredRecords), (1, 1))

    def test_the_log_call_never_raises(self):
        logger, _ = make_logger()
        logger.add_filter(lambda record: 1 / 0)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')


class TestSinkFilters(unittest.TestCase):

    def _two(self):
        logger, first = make_logger()
        second = io.StringIO()
        logger.add_sink('second', StreamSink(second, formatter=JsonFormatter()))
        return logger, first, second

    def test_only_that_sink_is_affected(self):
        logger, first, second = self._two()
        logger.set_sink_filter('second', lambda record: record.logType == 'error')
        logger.info('i')
        logger.error('e')
        self.assertEqual(messages(first), ['i', 'e'])
        self.assertEqual(messages(second), ['e'])

    def test_a_sink_filter_counts_for_that_sink_and_not_globally(self):
        logger, _, _ = self._two()
        logger.set_sink_filter('second', lambda record: False)
        for _ in range(3):
            logger.info('x')
        self.assertEqual(logger.sink_stats('second')['filtered'], 3)
        self.assertEqual(logger.sink_stats('capture')['filtered'], 0)
        self.assertEqual(logger.filteredRecords, 0)

    def test_none_removes_it(self):
        logger, _, second = self._two()
        logger.set_sink_filter('second', lambda record: False)
        logger.info('a')
        logger.set_sink_filter('second', None)
        logger.info('b')
        self.assertEqual(messages(second), ['b'])

    def test_a_filter_can_be_replaced(self):
        logger, _, second = self._two()
        logger.set_sink_filter('second', lambda record: False)
        logger.set_sink_filter('second', lambda record: True)
        logger.info('a')
        self.assertEqual(messages(second), ['a'])

    def test_it_runs_after_the_global_filters_and_only_for_what_they_kept(self):
        logger, _, _ = self._two()
        calls = []
        logger.add_filter(lambda record: record.message != 'dropped')
        logger.set_sink_filter('second', lambda record: calls.append(record.message) or True)
        logger.info('dropped')
        logger.info('kept')
        self.assertEqual(calls, ['kept'])

    def test_it_runs_only_for_a_record_the_routing_gave_the_sink(self):
        logger, _, _ = self._two()
        calls = []
        logger.set_sink_filter('second', lambda record: calls.append(record.logType) or True)
        logger.remove_sink('second')
        logger.info('x')
        self.assertEqual(calls, [])

    def test_a_sink_filter_that_raises_gives_the_record_to_the_sink(self):
        logger, _, second = self._two()
        logger.set_sink_filter('second', lambda record: 1 / 0)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info('x')
        self.assertEqual(messages(second), ['x'])
        self.assertEqual(logger.filterFailures, 1)

    def test_an_unknown_sink_or_a_bad_filter_is_refused(self):
        logger, _, _ = self._two()
        with self.assertRaises(ValueError):
            logger.set_sink_filter('missing', lambda record: True)
        with self.assertRaises(TypeError):
            logger.set_sink_filter('second', 'no')

    def test_each_sink_keeps_its_own_filter(self):
        logger, first, second = self._two()
        logger.set_sink_filter('capture', lambda record: record.fields.get('to') == 'first')
        logger.set_sink_filter('second', lambda record: record.fields.get('to') == 'second')
        logger.info('a', to='first')
        logger.info('b', to='second')
        self.assertEqual((messages(first), messages(second)), (['a'], ['b']))

    def test_a_filter_can_be_set_on_the_console_sink(self):
        from simple_log import CONSOLE_SINK
        stdout = io.StringIO()
        logger = Logger('app', logToFile=False, stdout=stdout)
        logger.set_sink_filter(CONSOLE_SINK, lambda record: record.message == 'yes')
        logger.info('no')
        logger.info('yes')
        self.assertEqual(stdout.getvalue().count('yes'), 1)
        self.assertNotIn('no', stdout.getvalue().replace('info', ''))


class TestSample(unittest.TestCase):

    def test_the_extremes(self):
        self.assertTrue(all(sample(1)(make_record()) for _ in range(500)))
        self.assertFalse(any(sample(0)(make_record()) for _ in range(500)))

    def test_a_share_is_kept(self):
        keep = sample(0.5)
        share = sum(keep(make_record()) for _ in range(20000)) / 20000
        self.assertTrue(0.45 < share < 0.55, share)

    def test_validation(self):
        for bad in ('0.5', None, True):
            with self.assertRaises(TypeError):
                sample(bad)
        for bad in (-0.1, 1.1):
            with self.assertRaises(ValueError):
                sample(bad)

    def test_in_a_logger_the_counters_add_up(self):
        logger, stream = make_logger()
        logger.add_filter(sample(0.3))
        for _ in range(1000):
            logger.info('x')
        self.assertEqual(len(messages(stream)) + logger.filteredRecords, 1000)


class TestManyThreads(unittest.TestCase):

    def test_the_counts_are_exact_under_many_threads(self):
        logger, stream = make_logger()
        logger.add_filter(lambda record: record.fields['n'] % 2 == 0)

        def work():
            for number in range(500):
                logger.info('m', n=number)

        threads = [threading.Thread(target=work) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(len(messages(stream)), 1500)
        self.assertEqual(logger.filteredRecords, 1500)

    def test_failures_are_counted_exactly_and_warned_once_under_many_threads(self):
        logger, stream = make_logger()
        logger.add_filter(lambda record: 1 / 0)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            threads = [threading.Thread(target=lambda: [logger.info('x') for _ in range(100)]) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
        self.assertEqual(logger.filterFailures, 600)
        self.assertEqual(error.getvalue().count('WARNING'), 1)
        self.assertEqual(len(messages(stream)), 600)

    def test_changing_filters_while_logging_never_breaks(self):
        logger, stream = make_logger()
        stop = threading.Event()
        errors = []

        def churn():
            try:
                while not stop.is_set():
                    def keep_all(record):
                        return True
                    logger.add_filter(keep_all)
                    logger.set_sink_filter('capture', keep_all)
                    logger.remove_filter(keep_all)
                    logger.set_sink_filter('capture', None)
                    stop.wait(0.0005)
            except Exception as error:
                errors.append(error)

        churner = threading.Thread(target=churn)
        churner.start()
        threads = [threading.Thread(target=lambda: [logger.info('x') for _ in range(150)]) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        stop.set()
        churner.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(messages(stream)), 900)


if __name__ == '__main__':
    unittest.main()
