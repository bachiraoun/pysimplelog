"""Tests of the bridge from Python's standard logging package: levels, fields, exceptions, undo and many threads.

Run from the repo root::

    python3 -m unittest tests.test_standard_logging -v
"""
import io
import json
import logging
import os
import sys
import threading
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import JsonFormatter  # noqa: E402
from sinks import StreamSink  # noqa: E402
from standard_logging import StandardLoggingHandler, redirect_standard_logging, restore_standard_logging  # noqa: E402


def make_logger(**arguments):
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()))
    return logger, stream


def parsed(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class BridgeCase(unittest.TestCase):
    """A test case that owns one standard logger name and always puts everything back."""

    def setUp(self):
        self.name = f'bridge.{uuid.uuid4().hex}'
        self.standard = logging.getLogger(self.name)
        self.standard.propagate = False
        self.logger, self.stream = make_logger()
        self.handlers = []

    def tearDown(self):
        for handler in self.handlers:
            if handler.targetLogger is not None:
                restore_standard_logging(handler)

    def redirect(self, **arguments):
        arguments.setdefault('loggerLevel', logging.DEBUG)
        handler = redirect_standard_logging(self.logger, name=self.name, **arguments)
        self.handlers.append(handler)
        return handler


class TestLevels(BridgeCase):

    def test_the_default_mapping(self):
        self.redirect(loggerLevel=1)
        for level, expected in ((logging.DEBUG, 'debug'), (5, 'debug'), (logging.INFO, 'info'), (logging.WARNING, 'warn'),
                                (logging.ERROR, 'error'), (logging.CRITICAL, 'critical'), (60, 'critical')):
            self.standard.log(level, f'at {level}')
        self.assertEqual([line['log_type'] for line in parsed(self.stream)],
                         ['debug', 'debug', 'info', 'warn', 'error', 'critical', 'critical'])

    def test_a_custom_level_counts_as_the_highest_one_it_reaches(self):
        self.redirect()
        for level in (15, 25, 35, 45):
            self.standard.log(level, 'x')
        self.assertEqual([line['log_type'] for line in parsed(self.stream)], ['debug', 'info', 'warn', 'error'])

    def test_a_level_map_by_number_and_by_name(self):
        logging.addLevelName(25, 'NOTICE')
        self.addCleanup(logging.addLevelName, 25, 'Level 25')
        self.redirect(levelMap={25: 'warn', 'TRACE': 'debug'}, loggerLevel=1)
        logging.addLevelName(7, 'TRACE')
        self.addCleanup(logging.addLevelName, 7, 'Level 7')
        self.standard.log(25, 'a')
        self.standard.log(7, 'b')
        self.standard.warning('c')
        self.assertEqual([line['log_type'] for line in parsed(self.stream)], ['warn', 'debug', 'warn'])

    def test_a_level_map_can_lower_a_level(self):
        self.redirect(levelMap={logging.ERROR: 'info'})
        self.standard.error('x')
        self.assertEqual(parsed(self.stream)[0]['log_type'], 'info')

    def test_a_level_map_with_an_unknown_log_type_is_refused(self):
        with self.assertRaises(ValueError):
            StandardLoggingHandler(self.logger, levelMap={logging.INFO: 'nope'})

    def test_a_level_map_that_is_not_a_dictionary_is_refused(self):
        with self.assertRaises(TypeError):
            StandardLoggingHandler(self.logger, levelMap=[(10, 'debug')])

    def test_the_handler_level_applies(self):
        self.redirect(level=logging.WARNING)
        self.standard.info('no')
        self.standard.warning('yes')
        self.assertEqual([line['message'] for line in parsed(self.stream)], ['yes'])

    def test_the_standard_logger_level_applies_first(self):
        self.redirect(loggerLevel=logging.ERROR)
        self.standard.warning('no')
        self.standard.error('yes')
        self.assertEqual([line['message'] for line in parsed(self.stream)], ['yes'])

    def test_the_logger_routing_applies_too(self):
        logger = Logger('app', logToFile=False, logToStdout=False, logTypes=None)
        stream = io.StringIO()
        logger.add_sink('only_errors', StreamSink(stream, formatter=JsonFormatter()), minLevel=30.0)
        handler = redirect_standard_logging(logger, name=self.name, loggerLevel=logging.DEBUG)
        self.addCleanup(restore_standard_logging, handler)
        self.standard.info('no')
        self.standard.error('yes')
        self.assertEqual([line['message'] for line in parsed(stream)], ['yes'])


class TestWhatTheRecordHolds(BridgeCase):

    def test_the_message_has_its_arguments_put_in(self):
        self.redirect()
        self.standard.info('%s has %d items, %.1f%%', 'cart', 3, 12.34)
        self.assertEqual(parsed(self.stream)[0]['message'], 'cart has 3 items, 12.3%')

    def test_a_percent_sign_without_arguments_is_left_alone(self):
        self.redirect()
        self.standard.info('100% done')
        self.assertEqual(parsed(self.stream)[0]['message'], '100% done')

    def test_the_standard_logger_name_is_a_field(self):
        self.redirect()
        self.standard.info('x')
        self.assertEqual(parsed(self.stream)[0]['fields']['logger_name'], self.name)

    def test_the_pysimplelog_logger_name_stays_the_logger(self):
        self.redirect()
        self.standard.info('x')
        self.assertEqual(parsed(self.stream)[0]['logger'], 'app')

    def test_extra_keys_become_fields(self):
        self.redirect()
        self.standard.info('x', extra={'order_id': 5, 'tenant': 'a'})
        fields = parsed(self.stream)[0]['fields']
        self.assertEqual((fields['order_id'], fields['tenant']), (5, 'a'))

    def test_the_standard_attributes_are_not_fields(self):
        self.redirect()
        self.standard.info('x', extra={'custom': 1})
        fields = parsed(self.stream)[0]['fields']
        for name in ('name', 'msg', 'args', 'levelname', 'pathname', 'lineno', 'created', 'thread', 'process', 'message'):
            self.assertNotIn(name, fields)
        self.assertEqual(set(fields), {'logger_name', 'custom'})

    def test_stack_info_becomes_a_field(self):
        self.redirect()
        self.standard.info('x', stack_info=True)
        self.assertIn('stack', parsed(self.stream)[0]['fields'])

    def test_no_stack_field_without_stack_info(self):
        self.redirect()
        self.standard.info('x')
        self.assertNotIn('stack', parsed(self.stream)[0]['fields'])

    def test_the_original_time_process_and_thread_are_kept(self):
        self.redirect()
        names = []

        def work():
            names.append((threading.current_thread().name, threading.get_ident()))
            self.standard.info('from a thread')
        thread = threading.Thread(target=work, name='bridge-worker')
        thread.start()
        thread.join(5)
        line = parsed(self.stream)[0]
        self.assertEqual((line['thread']['name'], line['thread']['id']), names[0])
        self.assertEqual(line['process']['id'], os.getpid())

    def test_the_timestamp_is_the_moment_of_the_original_record(self):
        self.redirect()
        record = self.standard.makeRecord(self.name, logging.INFO, __file__, 1, 'x', (), None)
        record.created = 1_700_000_000.25
        self.standard.handle(record)
        self.assertIn('2023-11-14', parsed(self.stream)[0]['timestamp'])
        self.assertIn('.250', parsed(self.stream)[0]['timestamp'])

    def test_the_caller_is_kept_when_the_logger_records_callers(self):
        self.logger.set_caller_info(True)
        self.redirect()
        self.standard.info('x')
        caller = parsed(self.stream)[0]['caller']
        self.assertEqual((caller['file'], caller['function']), ('test_standard_logging.py',
                                                                 'test_the_caller_is_kept_when_the_logger_records_callers'))

    def test_no_caller_when_the_logger_does_not_record_it(self):
        self.redirect()
        self.standard.info('x')
        self.assertNotIn('caller', parsed(self.stream)[0])

    def test_it_goes_through_the_processors_and_filters(self):
        self.logger.add_processor(lambda record: record._replace(message=record.message.upper()))
        self.logger.add_filter(lambda record: 'drop' not in record.message.lower())
        self.redirect()
        self.standard.info('keep')
        self.standard.info('drop')
        self.assertEqual([line['message'] for line in parsed(self.stream)], ['KEEP'])


class TestExceptions(BridgeCase):

    def test_logging_exception_gives_the_type_message_and_traceback(self):
        self.redirect()
        try:
            raise KeyError('missing')
        except KeyError:
            self.standard.exception('failed')
        exception = parsed(self.stream)[0]['exception']
        self.assertEqual(exception['type'], 'KeyError')
        self.assertIn('missing', exception['message'])
        self.assertIn('Traceback', exception['stacktrace'])

    def test_exc_info_true_and_an_instance(self):
        self.redirect()
        try:
            raise ValueError('one')
        except ValueError as error:
            self.standard.error('a', exc_info=True)
            self.standard.error('b', exc_info=error)
        self.assertEqual([line['exception']['type'] for line in parsed(self.stream)], ['ValueError', 'ValueError'])

    def test_no_exception_key_without_one(self):
        self.redirect()
        self.standard.error('x')
        self.assertNotIn('exception', parsed(self.stream)[0])

    def test_exc_info_with_nothing_to_report_is_harmless(self):
        self.redirect()
        self.standard.error('x', exc_info=True)
        self.assertEqual(len(parsed(self.stream)), 1)


class TestRedirectAndRestore(BridgeCase):

    def test_nothing_changes_until_it_is_called(self):
        self.standard.warning('nobody listens')
        self.assertEqual(self.stream.getvalue(), '')
        self.assertEqual(self.standard.handlers, [])

    def test_restore_removes_the_handler_and_the_level(self):
        self.standard.setLevel(logging.ERROR)
        handler = self.redirect(loggerLevel=logging.DEBUG)
        self.assertEqual(self.standard.level, logging.DEBUG)
        restore_standard_logging(handler)
        self.assertEqual((self.standard.level, self.standard.handlers), (logging.ERROR, []))
        self.standard.error('x')
        self.assertEqual(self.stream.getvalue(), '')

    def test_replace_removes_the_old_handlers_and_restore_puts_them_back(self):
        existing = logging.NullHandler()
        self.standard.addHandler(existing)
        handler = self.redirect(replace=True)
        self.assertEqual(self.standard.handlers, [handler])
        restore_standard_logging(handler)
        self.assertEqual(self.standard.handlers, [existing])

    def test_without_replace_the_old_handlers_stay(self):
        existing = logging.NullHandler()
        self.standard.addHandler(existing)
        handler = self.redirect()
        self.assertEqual(self.standard.handlers, [existing, handler])

    def test_a_second_redirect_to_the_same_logger_is_refused(self):
        self.redirect()
        with self.assertRaises(ValueError):
            self.redirect()

    def test_two_different_loggers_can_both_receive(self):
        self.redirect()
        second, secondStream = make_logger()
        handler = redirect_standard_logging(second, name=self.name)
        self.addCleanup(restore_standard_logging, handler)
        self.standard.info('x')
        self.assertEqual((len(parsed(self.stream)), len(parsed(secondStream))), (1, 1))

    def test_restoring_twice_is_refused(self):
        handler = self.redirect()
        restore_standard_logging(handler)
        with self.assertRaises(ValueError):
            restore_standard_logging(handler)

    def test_a_handler_not_made_by_redirect_cannot_be_restored(self):
        with self.assertRaises(ValueError):
            restore_standard_logging(StandardLoggingHandler(self.logger))

    def test_what_is_not_a_logger_is_refused(self):
        for bad in (None, logging.getLogger(), 'logger'):
            with self.assertRaises(TypeError):
                StandardLoggingHandler(bad)

    def test_a_child_logger_reaches_the_handler_of_its_parent(self):
        self.redirect()
        child = logging.getLogger(f'{self.name}.child.deeper')
        child.info('from below')
        line = parsed(self.stream)[0]
        self.assertEqual(line['fields']['logger_name'], f'{self.name}.child.deeper')

    def test_the_handler_has_no_lock_and_works_on_every_python(self):
        handler = self.redirect()
        self.assertIsNone(handler.lock)
        self.standard.info('x')
        self.assertEqual(len(parsed(self.stream)), 1)

    def test_a_filter_on_the_handler_applies(self):
        handler = self.redirect()
        handler.addFilter(lambda record: 'drop' not in record.getMessage())
        self.standard.info('drop')
        self.standard.info('keep')
        self.assertEqual([line['message'] for line in parsed(self.stream)], ['keep'])


class TestErrors(BridgeCase):

    def test_a_logger_that_cannot_take_the_record_does_not_break_the_caller(self):
        handler = self.redirect()
        self.logger.remove_sink('capture')

        def explode(*arguments, **keywords):
            raise RuntimeError('boom')
        self.logger.log_external = explode
        previous = logging.raiseExceptions
        logging.raiseExceptions = False
        try:
            self.standard.info('x')
        finally:
            logging.raiseExceptions = previous
        self.assertIsNotNone(handler)

    def test_a_message_that_cannot_be_formatted_does_not_break_the_caller(self):
        self.redirect()
        previous = logging.raiseExceptions
        logging.raiseExceptions = False
        try:
            self.standard.info('%d', 'not a number')
        finally:
            logging.raiseExceptions = previous
        self.assertEqual(self.stream.getvalue(), '')


class TestManyThreads(BridgeCase):

    def test_many_threads_log_through_the_standard_package(self):
        self.redirect()

        def work(number):
            for index in range(200):
                self.standard.info('%d-%d', number, index, extra={'worker': number})

        threads = [threading.Thread(target=work, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        lines = parsed(self.stream)
        self.assertEqual(len(lines), 1600)
        self.assertEqual(len({line['message'] for line in lines}), 1600)
        for line in lines:
            self.assertEqual(line['message'].split('-')[0], str(line['fields']['worker']))

    def test_adding_and_restoring_while_other_threads_log_never_breaks(self):
        errors = []
        stop = threading.Event()

        def churn():
            try:
                while not stop.is_set():
                    handler = redirect_standard_logging(self.logger, name=self.name)
                    restore_standard_logging(handler)
                    stop.wait(0.0005)
            except Exception as error:
                errors.append(error)

        churner = threading.Thread(target=churn)
        churner.start()
        threads = [threading.Thread(target=lambda: [self.standard.info('x') for _ in range(200)]) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        stop.set()
        churner.join(10)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
