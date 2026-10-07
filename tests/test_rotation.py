"""Log files that rotate while many threads write to them and while their settings are changed.

Run from the repo root::

    python3 -m unittest tests.test_rotation -v

A log file that is limited in size is closed and a new one started in the middle of the stream of records. Nothing may be
lost, repeated or cut in two when that happens, whoever else is writing, and changing the limit, the number of files to keep,
the flush mode or the file itself at the same moment must be safe. Every case here writes a few thousand records from
several threads and then reads the files back, one line at a time.
"""
import glob
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger, FILE_SINK  # noqa: E402
from sinks import FileSink  # noqa: E402

# Seconds a thread may take before the test is taken to be stuck
WAIT_SECONDS = 30.0
# A line of the log file, written by the default format: the time, the name of the logger, the severity, and the message
LINE = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d - rot <INFO> t(\d+)-(\d+)$')
# Largest size of a file in megabytes for the cases that must rotate often: about ten thousand bytes
SMALL_FILE_MEGABYTES = 0.01
SMALL_FILE_BYTES = int(SMALL_FILE_MEGABYTES * 1024 ** 2)


class RotationTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='rotation-')
        self.loggers = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for logger in self.loggers:
            logger.sinks[FILE_SINK].close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_logger(self, name='rot', **options):
        """Returns a logger that writes only to files named ``<name>_<N>.log`` in the folder of the test."""
        arguments = dict(logToStdout=False, logFile=os.path.join(self.folder, f'{name}.log'), logFileMaxSize=SMALL_FILE_MEGABYTES,
                         logFileFirstNumber=0, logFileRoll=None)
        arguments.update(options)
        logger = Logger('rot', **arguments)
        self.loggers.append(logger)
        return logger

    def files(self, name='rot'):
        """Returns the paths of the files of a logger, the oldest first."""
        found = []
        for path in glob.glob(os.path.join(self.folder, f'{name}_*.log')):
            match = re.search(rf'{re.escape(name)}_(\d+)\.log$', path)
            found.append((int(match.group(1)), path))
        return [path for _, path in sorted(found)]

    def read_all(self, name='rot'):
        """
        Reads every line of every file, the oldest file first.

        :Returns:
            #. records (list): Tuples ``(thread, sequence)``, in the order they are in the files.
        """
        records = []
        for path in self.files(name):
            with open(path, encoding='utf-8') as stream:
                for number, line in enumerate(stream, 1):
                    match = LINE.match(line.rstrip('\n'))
                    self.assertIsNotNone(match, f"{os.path.basename(path)} line {number} is not a whole record: {line!r}")
                    records.append((int(match.group(1)), int(match.group(2))))
        return records

    @staticmethod
    def run_threads(count, work):
        """Runs *work(index)* in *count* threads and returns the errors they raised, failing when one is stuck."""
        errors = []

        def guarded(index):
            try:
                work(index)
            except BaseException as error:           # any failure is what the test is looking for
                errors.append(repr(error))

        threads = [threading.Thread(target=guarded, args=(index,)) for index in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT_SECONDS)
            if thread.is_alive():
                errors.append('a thread is stuck')
        return errors

    def assert_each_thread_in_order(self, records):
        """Checks that the records of one thread are in the order that thread wrote them."""
        last = {}
        for thread, sequence in records:
            self.assertGreater(sequence, last.get(thread, -1), f"thread {thread} record {sequence} is out of order or repeated")
            last[thread] = sequence


