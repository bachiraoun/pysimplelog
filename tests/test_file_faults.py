"""What a file sink does when the disk, the folder, a compression or another process misbehaves.

Run from the repo root::

    python3 -m unittest tests.test_file_faults -v

What these tests establish, and the limit of each claim:

* A write that fails, for a full disk or a missing permission, never raises in the thread that logs. The record is counted in the
  statistics of the sink and the answer of the sink says it was not delivered. The sink writes again when the cause is gone.
* A file removed, or renamed, by another program is not noticed: the sink keeps its own open file until the next rotation. These tests
  pin that, because it is the same for every writer that keeps a file open, and a person who rotates logs from outside should know it.
* A compression that fails, or a process that dies in the middle of one, leaves the original file and no half-made compressed file.
* Several processes, each with a sink of its own on the same name, lose no line and tear none. Their files can interleave.
* A sink that is closed while threads write loses no record that it said it delivered.

Every case that starts a process runs it as a script with a time limit, so a hang is a failure and not a test run that never ends.
"""
import contextlib
import errno
import glob
import gzip
import io
import os
import re
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
import sinks as sinks_module  # noqa: E402
from simple_log import Logger  # noqa: E402
from sinks import FileSink, DELIVERED, RETRY  # noqa: E402
from record import LogRecord  # noqa: E402

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Seconds a test waits for something that must happen, and a script may run
WAIT_SECONDS = 15.0
SCRIPT_SECONDS = 120
# Largest size of a file in megabytes: about two thousand bytes, some twenty records
SMALL_FILE_MEGABYTES = 0.002
CAN_CHANGE_PERMISSIONS = os.name != 'nt' and not (hasattr(os, 'geteuid') and os.geteuid() == 0)

LINE_RE = re.compile(r'^[a-z0-9]+-?\d+x+$')


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


class ScriptedStream(io.BytesIO):
    """A file that refuses to write while *isFull* is true, as a full disk does."""

    isFull = False

    def write(self, data):
        if self.isFull:
            raise OSError(errno.ENOSPC, 'No space left on device')
        return super().write(data)


class FaultTestCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='faults-')
        self.sinks = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        # A test that took the permissions away must give them back, or the folder cannot be removed
        if os.path.isdir(self.folder):
            os.chmod(self.folder, 0o700)
        for sink in self.sinks:
            sink.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_sink(self, **options):
        sink = FileSink(os.path.join(self.folder, 'app'), 'log', formatter=lambda record: record.message, **options)
        self.sinks.append(sink)
        return sink

    def deliver(self, sink, text):
        """Delivers one record and returns the answer of the sink. The warning that a failure prints is not shown."""
        with contextlib.redirect_stderr(io.StringIO()):
            return sink.deliver(make_record(text))

    def read_lines(self):
        """Returns the text of every record in every file, plain or compressed, without a trace of the order."""
        found = []
        for path in glob.glob(os.path.join(self.folder, 'app_*.log*')):
            if path.endswith('.tmp'):
                continue
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'rt', encoding='utf-8') as stream:
                found.extend(stream.read().split())
        return found

    def names(self):
        return sorted(os.path.basename(path) for path in glob.glob(os.path.join(self.folder, '*')))

    def run_script(self, source, *arguments):
        script = source.replace('@PACKAGE@', PACKAGE_DIR)
        return subprocess.run([sys.executable, '-c', script, *map(str, arguments)], capture_output=True, text=True,
                              timeout=SCRIPT_SECONDS)


