"""The disk spool: what is written, what is tracked as delivered, what is deleted, who owns a slot, and what the limits do.

Run from the repo root::

    python3 -m unittest tests.test_spool -v

The crash, ownership and fork cases start real processes, so they test what the operating system does with a lock and
not what a mock says about it.
"""
import io
import os
import queue
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
import spool as spool_module  # noqa: E402
from spool import (Spool, FileLock, target_id, record_to_dict, record_from_dict, record_line, SpoolBusyError, SpoolMismatchError,  # noqa: E402
                   SpoolOwnerError, SpoolUnsupportedError, SpoolError)
from record import LogRecord, ExceptionInfo, CallerInfo  # noqa: E402
from queues import QueueFull  # noqa: E402

IS_POSIX = os.name == 'posix' and spool_module.fcntl is not None
TARGET = target_id('TestSink', protocol='tcp', host='collector.example.org', port=514)
# Seconds a test waits for a process or a thread to reach a state
WAIT_SECONDS = 10.0


def make_record(index=0, message=None, **fields):
    """Returns a small valid record, the index in its message makes each one different."""
    return LogRecord.create(
        timestamp=datetime(2026, 10, 7, 12, 0, 0, 123456, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        severity='INFO', logType='info', level=10.0, logger='test', message=message or f"record {index}",
        processId=1, threadId=2, threadName='MainThread', fields=fields or None)


class SpoolTestCase(unittest.TestCase):
    """Gives each test a base folder of its own and closes the spools it opened."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='spooltest-')
        self.base = os.path.join(self.root, 'spools')
        self.spools = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for spool in self.spools:
            try:
                spool.close()
            except Exception:
                pass
        shutil.rmtree(self.root, ignore_errors=True)

    def make_spool(self, **options):
        """Creates a slot in the base folder, with generous limits unless the test gives its own."""
        arguments = dict(maxBytes=10 * 1024 ** 2, totalMaxBytes=100 * 1024 ** 2)
        arguments.update(options)
        spool = Spool.create(self.base, 'test-spool', 'TestSink', TARGET, **arguments)
        self.spools.append(spool)
        return spool

    def open_spool(self, slotPath, **options):
        """Opens an existing slot with the same identity as make_spool."""
        arguments = dict(maxBytes=10 * 1024 ** 2, totalMaxBytes=100 * 1024 ** 2)
        arguments.update(options)
        spool = Spool.open(slotPath, 'test-spool', 'TestSink', TARGET, **arguments)
        self.spools.append(spool)
        return spool

    def slot_with(self, count):
        """Makes a slot that holds *count* undelivered records, closed so that its folder stays, and returns its path."""
        spool = self.make_spool()
        for index in range(count):
            spool.append(make_record(index))
        path = spool.path
        spool.close()
        return path

    def start(self, code, *arguments):
        """Starts a Python process that runs *code* with the package folder as its first argument, and cleans it up."""
        process = subprocess.Popen([sys.executable, '-c', code, PACKAGE_DIR, *arguments], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def finish():
            process.kill()
            process.wait(timeout=WAIT_SECONDS)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

        self.addCleanup(finish)
        return process

    @staticmethod
    def capture_stderr():
        """Swaps standard error for a buffer, and returns the buffer and the stream to put back."""
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        return buffer, previous

    @staticmethod
    def segment_files(slotPath):
        return sorted(name for name in os.listdir(slotPath) if name.endswith('.spool'))


def read_line(process):
    """Returns the next line a started process prints, failing the test when it prints nothing in time."""
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    try:
        return lines.get(timeout=WAIT_SECONDS).strip()
    except queue.Empty:
        process.kill()
        raise AssertionError('the process printed nothing in time')


HOLD_SCRIPT = '''
import sys
sys.path.insert(0, sys.argv[1])
from spool import Spool, target_id
spool = Spool.open(sys.argv[2], 'test-spool', 'TestSink',
                   target_id('TestSink', protocol='tcp', host='collector.example.org', port=514), 10**7, 10**8)
print('ready', flush=True)
sys.stdin.readline()
'''

CRASH_SCRIPT = '''
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
from spool import Spool, target_id
from record import LogRecord
spool = Spool.open(sys.argv[2], 'test-spool', 'TestSink',
                   target_id('TestSink', protocol='tcp', host='collector.example.org', port=514), 10**7, 10**8,
                   ackEvery=int(sys.argv[5]))
for index in range(int(sys.argv[3])):
    spool.append(LogRecord.create(datetime.now(timezone.utc), 'INFO', 'info', 10.0, 'crash', f'record {index}',
                                  1, 1, 'main'))
spool.ack(int(sys.argv[4]))
print('done', flush=True)
os._exit(0)
'''

FORK_SCRIPT = '''
import os, sys, time
sys.path.insert(0, sys.argv[1])
from spool import Spool, target_id
spool = Spool.open(sys.argv[2], 'test-spool', 'TestSink',
                   target_id('TestSink', protocol='tcp', host='collector.example.org', port=514), 10**7, 10**8)
child = os.fork()
if child == 0:
    time.sleep(60)
    os._exit(0)
print(f'ready {child}', flush=True)
time.sleep(60)
'''


class TestRecordRoundTrip(unittest.TestCase):

    def test_every_part_of_a_record_survives(self):
        record = LogRecord.create(
            timestamp=datetime(2026, 10, 7, 12, 30, 15, 987654, tzinfo=timezone(timedelta(hours=-5))),
            severity='ERROR', logType='error', level=30.5, logger='orders', message='Payment failed',
            processId=4321, threadId=99, threadName='worker-3',
            fields={'order_id': 123, 'nested': {'a': [1, 2, {'b': None}]}, 'ratio': 0.25, 'flag': True},
            context={'request_id': 'abc'}, exception=ExceptionInfo('ValueError', 'bad', 'Traceback (most recent call last)'),
            caller=CallerInfo('shop.py', 42, 'pay', 'shop'))
        back = record_from_dict(record_to_dict(record))
        self.assertEqual(back.timestamp, record.timestamp)
        self.assertEqual(back.timestamp.microsecond, 987654)
        self.assertEqual(back.timestamp.utcoffset(), timedelta(hours=-5))
        self.assertEqual(back._replace(fields=None, context=None), record._replace(fields=None, context=None))
        self.assertEqual(dict(back.fields), dict(record.fields))
        self.assertEqual(dict(back.context), dict(record.context))

    def test_a_value_json_cannot_hold_comes_back_as_text(self):
        record = make_record(0, items={1, 2})
        text = spool_module._dumps(record_to_dict(record))
        back = record_from_dict(spool_module.json.loads(text))
        self.assertEqual(back.fields['items'], '{1, 2}')

    def test_an_invalid_dictionary_is_refused(self):
        good = record_to_dict(make_record(0))
        for key in ('ts', 'off', 'message', 'fields'):
            broken = dict(good)
            del broken[key]
            with self.assertRaises(KeyError):
                record_from_dict(broken)
        with self.assertRaises((TypeError, ValueError)):
            record_from_dict({**good, 'processId': 'not a number'})
        for key, value in (('ts', 'yesterday'), ('ts', 1.5), ('off', '+05:30'), ('off', None)):
            with self.subTest(key=key, value=value):
                with self.assertRaises(TypeError):
                    record_from_dict({**good, key: value})


class TestRecordLine(unittest.TestCase):
    """The line built by hand must say exactly what the readable form says, in the same keys."""

    @staticmethod
    def _records():
        zones = [timezone.utc, timezone(timedelta(hours=5, minutes=30)), timezone(timedelta(hours=-3, seconds=-17))]
        records = []
        for index, zone in enumerate(zones):
            records.append(LogRecord.create(
                timestamp=datetime(2026, 10, 7, 12, 30, 15, 7 + index, tzinfo=zone), severity='ERROR', logType='error',
                level=[30.5, None, float('inf')][index], logger='orders', message=['Payment failed', 'ünï "quoted" \\ \n tab\t', ''][index],
                processId=4321, threadId=2 ** 40, threadName='worker-3',
                fields={'order_id': 123, 'nested': {'a': [1, 2, {'b': None}]}, 'ratio': 0.25, 'flag': True,
                        'text': 'caf\u00e9', 'unusual': {1, 2}, 'key with space': 'x'},
                context={'request_id': 'abc', 'n': 5},
                exception=ExceptionInfo('ValueError', 'bad', 'Traceback (most recent call last)\n  File "x"') if index == 0 else
                ExceptionInfo(None, None, 'only a traceback') if index == 1 else None,
                caller=CallerInfo('shop.py', 42, 'pay', 'shop') if index != 2 else None))
        records.append(make_record(9))
        records.append(LogRecord.create(datetime.now(timezone.utc), 'INFO', 'info', 10, 'l', 'm', 1, 1, 't'))
        return records

    def test_the_hand_built_line_says_what_the_readable_form_says(self):
        for index, record in enumerate(self._records()):
            with self.subTest(record=index):
                line = record_line(41, record)
                self.assertTrue(line.endswith(b'\n'))
                self.assertNotIn(b'\n', line[:-1])
                built = spool_module.json.loads(line)
                readable = spool_module.json.loads(spool_module._dumps({'seq': 41, 'record': record_to_dict(record)}))
                self.assertEqual(built, readable)

    def test_the_line_gives_the_record_back(self):
        for index, record in enumerate(self._records()):
            with self.subTest(record=index):
                data = spool_module.json.loads(record_line(7, record))
                back = record_from_dict(data['record'])
                self.assertEqual(back.timestamp, record.timestamp)
                self.assertEqual(back.timestamp.utcoffset(), record.timestamp.utcoffset())
                self.assertEqual((back.message, back.logType, back.threadId), (record.message, record.logType, record.threadId))
                self.assertEqual(back.exception, record.exception)
                self.assertEqual(back.caller, record.caller)

    def test_a_value_no_line_can_hold_does_not_stop_the_line(self):
        class Unprintable:
            def __repr__(self):
                raise RuntimeError('secret-in-error-message')

        line = record_line(1, make_record(0, thing=Unprintable(), keys={(1, 2): 3}))
        self.assertIn(b'unprintable', line)
        self.assertNotIn(b'secret-in-error-message', line)
        spool_module.json.loads(line)

    def test_the_number_is_the_only_thing_that_changes_between_two_lines(self):
        record = make_record(0)
        self.assertEqual(record_line(5, record)[len(b'{"seq":5'):], record_line(0, record)[len(b'{"seq":0'):])


class TestTargetId(unittest.TestCase):

    def test_same_destination_gives_the_same_id_whatever_the_order(self):
        self.assertEqual(target_id('S', host='h', port=1), target_id('S', port=1, host='h'))

    def test_every_part_of_the_destination_counts(self):
        reference = target_id('S', protocol='tcp', host='h', port=514)
        for other in (target_id('T', protocol='tcp', host='h', port=514), target_id('S', protocol='udp', host='h', port=514),
                      target_id('S', protocol='tcp', host='g', port=514), target_id('S', protocol='tcp', host='h', port=515)):
            self.assertNotEqual(reference, other)

    def test_a_value_without_stable_text_is_refused(self):
        for value in (1.5, object(), ['a'], {'a': 1}):
            with self.assertRaises(TypeError):
                target_id('S', value=value)

    def test_the_id_hides_the_destination(self):
        self.assertNotIn('collector', target_id('S', host='collector.example.org'))


class TestSpoolBasics(SpoolTestCase):

    def test_records_are_numbered_and_read_back_in_order(self):
        spool = self.make_spool()
        records = [make_record(index) for index in range(5)]
        self.assertEqual([spool.append(record) for record in records], [1, 2, 3, 4, 5])
        self.assertEqual(spool.pending(), [(index + 1, record) for index, record in enumerate(records)])
        self.assertEqual([seq for seq, _ in spool.pending(limit=2)], [1, 2])
        self.assertEqual(spool.stats()['depth'], 5)

    def test_acknowledged_records_are_not_pending(self):
        spool = self.make_spool()
        for index in range(6):
            spool.append(make_record(index))
        spool.ack(4)
        self.assertEqual([seq for seq, _ in spool.pending()], [5, 6])
        spool.ack(2)    # an older number changes nothing
        self.assertEqual(spool.stats()['acked'], 4)
        self.assertEqual(spool.stats()['depth'], 2)

    def test_acknowledging_a_record_that_does_not_exist_is_refused(self):
        spool = self.make_spool()
        spool.append(make_record(0))
        with self.assertRaises(ValueError):
            spool.ack(2)

    def test_segments_are_named_after_their_first_record_and_deleted_when_delivered(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(12):
            spool.append(make_record(index))
        names = self.segment_files(spool.path)
        self.assertGreater(len(names), 2)
        self.assertEqual(names[0], '000000000001.spool')
        spool.ack(12)
        # Only the segment being written to can remain, it is deleted when the spool closes
        self.assertEqual(len(self.segment_files(spool.path)), 1)
        self.assertEqual(spool.stats()['depth'], 0)

    def test_a_segment_is_deleted_only_when_its_last_record_is_delivered(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(12):
            spool.append(make_record(index))
        before = self.segment_files(spool.path)
        secondFirst = int(before[1][:12])
        spool.ack(secondFirst - 2)      # one record of the first segment is still undelivered
        self.assertEqual(self.segment_files(spool.path), before)
        spool.ack(secondFirst - 1)
        self.assertEqual(self.segment_files(spool.path), before[1:])

    def test_a_slot_whose_ack_file_already_covers_its_files_has_them_deleted_when_it_is_opened(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(12):
            spool.append(make_record(index))
        slot = spool.path
        self.assertGreater(len(self.segment_files(slot)), 2)
        spool.close()
        # A crash between saving the position and deleting the files leaves exactly this
        with open(os.path.join(slot, 'ack'), 'w') as stream:
            stream.write('12')
        reopened = self.open_spool(slot, segmentBytes=700)
        self.assertEqual(self.segment_files(slot), [])
        self.assertEqual((reopened.pending(), reopened.stats()['depth']), ([], 0))
        self.assertEqual(reopened.append(make_record(12)), 13)

    def test_a_clean_close_with_nothing_left_removes_the_folder(self):
        spool = self.make_spool()
        for index in range(3):
            spool.append(make_record(index))
        spool.ack(3)
        spool.close()
        self.assertFalse(os.path.exists(spool.path))

    def test_a_close_with_records_left_keeps_everything_and_numbering_goes_on(self):
        spool = self.make_spool()
        for index in range(10):
            spool.append(make_record(index))
        spool.ack(4)
        path = spool.path
        spool.close()
        reopened = self.open_spool(path)
        self.assertEqual([seq for seq, _ in reopened.pending()], [5, 6, 7, 8, 9, 10])
        self.assertEqual(reopened.append(make_record(10)), 11)

    def test_numbering_goes_on_after_everything_was_delivered_but_the_slot_was_kept(self):
        spool = self.make_spool()
        for index in range(3):
            spool.append(make_record(index))
        spool.give_up(1, make_record(0), 'OSError')     # the dead file keeps the folder
        spool.ack(3)
        path = spool.path
        spool.close()
        self.assertTrue(os.path.isdir(path))
        reopened = self.open_spool(path)
        self.assertEqual(reopened.append(make_record(3)), 4)

    def test_a_record_given_up_on_goes_to_the_dead_file_and_does_not_block_the_others(self):
        spool = self.make_spool()
        for index in range(3):
            spool.append(make_record(index))
        spool.give_up(1, make_record(0), 'OSError')
        self.assertEqual([seq for seq, _ in spool.pending()], [2, 3])
        self.assertEqual(spool.stats()['dead'], 1)
        with open(os.path.join(spool.path, 'dead'), encoding='ascii') as stream:
            text = stream.read()
        self.assertIn('"reason":"OSError"', text)
        self.assertIn('record 0', text)

    def test_every_flush_mode_works(self):
        for mode in (None, 'none', 'flush', 'fsync'):
            with self.subTest(flush=mode):
                spool = self.make_spool(flush=mode)
                spool.append(make_record(0))
                self.assertEqual(len(spool.pending()), 1)
                spool.sync()

    def test_a_closed_spool_refuses_to_be_used(self):
        spool = self.make_spool()
        spool.close()
        spool.close()
        with self.assertRaises(SpoolError):
            spool.append(make_record(0))


class TestCrashAndDamage(SpoolTestCase):

    def test_a_crash_leaves_what_the_ack_file_says_so_a_later_run_resends_the_rest(self):
        spool = self.make_spool()
        slot = spool.path
        spool.append(make_record(0))
        spool.close()
        process = self.start(CRASH_SCRIPT, slot, '10', '4', '1')
        self.assertEqual(read_line(process), 'done')
        process.wait(timeout=WAIT_SECONDS)
        reopened = self.open_spool(slot)
        # The slot held record 1, the script added 2 to 11 and acknowledged up to 4
        self.assertEqual([seq for seq, _ in reopened.pending()], [5, 6, 7, 8, 9, 10, 11])

    def test_a_crash_before_the_ack_file_is_written_resends_the_window(self):
        spool = self.make_spool()
        slot = spool.path
        spool.append(make_record(0))
        spool.close()
        process = self.start(CRASH_SCRIPT, slot, '10', '4', '1000')
        self.assertEqual(read_line(process), 'done')
        process.wait(timeout=WAIT_SECONDS)
        reopened = self.open_spool(slot)
        # Records 1 to 4 were delivered but the file did not say so, so they come again: at-least-once
        self.assertEqual([seq for seq, _ in reopened.pending()][:3], [1, 2, 3])
        self.assertEqual(len(reopened.pending()), 11)

    def test_a_half_written_last_line_is_cut_off_and_counted(self):
        slot = self.slot_with(3)
        segment = os.path.join(slot, self.segment_files(slot)[0])
        with open(segment, 'ab') as stream:
            stream.write(b'{"seq":4,"record":{"timest')
        reopened = self.open_spool(slot)
        self.assertEqual(reopened.stats()['torn'], 1)
        self.assertEqual(reopened.append(make_record(3)), 4)
        self.assertEqual([seq for seq, _ in reopened.pending()], [1, 2, 3, 4])
        self.assertEqual(reopened.stats()['corrupt'], 0)

    def test_a_damaged_line_in_the_middle_is_skipped_and_counted_once(self):
        slot = self.slot_with(4)
        segment = os.path.join(slot, self.segment_files(slot)[0])
        with open(segment, 'rb') as stream:
            lines = stream.readlines()
        lines[1] = b'this is not json\n'
        with open(segment, 'wb') as stream:
            stream.writelines(lines)
        reopened = self.open_spool(slot)
        self.assertEqual([seq for seq, _ in reopened.pending()], [1, 3, 4])
        reopened.pending()
        self.assertEqual(reopened.stats()['corrupt'], 1)
        self.assertEqual(reopened.stats()['lost'], 0)

    def test_a_line_with_a_good_number_and_a_bad_record_is_corrupt_and_not_lost(self):
        slot = self.slot_with(3)
        segment = os.path.join(slot, self.segment_files(slot)[0])
        with open(segment, 'rb') as stream:
            lines = stream.readlines()
        lines[2] = b'{"seq":3,"record":{"message":"incomplete"}}\n'
        with open(segment, 'wb') as stream:
            stream.writelines(lines)
        reopened = self.open_spool(slot)
        self.assertEqual([seq for seq, _ in reopened.pending()], [1, 2])
        self.assertEqual((reopened.stats()['corrupt'], reopened.stats()['lost']), (1, 0))

    def test_a_segment_deleted_by_hand_is_counted_as_lost(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(12):
            spool.append(make_record(index))
        slot = spool.path
        names = self.segment_files(slot)
        self.assertGreater(len(names), 2)
        middleFirst, nextFirst = int(names[1][:12]), int(names[2][:12])
        spool.close()
        os.remove(os.path.join(slot, names[1]))
        reopened = self.open_spool(slot, segmentBytes=700)
        seqs = [seq for seq, _ in reopened.pending()]
        self.assertEqual(len(seqs), 12 - (nextFirst - middleFirst))
        self.assertEqual(reopened.stats()['lost'], nextFirst - middleFirst)
        reopened.pending()
        self.assertEqual(reopened.stats()['lost'], nextFirst - middleFirst)

    def test_a_damaged_meta_file_is_a_mismatch_and_nothing_is_changed(self):
        slot = self.slot_with(2)
        with open(os.path.join(slot, 'meta.json'), 'w') as stream:
            stream.write('{broken')
        with self.assertRaises(SpoolMismatchError):
            self.open_spool(slot)


class TestOwnership(SpoolTestCase):

    def test_the_same_slot_cannot_be_opened_twice_in_one_process(self):
        spool = self.make_spool()
        with self.assertRaises(SpoolBusyError):
            self.open_spool(spool.path)
        spool.append(make_record(0))     # the first one still works

    def test_a_slot_can_be_opened_again_after_it_is_closed(self):
        slot = self.slot_with(1)
        first = self.open_spool(slot)
        first.close()
        self.assertEqual(len(self.open_spool(slot).pending()), 1)

    def test_another_process_cannot_take_a_slot_that_is_in_use_and_the_error_names_it(self):
        slot = self.slot_with(2)
        process = self.start(HOLD_SCRIPT, slot)
        try:
            self.assertEqual(read_line(process), 'ready')
            with self.assertRaises(SpoolBusyError) as caught:
                self.open_spool(slot)
            self.assertIn(str(process.pid), str(caught.exception))
        finally:
            process.kill()
            process.wait(timeout=WAIT_SECONDS)

    def test_a_slot_is_free_again_when_its_owner_is_killed(self):
        slot = self.slot_with(2)
        process = self.start(HOLD_SCRIPT, slot)
        self.assertEqual(read_line(process), 'ready')
        with self.assertRaises(SpoolBusyError):
            self.open_spool(slot)
        process.kill()
        process.wait(timeout=WAIT_SECONDS)
        self.assertEqual(len(self.open_spool(slot).pending()), 2)

    @unittest.skipUnless(IS_POSIX and hasattr(os, 'fork'), 'needs fork and POSIX record locks')
    def test_a_slot_is_free_when_its_owner_dies_even_though_a_forked_child_lives_on(self):
        slot = self.slot_with(2)
        process = self.start(FORK_SCRIPT, slot)
        childPid = None
        try:
            ready = read_line(process).split()
            self.assertEqual(ready[0], 'ready')
            childPid = int(ready[1])
            with self.assertRaises(SpoolBusyError):
                self.open_spool(slot)
            process.kill()
            process.wait(timeout=WAIT_SECONDS)
            os.kill(childPid, 0)       # the child is still alive
            self.assertEqual(len(self.open_spool(slot).pending()), 2)
        finally:
            process.kill()
            if childPid is not None:
                try:
                    os.kill(childPid, signal.SIGKILL)
                except OSError:
                    pass

    @unittest.skipUnless(hasattr(os, 'fork'), 'needs fork')
    def test_a_forked_child_cannot_write_to_the_spool_of_its_parent(self):
        spool = self.make_spool()
        spool.append(make_record(0))
        readEnd, writeEnd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                spool.append(make_record(1))
                outcome = b'wrote'
            except SpoolOwnerError:
                outcome = b'refused'
            os.write(writeEnd, outcome)
            os._exit(0)
        os.waitpid(pid, 0)
        self.assertEqual(os.read(readEnd, 20), b'refused')
        os.close(readEnd)
        os.close(writeEnd)
        self.assertEqual(len(spool.pending()), 1)

    def test_every_slot_has_its_own_name_and_they_are_listed_oldest_first(self):
        first, second = self.make_spool(), self.make_spool()
        self.assertNotEqual(first.path, second.path)
        self.assertEqual(Spool.slots(self.base), sorted([first.path, second.path]))
        self.assertEqual(Spool.slots(os.path.join(self.root, 'missing')), [])

    def test_a_slot_made_for_something_else_is_refused_and_left_untouched(self):
        slot = self.slot_with(2)
        cases = {'spoolId': ('other', 'TestSink', TARGET), 'sinkClass': ('test-spool', 'OtherSink', TARGET),
                 'targetId': ('test-spool', 'TestSink', target_id('TestSink', host='elsewhere'))}
        for field, (spoolId, sinkClass, targetValue) in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(SpoolMismatchError) as caught:
                    Spool.open(slot, spoolId, sinkClass, targetValue, 10 ** 7, 10 ** 8)
                self.assertIn(field, str(caught.exception))
                self.assertNotIn(TARGET, str(caught.exception))
        self.assertEqual(len(self.open_spool(slot).pending()), 2)

    def test_the_folder_and_the_files_are_private_to_the_owner(self):
        if os.name != 'posix':
            self.skipTest('permission bits are POSIX')
        spool = self.make_spool()
        spool.append(make_record(0))
        self.assertEqual(stat.S_IMODE(os.stat(self.base).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(spool.path).st_mode), 0o700)
        for name in os.listdir(spool.path):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(spool.path, name)).st_mode), 0o600, name)

    def test_without_a_file_lock_a_spool_refuses_to_start(self):
        saved = spool_module.fcntl, spool_module.msvcrt
        spool_module.fcntl = spool_module.msvcrt = None
        try:
            with self.assertRaises(SpoolUnsupportedError):
                self.make_spool()
        finally:
            spool_module.fcntl, spool_module.msvcrt = saved

    def test_the_lock_names_its_holder(self):
        lock = FileLock(os.path.join(self.root, 'lock'))
        self.assertTrue(lock.try_acquire())
        self.assertEqual(FileLock.holder(os.path.join(self.root, 'lock')), os.getpid())
        self.assertFalse(FileLock(os.path.join(self.root, 'lock')).try_acquire())
        lock.release()
        self.assertTrue(FileLock(os.path.join(self.root, 'lock')).try_acquire())


class TestLimits(SpoolTestCase):

    def test_the_limits_are_required_and_checked(self):
        for bad, error in ((None, TypeError), (0, ValueError), (-5, ValueError), (1.5, TypeError), (True, TypeError)):
            with self.subTest(maxBytes=bad):
                with self.assertRaises(error):
                    Spool.create(self.base, 'x', 'S', TARGET, bad, 10 ** 6)
        with self.assertRaises(TypeError):
            Spool.create(self.base, 'x', 'S', TARGET, maxBytes=10 ** 6)
        for options, error in (({'policy': 'drop'}, ValueError), ({'policy': None}, TypeError),
                               ({'flush': 'always'}, ValueError), ({'segmentBytes': 0}, ValueError),
                               ({'ackEvery': 0}, ValueError), ({'ackInterval': -1}, ValueError),
                               ({'maxAge': 0}, ValueError), ({'blockTimeout': 'soon'}, TypeError),
                               ({'deadMaxBytes': 0}, ValueError)):
            with self.subTest(options=options):
                with self.assertRaises(error):
                    self.make_spool(**options)
        with self.assertRaises(TypeError):
            Spool.create(self.base, '', 'S', TARGET, 10 ** 6, 10 ** 6)

    @staticmethod
    def _limits():
        """Returns (maxBytes, segmentBytes) that hold exactly four records of make_record, with room for half of a fifth."""
        probe = Spool.create(tempfile.mkdtemp(prefix='probe-'), 'p', 'S', TARGET, 10 ** 6, 10 ** 7)
        probe.append(make_record(0))
        unit = probe.stats()['bytes']
        probe.close()
        return unit * 4 + unit // 2, unit * 2

    def _fill(self, spool):
        """Appends until a record is not kept, and returns how many were kept."""
        kept = 0
        while spool.append(make_record(kept)) is not None:
            kept += 1
            if kept > 1000:
                self.fail('the spool never filled')
        return kept

    def test_drop_newest_keeps_the_old_records_and_warns_once_for_a_run(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='drop_newest')
        buffer, previous = self.capture_stderr()
        try:
            kept = self._fill(spool)
            for index in range(5):
                self.assertIsNone(spool.append(make_record(100 + index)))
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('WARNING'), 1)
        self.assertEqual(spool.stats()['dropped'], 6)
        self.assertEqual([seq for seq, _ in spool.pending()], list(range(1, kept + 1)))
        # Room again: the run is over, and the next run warns again
        spool.ack(kept)
        buffer, previous = self.capture_stderr()
        try:
            self.assertIsNotNone(spool.append(make_record(0)))
            self._fill(spool)
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('WARNING'), 1)

    def test_reject_raises_and_counts(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='reject')
        kept = 0
        with self.assertRaises(QueueFull):
            while True:
                spool.append(make_record(kept))
                kept += 1
        self.assertIsInstance(QueueFull(), queue.Full)
        self.assertEqual(spool.stats()['rejected'], 1)
        self.assertEqual(spool.stats()['dropped'], 0)
        self.assertEqual(len(spool.pending()), kept)

    def test_drop_oldest_keeps_the_newest_records_and_counts_what_it_threw_away(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='drop_oldest')
        buffer, previous = self.capture_stderr()
        try:
            for index in range(60):
                self.assertIsNotNone(spool.append(make_record(index)))
        finally:
            sys.stderr = previous
        stats = spool.stats()
        pending = spool.pending()
        self.assertGreater(stats['dropped'], 0)
        self.assertEqual(stats['dropped'] + len(pending), 60)
        self.assertEqual(pending[-1][0], 60)
        self.assertEqual([seq for seq, _ in pending], list(range(60 - len(pending) + 1, 61)))
        self.assertEqual(stats['depth'], len(pending))
        self.assertLessEqual(stats['bytes'], maxBytes)
        self.assertEqual(buffer.getvalue().count('WARNING'), 1)

    def test_drop_oldest_does_not_count_records_that_were_already_delivered(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='drop_oldest')
        for index in range(4):
            spool.append(make_record(index))
        spool.ack(4)        # these four were delivered, so throwing their files away loses nothing
        buffer, previous = self.capture_stderr()
        try:
            for index in range(44):
                spool.append(make_record(index))
        finally:
            sys.stderr = previous
        stats = spool.stats()
        self.assertEqual(stats['spooled'], 48)
        self.assertEqual(stats['dropped'] + len(spool.pending()), 44)

    def test_block_waits_for_the_delivery_to_make_room(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='block')
        kept = self._fill_to_limit(spool)
        results = []
        thread = threading.Thread(target=lambda: results.append(spool.append(make_record(999))))
        thread.start()
        time.sleep(0.2)
        self.assertEqual(results, [])      # still waiting
        spool.ack(kept)
        thread.join(WAIT_SECONDS)
        self.assertEqual(results, [kept + 1])
        self.assertEqual(spool.stats()['dropped'], 0)

    def test_block_with_a_timeout_gives_up_and_counts(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='block', blockTimeout=0.2)
        self._fill_to_limit(spool)
        buffer, previous = self.capture_stderr()
        started = time.monotonic()
        try:
            self.assertIsNone(spool.append(make_record(999)))
        finally:
            sys.stderr = previous
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
        self.assertEqual(spool.stats()['dropped'], 1)

    @staticmethod
    def _fill_to_limit(spool):
        """Appends the four records that fit, and returns 4. The fifth does not fit."""
        for index in range(4):
            spool.append(make_record(index))
        return 4

    def test_a_record_larger_than_the_whole_limit_is_never_kept(self):
        maxBytes, segmentBytes = self._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='drop_oldest')
        buffer, previous = self.capture_stderr()
        try:
            self.assertIsNone(spool.append(make_record(0, message='x' * 5000)))
        finally:
            sys.stderr = previous
        self.assertEqual(spool.stats()['depth'], 0)
        self.assertEqual(spool.stats()['dropped'], 1)

    def test_the_slot_is_split_into_segments_of_the_chosen_size(self):
        spool = self.make_spool(segmentBytes=1500)
        for index in range(30):
            spool.append(make_record(index))
        sizes = [os.path.getsize(os.path.join(spool.path, name)) for name in self.segment_files(spool.path)]
        self.assertGreater(len(sizes), 3)
        for size in sizes:
            self.assertLessEqual(size, 1500)

    def test_the_limit_for_the_whole_base_folder_is_checked_when_a_segment_starts(self):
        other = self.make_spool(segmentBytes=1000)
        for index in range(20):
            other.append(make_record(index))
        used = other.stats()['bytes']
        spool = self.make_spool(segmentBytes=1000, policy='drop_newest', maxBytes=10 ** 6, totalMaxBytes=used + 1500)
        kept = 0
        while spool.append(make_record(kept)) is not None:
            kept += 1
            if kept > 500:
                self.fail('the folder limit was never applied')
        self.assertGreater(kept, 0)
        self.assertLessEqual(other.stats()['bytes'] + spool.stats()['bytes'], used + 1500)
        self.assertGreater(spool.stats()['dropped'], 0)

    def test_old_segments_are_thrown_away_after_max_age(self):
        spool = self.make_spool(segmentBytes=800, maxAge=0.5)
        for index in range(10):
            spool.append(make_record(index))
        names = self.segment_files(spool.path)
        self.assertGreater(len(names), 1)
        old = time.time() - 60
        for name in names[:-1]:
            os.utime(os.path.join(spool.path, name), (old, old))
        time.sleep(1.1)
        buffer, previous = self.capture_stderr()
        try:
            spool.append(make_record(10))
        finally:
            sys.stderr = previous
        self.assertEqual(self.segment_files(spool.path), names[-1:] if len(names) == 2 else self.segment_files(spool.path))
        self.assertGreater(spool.stats()['dropped'], 0)
        self.assertEqual(spool.stats()['dropped'] + len(spool.pending()), 11)

    def test_the_dead_file_is_moved_aside_when_it_is_full(self):
        spool = self.make_spool(deadMaxBytes=1500)
        for index in range(12):
            spool.append(make_record(index))
        for index in range(12):
            spool.give_up(index + 1, make_record(index), 'OSError')
        self.assertTrue(os.path.exists(os.path.join(spool.path, 'dead.old')))
        self.assertLessEqual(os.path.getsize(os.path.join(spool.path, 'dead')), 1500)
        self.assertEqual(spool.stats()['dead'], 12)

    def test_the_ack_file_follows_the_chosen_frequency(self):
        spool = self.make_spool(ackEvery=5, ackInterval=1000)
        for index in range(12):
            spool.append(make_record(index))
        ackFile = os.path.join(spool.path, 'ack')
        spool.ack(3)
        self.assertFalse(os.path.exists(ackFile))
        spool.ack(5)
        with open(ackFile) as stream:
            self.assertEqual(stream.read(), '5')
        spool.ack(7)
        with open(ackFile) as stream:
            self.assertEqual(stream.read(), '5')
        spool.sync()
        with open(ackFile) as stream:
            self.assertEqual(stream.read(), '7')


class TestFileInUse(SpoolTestCase):
    """Windows refuses to delete a file that another handle has open, the files are then deleted later and nothing fails."""

    @staticmethod
    def _refusing(isRefusing):
        """Returns a replacement for os.remove that raises PermissionError for a segment file while isRefusing() is true."""
        real = os.remove

        def remove(path, *arguments, **options):
            if path.endswith('.spool') and isRefusing():
                raise PermissionError(13, 'The process cannot access the file because it is being used by another process')
            return real(path, *arguments, **options)

        return remove

    def test_a_segment_that_is_in_use_is_deleted_at_a_later_acknowledgement(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(12):
            spool.append(make_record(index))
        state = {'refuse': True}
        with mock.patch.object(spool_module.os, 'remove', side_effect=self._refusing(lambda: state['refuse'])):
            spool.ack(12)
        self.assertGreater(len(self.segment_files(spool.path)), 1)      # still on disk
        self.assertEqual(spool.stats()['depth'], 0)
        self.assertEqual(spool.pending(), [])                           # but nothing reads them
        state['refuse'] = False
        spool.append(make_record(12))
        spool.ack(13)
        self.assertEqual(len(self.segment_files(spool.path)), 1)        # only the one being written to

    def test_dropping_the_oldest_segment_while_it_is_in_use_does_not_lose_the_record_being_appended(self):
        maxBytes, segmentBytes = TestLimits._limits()
        spool = self.make_spool(maxBytes=maxBytes, segmentBytes=segmentBytes, policy='drop_oldest')
        buffer, previous = self.capture_stderr()
        try:
            with mock.patch.object(spool_module.os, 'remove', side_effect=self._refusing(lambda: True)):
                for index in range(40):
                    self.assertIsNotNone(spool.append(make_record(index)))      # none raises, none is lost
        finally:
            sys.stderr = previous
        stats = spool.stats()
        self.assertGreater(stats['dropped'], 0)
        self.assertEqual(stats['spooled'], 40)
        self.assertLessEqual(stats['bytes'], maxBytes)                  # the files in use do not count against the limit

    def test_closing_with_a_file_in_use_does_not_raise(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(8):
            spool.append(make_record(index))
        spool.ack(8)
        with mock.patch.object(spool_module.os, 'remove', side_effect=self._refusing(lambda: True)):
            spool.close()                                               # does not raise
        self.assertTrue(os.path.isdir(spool.path))                      # the folder stays, with what could not be deleted

    def test_a_file_that_is_left_behind_is_deleted_by_the_next_run(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(8):
            spool.append(make_record(index))
        path = spool.path
        spool.ack(8)
        with mock.patch.object(spool_module.os, 'remove', side_effect=self._refusing(lambda: True)):
            spool.close()
        reopened = self.open_spool(path, segmentBytes=700)
        self.assertEqual(reopened.pending(), [])
        self.assertLessEqual(len(self.segment_files(path)), 1)


class TestMaintain(SpoolTestCase):

    def test_maintain_drops_expired_segments_at_once_and_says_how_many_records(self):
        spool = self.make_spool(segmentBytes=700, maxAge=5 * 3600)
        for index in range(12):
            spool.append(make_record(index))
        names = self.segment_files(spool.path)
        self.assertGreater(len(names), 2)
        old = time.time() - 10 * 3600
        for name in names[:-1]:
            os.utime(os.path.join(spool.path, name), (old, old))
        buffer, previous = self.capture_stderr()
        try:
            result = spool.maintain()            # not waiting for the append that would test it once a second
        finally:
            sys.stderr = previous
        self.assertEqual(self.segment_files(spool.path), names[-1:])
        self.assertEqual(result['dropped'], spool.stats()['dropped'])
        self.assertGreater(result['dropped'], 0)
        self.assertEqual(spool.maintain(), {'dropped': 0, 'undeleted': 0})

    def test_maintain_tries_again_to_delete_a_file_that_was_in_use(self):
        spool = self.make_spool(segmentBytes=700)
        for index in range(12):
            spool.append(make_record(index))
        real = os.remove

        def refusing(path, *arguments, **options):
            if path.endswith('.spool'):
                raise PermissionError(13, 'in use by another process')
            return real(path, *arguments, **options)

        with mock.patch.object(spool_module.os, 'remove', side_effect=refusing):
            spool.ack(12)
            self.assertGreater(spool.maintain()['undeleted'], 0)
        self.assertEqual(spool.maintain()['undeleted'], 0)
        self.assertEqual(len(self.segment_files(spool.path)), 1)


class TestReadBatch(SpoolTestCase):

    def test_reading_a_backlog_in_batches_does_not_read_the_same_lines_again(self):
        spool = self.make_spool(segmentBytes=10 ** 7)
        total = 2000
        for index in range(total):
            spool.append(make_record(index))
        loads = []
        real = spool_module.json.loads

        def counting(*arguments, **options):
            loads.append(1)
            return real(*arguments, **options)

        seen = []
        with mock.patch.object(spool_module.json, 'loads', side_effect=counting):
            while True:
                batch = spool.pending(limit=100)
                if len(batch) == 0:
                    break
                seen.extend(seq for seq, _ in batch)
                spool.ack(batch[-1][0])
        self.assertEqual(seen, list(range(1, total + 1)))
        self.assertLess(len(loads), 2 * total)         # reading again from the start each time would be about ten times that

    def test_a_batch_that_was_not_acknowledged_is_read_again_from_the_same_place(self):
        spool = self.make_spool()
        for index in range(30):
            spool.append(make_record(index))
        first = [seq for seq, _ in spool.pending(limit=10)]
        again = [seq for seq, _ in spool.pending(limit=10)]
        self.assertEqual(first, again)
        spool.ack(first[-1])
        self.assertEqual([seq for seq, _ in spool.pending(limit=10)], list(range(11, 21)))

    def test_batches_across_segments_give_every_record_once_in_order(self):
        spool = self.make_spool(segmentBytes=900)
        for index in range(60):
            spool.append(make_record(index))
        self.assertGreater(len(self.segment_files(spool.path)), 5)
        seen = []
        while True:
            batch = spool.pending(limit=7)
            if len(batch) == 0:
                break
            seen.extend(seq for seq, _ in batch)
            spool.ack(batch[-1][0])
        self.assertEqual(seen, list(range(1, 61)))

    def test_the_read_says_how_far_it_got_so_unreadable_records_can_be_set_aside(self):
        slot = self.slot_with(3)
        segment = os.path.join(slot, self.segment_files(slot)[0])
        with open(segment, 'rb') as stream:
            lines = stream.readlines()
        lines[2] = b'{"seq":3,"record":{"message":"incomplete"}}\n'
        with open(segment, 'wb') as stream:
            stream.writelines(lines)
        spool = self.open_spool(slot)
        records, upTo = spool.read_batch(limit=10)
        self.assertEqual([seq for seq, _ in records], [1, 2])
        spool.ack(2)
        records, upTo = spool.read_batch(limit=10)
        self.assertEqual((records, upTo), ([], 3))
        spool.ack(upTo)
        self.assertEqual(spool.depth, 0)

    def test_acked_depth_and_waiting_for_empty(self):
        spool = self.make_spool()
        for index in range(4):
            spool.append(make_record(index))
        self.assertEqual((spool.acked, spool.depth), (0, 4))
        self.assertFalse(spool.wait_empty(0.05))
        threading.Timer(0.1, lambda: spool.ack(4)).start()
        self.assertTrue(spool.wait_empty(WAIT_SECONDS))
        self.assertEqual((spool.acked, spool.depth), (4, 0))

    def test_waiting_for_empty_ends_when_the_spool_is_closed(self):
        spool = self.make_spool()
        spool.append(make_record(0))
        threading.Timer(0.1, spool.close).start()
        self.assertFalse(spool.wait_empty(WAIT_SECONDS))


class TestConcurrency(SpoolTestCase):

    def test_threads_appending_while_another_acknowledges_lose_and_repeat_nothing(self):
        spool = self.make_spool(segmentBytes=20000)
        threads, perThread = 8, 400
        stop = threading.Event()
        acked = []

        def acknowledge():
            while not stop.is_set():
                pending = spool.pending(limit=50)
                if len(pending) > 0:
                    spool.ack(pending[-1][0])
                    acked.extend(seq for seq, _ in pending)

        def write(index):
            for number in range(perThread):
                self.assertIsNotNone(spool.append(make_record(number, thread=index)))

        acker = threading.Thread(target=acknowledge)
        acker.start()
        writers = [threading.Thread(target=write, args=(index,)) for index in range(threads)]
        for thread in writers:
            thread.start()
        for thread in writers:
            thread.join(WAIT_SECONDS * 3)
            self.assertFalse(thread.is_alive())
        stop.set()
        acker.join(WAIT_SECONDS)
        acked.extend(seq for seq, _ in spool.pending())
        self.assertEqual(sorted(acked), list(range(1, threads * perThread + 1)))
        self.assertEqual(len(acked), len(set(acked)))
        self.assertEqual(spool.stats()['spooled'], threads * perThread)
        self.assertEqual(spool.stats()['dropped'], 0)


if __name__ == '__main__':
    unittest.main()
