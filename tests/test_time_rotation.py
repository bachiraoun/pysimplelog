"""Log files that start a new file at the start of an hour, a day, a week or a month.

Run from the repo root::

    python3 -m unittest tests.test_time_rotation -v

A sink given ``rotateEvery`` names its files by date and starts a new one when a record of a later period arrives. The records here
carry the time they are given, so no test waits for a clock, and the folder holds one file per period.

* TestNames -- the name of the file for each period, and the edges of a week and a year
* TestRotation -- one file per period, the split by size inside a period, late records, a restart and a sink that wakes up late
* TestRetention -- the number of files to keep, their age and their compression
* TestOtherFiles -- files that are not of the period are left alone
* TestArguments -- wrong values, and the forms that ``logger.add`` takes
* TestClockChanges -- the change of the clock in spring and in autumn
* TestConcurrency -- threads across a boundary and processes on one file
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from record import LogRecord  # noqa: E402
from sinks import FileSink  # noqa: E402
from sink_options import build_file_sink, parse_rotation  # noqa: E402

WAIT_SECONDS = 30.0
# Largest size of a file in megabytes that holds two lines of LONG_LINE: about a thousand bytes
SMALL_FILE_MEGABYTES = 0.001
LONG_LINE = 'x' * 599 + '\n'


def stamp(year, month, day, hour=0, minute=0):
    """Returns a timezone aware time that is this wall-clock time in the zone of the machine."""
    return datetime(year, month, day, hour, minute).astimezone()


def make_record(when):
    return LogRecord.create(when, 'INFO', 'info', 10.0, 'test', 'message', 1, 1, 'MainThread')


def wait_until(condition, what, timeout=WAIT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def hold_compression_after_the_copy_exists(testCase):
    """
    Makes compression stop after the compressed file exists and before the original is deleted, until released.

    :Parameters:
        #. testCase (unittest.TestCase): The test, which gets the clean-up.

    :Returns:
        #. release (threading.Event): Set it to let the compression go on.
        #. reached (threading.Event): Set when the compression is held.
        #. held (list): Gets the path of the original that is held.
    """
    release, reached, held = threading.Event(), threading.Event(), []
    original = FileSink._compress_file
    real_remove = os.remove

    def slow_remove(target):
        # os.remove is patched for every thread, and only the compression thread is held
        if threading.current_thread().name == 'pysimplelog-file-compress' and len(held) == 0:
            held.append(target)
            reached.set()
            release.wait(10)
        real_remove(target)

    def slow_compress(sink, path):
        # The real work, with the delete of the original held back: the window where the file and its compressed copy both exist
        with mock.patch('sinks.os.remove', side_effect=slow_remove):
            original(sink, path)
    patcher = mock.patch.object(FileSink, '_compress_file', slow_compress)
    patcher.start()
    testCase.addCleanup(patcher.stop)
    testCase.addCleanup(release.set)
    return release, reached, held


class TimeRotationTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='time-rotation-')
        self.sinks = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for sink in self.sinks:
            sink.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_sink(self, startedAt=None, **options):
        """Returns a sink for ``<folder>/app_<period>.log`` that thinks it is *startedAt* when it is made."""
        arguments = dict(rotateEvery='daily')
        arguments.update(options)
        startedAt = stamp(2026, 10, 11, 8) if startedAt is None else startedAt
        with mock.patch.object(FileSink, '_now', new=lambda self: startedAt):
            sink = FileSink(os.path.join(self.folder, 'app'), **arguments)
        self.sinks.append(sink)
        return sink

    @staticmethod
    def write(sink, text, when):
        sink.write(text if text.endswith('\n') else text + '\n', make_record(when))

    def names(self):
        return sorted(os.listdir(self.folder))

    def read(self, name):
        with open(os.path.join(self.folder, name), encoding='utf-8') as stream:
            return stream.read().splitlines()


class TestNames(TimeRotationTestCase):

    def test_the_name_of_the_file_follows_the_period(self):
        cases = (('hourly', 'app_2026-10-11T08.log'), ('daily', 'app_2026-10-11.log'),
                 ('weekly', 'app_2026-W41.log'), ('monthly', 'app_2026-10.log'))
        for period, expected in cases:
            with self.subTest(period=period):
                folder = tempfile.mkdtemp(prefix='time-rotation-names-')
                self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
                with mock.patch.object(FileSink, '_now', new=lambda self: stamp(2026, 10, 11, 8, 30)):
                    sink = FileSink(os.path.join(folder, 'app'), rotateEvery=period)
                sink.write('line\n', make_record(stamp(2026, 10, 11, 8, 30)))
                sink.close()
                self.assertEqual(os.listdir(folder), [expected])

    def test_a_week_belongs_to_the_year_of_its_thursday(self):
        # 31 December 2026 and 1 January 2027 are in the same ISO week, the last one of 2026
        sink = self.make_sink(stamp(2026, 12, 31, 8), rotateEvery='weekly')
        self.write(sink, 'a', stamp(2026, 12, 31, 8))
        self.write(sink, 'b', stamp(2027, 1, 1, 8))
        self.assertEqual(self.names(), ['app_2026-W53.log'])

    def test_a_new_year_starts_a_new_day_file(self):
        sink = self.make_sink(stamp(2026, 12, 31, 23, 59))
        self.write(sink, 'a', stamp(2026, 12, 31, 23, 59))
        self.write(sink, 'b', stamp(2027, 1, 1, 0, 1))
        self.assertEqual(self.names(), ['app_2026-12-31.log', 'app_2027-01-01.log'])

    def test_the_end_of_a_month_starts_a_new_monthly_file(self):
        sink = self.make_sink(stamp(2026, 1, 31, 20), rotateEvery='monthly')
        self.write(sink, 'a', stamp(2026, 1, 31, 23, 59))
        self.write(sink, 'b', stamp(2026, 2, 1, 0, 1))
        self.assertEqual(self.names(), ['app_2026-01.log', 'app_2026-02.log'])


class TestRotation(TimeRotationTestCase):

    def test_each_day_has_its_own_file_and_nothing_is_lost(self):
        sink = self.make_sink()
        self.write(sink, 'monday 1', stamp(2026, 10, 11, 8))
        self.write(sink, 'monday 2', stamp(2026, 10, 11, 23, 59))
        self.write(sink, 'tuesday 1', stamp(2026, 10, 12, 0, 1))
        self.write(sink, 'wednesday 1', stamp(2026, 10, 13, 9))
        self.assertEqual(self.names(), ['app_2026-10-11.log', 'app_2026-10-12.log', 'app_2026-10-13.log'])
        self.assertEqual(self.read('app_2026-10-11.log'), ['monday 1', 'monday 2'])
        self.assertEqual(self.read('app_2026-10-12.log'), ['tuesday 1'])

    def test_a_day_without_records_has_no_file(self):
        sink = self.make_sink()
        self.write(sink, 'a', stamp(2026, 10, 11, 8))
        self.write(sink, 'b', stamp(2026, 10, 14, 8))
        self.assertEqual(self.names(), ['app_2026-10-11.log', 'app_2026-10-14.log'])

    def test_a_late_record_stays_in_the_current_file_and_the_files_never_go_back(self):
        sink = self.make_sink()
        self.write(sink, 'after midnight', stamp(2026, 10, 12, 0, 0))
        self.write(sink, 'late, stamped before midnight', stamp(2026, 10, 11, 23, 59))
        self.write(sink, 'after midnight again', stamp(2026, 10, 12, 0, 1))
        self.assertEqual(self.names(), ['app_2026-10-12.log'])
        self.assertEqual(len(self.read('app_2026-10-12.log')), 3)

    def test_a_split_by_size_inside_a_period_adds_a_number_and_the_next_day_starts_again(self):
        sink = self.make_sink(maxSize=SMALL_FILE_MEGABYTES)
        for index in range(3):
            self.write(sink, LONG_LINE, stamp(2026, 10, 11, 8, index))
        self.write(sink, 'next day', stamp(2026, 10, 12, 8))
        self.assertEqual(self.names(), ['app_2026-10-11.log', 'app_2026-10-11_1.log', 'app_2026-10-12.log'])
        self.assertEqual(len(self.read('app_2026-10-11.log')), 2)
        self.assertEqual(len(self.read('app_2026-10-11_1.log')), 1)

    def test_a_sink_made_again_in_the_same_period_continues_in_the_same_file(self):
        first = self.make_sink()
        self.write(first, 'before the restart', stamp(2026, 10, 11, 9))
        first.close()
        second = self.make_sink(stamp(2026, 10, 11, 10))
        self.write(second, 'after the restart', stamp(2026, 10, 11, 10))
        self.assertEqual(self.names(), ['app_2026-10-11.log'])
        self.assertEqual(self.read('app_2026-10-11.log'), ['before the restart', 'after the restart'])

    def test_a_restart_continues_the_split_numbering_of_the_period(self):
        first = self.make_sink(maxSize=SMALL_FILE_MEGABYTES)
        for index in range(3):
            self.write(first, LONG_LINE, stamp(2026, 10, 11, 8, index))
        first.close()
        second = self.make_sink(stamp(2026, 10, 11, 10), maxSize=SMALL_FILE_MEGABYTES)
        self.write(second, 'after the restart', stamp(2026, 10, 11, 10))
        self.assertEqual(self.names(), ['app_2026-10-11.log', 'app_2026-10-11_1.log'])
        self.assertEqual(len(self.read('app_2026-10-11_1.log')), 2)

    def test_a_closed_sink_that_wakes_up_in_a_later_period_starts_the_file_of_that_period(self):
        sink = self.make_sink()
        self.write(sink, 'monday', stamp(2026, 10, 11, 23, 0))
        sink.close()
        self.write(sink, 'tuesday', stamp(2026, 10, 12, 1, 0))
        self.assertEqual(self.read('app_2026-10-11.log'), ['monday'])
        self.assertEqual(self.read('app_2026-10-12.log'), ['tuesday'])

    def test_a_sink_that_starts_lazily_and_gets_its_first_record_later_uses_the_period_of_the_record(self):
        sink = self.make_sink(stamp(2026, 10, 11, 23, 59), startLazily=True)
        self.write(sink, 'first', stamp(2026, 10, 12, 0, 5))
        self.assertEqual(self.names(), ['app_2026-10-12.log'])

    def test_a_file_without_time_rotation_is_not_affected(self):
        sink = self.make_sink(rotateEvery=None)
        self.write(sink, 'a', stamp(2026, 10, 11, 8))
        self.write(sink, 'b', stamp(2026, 10, 13, 8))
        self.assertEqual(self.names(), ['app_0.log'])
        self.assertEqual(self.read('app_0.log'), ['a', 'b'])


class TestRetention(TimeRotationTestCase):

    def test_only_the_newest_files_are_kept(self):
        sink = self.make_sink(roll=3)
        for day in range(11, 17):
            self.write(sink, f'day {day}', stamp(2026, 10, day, 8))
        self.assertEqual(self.names(), ['app_2026-10-14.log', 'app_2026-10-15.log', 'app_2026-10-16.log'])

    def test_the_files_of_a_split_count_one_by_one(self):
        sink = self.make_sink(roll=3, maxSize=SMALL_FILE_MEGABYTES)
        for index in range(3):
            self.write(sink, LONG_LINE, stamp(2026, 10, 11, 8, index))
        self.write(sink, 'day 12', stamp(2026, 10, 12, 8))
        self.write(sink, 'day 13', stamp(2026, 10, 13, 8))
        self.assertEqual(self.names(), ['app_2026-10-11_1.log', 'app_2026-10-12.log', 'app_2026-10-13.log'])

    def test_a_file_older_than_the_maximum_age_is_deleted_when_a_period_ends(self):
        sink = self.make_sink(maxAge=3600)
        self.write(sink, 'old', stamp(2026, 10, 11, 8))
        oldPath = os.path.join(self.folder, 'app_2026-10-11.log')
        longAgo = time.time() - 7200
        os.utime(oldPath, (longAgo, longAgo))
        self.write(sink, 'new', stamp(2026, 10, 12, 8))
        self.assertEqual(self.names(), ['app_2026-10-12.log'])

    def test_a_file_is_compressed_when_its_period_is_over_without_any_size_limit(self):
        sink = self.make_sink(compress='gz')
        self.write(sink, 'monday', stamp(2026, 10, 11, 8))
        self.write(sink, 'tuesday', stamp(2026, 10, 12, 8))
        wait_until(lambda: self.names() == ['app_2026-10-11.log.gz', 'app_2026-10-12.log'], 'the compression of the first day')

    def test_a_compressed_file_counts_for_the_number_of_files_to_keep(self):
        sink = self.make_sink(compress='gz', roll=2)
        for day in range(11, 15):
            self.write(sink, f'day {day}', stamp(2026, 10, day, 8))
        # A file being compressed when a period starts is kept for the moment, and the next test removes it
        def only_two_remain():
            sink.enforce_retention()
            return len(self.names()) == 2

        wait_until(only_two_remain, 'the old files to go')
        self.assertTrue(self.names()[-1].startswith('app_2026-10-14'))

    def test_the_compressed_copy_of_a_file_being_compressed_is_not_deleted_by_the_count(self):
        release, reached, held = hold_compression_after_the_copy_exists(self)
        sink = self.make_sink(compress='gz', roll=2)
        for day in range(11, 15):
            self.write(sink, f'day {day}', stamp(2026, 10, day, 8))
        self.assertTrue(reached.wait(10), 'the compression did not get to the delete')
        sink.enforce_retention()
        self.assertTrue(os.path.isfile(f"{held[0]}.gz"), 'the compressed copy was deleted while its original was still being compressed')
        release.set()

    def test_the_age_does_not_delete_the_compressed_copy_of_a_file_being_compressed(self):
        release, reached, held = hold_compression_after_the_copy_exists(self)
        sink = self.make_sink(compress='gz', maxAge=3600)
        self.write(sink, 'old', stamp(2026, 10, 11, 8))
        self.write(sink, 'new', stamp(2026, 10, 12, 8))
        self.assertTrue(reached.wait(10), 'the compression did not get to the delete')
        gzPath = f"{held[0]}.gz"
        longAgo = time.time() - 7200
        os.utime(gzPath, (longAgo, longAgo))
        sink.enforce_retention()
        self.assertTrue(os.path.isfile(gzPath), 'the compressed copy was deleted while its original was still being compressed')
        release.set()

    def test_a_compressed_period_file_is_never_written_to_again_beside_its_twin(self):
        sink = self.make_sink(compress='gz')
        self.write(sink, 'monday', stamp(2026, 10, 11, 8))
        self.write(sink, 'tuesday', stamp(2026, 10, 12, 8))
        wait_until(lambda: 'app_2026-10-11.log.gz' in self.names(), 'the compression')
        again = self.make_sink(stamp(2026, 10, 11, 9), compress='gz')
        self.write(again, 'monday again', stamp(2026, 10, 11, 9))
        self.assertIn('app_2026-10-11.log.gz', self.names())
        self.assertIn('app_2026-10-11_1.log', self.names())
        self.assertEqual(self.read('app_2026-10-11_1.log'), ['monday again'])

    def test_a_temporary_file_of_a_cut_compression_is_cleaned_at_the_start(self):
        leftover = os.path.join(self.folder, 'app_2026-10-10.log.gz.tmp')
        with open(leftover, 'wb') as stream:
            stream.write(b'cut')
        self.make_sink(compress='gz')
        self.assertFalse(os.path.exists(leftover))


class TestOtherFiles(TimeRotationTestCase):

    def test_numbered_files_and_files_of_another_period_are_left_alone_and_not_counted(self):
        for name in ('app_0.log', 'app_1.log', 'app_2026-10.log', 'app_2026-W40.log', 'app.log'):
            with open(os.path.join(self.folder, name), 'w') as stream:
                stream.write('keep\n')
        sink = self.make_sink(roll=1)
        self.write(sink, 'monday', stamp(2026, 10, 11, 8))
        self.write(sink, 'tuesday', stamp(2026, 10, 12, 8))
        self.assertEqual(self.names(), ['app.log', 'app_0.log', 'app_1.log', 'app_2026-10-12.log', 'app_2026-10.log', 'app_2026-W40.log'])


class TestArguments(TimeRotationTestCase):

    def test_a_wrong_period_is_refused(self):
        with self.assertRaises(ValueError):
            FileSink(os.path.join(self.folder, 'app'), rotateEvery='fortnightly')
        for wrong in (3, True, ['daily']):
            with self.subTest(wrong=wrong):
                with self.assertRaises(TypeError):
                    FileSink(os.path.join(self.folder, 'app'), rotateEvery=wrong)

    def test_compress_needs_a_size_or_a_period(self):
        with self.assertRaises(ValueError):
            FileSink(os.path.join(self.folder, 'app'), compress='gz')
        sink = FileSink(os.path.join(self.folder, 'app'), compress='gz', rotateEvery='daily')
        self.sinks.append(sink)
        sink.set_compress(None)
        sink.set_compress('gz')
        sink.set_max_size(None)

    def test_the_forms_of_rotation(self):
        self.assertEqual(parse_rotation('daily'), ('daily', None))
        self.assertEqual(parse_rotation(' Weekly '), ('weekly', None))
        self.assertEqual(parse_rotation('500 MB'), (None, 500.0))
        self.assertEqual(parse_rotation(10), (None, 10.0))
        self.assertEqual(parse_rotation(('daily', '1 GB')), ('daily', 1024.0))

    def test_a_wrong_rotation_says_what_is_accepted(self):
        for wrong in ('dayly', '00:00', ('daily',), ('500 MB', 'daily'), ('daily', 'big')):
            with self.subTest(wrong=wrong):
                with self.assertRaises(ValueError) as context:
                    parse_rotation(wrong)
                self.assertTrue(len(str(context.exception)) > 0)
        with self.assertRaisesRegex(ValueError, "daily"):
            parse_rotation('dayly')

    def test_logger_add_takes_a_period_or_a_period_with_a_size(self):
        logger = Logger('rot', logToFile=False, logToStdout=False)
        logger.add(os.path.join(self.folder, 'a.log'), rotation='daily', retention=5, compression='gz', name='a')
        logger.add(os.path.join(self.folder, 'b.log'), rotation=('hourly', '10 MB'), name='b')
        logger.info('hello')
        logger.remove('a')
        logger.remove('b')
        today = datetime.now().astimezone()
        self.assertIn(f"a_{today.strftime('%Y-%m-%d')}.log", self.names())
        self.assertIn(f"b_{today.strftime('%Y-%m-%dT%H')}.log", self.names())

    def test_retention_is_accepted_with_a_period_and_still_refused_without_rotation(self):
        build_file_sink(os.path.join(self.folder, 'a.log'), 'text', 'daily', '30 days', None)
        with self.assertRaises(ValueError):
            build_file_sink(os.path.join(self.folder, 'b.log'), 'text', None, '30 days', None)


class TestClockChanges(TimeRotationTestCase):

    def setUp(self):
        super().setUp()
        if not hasattr(time, 'tzset'):
            self.skipTest('the zone of the process cannot be changed on this system')
        try:
            from zoneinfo import ZoneInfo
            self.zone = ZoneInfo('America/New_York')
        except Exception:
            self.skipTest('no time zone data on this system')
        self.addCleanup(self._restore_zone, os.environ.get('TZ'))
        os.environ['TZ'] = 'America/New_York'
        time.tzset()

    @staticmethod
    def _restore_zone(previous):
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        time.tzset()

    def test_the_hour_that_does_not_exist_in_spring_has_no_file(self):
        sink = self.make_sink(datetime(2026, 3, 8, 1, 0, tzinfo=self.zone), rotateEvery='hourly')
        self.write(sink, 'before', datetime(2026, 3, 8, 1, 30, tzinfo=self.zone))
        self.write(sink, 'after', datetime(2026, 3, 8, 3, 30, tzinfo=self.zone))
        self.assertEqual(self.names(), ['app_2026-03-08T01.log', 'app_2026-03-08T03.log'])

    def test_the_hour_that_happens_twice_in_autumn_stays_in_one_file(self):
        sink = self.make_sink(datetime(2026, 11, 1, 0, 0, tzinfo=self.zone), rotateEvery='hourly')
        self.write(sink, 'first time', datetime(2026, 11, 1, 1, 30, fold=0, tzinfo=self.zone))
        self.write(sink, 'second time', datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=self.zone))
        self.write(sink, 'next hour', datetime(2026, 11, 1, 2, 30, tzinfo=self.zone))
        self.assertEqual(self.names(), ['app_2026-11-01T01.log', 'app_2026-11-01T02.log'])
        self.assertEqual(self.read('app_2026-11-01T01.log'), ['first time', 'second time'])

    def test_a_day_of_twenty_three_or_twenty_five_hours_is_still_one_file(self):
        sink = self.make_sink(datetime(2026, 3, 8, 0, 0, tzinfo=self.zone))
        self.write(sink, 'a', datetime(2026, 3, 8, 0, 5, tzinfo=self.zone))
        self.write(sink, 'b', datetime(2026, 3, 8, 23, 55, tzinfo=self.zone))
        self.write(sink, 'c', datetime(2026, 3, 9, 0, 5, tzinfo=self.zone))
        self.assertEqual(self.names(), ['app_2026-03-08.log', 'app_2026-03-09.log'])
        self.assertEqual(self.read('app_2026-03-08.log'), ['a', 'b'])


CHILD_SCRIPT = """
import sys, datetime
sys.path.insert(0, {root!r})
from sinks import FileSink
from record import LogRecord
sink = FileSink({base!r}, rotateEvery='daily')
for index in range({count}):
    record = LogRecord.create(datetime.datetime.now(datetime.timezone.utc), 'INFO', 'info', 10.0, 'test', 'm', 1, 1, 'MainThread')
    sink.write('process {number} line %05d ' % index + 'y' * 80 + '\\n', record)