class TestDiskFull(FaultTestCase):

    def full_sink(self):
        sink = self.make_sink()
        stream = ScriptedStream()
        stream.isFull = True
        sink._open_stream = lambda: stream
        return sink, stream

    def test_a_full_disk_is_counted_and_never_raised(self):
        sink, _ = self.full_sink()
        self.assertEqual(self.deliver(sink, 'lost'), RETRY)
        self.assertEqual(sink.stats['failed'], 1)
        self.assertEqual(sink.stats['processed'], 0)
        self.assertIsInstance(sink.stats['last_error'], OSError)
        self.assertEqual(sink.stats['last_error'].errno, errno.ENOSPC)

    def test_every_failure_is_counted(self):
        sink, _ = self.full_sink()
        for _ in range(5):
            self.assertEqual(self.deliver(sink, 'lost'), RETRY)
        self.assertEqual(sink.stats['failed'], 5)

    def test_the_sink_writes_again_when_there_is_room(self):
        sink, stream = self.full_sink()
        self.assertEqual(self.deliver(sink, 'while-full'), RETRY)
        stream.isFull = False
        self.assertEqual(self.deliver(sink, 'with-room'), DELIVERED)
        self.assertEqual(stream.getvalue(), b'with-room\n')
        self.assertEqual((sink.stats['failed'], sink.stats['processed']), (1, 1))

    def test_a_logger_does_not_raise_for_a_full_disk(self):
        logger = Logger('t', logToStdout=False, logToFile=False)
        sink, _ = self.full_sink()
        logger.add_sink('file', sink)
        self.addCleanup(lambda: logger.clear_sinks(timeout=1))
        with contextlib.redirect_stderr(io.StringIO()) as warning:
            logger.info("hello")
        self.assertEqual(logger.sink_stats('file')['delivery']['failed'], 1)
        self.assertIn('sink_stats', warning.getvalue())


@unittest.skipUnless(CAN_CHANGE_PERMISSIONS, 'needs permissions that can be taken away, and a user that is not root')
class TestPermissions(FaultTestCase):

    def test_a_folder_that_cannot_be_written_is_counted_and_the_sink_recovers(self):
        sink = self.make_sink()
        os.chmod(self.folder, 0o500)
        self.assertEqual(self.deliver(sink, 'refused'), RETRY)
        self.assertEqual(sink.stats['failed'], 1)
        self.assertIsInstance(sink.stats['last_error'], PermissionError)
        os.chmod(self.folder, 0o700)
        self.assertEqual(self.deliver(sink, 'accepted'), DELIVERED)
        self.assertEqual(self.read_lines(), ['accepted'])

    def test_a_refusal_when_a_file_is_rotated_loses_no_record_that_was_delivered(self):
        sink = self.make_sink(maxSize=SMALL_FILE_MEGABYTES, firstNumber=0)
        delivered, refused = [], 0
        for index in range(15):
            self.assertEqual(self.deliver(sink, line_of(index)), DELIVERED)
            delivered.append(line_of(index))
        os.chmod(self.folder, 0o500)
        # The file that is open takes records until it is full, then the new file cannot be made
        for index in range(15, 60):
            if self.deliver(sink, line_of(index)) == DELIVERED:
                delivered.append(line_of(index))
            else:
                refused += 1
        self.assertGreater(refused, 0)
        os.chmod(self.folder, 0o700)
        for index in range(60, 70):
            self.assertEqual(self.deliver(sink, line_of(index)), DELIVERED)
            delivered.append(line_of(index))
        sink.close()
        self.assertEqual(sorted(self.read_lines()), sorted(delivered))


