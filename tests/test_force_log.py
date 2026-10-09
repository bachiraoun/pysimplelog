"""Tests of ``force_log``: a record that must appear, whatever the levels, the type flags, the filters and ``disable()`` say.

Run from the repo root::

    python3 -m unittest tests.test_force_log -v
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import namespaces  # noqa: E402
from simple_log import Logger, CONSOLE_SINK, FILE_SINK  # noqa: E402
from processors import redact_fields  # noqa: E402
from secret import Secret  # noqa: E402
from sinks import Sink  # noqa: E402


def lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def messages(stream):
    return [record['message'] for record in lines(stream)]


class Keep(Sink):
    """Keeps the records it receives."""

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)
        self.got = []

    def write(self, text, record):
        self.got.append(record.message)


def make_logger(sinkOptions=None, **arguments):
    """Returns a logger with no console and no file, and a JSON output named ``audit`` that keeps what it gets."""
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add(stream, name='audit', format='json', **(sinkOptions or {}))
    return logger, stream


class TestWhatForceIgnores(unittest.TestCase):

    def test_a_log_type_that_is_switched_off(self):
        logger, stream = make_logger(sinkOptions={'logTypeFlags': {'debug': False}})
        logger.debug('normal')
        logger.force_log('debug', 'forced')
        self.assertEqual(messages(stream), ['forced'])

    def test_the_level_of_a_sink(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        strict = io.StringIO()
        logger.add(strict, name='strict', format='json', level='critical')
        logger.info('normal')
        logger.force_log('info', 'forced')
        self.assertEqual(messages(strict), ['forced'])

    def test_the_global_filters_and_the_filter_of_a_sink(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        calls = []
        stream = io.StringIO()
        logger.add(stream, format='json', filter=lambda record: calls.append('sink') or False)
        logger.add_filter(lambda record: calls.append('global') or False)
        logger.info('normal')
        calls.clear()
        logger.force_log('info', 'forced')
        self.assertEqual(calls, [])
        self.assertEqual(messages(stream), ['forced'])
        self.assertEqual(logger.filteredRecords, 1)

    def test_disable(self):
        logger, stream = make_logger()
        namespaces.disable('app')
        try:
            logger.info('normal')
            logger.force_log('info', 'forced')
        finally:
            namespaces.enable('app')
        self.assertEqual(messages(stream), ['forced'])

    def test_a_logger_with_every_type_off(self):
        logger, stream = make_logger(sinkOptions={'defaultFlag': False})
        logger.critical('normal')
        logger.force_log('critical', 'forced')
        self.assertEqual(messages(stream), ['forced'])


class TestWhereItGoes(unittest.TestCase):

    def test_every_sink_that_is_switched_on_by_default(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        first, second = Keep(), Keep()
        logger.add(first, name='first')
        logger.add(second, name='second', level='critical')
        logger.force_log('info', 'forced')
        self.assertEqual((first.got, second.got), (['forced'], ['forced']))

    def test_the_sinks_that_are_named(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        first, second = Keep(), Keep()
        logger.add(first, name='first')
        logger.add(second, name='second')
        logger.force_log('info', 'forced', sinks=['second'])
        self.assertEqual((first.got, second.got), ([], ['forced']))

    def test_the_built_in_console(self):
        console = io.StringIO()
        logger = Logger('app', logToFile=False, stdout=console)
        logger.force_log('debug', 'forced', sinks=[CONSOLE_SINK])
        self.assertIn('forced', console.getvalue())

    def test_the_console_is_one_of_all_the_sinks(self):
        console = io.StringIO()
        logger = Logger('app', logToFile=False, stdout=console)
        kept = Keep()
        logger.add(kept)
        logger.force_log('info', 'forced')
        self.assertIn('forced', console.getvalue())
        self.assertEqual(kept.got, ['forced'])

    def test_no_sink_at_all(self):
        logger, stream = make_logger()
        seen = []
        logger.add_processor(lambda record: seen.append(record.message) or record)
        logger.force_log('info', 'forced', sinks=[])
        self.assertEqual(stream.getvalue(), '')
        self.assertEqual(seen, ['forced'])
        self.assertEqual(logger.lastRecord.message, 'forced')

    def test_a_sink_that_is_switched_off_stays_silent_even_when_named(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        kept = Keep()
        logger.add_sink('off', kept, enabled=False)
        logger.force_log('info', 'to all')
        logger.force_log('info', 'to the name', sinks=['off'])
        self.assertEqual(kept.got, [])

    def test_a_logger_with_the_console_off_prints_nothing(self):
        console = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False, stdout=console)
        logger.force_log('error', 'forced')
        self.assertEqual(console.getvalue(), '')

    def test_a_logger_with_the_file_off_creates_no_file(self):
        folder = tempfile.mkdtemp(prefix='force-')
        self.addCleanup(shutil.rmtree, folder, True)
        logger = Logger('app', logToFile=False, logToStdout=False, logFile=os.path.join(folder, 'app.log'))
        logger.force_log('error', 'forced')
        logger.clear_sinks()
        self.assertEqual(os.listdir(folder), [])

    def test_a_logger_with_the_file_on_writes_the_forced_record(self):
        folder = tempfile.mkdtemp(prefix='force-')
        self.addCleanup(shutil.rmtree, folder, True)
        logger = Logger('app', logToFile=True, logToStdout=False, logFile=os.path.join(folder, 'app.log'))
        logger.force_log('debug', 'forced', sinks=[FILE_SINK])
        logger.flush()
        # Windows cannot delete a file that is still open
        logger.sinks[FILE_SINK].close()
        text = ''
        for name in os.listdir(folder):
            with open(os.path.join(folder, name)) as handle:
                text += handle.read()
        self.assertIn('forced', text)

    def test_a_wrong_name_raises_and_nothing_is_written(self):
        logger, stream = make_logger()
        with self.assertRaises(ValueError):
            logger.force_log('info', 'forced', sinks=['audit', 'missing'])
        self.assertEqual(stream.getvalue(), '')

    def test_sinks_must_be_a_list(self):
        logger, _ = make_logger()
        with self.assertRaises(TypeError):
            logger.force_log('info', 'forced', sinks='audit')
        with self.assertRaises(TypeError):
            logger.force_log('info', 'forced', sinks=CONSOLE_SINK)


class TestTheRestOfTheCall(unittest.TestCase):

    def test_the_processors_still_run_so_redaction_applies(self):
        logger, stream = make_logger(processors=[redact_fields()])
        logger.force_log('info', 'login', password='hunter2', value=Secret('s3cret'))
        self.assertNotIn('hunter2', stream.getvalue())
        self.assertNotIn('s3cret', stream.getvalue())

    def test_a_processor_that_fails_drops_the_forced_record(self):
        def broken(record):
            raise RuntimeError('no')

        logger, stream = make_logger(processors=[broken])
        with contextlib.redirect_stderr(io.StringIO()):
            logger.force_log('info', 'forced')
        self.assertEqual(stream.getvalue(), '')

    def test_formatting_fields_and_the_returned_message(self):
        logger, stream = make_logger()
        result = logger.force_log('info', 'User {} stopped it', 7, reason='shutdown')
        record = lines(stream)[0]
        self.assertEqual(result, 'User 7 stopped it')
        self.assertEqual(record['message'], 'User 7 stopped it')
        self.assertEqual(record['fields'], {'reason': 'shutdown'})

    def test_stdout_and_file_are_ordinary_fields_now(self):
        logger, stream = make_logger()
        logger.force_log('info', 'forced', stdout=1, file='x')
        self.assertEqual(lines(stream)[0]['fields'], {'stdout': 1, 'file': 'x'})

    def test_an_exception(self):
        logger, stream = make_logger()
        try:
            1 / 0
        except ZeroDivisionError:
            logger.force_log('error', 'failed', exc_info=True)
        self.assertEqual(lines(stream)[0]['exception']['type'], 'ZeroDivisionError')

    def test_the_count_constraint(self):
        logger, stream = make_logger()
        for _ in range(5):
            logger.force_log('info', 'again', countConstraint=2)
        self.assertEqual(messages(stream), ['again', 'again'])

    def test_a_function_as_the_message_is_refused(self):
        logger, _ = make_logger()
        with self.assertRaises(TypeError):
            logger.force_log('info', lambda: 'x')

    def test_an_unknown_log_type_follows_the_policy_of_log(self):
        logger, _ = make_logger()
        with self.assertRaises(Exception) as forced:
            logger.force_log('nope', 'x')
        with self.assertRaises(Exception) as normal:
            logger.log('nope', 'x')
        self.assertIs(type(forced.exception), type(normal.exception))


class TestOptAndBind(unittest.TestCase):

    def test_lazy_values(self):
        logger, stream = make_logger()
        calls = []
        logger.opt(lazy=True).force_log('info', 'value {}', lambda: calls.append(1) or 42)
        self.assertEqual(calls, [1])
        self.assertEqual(messages(stream), ['value 42'])

    def test_the_caller_depth(self):
        logger, stream = make_logger(callerInfo=True)

        def wrapper():
            logger.opt(depth=1).force_log('info', 'x')

        def application_code():
            wrapper()

        application_code()
        self.assertEqual(lines(stream)[0]['caller']['function'], 'application_code')

    def test_the_exception_option(self):
        logger, stream = make_logger()
        try:
            1 / 0
        except ZeroDivisionError:
            logger.opt(exception=True).force_log('error', 'failed')
        self.assertEqual(lines(stream)[0]['exception']['type'], 'ZeroDivisionError')

    def test_bound_values_and_context(self):
        logger, stream = make_logger()
        with logger.context(request_id='r-1'):
            logger.bind(job='nightly').force_log('info', 'forced')
        record = lines(stream)[0]
        self.assertEqual(record['context'], {'job': 'nightly', 'request_id': 'r-1'})

    def test_a_bound_logger_with_options_and_sinks(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        kept = Keep()
        logger.add(kept, name='kept', level='critical')
        logger.bind(job='x').opt(lazy=True).force_log('info', 'v {}', lambda: 5, sinks=['kept'])
        self.assertEqual(kept.got, ['v 5'])


class TestQueuesAndThreads(unittest.TestCase):

    def test_with_the_logger_queue(self):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False, enqueue=True)
        try:
            logger.add(stream, format='json', level='critical')
            logger.force_log('info', 'forced')
            logger.info('normal')
            self.assertTrue(logger.flush(timeout=10))
        finally:
            logger.clear_sinks()
        self.assertEqual(messages(stream), ['forced'])

    def test_with_a_threaded_sink(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        kept = Keep()
        logger.add(kept, name='kept', level='critical', threaded=True)
        try:
            logger.force_log('info', 'forced')
            self.assertTrue(logger.flush(timeout=10))
        finally:
            logger.clear_sinks()
        self.assertEqual(kept.got, ['forced'])

    def test_a_forced_record_obeys_the_queue_policy_of_the_sink(self):
        import threading
        gate = threading.Event()
        started = threading.Event()

        class Stuck(Sink):
            def __init__(self):
                super().__init__(formatter=lambda record: record.message)
                self.got = []

            def write(self, text, record):
                started.set()
                gate.wait(10)
                self.got.append(record.message)

        logger = Logger('app', logToFile=False, logToStdout=False)
        stuck = Stuck()
        logger.add_sink('stuck', stuck, threaded=True, threadQueueSize=2, threadQueuePolicy='drop_newest')
        try:
            logger.force_log('info', '0')
            self.assertTrue(started.wait(10))
            # The warning that records are dropped goes to the error stream, this test does not need to show it
            with contextlib.redirect_stderr(io.StringIO()):
                for number in range(1, 8):
                    logger.force_log('info', str(number))
            gate.set()
            self.assertTrue(logger.flush(timeout=10))
        finally:
            gate.set()
            logger.clear_sinks()
        self.assertEqual(stuck.got, ['0', '1', '2'])


if __name__ == '__main__':
    unittest.main()
