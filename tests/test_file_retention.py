"""Deleting old log files, compressing rotated ones, and the housekeeping of the logger.

Run from the repo root::

    python3 -m unittest tests.test_file_retention -v

Files go when there are too many or they are too old, and they are compressed when they are rotated out. None of it may lose a
record that should be kept, delete the file being written, or make the thread that logs wait. The age is tested when something
happens, a rotation, a start, a write once a minute, or a call to ``enforce_retention`` or ``Logger.maintain``, and these tests
make each of those happen.
"""
import glob
import gzip
import io
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import sinks as sinks_module  # noqa: E402
from SimpleLog import Logger, FILE_SINK  # noqa: E402
from sinks import FileSink, Sink  # noqa: E402
from record import LogRecord  # noqa: E402

# Seconds a test waits for something that must happen
WAIT_SECONDS = 15.0
# Largest size of a file in megabytes: about two thousand bytes, some twenty records
SMALL_FILE_MEGABYTES = 0.002
HOUR = 3600


def make_record(text):
    return LogRecord.create(datetime.now(timezone.utc), 'INFO', 'info', 10.0, 'test', text, 1, 1, 'MainThread')


def line_of(index):
    """The text of record *index*: a hundred bytes, so a file of the small size holds about twenty."""
    return f"r{index:05d}" + 'x' * 90


def wait_until(condition, what, timeout=WAIT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def compression_threads():
    return [thread for thread in threading.enumerate() if thread.name == 'pysimplelog-file-compress' and thread.is_alive()]


class FileTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='retention-')
        self.sinks = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for sink in self.sinks:
            sink.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_sink(self, **options):
        arguments = dict(maxSize=SMALL_FILE_MEGABYTES, firstNumber=0)
        arguments.update(options)
        sink = FileSink(os.path.join(self.folder, 'app'), 'log', formatter=lambda record: record.message, **arguments)
        self.sinks.append(sink)
        return sink

    def write(self, sink, first, count):
        for index in range(first, first + count):
            sink.emit(make_record(line_of(index)))

    def names(self):
        return sorted(os.path.basename(path) for path in glob.glob(os.path.join(self.folder, '*')))

    def path(self, name):
        return os.path.join(self.folder, name)

    def age(self, name, seconds):
        """Makes a file look as if it was last changed *seconds* ago."""
        moment = time.time() - seconds
        os.utime(self.path(name), (moment, moment))

    def read_everything(self):
        """Returns the text of every record in every file, plain or compressed, the oldest file first."""
        found = []
        for path in glob.glob(os.path.join(self.folder, 'app_*.log*')):
            if path.endswith('.tmp'):
                continue
            number = int(re.search(r'app_(\d+)\.log', path).group(1))
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'rt', encoding='utf-8') as stream:
                found.append((number, stream.read().split()))
        return [text for _, lines in sorted(found) for text in lines]

    def rotated_plain_files(self, sink):
        return [name for name in self.names() if re.fullmatch(r'app_\d+\.log', name) and self.path(name) != sink.path]


class TestSettings(FileTestCase):

    def test_the_new_arguments_are_checked(self):
        for options, error in (({'maxAge': 0}, ValueError), ({'maxAge': -5}, ValueError), ({'maxAge': 'week'}, TypeError),
                               ({'maxAge': True}, TypeError), ({'compress': 'zip'}, ValueError), ({'compress': 5}, TypeError),
                               ({'compress': 'gz', 'maxSize': None}, ValueError)):
            with self.subTest(options=options):
                with self.assertRaises(error):
                    self.make_sink(**options)

    def test_the_setters_are_checked_and_compress_keeps_the_size_limit(self):
        sink = self.make_sink()
        sink.set_max_age(60)
        sink.set_max_age(None)
        sink.set_compress('gz')
        with self.assertRaises(ValueError):
            sink.set_max_size(None)
        sink.set_compress(None)
        sink.set_max_size(None)
        with self.assertRaises(ValueError):
            sink.set_compress('gz')
        with self.assertRaises(ValueError):
            sink.set_max_age(0)

    def test_nothing_new_happens_when_the_new_arguments_are_not_used(self):
        sink = self.make_sink(roll=3, maxSize=1)         # a megabyte: nothing rotates in thirty records
        with mock.patch.object(FileSink, '_list_existing', wraps=sink._list_existing) as listing:
            self.write(sink, 0, 30)
        self.assertEqual(compression_threads(), [])
        self.assertEqual(sink.stats['files_compressed'], 0)
        self.assertEqual(sink.maintain(), {'files_deleted': 0})
        self.assertEqual(listing.call_count, 0)