@unittest.skipIf(os.name == 'nt', 'Windows does not let another program rename or delete a file that is open')
class TestChangesFromOutside(FaultTestCase):
    """Pins what happens when another program renames or removes the log, as a rotation by another tool does."""

    def test_set_path_after_an_outside_rename_opens_a_new_file(self):
        # The way the documentation tells to rotate from outside
        sink = self.make_sink()
        self.assertEqual(self.deliver(sink, 'before'), DELIVERED)
        renamed = sink.path + '.rotated'
        os.rename(sink.path, renamed)
        sink.set_path(os.path.join(self.folder, 'app'), 'log')
        self.assertEqual(self.deliver(sink, 'after'), DELIVERED)
        sink.flush()
        with open(renamed) as stream:
            self.assertEqual(stream.read().split(), ['before'])
        with open(sink.path) as stream:
            self.assertEqual(stream.read().split(), ['after'])

    def test_an_external_rename_keeps_writing_to_the_renamed_file(self):
        sink = self.make_sink()
        self.assertEqual(self.deliver(sink, 'before'), DELIVERED)
        renamed = sink.path + '.rotated'
        os.rename(sink.path, renamed)
        self.assertEqual(self.deliver(sink, 'after'), DELIVERED)
        sink.flush()
        self.assertFalse(os.path.exists(sink.path))
        with open(renamed) as stream:
            self.assertEqual(stream.read().split(), ['before', 'after'])

    def test_records_written_after_the_folder_was_removed_are_not_on_the_disk(self):
        sink = self.make_sink(maxSize=SMALL_FILE_MEGABYTES, firstNumber=0)
        self.assertEqual(self.deliver(sink, line_of(0)), DELIVERED)
        shutil.rmtree(self.folder)
        # The open file still takes records, but nobody can read it, and the sink does not know
        self.assertEqual(self.deliver(sink, line_of(1)), DELIVERED)
        self.assertFalse(os.path.exists(self.folder))

    def test_the_folder_is_made_again_at_the_next_rotation(self):
        sink = self.make_sink(maxSize=SMALL_FILE_MEGABYTES, firstNumber=0)
        self.assertEqual(self.deliver(sink, line_of(0)), DELIVERED)
        shutil.rmtree(self.folder)
        for index in range(1, 60):
            self.assertEqual(self.deliver(sink, line_of(index)), DELIVERED)
        self.assertTrue(os.path.isdir(self.folder))
        found = self.read_lines()
        self.assertIn(line_of(59), found)
        # The first record and the ones written into the removed file before the rotation are gone, and nothing said so
        self.assertNotIn(line_of(0), found)
        self.assertLess(len(found), 59)