class TestManyThreadsAcrossRotations(RotationTestCase):

    THREADS, PER_THREAD = 8, 400

    def _write(self, logger):
        def work(index):
            for sequence in range(self.PER_THREAD):
                logger.info(f't{index}-{sequence}')

        return self.run_threads(self.THREADS, work)

    def test_nothing_is_lost_repeated_or_cut_across_many_rotations(self):
        logger = self.make_logger()
        self.assertEqual(self._write(logger), [])
        logger.flush()
        records = self.read_all()
        self.assertGreater(len(self.files()), 5, 'the test must rotate many times to mean anything')
        self.assertEqual(len(records), self.THREADS * self.PER_THREAD)
        self.assertEqual(len(set(records)), len(records))
        self.assert_each_thread_in_order(records)

    def test_a_file_exceeds_the_limit_by_at_most_one_record(self):
        logger = self.make_logger()
        self._write(logger)
        logger.flush()
        longest = 0
        for path in self.files():
            with open(path, 'rb') as stream:
                longest = max(longest, max(len(line) for line in stream))
        for path in self.files():
            self.assertLessEqual(os.path.getsize(path), SMALL_FILE_BYTES + longest, os.path.basename(path))

    def test_the_files_are_numbered_without_gaps(self):
        logger = self.make_logger()
        self._write(logger)
        logger.flush()
        numbers = [int(re.search(r'_(\d+)\.log$', path).group(1)) for path in self.files()]
        self.assertEqual(numbers, list(range(numbers[0], numbers[0] + len(numbers))))
        self.assertEqual(numbers[0], 0)

    def test_with_a_limit_on_the_files_kept_the_oldest_go_and_each_thread_keeps_a_whole_end(self):
        logger = self.make_logger(logFileRoll=3)
        self.assertEqual(self._write(logger), [])
        logger.flush()
        self.assertLessEqual(len(self.files()), 3)
        records = self.read_all()
        self.assert_each_thread_in_order(records)
        # The oldest files were deleted, so what is left of each thread is its latest records, with nothing missing in between
        kept = {}
        for thread, sequence in records:
            kept.setdefault(thread, []).append(sequence)
        for thread, sequences in kept.items():
            self.assertEqual(sequences, list(range(sequences[0], sequences[-1] + 1)), f"thread {thread} lost records in the middle")
            self.assertEqual(sequences[-1], self.PER_THREAD - 1, f"thread {thread} lost its latest records")

    def test_the_enqueue_mode_writes_everything_once_flush_returns(self):
        logger = self.make_logger(enqueue=True)
        self.assertEqual(self._write(logger), [])
        logger.flush()
        records = self.read_all()
        self.assertEqual(len(records), self.THREADS * self.PER_THREAD)
        self.assertEqual(len(set(records)), len(records))
        self.assert_each_thread_in_order(records)

    def test_a_file_sink_of_a_thread_of_its_own_writes_everything_when_it_is_removed(self):
        logger = Logger('rot', logToStdout=False, logToFile=False)
        sink = FileSink(os.path.join(self.folder, 'rot'), 'log', formatter='text', maxSize=SMALL_FILE_MEGABYTES, firstNumber=0)
        # A full queue would drop records, which is its default and not what is under test, so it waits instead
        logger.add_sink('f', sink, threaded=True, threadQueuePolicy='block')
        self.addCleanup(sink.close)
        self.assertEqual(self.run_threads(4, lambda index: [logger.info(f't{index}-{n}') for n in range(300)]), [])
        logger.remove_sink('f', timeout=WAIT_SECONDS)
        records = []
        for path in self.files():
            with open(path, encoding='utf-8') as stream:
                records += [line.rstrip('\n').rsplit(' ', 1)[1] for line in stream if line.strip()]
        self.assertEqual(len(records), 4 * 300)
        self.assertEqual(len(set(records)), len(records))


class TestRotationRules(RotationTestCase):

    def test_with_one_thread_the_files_are_exactly_the_last_ones(self):
        logger = self.make_logger(logFileRoll=3)
        for sequence in range(2000):
            logger.info(f't0-{sequence}')
        logger.flush()
        numbers = [int(re.search(r'_(\d+)\.log$', path).group(1)) for path in self.files()]
        self.assertEqual(len(numbers), 3)
        self.assertEqual(numbers, list(range(numbers[0], numbers[0] + 3)))
        self.assertGreater(numbers[0], 0, 'older files must have been deleted')
        records = self.read_all()
        self.assertEqual(records[-1], (0, 1999))

    def test_lowering_the_number_of_files_to_keep_deletes_the_surplus_at_the_next_rotation(self):
        logger = self.make_logger()
        for sequence in range(1500):
            logger.info(f't0-{sequence}')
        logger.flush()
        self.assertGreater(len(self.files()), 5)
        logger.set_log_file_roll(2)
        for sequence in range(1500, 3000):
            logger.info(f't0-{sequence}')
        logger.flush()
        self.assertLessEqual(len(self.files()), 2)
        self.assertEqual(self.read_all()[-1], (0, 2999))

    def test_raising_or_removing_the_limit_on_the_files_keeps_what_there_is(self):
        logger = self.make_logger(logFileRoll=2)
        for sequence in range(1500):
            logger.info(f't0-{sequence}')
        logger.flush()
        self.assertLessEqual(len(self.files()), 2)
        logger.set_log_file_roll(None)
        kept = len(self.files())
        for sequence in range(1500, 3000):
            logger.info(f't0-{sequence}')
        logger.flush()
        self.assertGreater(len(self.files()), kept)

    def test_without_a_limit_on_the_size_one_file_holds_everything(self):
        logger = self.make_logger(logFileMaxSize=None)
        for sequence in range(300):
            logger.info(f't0-{sequence}')
        logger.flush()
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(len(self.read_all()), 300)

    def test_a_logger_started_again_continues_in_the_newest_file_and_keeps_the_numbering(self):
        first = self.make_logger()
        for sequence in range(300):
            first.info(f't0-{sequence}')
        first.flush()
        first.sinks[FILE_SINK].close()
        before = self.files()
        second = self.make_logger()
        for sequence in range(300, 600):
            second.info(f't0-{sequence}')
        second.flush()
        after = self.files()
        self.assertEqual(after[:len(before)], before)
        self.assertGreaterEqual(len(after), len(before))
        records = self.read_all()
        self.assertEqual(len(records), 600)
        self.assert_each_thread_in_order(records)