class TestAge(FileTestCase):

    def _rotated(self, **options):
        """Returns a sink that has rotated several times, with its older files made two hours old."""
        sink = self.make_sink(**options)
        self.write(sink, 0, 100)
        old = [name for name in self.names() if self.path(name) != sink.path]
        self.assertGreater(len(old), 2)
        for name in old:
            self.age(name, 2 * HOUR)
        return sink, old

    def test_old_rotated_files_are_deleted_when_retention_is_enforced(self):
        sink, old = self._rotated(maxAge=HOUR)
        self.assertEqual(sink.enforce_retention(), len(old))
        self.assertEqual(self.names(), [os.path.basename(sink.path)])
        self.assertEqual(sink.stats['files_deleted'], len(old))

    def test_files_younger_than_the_age_stay(self):
        sink, old = self._rotated(maxAge=3 * HOUR)
        self.assertEqual(sink.enforce_retention(), 0)
        self.assertEqual(len(self.names()), len(old) + 1)

    def test_the_file_being_written_is_never_deleted_whatever_its_age(self):
        sink = self.make_sink(maxAge=HOUR)
        self.write(sink, 0, 5)
        self.age(os.path.basename(sink.path), 5 * HOUR)
        self.assertEqual(sink.enforce_retention(), 0)
        self.write(sink, 5, 5)
        self.assertEqual(len(self.read_everything()), 10)

    def test_a_rotation_deletes_old_files(self):
        sink, old = self._rotated(maxAge=HOUR)
        self.write(sink, 100, 40)               # at least one more rotation
        for name in old:
            self.assertNotIn(name, self.names())

    def test_starting_a_sink_deletes_old_files_but_continues_in_the_newest(self):
        first = self.make_sink()
        self.write(first, 0, 100)
        first.close()
        names = self.names()
        for name in names[:-1]:
            self.age(name, 2 * HOUR)
        second = self.make_sink(maxAge=HOUR)
        self.assertEqual(self.names(), [names[-1]])
        self.assertEqual(os.path.basename(second.path), names[-1])

    def test_writes_test_the_age_at_most_once_in_the_interval(self):
        sink = self.make_sink(maxSize=None, maxAge=HOUR)
        with mock.patch.object(FileSink, '_tidy', wraps=sink._tidy) as tidy, \
                mock.patch.object(FileSink, 'RETENTION_CHECK_SECONDS', 0.3):
            self.write(sink, 0, 200)
            self.assertEqual(tidy.call_count, 1)
            time.sleep(0.35)
            self.write(sink, 200, 5)
            self.assertEqual(tidy.call_count, 2)

    def test_files_that_are_too_old_go_on_a_write_even_when_nothing_rotates(self):
        sink = self.make_sink(maxAge=HOUR)
        self.write(sink, 0, 60)                 # several files
        old = [name for name in self.names() if self.path(name) != sink.path]
        for name in old:
            self.age(name, 2 * HOUR)
        sink.set_max_age(HOUR)                  # makes the next write test the age
        self.write(sink, 60, 1)
        for name in old:
            self.assertNotIn(name, self.names())

    def test_the_number_of_files_and_the_age_both_apply(self):
        sink = self.make_sink(roll=4, maxAge=HOUR)
        self.write(sink, 0, 100)
        self.assertLessEqual(len(self.names()), 4)
        names = self.names()
        self.age(names[0], 2 * HOUR)
        self.assertEqual(sink.enforce_retention(), 1)
        self.assertNotIn(names[0], self.names())

    def test_a_file_that_cannot_be_deleted_stays_and_goes_at_the_next_test(self):
        sink, old = self._rotated(maxAge=HOUR)
        real = os.remove

        def refusing(path, *arguments):
            if os.path.basename(path) == old[0]:
                raise PermissionError(13, 'in use by another process')
            return real(path, *arguments)

        with mock.patch.object(sinks_module.os, 'remove', side_effect=refusing):
            self.assertEqual(sink.enforce_retention(), len(old) - 1)
        self.assertIn(old[0], self.names())
        self.assertEqual(sink.enforce_retention(), 1)
        self.assertNotIn(old[0], self.names())