sink.close()
"""


class TestConcurrency(TimeRotationTestCase):

    def test_threads_across_a_boundary_lose_and_repeat_nothing_and_the_days_do_not_mix(self):
        sink = self.make_sink(startedAt=stamp(2026, 10, 11, 8))
        threads, perThread = 8, 200

        def work(index):
            for sequence in range(perThread):
                day = 11 if sequence < perThread // 2 else 12
                self.write(sink, f't{index}-{sequence}', stamp(2026, 10, day, 12))

        workers = [threading.Thread(target=work, args=(index,)) for index in range(threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(WAIT_SECONDS)
        lines = self.read('app_2026-10-11.log') + self.read('app_2026-10-12.log')
        self.assertEqual(len(lines), threads * perThread)
        self.assertEqual(len(set(lines)), threads * perThread)
        # A record of the second day is never written before the first day is over
        for line in self.read('app_2026-10-11.log'):
            self.assertLess(int(line.split('-')[1]), perThread)

    @unittest.skipIf(os.name == 'nt', 'several processes cannot safely append to one file on Windows')
    def test_several_processes_on_one_daily_file_tear_no_line(self):
        root = os.path.join(os.path.dirname(__file__), '..')
        base = os.path.join(self.folder, 'shared')
        children = [subprocess.Popen([sys.executable, '-c', CHILD_SCRIPT.format(root=root, base=base, count=250, number=number)])
                    for number in range(4)]
        for child in children:
            self.assertEqual(child.wait(WAIT_SECONDS), 0)
        names = [name for name in os.listdir(self.folder) if name.startswith('shared_')]
        self.assertEqual(len(names), 1)
        lines = self.read(names[0])
        self.assertEqual(len(lines), 1000)
        for line in lines:
            self.assertRegex(line, r'^process \d line \d{5} y{80}$')


if __name__ == '__main__':
    unittest.main()