class TestChangingSettingsWhileLogging(RotationTestCase):

    def _change_until_done(self, logger, changes, duration=1.5):
        """Returns a function for a thread that applies *changes* one after the other, in a loop, for some time."""
        def work(index):
            deadline = time.monotonic() + duration
            count = 0
            while time.monotonic() < deadline:
                changes[count % len(changes)](logger)
                count += 1
        return work

    def _log_until_done(self, logger, duration=1.5):
        """Returns a function for a thread that logs records, numbered, until the time is up."""
        counts = {}

        def work(index):
            sequence = 0
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                logger.info(f't{index}-{sequence}')
                sequence += 1
            counts[index] = sequence

        return work, counts

    def test_changing_the_size_the_number_of_files_and_the_flush_mode_while_logging(self):
        logger = self.make_logger()
        write, counts = self._log_until_done(logger)
        changes = [lambda l: l.set_log_file_maximum_size(0.005), lambda l: l.set_log_file_maximum_size(0.02),
                   lambda l: l.set_log_file_roll(None), lambda l: l.set_log_file_roll(4),
                   lambda l: l.set_log_file_maximum_size(None), lambda l: l.set_log_file_maximum_size(0.01),
                   lambda l: l.flush(), lambda l: l.set_log_file_first_number(0)]
        change = self._change_until_done(logger, changes)

        def work(index):
            (change if index == 4 else write)(index)

        errors = self.run_threads(5, work)
        logger.flush()
        self.assertEqual(errors, [])
        records = self.read_all()                       # every line that is there is a whole record
        self.assertGreater(len(records), 0)
        self.assert_each_thread_in_order(records)

    def test_changing_the_file_itself_while_logging_loses_nothing(self):
        logger = self.make_logger(name='a')
        write, counts = self._log_until_done(logger)
        folder = self.folder
        changes = [lambda l: l.set_log_file_basename(os.path.join(folder, 'b')),
                   lambda l: l.set_log_file_basename(os.path.join(folder, 'a'))]
        change = self._change_until_done(logger, changes)
        errors = self.run_threads(5, lambda index: (change if index == 4 else write)(index))
        logger.flush()
        self.assertEqual(errors, [])
        both = self.read_all('a') + self.read_all('b')
        self.assertEqual(len(both), sum(counts.values()))
        self.assertEqual(len(set(both)), len(both))

    def test_turning_the_file_off_and_on_while_logging_never_repeats_or_cuts_a_record(self):
        logger = self.make_logger()
        write, counts = self._log_until_done(logger)
        change = self._change_until_done(logger, [lambda l: l.set_log_to_file_flag(False), lambda l: l.set_log_to_file_flag(True)])
        errors = self.run_threads(5, lambda index: (change if index == 4 else write)(index))
        logger.flush()
        self.assertEqual(errors, [])
        records = self.read_all()
        self.assertEqual(len(set(records)), len(records))
        self.assertLessEqual(len(records), sum(counts.values()))
        self.assert_each_thread_in_order(records)


if __name__ == '__main__':
    unittest.main()