class TestCompression(FileTestCase):

    def wait_for_compression(self, sink, expected=None):
        wait_until(lambda: compression_threads() == [], 'the compression thread to end')
        if expected is not None:
            self.assertEqual(sink.stats['files_compressed'], expected)

    def test_rotated_files_are_compressed_and_hold_the_same_text(self):
        sink = self.make_sink(compress='gz')
        self.write(sink, 0, 100)
        sink.close()
        self.assertEqual(compression_threads(), [])
        names = self.names()
        self.assertGreater(len([name for name in names if name.endswith('.gz')]), 2)
        self.assertEqual([name for name in names if re.fullmatch(r'app_\d+\.log', name)], [os.path.basename(sink.path)])
        self.assertFalse([name for name in names if name.endswith('.tmp')])
        self.assertEqual(self.read_everything(), [line_of(index) for index in range(100)])
        self.assertEqual(sink.stats['files_compressed'], len([name for name in names if name.endswith('.gz')]))
        self.assertEqual(sink.stats['compress_failed'], 0)

    def test_compressed_files_keep_their_numbers_and_count_for_roll(self):
        sink = self.make_sink(compress='gz', roll=3)
        self.write(sink, 0, 200)
        sink.close()
        names = self.names()
        self.assertLessEqual(len(names), 3)
        numbers = [int(re.search(r'app_(\d+)\.log', name).group(1)) for name in names]
        self.assertEqual(numbers, list(range(numbers[0], numbers[0] + len(numbers))))

    def test_a_number_that_was_compressed_is_never_used_again(self):
        first = self.make_sink(compress='gz')
        self.write(first, 0, 100)
        first.close()
        compressed = {int(re.search(r'app_(\d+)', name).group(1)) for name in self.names() if name.endswith('.gz')}
        second = self.make_sink(compress='gz')
        self.write(second, 100, 100)
        second.close()
        plain = [int(re.search(r'app_(\d+)', name).group(1)) for name in self.names() if re.fullmatch(r'app_\d+\.log', name)]
        self.assertFalse(compressed & set(plain), 'a number is used by a compressed file and by a plain one')
        self.assertEqual(self.read_everything(), [line_of(index) for index in range(200)])

    def test_when_the_newest_file_is_compressed_a_new_one_is_started_after_it(self):
        first = self.make_sink(compress='gz')
        self.write(first, 0, 25)                 # one rotation
        first.close()
        newest = max(int(re.search(r'app_(\d+)', name).group(1)) for name in self.names())
        # Everything is compressed, as a program that stopped after a rotation would leave it
        for name in list(self.names()):
            if not name.endswith('.gz'):
                with open(self.path(name), 'rb') as source, gzip.open(self.path(name) + '.gz', 'wb') as target:
                    shutil.copyfileobj(source, target)
                os.remove(self.path(name))
        second = self.make_sink(compress='gz')
        self.assertEqual(os.path.basename(second.path), f'app_{newest + 1}.log')

    def test_a_full_set_of_compressed_files_makes_room_for_the_new_file(self):
        for number in range(3):
            with gzip.open(self.path(f'app_{number}.log.gz'), 'wt') as stream:
                stream.write(line_of(number) + '\n')
        sink = self.make_sink(compress='gz', roll=3)
        self.write(sink, 3, 1)
        names = self.names()
        self.assertLessEqual(len(names), 3)
        self.assertNotIn('app_0.log.gz', names)
        self.assertIn('app_3.log', names)

    def test_the_compressed_file_keeps_the_modification_time_of_the_original(self):
        with open(self.path('app_0.log'), 'w') as stream:
            stream.write(line_of(0) + '\n')
        self.age('app_0.log', 5 * HOUR)
        original = os.path.getmtime(self.path('app_0.log'))
        with open(self.path('app_1.log'), 'w') as stream:
            stream.write(line_of(1) + '\n')
        sink = self.make_sink(compress='gz')
        self.wait_for_compression(sink, expected=1)
        self.assertAlmostEqual(os.path.getmtime(self.path('app_0.log.gz')), original, delta=1.0)

    def test_leftovers_of_an_earlier_run_are_compressed_when_the_sink_starts(self):
        first = self.make_sink()
        self.write(first, 0, 100)
        first.close()
        plain = [name for name in self.names() if name != os.path.basename(first.path)]
        self.assertGreater(len(plain), 2)
        second = self.make_sink(compress='gz')
        self.wait_for_compression(second, expected=len(plain))
        self.assertEqual(self.read_everything(), [line_of(index) for index in range(100)])

    def test_a_plain_file_with_a_compressed_twin_and_a_stray_temporary_file_are_cleaned(self):
        for number in (0, 1):
            with open(self.path(f'app_{number}.log'), 'w') as stream:
                stream.write(line_of(number) + '\n')
        with gzip.open(self.path('app_0.log.gz'), 'wt') as stream:
            stream.write(line_of(0) + '\n')
        with open(self.path('app_5.log.gz.tmp'), 'wb') as stream:
            stream.write(b'half of a compression')
        self.make_sink(compress='gz')
        self.assertNotIn('app_0.log', self.names())
        self.assertNotIn('app_5.log.gz.tmp', self.names())
        self.assertIn('app_0.log.gz', self.names())
        self.assertIn('app_1.log', self.names())

    def test_a_failing_compression_keeps_the_original_warns_once_and_is_tried_again(self):
        first = self.make_sink()
        self.write(first, 0, 100)
        first.close()
        plain = [name for name in self.names() if name != os.path.basename(first.path)]
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            with mock.patch.object(sinks_module.gzip, 'open', side_effect=OSError('disk is full')):
                second = self.make_sink(compress='gz')
                wait_until(lambda: second.stats['compress_failed'] >= len(plain) and compression_threads() == [], 'the failures')
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('could not compress'), 1)
        for name in plain:
            self.assertIn(name, self.names())
        self.assertFalse([name for name in self.names() if name.endswith('.tmp')])
        second.enforce_retention()
        self.wait_for_compression(second)
        self.assertEqual(second.stats['files_compressed'], len(plain))
        self.assertEqual(self.read_everything(), [line_of(index) for index in range(100)])

    def test_the_thread_that_logs_does_not_wait_for_a_slow_compression(self):
        real = shutil.copyfileobj

        def slow(source, target, length=0):
            time.sleep(0.4)
            return real(source, target, length)

        sink = self.make_sink(compress='gz')
        with mock.patch.object(sinks_module.shutil, 'copyfileobj', side_effect=slow):
            self.write(sink, 0, 30)             # the first rotation starts a compression that takes 0.4 s
            started = time.perf_counter()
            self.write(sink, 30, 8)             # logging goes on while it runs
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.2)
            self.assertNotEqual(compression_threads(), [], 'the compression should still be running')
            self.wait_for_compression(sink)

    def test_there_is_no_thread_unless_compression_is_on_and_it_ends_when_the_work_is_done(self):
        plain = self.make_sink()
        self.write(plain, 0, 100)
        self.assertEqual(compression_threads(), [])
        sink = self.make_sink(compress='gz')
        self.write(sink, 100, 60)
        self.wait_for_compression(sink)
        self.assertEqual(compression_threads(), [])

    def test_closing_waits_for_the_compression_and_leaves_no_temporary_file(self):
        real = shutil.copyfileobj

        def slow(source, target, length=0):
            time.sleep(0.3)
            return real(source, target, length)

        sink = self.make_sink(compress='gz')
        with mock.patch.object(sinks_module.shutil, 'copyfileobj', side_effect=slow):
            self.write(sink, 0, 30)
            sink.close()
            self.assertEqual(compression_threads(), [])
        self.assertFalse([name for name in self.names() if name.endswith('.tmp')])
        self.assertEqual(self.read_everything(), [line_of(index) for index in range(30)])

    def test_files_that_were_waiting_when_the_sink_was_closed_are_compressed_at_the_next_start(self):
        real = shutil.copyfileobj

        def slow(source, target, length=0):
            time.sleep(0.2)
            return real(source, target, length)

        sink = self.make_sink(compress='gz')
        with mock.patch.object(sinks_module.shutil, 'copyfileobj', side_effect=slow):
            self.write(sink, 0, 100)
            sink.close()
        left = self.rotated_plain_files(sink)
        second = self.make_sink(compress='gz')
        self.wait_for_compression(second)
        self.assertEqual(self.rotated_plain_files(second), [])
        self.assertEqual(self.read_everything(), [line_of(index) for index in range(100)])
        self.assertIsNotNone(left)

    def test_age_does_not_delete_a_file_while_it_is_being_compressed(self):
        real = shutil.copyfileobj

        def slow(source, target, length=0):
            time.sleep(0.4)
            return real(source, target, length)

        sink = self.make_sink(compress='gz', maxAge=HOUR)
        with mock.patch.object(sinks_module.shutil, 'copyfileobj', side_effect=slow):
            self.write(sink, 0, 25)
            plain = self.rotated_plain_files(sink)
            self.assertEqual(len(plain), 1)
            self.age(plain[0], 2 * HOUR)
            self.assertEqual(sink.enforce_retention(), 0)       # it is busy, so it is not touched
            self.wait_for_compression(sink)
        self.age(plain[0] + '.gz', 2 * HOUR)
        self.assertEqual(sink.enforce_retention(), 1)            # now it is a compressed file, and too old
        self.assertNotIn(plain[0] + '.gz', self.names())

    @unittest.skipUnless(hasattr(os, 'fork'), 'needs fork')
    def test_a_forked_child_does_not_start_a_compression(self):
        sink = self.make_sink(compress='gz')
        self.write(sink, 0, 10)
        self.wait_for_compression(sink)
        readEnd, writeEnd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                self.write(sink, 10, 40)         # rotates in the child
                outcome = b'thread' if compression_threads() else b'none'
            except BaseException as error:
                outcome = repr(error).encode()
            os.write(writeEnd, outcome)
            os._exit(0)
        os.waitpid(pid, 0)
        self.assertEqual(os.read(readEnd, 200), b'none')
        os.close(readEnd)
        os.close(writeEnd)


