"""A sink with a spool: records kept on disk until delivered, in order, retried, adopted after a crash, never raising.

Run from the repo root::

    python3 -m unittest tests.test_durable -v

The crash and adoption cases start real processes and end them without any cleanup, which is what a crash looks like
to the files and the locks. A controllable sink stands for the collector: it can be down, slow, stuck, or fail for
one record only.
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
from unittest import mock

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from SimpleLog import Logger  # noqa: E402
from sinks import Sink, StreamSink, ConsoleSink  # noqa: E402
from spool import Spool, SpoolConfig  # noqa: E402
from queues import QueueFull  # noqa: E402
from contrib import siem_sink, siem_transport  # noqa: E402

# Seconds a test waits for something that must happen
WAIT_SECONDS = 15.0


def wait_until(condition, timeout=WAIT_SECONDS, what='the condition'):
    """Polls until the condition is true, and fails the test when it never is."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def poison_formatter(record):
    """A formatter that cannot render one message, the others are rendered as their text."""
    if record.message == 'poison':
        raise ValueError('cannot render this record')
    return record.message


class Collector(Sink):
    """
    The receiver, as a sink: it can be down, slow, stuck, or refuse one message.

    :Parameters:
        #. host (str): Where it says it sends. Only this makes the receiver of a spool.
        #. up (bool): False makes every write fail.
        #. mode (str): ``false`` to fail by returning False, ``raise`` to fail by raising an exception.
        #. delay (float): Seconds each write takes.
        #. failMessage (str, None): A message that is always refused.
        #. acceptLimit (int, None): The number of records accepted before every write fails.
    """
    SPOOL_DESTINATION = ('host',)

    def __init__(self, host='c1', up=True, mode='false', delay=0.0, formatter=None, failMessage=None, acceptLimit=None):
        super().__init__(formatter=formatter or (lambda record: record.message))
        self.host, self.up, self.mode, self.delay = host, up, mode, delay
        self.failMessage, self.acceptLimit = failMessage, acceptLimit
        self.gate = None
        self.got = []
        self.attempts = 0
        self.lock = threading.Lock()

    def write(self, text, record):
        if self.delay:
            time.sleep(self.delay)
        if self.gate is not None:
            self.gate.wait(WAIT_SECONDS)
        with self.lock:
            self.attempts += 1
            refused = (not self.up or record.message == self.failMessage
                       or (self.acceptLimit is not None and len(self.got) >= self.acceptLimit))
            if not refused:
                self.got.append((record.fields.get('event_id'), record.message))
        if refused:
            if self.mode == 'raise':
                raise ConnectionError('the collector is down')
            return False

    def messages(self):
        with self.lock:
            return [message for _, message in self.got]

    def ids(self):
        with self.lock:
            return [eventId for eventId, _ in self.got]


# The collector for a process that is ended without any cleanup. It is always down unless told otherwise
COLLECTOR_SOURCE = '''
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from SimpleLog import Logger
from sinks import Sink


class Collector(Sink):
    SPOOL_DESTINATION = ('host',)

    def __init__(self, host, up, idsFile):
        super().__init__(formatter=lambda record: record.message)
        self.host, self.up, self.idsFile = host, up, idsFile

    def write(self, text, record):
        if not self.up:
            return False
        with open(self.idsFile, 'a') as stream:
            stream.write(record.fields.get('event_id') + '\\n')


def make(base, host, up, spoolId, idsFile, ackInterval=1000):
    logger = Logger('child', logToFile=False, logToStdout=False)
    logger.add_sink('c', Collector(host, up, idsFile), threaded=True,
                    spool={'path': base, 'id': spoolId, 'maxBytes': 10**7, 'totalMaxBytes': 10**8,
                           'retryBackoffBase': 0.01, 'retryBackoffMax': 0.05, 'ackEvery': 10**6, 'ackInterval': ackInterval})
    return logger
'''

DOWN_SCRIPT = COLLECTOR_SOURCE + '''
base, host, spoolId, count = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
logger = make(base, host, False, spoolId, os.devnull)
for index in range(count):
    logger.info(f'orphan {index}')
print(os.path.basename(logger.sink_stats('c')['spool']['slot']), flush=True)
os._exit(0)
'''

