"""What happens to the records of a sink that is removed: they are delivered while the delivery progresses, the rest become
dead letters or are purged, and the number is always logged.

Run from the repo root::

    python3 -m unittest tests.test_sink_removal -v

The receiver of a spooled sink is a controllable sink: it can be down, slow, stuck, or accept only some records. The shutdown
and crash cases start real processes.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from simple_log import Logger  # noqa: E402
from sinks import Sink, StreamSink, FileSink  # noqa: E402
from spool import Spool, SpoolConfig, target_id  # noqa: E402
from record import LogRecord  # noqa: E402

# Seconds a test waits for something that must happen
WAIT_SECONDS = 15.0
DEAD_REASON = 'the sink was removed before delivery'


def wait_until(condition, timeout=WAIT_SECONDS, what='the condition'):
    """Polls until the condition is true, and fails the test when it never is."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


class Collector(Sink):
    """
    The receiver of a spool, as a sink.

    :Parameters:
        #. up (bool): False makes every write fail.
        #. delay (float): Seconds each write takes.
        #. acceptLimit (int, None): The number of records accepted before every write fails.
        #. failMessage (str, None): A message that is always refused.
    """
    SPOOL_DESTINATION = ('host',)

    def __init__(self, up=True, delay=0.0, acceptLimit=None, failMessage=None):
        super().__init__(formatter=lambda record: record.message)
        self.host = 'collector'
        self.up, self.delay, self.acceptLimit, self.failMessage = up, delay, acceptLimit, failMessage
        self.gate = None
        self.got = []
        self.lock = threading.Lock()

    def write(self, text, record):
        if self.delay:
            time.sleep(self.delay)
        if self.gate is not None:
            self.gate.wait(WAIT_SECONDS)
        with self.lock:
            refused = (not self.up or record.message == self.failMessage
                       or (self.acceptLimit is not None and len(self.got) >= self.acceptLimit))
            if not refused:
                self.got.append(record.message)
        return False if refused else None

    def messages(self):
        with self.lock:
            return list(self.got)


class Capture(Sink):
    """Keeps the severity and the message of what reaches it, to read the warnings a logger writes."""

    def __init__(self):
        super().__init__(formatter=lambda record: f"{record.severity} {record.message}")
        self.lines = []

    def write(self, text, record):
        self.lines.append(text)

    def warnings(self):
        return [line for line in self.lines if line.startswith('WARN')]