class TestThreads(FileTestCase):

    THREADS, PER_THREAD = 8, 250

    def _write_from_threads(self, sink, enforce=False):
        errors = []

        def work(index):
            try:
                for number in range(self.PER_THREAD):
                    sink.emit(make_record(f"t{index}-{number:04d}" + 'x' * 80))
            except BaseException as error:
                errors.append(repr(error))

        def tidy():
            # A scheduler calls it now and then, not in a tight loop: each call reads the folder under the lock of the sink
            try:
                while not stopTidy.wait(0.01):
                    sink.enforce_retention()
            except BaseException as error:
                errors.append(repr(error))

        stopTidy = threading.Event()
        threads = [threading.Thread(target=work, args=(index,)) for index in range(self.THREADS)]
        tidier = threading.Thread(target=tidy)
        if enforce:
            tidier.start()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT_SECONDS * 2)
            self.assertFalse(thread.is_alive())
        stopTidy.set()
        if enforce:
            tidier.join(WAIT_SECONDS)
        return errors

    def _records(self):
        found = {}
        for text in self.read_everything():
            match = re.match(r't(\d+)-(\d+)x+$', text)
            self.assertIsNotNone(match, f"not a whole record: {text!r}")
            found.setdefault(int(match.group(1)), []).append(int(match.group(2)))
        return found

    def test_compressing_while_many_threads_write_loses_nothing(self):
        sink = self.make_sink(compress='gz')
        self.assertEqual(self._write_from_threads(sink), [])
        sink.close()
        found = self._records()
        self.assertEqual(sorted(found), list(range(self.THREADS)))
        for thread, numbers in found.items():
            self.assertEqual(numbers, list(range(self.PER_THREAD)), f"thread {thread}")
        self.assertGreater(len([name for name in self.names() if name.endswith('.gz')]), 5)

    def test_compressing_and_keeping_the_newest_files_keeps_a_whole_end_of_every_thread(self):
        sink = self.make_sink(compress='gz', roll=4)
        self.assertEqual(self._write_from_threads(sink), [])
        sink.close()
        self.assertLessEqual(len(self.names()), 4)
        for thread, numbers in self._records().items():
            self.assertEqual(numbers, list(range(numbers[0], numbers[-1] + 1)), f"thread {thread} lost records in the middle")
            self.assertEqual(numbers[-1], self.PER_THREAD - 1)

    def test_enforcing_retention_from_another_thread_while_logging_is_safe(self):
        sink = self.make_sink(compress='gz', roll=5, maxAge=HOUR)
        self.assertEqual(self._write_from_threads(sink, enforce=True), [])
        sink.close()
        self.assertLessEqual(len(self.names()), 5)
        for thread, numbers in self._records().items():
            self.assertEqual(numbers, list(range(numbers[0], numbers[-1] + 1)), f"thread {thread} lost records in the middle")