DELIVER_THEN_CRASH_SCRIPT = COLLECTOR_SOURCE + '''
base, idsFile, count = sys.argv[2], sys.argv[3], int(sys.argv[4])
logger = make(base, 'c1', True, 'test', idsFile)
for index in range(count):
    logger.info(f'sent {index}')
deadline = time.time() + 10
while time.time() < deadline and logger.sink_stats('c')['delivery']['processed'] < count:
    time.sleep(0.005)
print(logger.sink_stats('c')['spool']['slot'], flush=True)
os._exit(0)
'''

HOLD_SCRIPT = COLLECTOR_SOURCE + '''
base, count = sys.argv[2], int(sys.argv[3])
logger = make(base, 'c1', False, 'test', os.devnull)
for index in range(count):
    logger.info(f'held {index}')
print('ready', flush=True)
sys.stdin.readline()
'''


class DurableTestCase(unittest.TestCase):
    """A base folder for each test, a logger without outputs, and everything cleaned up afterwards."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='durabletest-')
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

    def make(self, sink=None, hintSize=1000, **overrides):
        """Returns a logger with one sink named ``c`` that has a spool, and the sink."""
        logger = Logger('durable', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        sink = sink or Collector()
        logger.add_sink('c', sink, threaded=True, threadQueueSize=hintSize, spool=self.settings(**overrides))
        return logger, sink

    def spool_stats(self, logger):
        return logger.sink_stats('c')['spool']

    def slots(self):
        return [os.path.basename(path) for path in Spool.slots(self.base)]

    def run_script(self, script, *arguments):
        process = subprocess.Popen([sys.executable, '-c', script, PACKAGE_DIR, *arguments], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def finish():
            process.kill()
            process.wait(timeout=WAIT_SECONDS)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

        self.addCleanup(finish)
        return process

    def leave_orphan(self, count, host='c1', spoolId='test'):
        """Ends a process that logged *count* records to a collector that was down, and returns the name of its slot."""
        process = self.run_script(DOWN_SCRIPT, self.base, host, spoolId, str(count))
        slot = process.stdout.readline().strip()
        process.wait(timeout=WAIT_SECONDS)
        self.assertEqual(process.returncode, 0, process.stderr.read())
        return slot


class TestBasics(DurableTestCase):

    def test_records_are_delivered_in_order_and_the_spool_ends_empty(self):
        logger, sink = self.make()
        for index in range(50):
            logger.info(f'm{index}')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), [f'm{index}' for index in range(50)])
        stats = self.spool_stats(logger)
        self.assertEqual((stats['spooled'], stats['depth'], stats['dead'], stats['errors']), (50, 0, 0, 0))
        self.assertEqual(logger.sink_stats('c')['delivery']['processed'], 50)

    def test_a_clean_removal_leaves_nothing_on_disk(self):
        logger, sink = self.make()
        logger.info('one')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(len(self.slots()), 1)
        logger.remove_sink('c')
        self.assertEqual(self.slots(), [])

    def test_the_record_is_on_disk_when_the_call_returns(self):
        logger, sink = self.make(sink=Collector(up=False))
        logger.info('write it down first')
        slotPath = os.path.join(self.base, self.slots()[0])
        text = ''
        for name in os.listdir(slotPath):
            if name.endswith('.spool'):
                with open(os.path.join(slotPath, name), encoding='ascii') as stream:
                    text += stream.read()
        self.assertIn('write it down first', text)
        self.assertEqual(self.spool_stats(logger)['depth'], 1)

    def test_a_slow_sink_does_not_slow_the_log_calls(self):
        logger, sink = self.make(sink=Collector(delay=0.01))
        started = time.perf_counter()
        for index in range(100):
            logger.info(f'm{index}')
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.8)         # the sink alone needs a second for them
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(len(sink.messages()), 100)

    def test_eight_threads_logging_lose_nothing_and_keep_the_order_of_the_numbers(self):
        logger, sink = self.make()

        def write(index):
            for number in range(200):
                logger.info(f't{index}-{number}')

        threads = [threading.Thread(target=write, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT_SECONDS)
        logger.flush(timeout=WAIT_SECONDS)
        numbers = [int(eventId.rsplit('-', 1)[1]) for eventId in sink.ids()]
        self.assertEqual(numbers, list(range(1, 1601)))
        self.assertEqual(len(set(sink.messages())), 1600)


class TestEventId(DurableTestCase):

    def test_the_id_is_the_slot_and_the_sequence_number(self):
        logger, sink = self.make()
        for index in range(5):
            logger.info(f'm{index}')
        logger.flush(timeout=WAIT_SECONDS)
        slot = self.spool_stats(logger)['slot']
        self.assertEqual(sink.ids(), [f'{slot}-{number}' for number in range(1, 6)])

    def test_a_field_with_that_name_is_kept(self):
        logger, sink = self.make()
        logger.info('mine', event_id='my-own-id')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.ids(), ['my-own-id'])

    def test_the_field_can_be_renamed_or_switched_off(self):
        logger, sink = self.make(eventIdField='eventId')
        logger.info('x')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(len(sink.got), 1)
        recorded = []

        class Spy(Collector):
            def write(self, text, record):
                recorded.append(dict(record.fields))

        other, _ = self.make(sink=Spy(), eventIdField=None)
        other.info('y', k=1)
        other.flush(timeout=WAIT_SECONDS)
        self.assertEqual(recorded, [{'k': 1}])

    def test_the_id_of_a_record_is_the_same_each_time_it_is_sent(self):
        logger, sink = self.make(sink=Collector(up=False))
        logger.info('again')
        wait_until(lambda: sink.attempts >= 3, what='three attempts')
        sink.up = True
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(len(sink.got), 1)

    def test_the_id_reaches_a_json_sink(self):
        written = []

        class JsonCollector(Collector):
            def __init__(self):
                super().__init__(formatter='json')

            def write(self, text, record):
                written.append(json.loads(text))

        logger, _ = self.make(sink=JsonCollector())
        logger.info('hello')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertRegex(written[0]['fields']['event_id'], r'^\d{8}T\d{6}-\d+-[0-9a-f]{6}-1$')


class TestFailures(DurableTestCase):

    def _outage(self, mode):
        logger, sink = self.make(sink=Collector(up=False, mode=mode))
        for index in range(30):
            logger.info(f'm{index}')
        wait_until(lambda: self.spool_stats(logger)['retries'] >= 2, what='two retries')
        self.assertEqual(sink.messages(), [])
        sink.up = True
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), [f'm{index}' for index in range(30)])
        self.assertEqual(self.spool_stats(logger)['dead'], 0)

    def test_an_outage_where_the_sink_returns_false_loses_nothing(self):
        self._outage('false')

    def test_an_outage_where_the_sink_raises_loses_nothing(self):
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            self._outage('raise')
        finally:
            sys.stderr = previous

    def test_a_queue_of_hints_that_overflows_loses_nothing_and_keeps_the_order(self):
        logger, sink = self.make(sink=Collector(up=False), hintSize=1)
        for index in range(100):
            logger.info(f'm{index}')
        wait_until(lambda: self.spool_stats(logger)['retries'] >= 2, what='retries')
        sink.up = True
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), [f'm{index}' for index in range(100)])
        self.assertGreater(logger.sink_stats('c')['queue']['dropped'], 0)        # hints were dropped, records were not
        self.assertEqual(self.spool_stats(logger)['dropped'], 0)

    def test_a_record_that_cannot_be_rendered_is_parked_and_the_others_go_on(self):
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            logger, sink = self.make(sink=Collector(formatter=poison_formatter))
            for message in ('a', 'poison', 'b'):
                logger.info(message)
            logger.flush(timeout=WAIT_SECONDS)
        finally:
            sys.stderr = previous
        self.assertEqual(sink.messages(), ['a', 'b'])
        self.assertEqual(self.spool_stats(logger)['dead'], 1)
        slotPath = os.path.join(self.base, self.slots()[0])
        with open(os.path.join(slotPath, 'dead'), encoding='ascii') as stream:
            self.assertIn('poison', stream.read())

    def test_a_record_is_given_up_after_the_attempts_that_were_set(self):
        logger, sink = self.make(sink=Collector(failMessage='bad'), maxAttempts=3)
        for message in ('a', 'bad', 'c'):
            logger.info(message)
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), ['a', 'c'])
        stats = self.spool_stats(logger)
        self.assertEqual(stats['dead'], 1)
        self.assertGreaterEqual(stats['retries'], 3)

    def test_without_a_limit_it_keeps_trying_for_ever(self):
        logger, sink = self.make(sink=Collector(up=False))
        logger.info('patient')
        wait_until(lambda: sink.attempts >= 8, what='eight attempts')
        self.assertEqual(self.spool_stats(logger)['dead'], 0)
        sink.up = True
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), ['patient'])

    def test_no_failure_of_the_sink_or_the_disk_reaches_the_caller(self):
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            logger, sink = self.make(sink=Collector(up=False, mode='raise'), segmentBytes=600)
            shutil.rmtree(os.path.join(self.base, self.slots()[0]))     # the folder vanishes under the spool
            for index in range(40):
                logger.info(f'm{index}', pad='x' * 50)
        finally:
            sys.stderr = previous
        self.assertGreater(self.spool_stats(logger)['errors'], 0)
        self.assertEqual(buffer.getvalue().count('could not be kept in the spool'), 1)

    def test_a_full_spool_follows_its_policy_and_only_reject_reaches_the_caller(self):
        logger, sink = self.make(sink=Collector(up=False), maxBytes=3000, segmentBytes=1000, policy='drop_newest')
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            for index in range(40):
                logger.info(f'm{index}')
        finally:
            sys.stderr = previous
        self.assertGreater(self.spool_stats(logger)['dropped'], 0)
        rejecting, _ = self.make(sink=Collector(up=False, host='other'), maxBytes=3000, segmentBytes=1000, policy='reject')
        with self.assertRaises(QueueFull):
            for index in range(40):
                rejecting.info(f'm{index}')


class TestRunsOfAcknowledgements(DurableTestCase):

    def test_a_long_burst_is_acknowledged_in_runs_and_not_one_record_at_a_time(self):
        calls = []
        real = Spool.ack

        def counting(spool, seq):
            calls.append(seq)
            return real(spool, seq)

        sink = Collector()
        sink.gate = threading.Event()                    # the worker is held, so a backlog of hints piles up behind it
        logger, _ = self.make(sink=sink, hintSize=5000)
        with mock.patch.object(Spool, 'ack', counting):
            for index in range(2000):
                logger.info(f'm{index}')
            sink.gate.set()
            logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(len(sink.messages()), 2000)
        self.assertLess(len(calls), 60)                  # one for each record would be 2000
        self.assertEqual(calls[-1], 2000)
        self.assertEqual(self.spool_stats(logger)['depth'], 0)

    def test_what_was_delivered_before_a_failure_is_acknowledged_while_the_next_record_is_retried(self):
        sink = Collector(acceptLimit=7)
        sink.gate = threading.Event()               # a backlog of hints piles up, so the acknowledgements are deferred
        logger, _ = self.make(sink=sink, hintSize=100)
        for index in range(20):
            logger.info(f'm{index}')
        sink.gate.set()
        wait_until(lambda: self.spool_stats(logger)['retries'] >= 2, what='retries')
        stats = self.spool_stats(logger)
        self.assertEqual((stats['acked'], stats['depth']), (7, 13))        # not left waiting for the end of the outage
        sink.acceptLimit = None
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), [f'm{index}' for index in range(20)])

    def test_a_gap_in_the_hints_makes_the_worker_read_the_files_without_sending_a_record_twice(self):
        sink = Collector(delay=0.003)
        sink.gate = threading.Event()
        logger, _ = self.make(sink=sink, hintSize=5)
        for index in range(19):                      # the worker holds the first, the queue keeps the next five, the rest are dropped
            logger.info(f'm{index}')
        self.assertGreater(logger.sink_stats('c')['queue']['dropped'], 0)
        sink.gate.set()
        wait_until(lambda: len(sink.got) >= 2, what='the worker to start')
        logger.info('m19')                           # its hint gets in, and it is far ahead of the one the worker expects
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), [f'm{index}' for index in range(20)])

    def test_stopping_in_the_middle_of_a_backlog_keeps_only_what_was_not_delivered(self):
        sink = Collector(delay=0.004)
        logger, _ = self.make(sink=sink, hintSize=1000)
        for index in range(300):
            logger.info(f'm{index}')
        logger.remove_sink('c', timeout=0.2)
        delivered = len(sink.got)
        self.assertTrue(0 < delivered < 300)
        spool = Spool.open(os.path.join(self.base, self.slots()[0]), 'test', 'Collector',
                           __import__('spool').target_id('Collector', host='c1'), 10 ** 7, 10 ** 8)
        try:
            self.assertEqual([seq for seq, _ in spool.pending()], list(range(delivered + 1, 301)))
        finally:
            spool.close()

    def test_the_last_record_of_a_burst_is_acknowledged_without_waiting_for_more(self):
        logger, sink = self.make()
        logger.info('alone')
        wait_until(lambda: self.spool_stats(logger)['depth'] == 0, what='the record to be acknowledged')

    def test_a_record_parked_in_the_middle_of_a_run_acknowledges_the_run_before_it(self):
        logger, sink = self.make(sink=Collector(formatter=poison_formatter))
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            for message in ['a', 'b', 'poison', 'c', 'd']:
                logger.info(message)
            logger.flush(timeout=WAIT_SECONDS)
        finally:
            sys.stderr = previous
        self.assertEqual(sink.messages(), ['a', 'b', 'c', 'd'])
        stats = self.spool_stats(logger)
        self.assertEqual((stats['depth'], stats['dead'], stats['acked']), (0, 1, 5))

    def test_stopping_acknowledges_what_was_delivered(self):
        logger, sink = self.make()
        for index in range(30):
            logger.info(f'm{index}')
        logger.remove_sink('c', timeout=WAIT_SECONDS)
        self.assertEqual(self.slots(), [])               # everything was acknowledged, so nothing is kept


class TestFlushAndStop(DurableTestCase):

    def test_flush_gives_up_at_its_timeout_when_the_collector_is_down(self):
        logger, sink = self.make(sink=Collector(up=False))
        for index in range(3):
            logger.info(f'm{index}')
        started = time.monotonic()
        logger.flush(timeout=0.3)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(self.spool_stats(logger)['depth'], 3)

    def test_removing_a_sink_keeps_what_was_not_delivered(self):
        logger, sink = self.make(sink=Collector(up=False))
        for index in range(5):
            logger.info(f'm{index}')
        logger.remove_sink('c', timeout=0.2)
        self.assertEqual(len(self.slots()), 1)
        spool = Spool.open(os.path.join(self.base, self.slots()[0]), 'test', 'Collector',
                           __import__('spool').target_id('Collector', host='c1'), 10 ** 7, 10 ** 8)
        try:
            self.assertEqual(len(spool.pending()), 5)
        finally:
            spool.close()

    def test_removing_a_sink_ends_its_worker_thread(self):
        def workers():
            return [thread for thread in threading.enumerate() if thread.name == 'pysimplelog-durable-worker']

        before = len(workers())
        logger, sink = self.make()
        self.assertEqual(len(workers()), before + 1)
        logger.remove_sink('c')
        self.assertEqual(len(workers()), before)

    def test_a_worker_stuck_in_the_sink_does_not_hang_the_removal(self):
        sink = Collector()
        sink.gate = threading.Event()
        logger, _ = self.make(sink=sink)
        logger.info('stuck')
        wait_until(lambda: sink.attempts >= 1 or True, timeout=0.2)
        started = time.monotonic()
        logger.remove_sink('c', timeout=0.3)
        self.assertLess(time.monotonic() - started, 5.0)
        sink.gate.set()


class TestOrphans(DurableTestCase):

    def test_a_new_sink_sends_what_a_crashed_process_left_when_it_is_idle(self):
        orphan = self.leave_orphan(20)
        logger, sink = self.make(adoptOrphans=True, adoptInterval=0.05)
        wait_until(lambda: len(sink.got) >= 20, what='the orphan to be sent')
        self.assertEqual(sink.ids(), [f'{orphan}-{number}' for number in range(1, 21)])
        self.assertEqual(sink.messages(), [f'orphan {index}' for index in range(20)])
        wait_until(lambda: orphan not in self.slots(), what='the orphan slot to be deleted')
        stats = self.spool_stats(logger)
        self.assertEqual((stats['orphans_adopted'], stats['replayed']), (1, 20))

    def test_nothing_is_adopted_unless_asked_to(self):
        orphan = self.leave_orphan(5)
        logger, sink = self.make()
        logger.info('mine')
        logger.flush(timeout=WAIT_SECONDS)
        time.sleep(0.3)
        self.assertEqual(sink.messages(), ['mine'])
        self.assertIn(orphan, self.slots())

    def test_adopting_on_request(self):
        orphan = self.leave_orphan(12)
        logger, sink = self.make()
        result = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        self.assertEqual((result['replayed'], result['orphans_adopted'], result['orphans_skipped']), (12, 1, 0))
        self.assertEqual(sink.ids(), [f'{orphan}-{number}' for number in range(1, 13)])
        self.assertNotIn(orphan, self.slots())

    def test_a_crash_after_delivery_and_before_the_marker_resends_with_the_same_ids(self):
        idsFile = os.path.join(self.root, 'ids.txt')
        process = self.run_script(DELIVER_THEN_CRASH_SCRIPT, self.base, idsFile, '5')
        slot = process.stdout.readline().strip()
        process.wait(timeout=WAIT_SECONDS)
        with open(idsFile) as stream:
            firstRun = stream.read().split()
        self.assertEqual(len(firstRun), 5)
        logger, sink = self.make()
        result = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        self.assertEqual(result['replayed'], 5)
        self.assertEqual(sink.ids(), firstRun)            # the same five ids again: the receiver can tell
        self.assertNotIn(slot, self.slots())

    def test_a_slot_made_for_another_target_or_spool_id_is_left_alone(self):
        otherTarget = self.leave_orphan(4, host='elsewhere')
        otherId = self.leave_orphan(3, spoolId='another')
        logger, sink = self.make()
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            result = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
            logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        finally:
            sys.stderr = previous
        self.assertEqual((result['replayed'], result['orphans_skipped']), (0, 2))
        self.assertEqual(sink.got, [])
        self.assertIn(otherTarget, self.slots())
        self.assertIn(otherId, self.slots())
        self.assertEqual(buffer.getvalue().count('left alone'), 2)         # once for each slot, not for each look

    def test_a_slot_that_a_live_process_holds_is_not_taken_and_is_taken_once_that_process_dies(self):
        process = self.run_script(HOLD_SCRIPT, self.base, '6')
        self.assertEqual(process.stdout.readline().strip(), 'ready')
        logger, sink = self.make()
        self.assertEqual(logger.adopt_orphans('c', timeout=WAIT_SECONDS)['replayed'], 0)
        self.assertEqual(sink.got, [])
        process.kill()
        process.wait(timeout=WAIT_SECONDS)
        self.assertEqual(logger.adopt_orphans('c', timeout=WAIT_SECONDS)['replayed'], 6)

    def test_an_empty_orphan_slot_is_deleted(self):
        orphan = self.leave_orphan(0)
        self.assertIn(orphan, self.slots())
        logger, sink = self.make()
        logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        self.assertNotIn(orphan, self.slots())

    def test_adoption_stops_at_the_first_failure_and_goes_on_later(self):
        orphan = self.leave_orphan(10)
        logger, sink = self.make(sink=Collector(acceptLimit=4))
        result = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        self.assertEqual(result['replayed'], 4)
        self.assertIn(orphan, self.slots())
        sink.acceptLimit = None
        result = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        self.assertEqual(result['replayed'], 10)
        self.assertEqual(sink.messages(), [f'orphan {index}' for index in range(10)])
        self.assertNotIn(orphan, self.slots())

    def test_a_dead_receiver_does_not_block_the_records_of_this_process(self):
        self.leave_orphan(5)
        logger, sink = self.make(sink=Collector(failMessage='orphan 0'), adoptOrphans=True, adoptInterval=0.02)
        for index in range(10):
            logger.info(f'live {index}')
        wait_until(lambda: len([m for m in sink.messages() if m.startswith('live')]) == 10, what='the live records')
        self.assertEqual([m for m in sink.messages() if m.startswith('live')], [f'live {index}' for index in range(10)])

    def test_two_sinks_on_one_base_folder_get_slots_of_their_own(self):
        logger, first = self.make()
        second = Collector()
        logger.add_sink('d', second, threaded=True, spool=self.settings())
        logger.info('both')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual((first.messages(), second.messages()), (['both'], ['both']))
        self.assertEqual(len(self.slots()), 2)
        self.assertNotEqual(first.ids(), second.ids())


class TestFork(DurableTestCase):

    @unittest.skipUnless(hasattr(os, 'fork'), 'needs fork')
    def test_a_forked_child_sends_its_records_at_once_without_the_spool_of_its_parent(self):
        logger, sink = self.make()
        logger.info('before')
        logger.flush(timeout=WAIT_SECONDS)
        readEnd, writeEnd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                buffer = io.StringIO()
                sys.stderr = buffer
                logger.info('from the child')
                outcome = json.dumps({'unspooled': self.spool_stats(logger)['unspooled'], 'raised': False,
                                      'delivered': sink.messages(), 'warned': buffer.getvalue().count('forked')})
            except BaseException as error:
                outcome = json.dumps({'unspooled': -1, 'raised': repr(error)})
            os.write(writeEnd, outcome.encode())
            os._exit(0)
        os.waitpid(pid, 0)
        outcome = json.loads(os.read(readEnd, 1000))
        os.close(readEnd)
        os.close(writeEnd)
        self.assertEqual(outcome, {'unspooled': 1, 'raised': False, 'delivered': ['before', 'from the child'], 'warned': 1})
        logger.info('after')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.messages(), ['before', 'after'])             # the child's record is not in the parent's sink
        self.assertEqual(self.spool_stats(logger)['spooled'], 2)           # nor in the parent's spool


class TestSetup(DurableTestCase):

    def _refused(self, logger, error, sink=None, **options):
        arguments = dict(threaded=True, spool=self.settings())
        arguments.update(options)
        with self.assertRaises(error) as caught:
            logger.add_sink('c', sink or Collector(), **arguments)
        self.assertNotIn('c', logger.sinks)
        self.assertFalse(os.path.exists(self.base) and len(os.listdir(self.base)) > 0)
        return str(caught.exception)

    def setUp(self):
        super().setUp()
        self.logger = Logger('setup', logToFile=False, logToStdout=False)
        self.loggers.append(self.logger)

    def test_a_spool_needs_a_threaded_sink(self):
        self.assertIn('threaded', self._refused(self.logger, ValueError, threaded=False))

    def test_a_spool_needs_a_sink_object_that_writes_outside_the_process(self):
        self.assertIn('Sink object', self._refused(self.logger, TypeError, sink=io.StringIO()))
        self.assertIn('inside this process', self._refused(self.logger, TypeError, sink=StreamSink(io.StringIO())))
        self.assertIn('inside this process', self._refused(self.logger, TypeError, sink=ConsoleSink()))

    def test_a_sink_that_does_not_say_where_it_sends_needs_a_target(self):
        class Nameless(Sink):
            def write(self, text, record):
                pass

        self.assertIn('as text', self._refused(self.logger, TypeError, sink=Nameless()))
        self.logger.add_sink('c', Nameless(), threaded=True, spool=self.settings(target='billing-webhook-prod'))
        self.assertIn('c', self.logger.sinks)

    def test_a_target_does_not_make_a_stream_spoolable(self):
        message = self._refused(self.logger, TypeError, sink=StreamSink(io.StringIO()),
                                spool=self.settings(target='anything'))
        self.assertIn('inside this process', message)

    def test_wrong_settings_are_found_when_the_sink_is_added(self):
        self.assertIn('colour', self._refused(self.logger, TypeError, spool=self.settings(colour='red')))
        self._refused(self.logger, ValueError, spool=self.settings(maxBytes=0))
        self._refused(self.logger, TypeError, spool=5)
        self._refused(self.logger, TypeError, spool={'path': self.base})

    def test_a_dictionary_and_a_config_are_the_same(self):
        self.logger.add_sink('a', Collector(), threaded=True, spool=self.settings())
        self.logger.add_sink('b', Collector(host='c2'), threaded=True, spool=SpoolConfig(**self.settings()))
        self.assertEqual(len(self.slots()), 2)

    def test_a_refused_sink_leaves_its_name_free(self):
        self._refused(self.logger, ValueError, threaded=False)
        self.logger.add_sink('c', Collector(), threaded=True, spool=self.settings())

    def test_the_target_text_decides_who_adopts(self):
        class Anonymous(Sink):
            def __init__(self):
                super().__init__(formatter=lambda record: record.message)
                self.got = []

            def write(self, text, record):
                self.got.append(text.strip())

        logger = self.logger
        down = Anonymous()
        down.write = lambda text, record: False
        logger.add_sink('first', down, threaded=True, spool=self.settings(target='north'))
        logger.info('for the north')
        logger.remove_sink('first', timeout=0.2)
        south = Anonymous()
        logger.add_sink('second', south, threaded=True, spool=self.settings(target='south'))
        buffer, previous = io.StringIO(), sys.stderr
        sys.stderr = buffer
        try:
            result = logger.adopt_orphans('second', timeout=WAIT_SECONDS)
        finally:
            sys.stderr = previous
        self.assertEqual((result['replayed'], result['orphans_skipped']), (0, 1))
        north = Anonymous()
        logger.add_sink('third', north, threaded=True, spool=self.settings(target='north'))
        self.assertEqual(logger.adopt_orphans('third', timeout=WAIT_SECONDS)['replayed'], 1)
        self.assertEqual(north.got, ['for the north'])


class TestStats(DurableTestCase):

    def test_the_spool_numbers(self):
        logger, sink = self.make()
        logger.info('one')
        logger.flush(timeout=WAIT_SECONDS)
        stats = logger.sink_stats('c')
        for key in ('depth', 'bytes', 'segments', 'spooled', 'dropped', 'rejected', 'dead', 'retries', 'replayed',
                    'orphans_adopted', 'orphans_skipped', 'unspooled', 'errors', 'torn', 'corrupt', 'lost', 'slot', 'acked',
                    'next'):
            self.assertIn(key, stats['spool'], key)
        self.assertIsNotNone(stats['queue'])
        self.assertEqual(stats['delivery']['processed'], 1)

    def test_a_sink_without_a_spool_has_none(self):
        logger = Logger('plain', logToFile=False, logToStdout=False)
        logger.add_sink('p', Collector(), threaded=True)
        try:
            self.assertIsNone(logger.sink_stats('p')['spool'])
            with self.assertRaises(ValueError):
                logger.adopt_orphans('p')
        finally:
            logger.clear_sinks(timeout=0.5)
        with self.assertRaises(ValueError):
            logger.adopt_orphans('missing')


class FakeTcp(siem_transport.TCPSyslogTransport):
    """A TCP transport that connects to nothing: it keeps what it is sent, and can fail first."""

    def __init__(self, failures=0):
        super().__init__('Collector.Example.org', 6514)
        self.failures, self.sent = failures, []

    def send(self, payload):
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError('simulated')
        self.sent.append(payload)

    def close(self):
        pass


class TestSiem(DurableTestCase):

    def test_the_siem_sink_keeps_its_records_until_the_collector_has_them(self):
        transport = FakeTcp(failures=3)       # fewer than the breaker takes to open, it then refuses for thirty seconds
        drops = []
        logger = Logger('siem', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        siem_sink.attach(logger, transport, spool=self.settings(), maxRetries=0, onDrop=drops.append)
        for index in range(5):
            logger.error(f'e{index}')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(len(transport.sent), 5)
        self.assertEqual(len(drops), 3)                              # each failed send was reported, as before
        self.assertTrue(all(b'event_id=' in payload for payload in transport.sent))
        self.assertEqual(logger.sink_stats('siem')['spool']['depth'], 0)

    def test_a_spool_that_is_a_dictionary_works_and_the_destination_comes_from_the_transport(self):
        logger = Logger('siem', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        siem_sink.attach(logger, FakeTcp(), spool=self.settings())
        self.assertEqual(len(self.slots()), 1)

    def test_a_console_transport_cannot_be_spooled_and_nothing_is_left_behind(self):
        logger = Logger('siem', logToFile=False, logToStdout=False)
        with self.assertRaises(TypeError):
            siem_sink.attach(logger, siem_transport.ConsoleTransport(io.StringIO()), spool=self.settings())
        self.assertNotIn('siem', logger.sinks)

    def test_the_same_collector_under_another_token_adopts_the_slot(self):
        first = FakeTcp(failures=10 ** 6)
        logger = Logger('siem', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        siem_sink.attach(logger, first, spool=self.settings(), maxRetries=0)
        logger.error('left behind')
        logger.remove_sink('siem', timeout=0.2)
        second = FakeTcp()
        siem_sink.attach(logger, second, spool=self.settings(), maxRetries=0)
        self.assertEqual(logger.adopt_orphans('siem', timeout=WAIT_SECONDS)['replayed'], 1)
        self.assertEqual(len(second.sent), 1)


if __name__ == '__main__':
    unittest.main()