class TestCompressionFaults(FaultTestCase):

    def make_compressing_sink(self):
        return self.make_sink(maxSize=SMALL_FILE_MEGABYTES, firstNumber=0, compress='gz')

    def write(self, sink, count):
        for index in range(count):
            sink.emit(make_record(line_of(index)))

    def test_a_failure_in_the_middle_of_a_copy_keeps_the_original_and_removes_the_temporary_file(self):
        def breaks_after_some_bytes(source, target, length=0):
            target.write(source.read(10))
            raise OSError(errno.ENOSPC, 'No space left on device')

        with contextlib.redirect_stderr(io.StringIO()):
            with mock.patch.object(sinks_module.shutil, 'copyfileobj', side_effect=breaks_after_some_bytes):
                sink = self.make_compressing_sink()
                self.write(sink, 60)
                wait_until(lambda: sink.stats['compress_failed'] >= 1 and compression_threads() == [], 'the failures')
        names = self.names()
        self.assertEqual([name for name in names if name.endswith('.tmp') or name.endswith('.gz')], [])
        self.assertGreater(len([name for name in names if re.fullmatch(r'app_\d+\.log', name)]), 1)
        self.assertEqual(sorted(self.read_lines()), sorted(line_of(index) for index in range(60)))

    def test_the_compression_is_tried_again_when_the_cause_is_gone(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with mock.patch.object(sinks_module.shutil, 'copyfileobj', side_effect=OSError(errno.ENOSPC, 'No space left on device')):
                sink = self.make_compressing_sink()
                self.write(sink, 60)
                wait_until(lambda: sink.stats['compress_failed'] >= 1 and compression_threads() == [], 'the failures')
        sink.enforce_retention()
        wait_until(lambda: sink.stats['files_compressed'] >= 1 and compression_threads() == [], 'the compression')
        self.assertEqual(sorted(self.read_lines()), sorted(line_of(index) for index in range(60)))

    def test_a_temporary_file_left_by_a_killed_compression_is_removed_at_start(self):
        with open(os.path.join(self.folder, 'app_0.log'), 'w') as stream:
            stream.write(line_of(0) + '\n')
        with open(os.path.join(self.folder, 'app_0.log.gz.tmp'), 'wb') as stream:
            stream.write(b'half of a compressed file')
        sink = self.make_compressing_sink()
        wait_until(lambda: compression_threads() == [], 'the compression thread to end')
        self.assertEqual([name for name in self.names() if name.endswith('.tmp')], [])
        self.assertEqual(self.read_lines(), [line_of(0)])
        sink.close()

    def test_a_process_that_dies_in_the_middle_of_a_compression_leaves_the_original_whole(self):
        dying = '''
import os
import sys
sys.path.insert(0, "@PACKAGE@")
from datetime import datetime, timezone
import sinks
from sinks import FileSink
from record import LogRecord

def die(source, target, length=0):
    target.write(source.read(10))
    os._exit(9)

sinks.shutil.copyfileobj = die
sink = FileSink(sys.argv[1] + "/app", "log", formatter=lambda record: record.message, maxSize=0.002, firstNumber=0, compress="gz")
for number in range(200):
    text = "r%05d" % number + "x" * 90
    sink.emit(LogRecord.create(datetime.now(timezone.utc), "INFO", "info", 10.0, "test", text, 1, 1, "MainThread"))
sink.close()
'''
        result = self.run_script(dying, self.folder)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertNotEqual(glob.glob(os.path.join(self.folder, '*.tmp')), [], 'the script did not reach the compression')
        sink = self.make_compressing_sink()
        wait_until(lambda: compression_threads() == [], 'the compression thread to end')
        self.assertEqual([name for name in self.names() if name.endswith('.tmp')], [])
        found = self.read_lines()
        self.assertGreater(len(found), 0)
        self.assertEqual(len(found), len(set(found)), 'a record is in two files')
        for text in found:
            self.assertRegex(text, r'^r\d{5}x{90}$')
        sink.close()


@unittest.skipIf(os.name == 'nt', 'several processes cannot safely append to one file on Windows, see test_concurrency_matrix')
class TestManyProcesses(FaultTestCase):

    def test_processes_rotating_one_name_lose_no_line_and_tear_none(self):
        writing = '''
import sys
sys.path.insert(0, "@PACKAGE@")
from datetime import datetime, timezone
from sinks import FileSink, DELIVERED
from record import LogRecord

index, folder, count = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
sink = FileSink(folder + "/app", "log", formatter=lambda record: record.message, maxSize=0.002, firstNumber=0)
for number in range(count):
    text = "p%d-%04d" % (index, number) + "x" * 80
    answer = sink.deliver(LogRecord.create(datetime.now(timezone.utc), "INFO", "info", 10.0, "test", text, 1, 1, "MainThread"))
    if answer != DELIVERED:
        sys.exit(3)
sink.close()
'''
        processes, count = 4, 250
        script = writing.replace('@PACKAGE@', PACKAGE_DIR)
        children = [subprocess.Popen([sys.executable, '-c', script, str(index), self.folder, str(count)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for index in range(processes)]
        for child in children:
            _, error = child.communicate(timeout=SCRIPT_SECONDS)
            self.assertEqual(child.returncode, 0, error)
        found = self.read_lines()
        expected = [f"p{index}-{number:04d}" + 'x' * 80 for index in range(processes) for number in range(count)]
        for text in found:
            self.assertRegex(text, r'^p\d-\d{4}x{80}$')
        self.assertEqual(len(found), len(set(found)), 'a record is in two files')
        self.assertEqual(sorted(found), sorted(expected))
        self.assertGreater(len(glob.glob(os.path.join(self.folder, 'app_*.log'))), 1, 'the files were never rotated')


class TestShutdown(FaultTestCase):

    def test_closing_while_threads_write_loses_no_record_that_was_delivered(self):
        sink = self.make_sink(maxSize=SMALL_FILE_MEGABYTES, firstNumber=0)
        results, errors = [], []
        lock = threading.Lock()

        def write(index):
            try:
                for number in range(300):
                    answer = sink.deliver(make_record(f"t{index}-{number:04d}" + 'x' * 80))
                    with lock:
                        results.append(answer)
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=write, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        while any(thread.is_alive() for thread in threads):
            sink.close()
            time.sleep(0.002)
        for thread in threads:
            thread.join()
        sink.close()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1200)
        found = self.read_lines()
        self.assertEqual(len(found), results.count(DELIVERED))
        self.assertEqual(len(found), len(set(found)), 'a record is in two files')


if __name__ == '__main__':
    unittest.main()