class FaultySink(Sink):
    """A sink whose housekeeping fails."""

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)

    def write(self, text, record):
        pass

    def maintain(self):
        raise RuntimeError('housekeeping broke')


class TestLoggerMaintain(FileTestCase):

    def _logger(self):
        logger = Logger('maintain', logToStdout=False, logToFile=False)
        self.addCleanup(lambda: logger.clear_sinks(timeout=1))
        return logger

    def test_it_does_the_housekeeping_of_every_sink_and_names_them(self):
        logger = self._logger()
        sink = self.make_sink(maxAge=HOUR)
        logger.add_sink('files', sink)
        logger.add_sink('plain', io.StringIO())
        self.write(sink, 0, 100)
        old = [name for name in self.names() if self.path(name) != sink.path]
        for name in old:
            self.age(name, 2 * HOUR)
        self.assertEqual(logger.maintain()['files'], {'files_deleted': len(old)})
        self.assertEqual(logger.maintain()['files'], {'files_deleted': 0})
        self.assertNotIn('plain', logger.maintain())                 # a sink without housekeeping is not in the answer

    def test_it_reaches_the_file_of_the_logger_itself(self):
        logger = Logger('maintain', logToStdout=False, logFile=os.path.join(self.folder, 'own.log'), logFileMaxSize=SMALL_FILE_MEGABYTES,
                        logFileFirstNumber=0, logFileRoll=None)
        self.addCleanup(lambda: logger.sinks[FILE_SINK].close())
        for index in range(100):
            logger.info(line_of(index))
        logger.flush()
        before = len(glob.glob(os.path.join(self.folder, 'own_*.log')))
        self.assertGreater(before, 3)
        logger.set_log_file_roll(2)             # applied at the next rotation, unless housekeeping does it now
        result = logger.maintain()
        self.assertEqual(result[FILE_SINK], {'files_deleted': before - 2})
        self.assertEqual(len(glob.glob(os.path.join(self.folder, 'own_*.log'))), 2)

    def test_only_the_sinks_that_have_housekeeping_are_in_the_answer(self):
        logger = self._logger()
        logger.add_sink('plain', io.StringIO())
        # The file of the logger itself is the only one with housekeeping, even when file logging is switched off
        self.assertEqual(logger.maintain(), {FILE_SINK: {'files_deleted': 0}})

    def test_a_sink_whose_housekeeping_fails_is_reported_once_and_the_others_go_on(self):
        logger = self._logger()
        sink = self.make_sink(maxAge=HOUR)
        logger.add_sink('a faulty one', FaultySink())
        logger.add_sink('files', sink)
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            first = logger.maintain()
            second = logger.maintain()
        finally:
            sys.stderr = previous
        self.assertEqual(first['a faulty one'], {'error': 'RuntimeError'})
        self.assertEqual(second['a faulty one'], {'error': 'RuntimeError'})
        self.assertEqual(first['files'], {'files_deleted': 0})
        self.assertEqual(buffer.getvalue().count('housekeeping of sink'), 1)

    def test_a_base_sink_has_no_housekeeping(self):
        self.assertIsNone(FaultySink.__mro__[1].maintain(FaultySink()))

    def test_a_spool_drops_its_expired_segments_and_reports_it(self):
        from spool import Spool
        logger = self._logger()

        class Collector(Sink):
            SPOOL_DESTINATION = ('host',)
            host = 'h'

            def __init__(self):
                super().__init__(formatter=lambda record: record.message)

            def write(self, text, record):
                return False                    # down: everything stays in the spool

        spoolFolder = os.path.join(self.folder, 'spool')
        logger.add_sink('c', Collector(), threaded=True,
                        spool={'path': spoolFolder, 'id': 's', 'maxBytes': 10 ** 7, 'totalMaxBytes': 10 ** 8, 'segmentBytes': 800,
                               'maxAge': 5 * HOUR, 'retryBackoffBase': 30, 'retryBackoffMax': 30})
        for index in range(60):
            logger.info(line_of(index))
        slot = Spool.slots(spoolFolder)[0]
        segments = sorted(name for name in os.listdir(slot) if name.endswith('.spool'))
        self.assertGreater(len(segments), 3)
        old = time.time() - 10 * HOUR
        for name in segments[:-1]:
            os.utime(os.path.join(slot, name), (old, old))
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            result = logger.maintain()
        finally:
            sys.stderr = previous
        self.assertGreater(result['c']['spool']['dropped'], 0)
        self.assertEqual(result['c']['spool']['undeleted'], 0)
        self.assertEqual(sorted(name for name in os.listdir(slot) if name.endswith('.spool')), segments[-1:])

    def test_it_is_safe_to_call_while_threads_log(self):
        logger = self._logger()
        sink = self.make_sink(compress='gz', maxAge=HOUR, roll=6)
        logger.add_sink('files', sink)
        errors = []

        def log(index):
            try:
                for number in range(300):
                    logger.info(f"t{index}-{number:04d}" + 'x' * 80)
            except BaseException as error:
                errors.append(repr(error))

        threads = [threading.Thread(target=log, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 1.0
        while any(thread.is_alive() for thread in threads) and time.monotonic() < deadline + WAIT_SECONDS:
            logger.maintain()
        for thread in threads:
            thread.join(WAIT_SECONDS)
        self.assertEqual(errors, [])

    def test_the_documented_thread_of_your_own_works(self):
        logger = self._logger()
        sink = self.make_sink(maxAge=HOUR)
        logger.add_sink('files', sink)
        self.write(sink, 0, 100)
        old = [name for name in self.names() if self.path(name) != sink.path]
        for name in old:
            self.age(name, 2 * HOUR)

        def keep_tidy(logger, everySeconds=3600):
            stop = threading.Event()

            def run():
                while not stop.wait(everySeconds):
                    logger.maintain()

            threading.Thread(target=run, daemon=True).start()
            return stop

        stop = keep_tidy(logger, everySeconds=0.05)
        try:
            wait_until(lambda: self.names() == [os.path.basename(sink.path)], 'the thread to delete the old files')
        finally:
            stop.set()


if __name__ == '__main__':
    unittest.main()