class RemovalTestCase(unittest.TestCase):
    """A base folder for the spools of each test, and everything cleaned up afterwards."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='removaltest-')
        self.base = os.path.join(self.root, 'spools')
        self.loggers = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for logger in self.loggers:
            try:
                logger.clear_sinks(timeout=0.5)
            except Exception:
                pass
        shutil.rmtree(self.root, ignore_errors=True)

    def settings(self, **overrides):
        values = dict(path=self.base, id='test', maxBytes=10 * 1024 ** 2, totalMaxBytes=100 * 1024 ** 2,
                      retryBackoffBase=0.01, retryBackoffMax=0.05)
        values.update(overrides)
        return values

    def make(self, collector=None, name='c', **spool):
        """Returns a logger with a capture sink named ``cap`` and a spooled collector named *name*, the collector, and the capture."""
        logger = Logger('removal', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        capture = Capture()
        logger.add_sink('cap', capture)
        collector = collector or Collector()
        logger.add_sink(name, collector, threaded=True, threadQueueSize=1000, spool=self.settings(**spool))
        return logger, collector, capture

    def slots(self):
        return [os.path.basename(path) for path in Spool.slots(self.base)] if os.path.isdir(self.base) else []

    def all_dead_messages(self):
        """The messages in the dead files of every slot."""
        return sorted(message for slot in self.slots() for message in self.dead_messages(slot))

    def dead_messages(self, slot=None):
        """The messages in the dead file of the only slot (or the slot given), in the order they were written."""
        slot = slot or self.slots()[0]
        path = os.path.join(self.base, slot, 'dead')
        if not os.path.exists(path):
            return []
        with open(path, encoding='ascii') as stream:
            return [json.loads(line)['record']['message'] for line in stream]

    def dead_reasons(self, slot=None):
        slot = slot or self.slots()[0]
        with open(os.path.join(self.base, slot, 'dead'), encoding='ascii') as stream:
            return [json.loads(line)['reason'] for line in stream]


class TestDeadLetters(RemovalTestCase):

    def test_what_a_down_receiver_did_not_get_becomes_dead_letters_in_order(self):
        logger, collector, capture = self.make(Collector(up=False))
        for index in range(5):
            logger.info(f'm{index}')
        logger.remove_sink('c', timeout=0.3)
        self.assertEqual(self.dead_messages(), [f'm{index}' for index in range(5)])
        self.assertEqual(set(self.dead_reasons()), {DEAD_REASON})
        self.assertEqual(collector.messages(), [])

    def test_nothing_stays_live_for_a_sink_added_later(self):
        logger, collector, capture = self.make(Collector(up=False))
        logger.info('left')
        logger.remove_sink('c', timeout=0.3)
        later, laterCollector, _ = self.make(name='again', adoptOrphans=True, adoptInterval=0.05)
        later.info('mine')
        later.flush(timeout=WAIT_SECONDS)
        time.sleep(0.4)
        self.assertEqual(laterCollector.messages(), ['mine'])             # the dead letter was not sent
        self.assertEqual(self.all_dead_messages(), ['left'])

    def test_the_warning_names_the_sink_the_count_the_action_and_the_place(self):
        logger, collector, capture = self.make(Collector(up=False), name='billing')
        for index in range(4):
            logger.info(f'm{index}')
        logger.remove_sink('billing', timeout=0.3)
        warnings = capture.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("'billing'", warnings[0])
        self.assertIn('4 undelivered records', warnings[0])
        self.assertIn('Action: dead_letter', warnings[0])
        self.assertIn(self.base, warnings[0])

    def test_a_clean_removal_logs_nothing_and_leaves_no_folder(self):
        logger, collector, capture = self.make()
        for index in range(50):
            logger.info(f'm{index}')
        logger.remove_sink('c')
        self.assertEqual(collector.messages(), [f'm{index}' for index in range(50)])
        self.assertEqual(capture.warnings(), [])
        self.assertEqual(self.slots(), [])

    def test_a_sink_that_never_received_a_record_leaves_nothing(self):
        logger, collector, capture = self.make(Collector(up=False))
        logger.remove_sink('c', timeout=0.3)
        self.assertEqual(capture.warnings(), [])
        self.assertEqual(self.slots(), [])

    def test_nothing_is_lost_and_nothing_is_sent_twice(self):
        logger, collector, capture = self.make(Collector(acceptLimit=137))
        for index in range(500):
            logger.info(f'm{index}')
        logger.remove_sink('c', timeout=0.5)
        everything = [f'm{index}' for index in range(500)]
        self.assertEqual(collector.messages(), everything[:137])
        self.assertEqual(self.dead_messages(), everything[137:])
        self.assertIn('363 undelivered records', capture.warnings()[0])

    def test_records_logged_after_the_removal_do_not_reach_the_sink(self):
        logger, collector, capture = self.make()
        logger.info('before')
        logger.remove_sink('c')
        logger.info('after')
        logger.flush(timeout=1.0)
        self.assertEqual(collector.messages(), ['before'])

    def test_a_removal_while_other_threads_log_loses_nothing_and_duplicates_nothing(self):
        logger, collector, capture = self.make(Collector(delay=0.0005))
        failures = []

        def produce(producer):
            try:
                for index in range(1500):
                    logger.info(f'p{producer}-{index}')
            except Exception as error:         # a producer must never see an error because a sink was removed
                failures.append(error)

        threads = [threading.Thread(target=produce, args=(number,)) for number in range(4)]
        for thread in threads:
            thread.start()
        time.sleep(0.15)
        logger.remove_sink('c', timeout=0.3)
        for thread in threads:
            thread.join(timeout=WAIT_SECONDS)
        self.assertEqual(failures, [])
        delivered, dead = collector.messages(), self.dead_messages() if self.slots() else []
        self.assertEqual(len(delivered), len(set(delivered)))
        self.assertEqual(len(dead), len(set(dead)))
        self.assertEqual(set(delivered) & set(dead), set())
        for producer in range(4):                                       # each producer's records keep their order
            mine = [int(message.split('-')[1]) for message in delivered + dead if message.startswith(f'p{producer}-')]
            self.assertEqual(mine, sorted(mine))


class TestPurge(RemovalTestCase):

    def test_purge_deletes_the_records_and_the_folder_and_says_so(self):
        logger, collector, capture = self.make(Collector(up=False), onRemove='purge')
        for index in range(5):
            logger.info(f'm{index}')
        logger.remove_sink('c', timeout=0.3)
        self.assertEqual(self.slots(), [])
        self.assertFalse(os.path.exists(self.base) and any(os.scandir(self.base)))
        self.assertEqual(len(capture.warnings()), 1)
        self.assertIn('5 undelivered records', capture.warnings()[0])
        self.assertIn('Action: purge', capture.warnings()[0])

    def test_dead_letters_keep_what_was_parked_earlier_and_purge_deletes_it(self):
        for onRemove, kept in (('dead_letter', ['bad', 'm1', 'm2']), ('purge', None)):
            with self.subTest(onRemove=onRemove):
                shutil.rmtree(self.base, ignore_errors=True)
                logger, collector, capture = self.make(Collector(failMessage='bad'), onRemove=onRemove, maxAttempts=2)
                logger.info('bad')                                    # refused for good, so it is parked after two tries
                wait_until(lambda: logger.sink_stats('c')['spool']['dead'] == 1, what='the record to be parked')
                collector.up = False
                logger.info('m1')
                logger.info('m2')
                logger.remove_sink('c', timeout=0.3)
                if kept is None:
                    self.assertEqual(self.slots(), [])
                    self.assertIn('Action: purge', capture.warnings()[0])
                else:
                    self.assertEqual(self.all_dead_messages(), sorted(kept))
                self.loggers.pop().clear_sinks(timeout=0.2)


class TestDrain(RemovalTestCase):

    def test_a_backlog_that_keeps_being_delivered_is_waited_for_beyond_the_timeout(self):
        logger, collector, capture = self.make(Collector(delay=0.01))
        for index in range(150):                               # about 1.5 seconds of work
            logger.info(f'm{index}')
        started = time.monotonic()
        logger.remove_sink('c', timeout=0.4)
        self.assertGreater(time.monotonic() - started, 0.8)
        self.assertEqual(collector.messages(), [f'm{index}' for index in range(150)])
        self.assertEqual(capture.warnings(), [])

    def test_a_delivery_that_stands_still_ends_after_the_timeout_and_not_after_the_longest_wait(self):
        logger, collector, capture = self.make(Collector(up=False), maxDrainSeconds=300)
        for index in range(3):
            logger.info(f'm{index}')
        started = time.monotonic()
        logger.remove_sink('c', timeout=0.5)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(len(capture.warnings()), 1)

    def test_a_stuck_receiver_ends_after_the_timeout(self):
        collector = Collector()
        collector.gate = threading.Event()                      # every write waits
        logger, _, capture = self.make(collector)
        for index in range(3):
            logger.info(f'm{index}')
        started = time.monotonic()
        try:
            logger.remove_sink('c', timeout=0.5)
            self.assertLess(time.monotonic() - started, 6.0)
        finally:
            collector.gate.set()

    def test_the_longest_wait_ends_a_delivery_that_never_stops_progressing(self):
        logger, collector, capture = self.make(Collector(delay=0.004), maxDrainSeconds=0.3)
        for index in range(400):
            logger.info(f'm{index}')
        started = time.monotonic()
        logger.remove_sink('c', timeout=5.0)
        self.assertLess(time.monotonic() - started, 3.0)
        delivered, dead = collector.messages(), self.dead_messages()
        self.assertTrue(0 < len(delivered) < 400)
        self.assertEqual(delivered + dead, [f'm{index}' for index in range(400)])


class TestAllKindsOfSink(RemovalTestCase):

    def test_a_threaded_sink_without_a_spool_keeps_its_own_behavior(self):
        logger = Logger('plain', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        capture = Capture()
        logger.add_sink('cap', capture)
        slow = Collector(delay=0.2)
        logger.add_sink('slow', slow, threaded=True)
        for index in range(20):
            logger.info(f'm{index}')
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            logger.remove_sink('slow', timeout=0.3)
        finally:
            sys.stderr = previous
        self.assertEqual(capture.warnings(), [])                          # the report is for spools, this sink warns on the error stream as before
        self.assertEqual(self.slots(), [])

    def test_a_sink_that_is_not_threaded_is_removed_and_closed(self):
        logger = Logger('plain', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        capture = Capture()
        logger.add_sink('cap', capture)
        stream = io.StringIO()
        logger.add_sink('stream', StreamSink(stream))
        logger.info('seen')
        logger.remove_sink('stream')
        logger.info('not seen')
        self.assertIn('seen', stream.getvalue())
        self.assertNotIn('not seen', stream.getvalue())
        self.assertEqual(capture.warnings(), [])

    def test_a_file_sink_is_flushed_when_removed(self):
        logger = Logger('plain', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        logger.add_sink('file', FileSink(os.path.join(self.root, 'out'), extension='log', formatter=None, flush='none'))
        for index in range(20):
            logger.info(f'line {index}')
        logger.remove_sink('file')
        with open(os.path.join(self.root, 'out_0.log'), encoding='utf-8') as stream:
            self.assertEqual(len(stream.read().splitlines()), 20)

    def test_removing_a_name_that_is_not_there_or_is_not_a_name_is_refused(self):
        logger = Logger('plain', logToFile=False, logToStdout=False)
        with self.assertRaises(ValueError):
            logger.remove_sink('missing')
        with self.assertRaises(TypeError):
            logger.remove_sink(3)

    def test_a_sink_can_be_added_and_removed_many_times_without_leaking_threads(self):
        logger = Logger('cycles', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        capture = Capture()
        logger.add_sink('cap', capture)
        before = threading.active_count()
        for cycle in range(30):
            collector = Collector()
            logger.add_sink('c', collector, threaded=True, spool=self.settings(id=f'cycle{cycle % 3}'))
            for index in range(10):
                logger.info(f'{cycle}-{index}')
            logger.remove_sink('c')
            self.assertEqual(collector.messages(), [f'{cycle}-{index}' for index in range(10)])
        self.assertEqual(capture.warnings(), [])
        self.assertEqual(self.slots(), [])
        self.assertLessEqual(threading.active_count(), before + 1)

    def test_clear_sinks_reports_each_sink_that_had_records_left_on_the_error_stream(self):
        logger = Logger('clear', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        for name, up in (('a', False), ('b', True), ('c', False)):
            logger.add_sink(name, Collector(up=up), threaded=True, spool=self.settings(id=name))
            logger.info(f'for {name}')
        wait_until(lambda: logger.sink_stats('b')['spool']['depth'] == 0, what='the sink b to deliver')
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            logger.clear_sinks(timeout=0.3)
        finally:
            sys.stderr = previous
        text = buffer.getvalue()
        self.assertIn("'a'", text)
        self.assertIn("'c'", text)
        self.assertNotIn("'b'", text)
        self.assertEqual(text.count('undelivered records'), 2)

    def test_clear_sinks_on_a_logger_without_sinks_does_nothing(self):
        logger = Logger('empty', logToFile=False, logToStdout=False)
        logger.clear_sinks()

    def test_two_sinks_with_a_spool_are_reported_one_each_and_keep_their_own_records(self):
        logger = Logger('two', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        capture = Capture()
        logger.add_sink('cap', capture)
        for name in ('one', 'two'):
            logger.add_sink(name, Collector(up=False), threaded=True, spool=self.settings(id=name))
        for index in range(3):
            logger.info(f'm{index}')
        logger.remove_sink('one', timeout=0.3)
        logger.remove_sink('two', timeout=0.3)
        self.assertEqual(len(capture.warnings()), 2)
        slots = self.slots()
        self.assertEqual(len(slots), 2)
        deadLists = sorted(self.dead_messages(slot) for slot in slots)
        # The warning about the first removal is a record like any other, it reached the second sink that was still there and was down
        self.assertEqual(deadLists[0], ['m0', 'm1', 'm2'])
        self.assertEqual(deadLists[1][:3], ['m0', 'm1', 'm2'])
        self.assertEqual(len(deadLists[1]), 4)
        self.assertIn("The sink 'one' was removed", deadLists[1][3])


SHUTDOWN_SCRIPT = '''
import sys
sys.path.insert(0, sys.argv[1])
from simple_log import Logger
from sinks import Sink


class Down(Sink):
    SPOOL_DESTINATION = ('host',)
    host = 'collector'

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)

    def write(self, text, record):
        return False


logger = Logger('child', logToFile=False, logToStdout=False, shutdownTimeout=0.4)
logger.add_sink('c', Down(), threaded=True, spool={'path': sys.argv[2], 'id': 'test', 'maxBytes': 10**7, 'totalMaxBytes': 10**8,
                                                   'retryBackoffBase': 0.01, 'retryBackoffMax': 0.05, 'onRemove': sys.argv[3]})
for index in range(3):
    logger.info(f'm{index}')
'''

CRASH_SCRIPT = '''
import os, sys
sys.path.insert(0, sys.argv[1])
from simple_log import Logger
from sinks import Sink


class Collector(Sink):
    SPOOL_DESTINATION = ('host',)
    host = 'collector'

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)

    def write(self, text, record):
        return False


logger = Logger('child', logToFile=False, logToStdout=False)
logger.add_sink('c', Collector(), threaded=True, spool={'path': sys.argv[2], 'id': 'test', 'maxBytes': 10**7, 'totalMaxBytes': 10**8,
                                                        'retryBackoffBase': 0.01, 'retryBackoffMax': 0.05})
for index in range(3):
    logger.info(f'm{index}')
os._exit(0)
'''


class TestEndOfProgram(RemovalTestCase):

    def run_script(self, script, *arguments):
        return subprocess.run([sys.executable, '-c', script, PACKAGE_DIR, self.base, *arguments], capture_output=True, text=True,
                              timeout=60)

    def test_a_program_that_ends_with_records_left_says_so_on_the_error_stream_and_keeps_dead_letters(self):
        result = self.run_script(SHUTDOWN_SCRIPT, 'dead_letter')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ended with 3 undelivered records', result.stderr)
        self.assertIn('dead_letter', result.stderr)
        self.assertEqual(self.dead_messages(), ['m0', 'm1', 'm2'])

    def test_a_program_that_ends_with_a_purging_spool_leaves_nothing(self):
        result = self.run_script(SHUTDOWN_SCRIPT, 'purge')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ended with 3 undelivered records', result.stderr)
        self.assertEqual(self.slots(), [])

    def test_a_crash_still_leaves_a_slot_that_another_sink_adopts(self):
        result = self.run_script(CRASH_SCRIPT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.slots()), 1)
        logger, collector, capture = self.make(adoptOrphans=True, adoptInterval=0.05)
        wait_until(lambda: len(collector.messages()) == 3, what='the crashed slot to be sent')
        self.assertEqual(sorted(collector.messages()), ['m0', 'm1', 'm2'])


class TestSettings(RemovalTestCase):

    def config(self, **overrides):
        values = dict(path=self.base, id='test', maxBytes=1024, totalMaxBytes=4096)
        values.update(overrides)
        return SpoolConfig(**values)

    def test_the_defaults(self):
        config = self.config()
        self.assertEqual((config.onRemove, config.maxDrainSeconds), ('dead_letter', 300.0))

    def test_the_settings_can_be_given_as_a_dictionary(self):
        config = SpoolConfig.coerce({'path': self.base, 'id': 'test', 'maxBytes': 1024, 'totalMaxBytes': 4096,
                                     'onRemove': 'purge', 'maxDrainSeconds': 12})
        self.assertEqual((config.onRemove, config.maxDrainSeconds), ('purge', 12))

    def test_values_that_are_not_allowed_are_refused(self):
        for overrides, error in (({'onRemove': 'keep'}, ValueError), ({'onRemove': None}, ValueError),
                                 ({'maxDrainSeconds': 0}, ValueError), ({'maxDrainSeconds': -1}, ValueError),
                                 ({'maxDrainSeconds': True}, TypeError), ({'maxDrainSeconds': 'ten'}, TypeError)):
            with self.subTest(overrides=overrides):
                with self.assertRaises(error):
                    self.config(**overrides)

    def test_a_setting_that_does_not_exist_is_still_refused(self):
        with self.assertRaises(TypeError):
            SpoolConfig.coerce({'path': self.base, 'id': 'test', 'maxBytes': 1024, 'totalMaxBytes': 4096, 'onremove': 'purge'})

    def test_a_bad_value_is_refused_when_the_sink_is_added_and_leaves_nothing_behind(self):
        logger = Logger('bad', logToFile=False, logToStdout=False)
        with self.assertRaises(ValueError):
            logger.add_sink('c', Collector(), threaded=True, spool=self.settings(onRemove='keep'))
        self.assertNotIn('c', logger.sinks)
        self.assertEqual(self.slots(), [])


def make_record(index):
    return LogRecord.create(timestamp=__import__('datetime').datetime(2026, 10, 7, 12, 0, 0, tzinfo=__import__('datetime').timezone.utc),
                            severity='INFO', logType='info', level=10.0, logger='test', message=f'record {index}',
                            processId=1, threadId=2, threadName='MainThread', fields=None)


class TestSpoolLevel(RemovalTestCase):
    """The two operations of the spool the removal is made of."""

    def make_spool(self):
        spool = Spool.create(self.base, 'test-spool', 'TestSink', target_id('TestSink', host='h'), maxBytes=10 ** 7, totalMaxBytes=10 ** 8)
        self.addCleanup(lambda: spool.close())
        return spool

    def test_dead_letter_pending_moves_every_record_in_order_even_beyond_one_read(self):
        spool = self.make_spool()
        for index in range(1300):                                       # more than the 500 read at a time
            spool.append(make_record(index))
        spool.ack(100)                                                    # the first hundred were delivered
        moved = spool.dead_letter_pending('because')
        self.assertEqual(moved, 1200)
        self.assertEqual(spool.pending(), [])
        self.assertEqual(spool.depth, 0)
        slot = os.path.basename(spool.path)
        self.assertEqual(self.dead_messages(slot), [f'record {index}' for index in range(100, 1300)])
        self.assertEqual(set(self.dead_reasons(slot)), {'because'})

    def test_dead_letter_pending_on_an_empty_spool_moves_nothing(self):
        self.assertEqual(self.make_spool().dead_letter_pending('because'), 0)

    def test_close_with_purge_returns_the_number_deleted_and_removes_everything(self):
        spool = self.make_spool()
        for index in range(7):
            spool.append(make_record(index))
        spool.give_up(1, make_record(0), 'parked')                       # one dead letter that is already there
        self.assertEqual(spool.close(purge=True), 7)                     # six not delivered, and the one parked earlier
        self.assertEqual(self.slots(), [])

    def test_close_without_purge_keeps_the_records_and_closing_twice_does_nothing(self):
        spool = self.make_spool()
        for index in range(4):
            spool.append(make_record(index))
        self.assertEqual(spool.close(), 0)
        self.assertEqual(spool.close(purge=True), 0)                      # already closed
        self.assertEqual(len(self.slots()), 1)

    def test_close_with_purge_on_a_spool_that_was_fully_delivered_returns_zero(self):
        spool = self.make_spool()
        for index in range(3):
            spool.append(make_record(index))
        spool.ack(3)
        self.assertEqual(spool.close(purge=True), 0)
        self.assertEqual(self.slots(), [])


if __name__ == '__main__':
    unittest.main()
