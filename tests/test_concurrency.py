"""End-to-end tests with many threads: exact counts, changing the pipeline while logging, closing, and leaving with a backlog.

Run from the repo root::

    python3 -m unittest tests.test_concurrency -v
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import JsonFormatter  # noqa: E402
from log_context import context  # noqa: E402
from sinks import StreamSink  # noqa: E402

PACKAGE_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
THREADS = 8
PER_THREAD = 250


class LockedStream:
    """A text stream that counts writes safely, so a lost or doubled record shows up as a wrong count."""

    def __init__(self):
        self.lines = []
        self._lock = threading.Lock()

    def write(self, text):
        with self._lock:
            self.lines.extend(part for part in text.split('\n') if len(part) > 0)
        return len(text)

    def flush(self):
        pass


def run_threads(function, count=THREADS):
    threads = [threading.Thread(target=function, args=(number,)) for number in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)
        assert not thread.is_alive(), 'a thread did not finish'


class TestExactCounts(unittest.TestCase):

    def _check(self, logger, stream, total):
        logger.flush()
        records = [json.loads(line) for line in stream.lines]
        self.assertEqual(len(records), total)
        self.assertEqual(len({record['message'] for record in records}), total)
        for number in range(THREADS):
            indexes = [int(record['message'].split('-')[1]) for record in records if record['message'].startswith(f'{number}-')]
            self.assertEqual(sorted(indexes), list(range(PER_THREAD)))
            # One thread's records keep their order
            self.assertEqual(indexes, sorted(indexes))

    def _logger(self, **arguments):
        stream = LockedStream()
        logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
        logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()))
        return logger, stream

    def test_synchronous(self):
        logger, stream = self._logger()
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(PER_THREAD)])
        self._check(logger, stream, THREADS * PER_THREAD)

    def test_with_the_logger_queue(self):
        logger, stream = self._logger(enqueue=True)
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(PER_THREAD)])
        self._check(logger, stream, THREADS * PER_THREAD)

    def test_with_a_threaded_sink_that_blocks(self):
        stream = LockedStream()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()), threaded=True, threadQueueSize=8,
                        threadQueuePolicy='block')
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(PER_THREAD)])
        self._check(logger, stream, THREADS * PER_THREAD)

    def test_with_every_pipeline_part_in_use(self):
        logger, stream = self._logger(enqueue=True)
        logger.add_processor(lambda record: record._replace(fields={**record.fields, 'p': 1}))
        logger.add_filter(lambda record: True)
        logger.set_sink_filter('capture', lambda record: True)

        def work(number):
            with context(worker=number):
                for index in range(PER_THREAD):
                    logger.bind(i=index).info(f'{number}-{index}', n=number)
        run_threads(work)
        self._check(logger, stream, THREADS * PER_THREAD)
        for line in stream.lines:
            record = json.loads(line)
            self.assertEqual(record['context']['worker'], record['fields']['n'])
            self.assertEqual(record['fields']['p'], 1)

    def test_the_counts_are_exact_for_each_of_many_sinks(self):
        logger, _ = self._logger()
        streams = [LockedStream() for _ in range(10)]
        for number, stream in enumerate(streams):
            logger.add_sink(f's{number}', StreamSink(stream, formatter=JsonFormatter()), threaded=number % 2 == 0,
                            threadQueuePolicy='block')
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(PER_THREAD)])
        logger.flush()
        for stream in streams:
            self.assertEqual(len(stream.lines), THREADS * PER_THREAD)

    def test_every_log_type_at_once(self):
        logger, stream = self._logger()
        types = ('debug', 'info', 'warn', 'error', 'critical')
        run_threads(lambda number: [logger.log(types[index % 5], f'{number}-{index}') for index in range(PER_THREAD)])
        logger.flush()
        records = [json.loads(line) for line in stream.lines]
        self.assertEqual(len(records), THREADS * PER_THREAD)
        for record in records:
            self.assertEqual(record['log_type'], types[int(record['message'].split('-')[1]) % 5])


class TestChangingWhileLogging(unittest.TestCase):

    def test_sinks_come_and_go_while_a_steady_sink_gets_everything(self):
        steady = LockedStream()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add_sink('steady', StreamSink(steady, formatter=JsonFormatter()))
        stop = threading.Event()
        errors = []

        def churn():
            number = 0
            try:
                while not stop.is_set():
                    name = f'temporary{number % 5}'
                    logger.add_sink(name, StreamSink(io.StringIO(), formatter=JsonFormatter()), threaded=number % 2 == 0)
                    logger.remove_sink(name)
                    number += 1
            except Exception as error:
                errors.append(error)

        churner = threading.Thread(target=churn)
        churner.start()
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(PER_THREAD)], count=4)
        stop.set()
        churner.join(30)
        logger.flush()
        self.assertEqual(errors, [])
        self.assertEqual(len(steady.lines), 4 * PER_THREAD)

    def test_filters_processors_and_formatters_change_while_logging(self):
        stream = LockedStream()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add_sink('s', StreamSink(stream, formatter=JsonFormatter()))
        stop = threading.Event()
        errors = []

        def keep_all(record):
            return True

        def same(record):
            return record

        def churn():
            try:
                while not stop.is_set():
                    logger.add_filter(keep_all)
                    logger.add_processor(same)
                    logger.set_sink_filter('s', keep_all)
                    logger.set_sink_formatter('s', None)
                    logger.remove_filter(keep_all)
                    logger.remove_processor(same)
                    logger.set_sink_filter('s', None)
                    stop.wait(0.0005)
            except Exception as error:
                errors.append(error)

        churner = threading.Thread(target=churn)
        churner.start()
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(150)], count=4)
        stop.set()
        churner.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(len(stream.lines), 600)
        for line in stream.lines:
            json.loads(line)

    def test_flush_from_many_threads_while_others_log(self):
        stream = LockedStream()
        logger = Logger('app', logToFile=False, logToStdout=False, enqueue=True)
        logger.add_sink('s', StreamSink(stream, formatter=JsonFormatter()))
        errors = []

        def flusher(number):
            try:
                for _ in range(20):
                    logger.flush()
            except Exception as error:
                errors.append(error)

        flushers = [threading.Thread(target=flusher, args=(number,)) for number in range(3)]
        for thread in flushers:
            thread.start()
        run_threads(lambda number: [logger.info(f'{number}-{index}') for index in range(100)], count=4)
        for thread in flushers:
            thread.join(60)
        logger.flush()
        self.assertEqual(errors, [])
        self.assertEqual(len(stream.lines), 400)


class TestClosing(unittest.TestCase):

    def test_removing_a_threaded_sink_writes_what_it_had_queued(self):
        stream = LockedStream()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add_sink('s', StreamSink(stream, formatter=JsonFormatter()), threaded=True, threadQueuePolicy='block')
        for index in range(500):
            logger.info(str(index))
        logger.remove_sink('s')
        self.assertEqual(len(stream.lines), 500)

    def test_logging_while_a_sink_is_removed_never_raises(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        errors = []

        def work(number):
            try:
                for index in range(200):
                    logger.info(f'{number}-{index}')
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=work, args=(number,)) for number in range(4)]
        for thread in threads:
            thread.start()
        for round_ in range(20):
            logger.add_sink('x', StreamSink(io.StringIO(), formatter=JsonFormatter()), threaded=True)
            logger.remove_sink('x')
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])


class TestLeavingWithABacklog(unittest.TestCase):

    def test_the_program_writes_everything_it_logged_before_it_ends(self):
        with tempfile.TemporaryDirectory() as folder:
            outputPath = os.path.join(folder, 'out.log')
            script = textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {PACKAGE_FOLDER!r})
                from simple_log import Logger
                from sinks import StreamSink
                handle = open({outputPath!r}, 'w', encoding='utf-8')
                logger = Logger('app', logToFile=False, logToStdout=False, enqueue=True)
                logger.add_sink('s', StreamSink(handle, formatter='{{message}}'), threaded=True, threadQueuePolicy='block')
                for index in range(3000):
                    logger.info(str(index))
            """)
            completed = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with open(outputPath, encoding='utf-8') as stream:
                lines = stream.read().split()
        self.assertEqual(lines, [str(index) for index in range(3000)])


if __name__ == '__main__':
    unittest.main()
