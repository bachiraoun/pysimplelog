"""Tests of the delivery of records in groups: the sink API, a threaded sink, and a sink with a spool.

Run from the repo root::

    python3 -m unittest tests.test_batching -v
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PACKAGE_DIR)
from simple_log import Logger  # noqa: E402
from sinks import Sink, StreamSink, DELIVERED, RETRY, REJECTED, SPLIT  # noqa: E402
from spool import Spool  # noqa: E402
from record import LogRecord  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

WAIT_SECONDS = 15.0
POISON = 'poison'


def render(record):
    """A formatter that cannot render one message, the others are rendered as their text."""
    if record.message == POISON:
        raise ValueError('cannot render this record')
    return record.message


def wait_until(condition, timeout=WAIT_SECONDS, what='the condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def make_record(message='m'):
    return LogRecord.create(datetime(2026, 1, 1, tzinfo=timezone.utc), 'INFO', 'info', 10.0, 'app', message, 1, 2, 'main')


class GroupSink(Sink):
    """
    A sink that sends groups. Every call is recorded, and what it does is set by ``state``.

    :Parameters:
        #. state (str): ``up`` delivers, ``down`` answers False, ``raise`` raises an exception.
        #. refuse (tuple): Messages that make the destination refuse a whole group that holds one, with SPLIT.
        #. acceptLimit (None, int): The number of records delivered before every call fails.
        #. delay (float): Seconds each call takes.
    """
    SPOOL_DESTINATION = ('host',)

    def __init__(self, host='g1', batchSize=5, batchInterval=0.0, state='up', refuse=(), acceptLimit=None, delay=0.0):
        super().__init__(formatter=render, batchSize=batchSize, batchInterval=batchInterval)
        self.host, self.state, self.refuse, self.acceptLimit, self.delay = host, state, tuple(refuse), acceptLimit, delay
        self.calls, self.callIds, self.got, self.gotIds = [], [], [], []
        # Events that hold the calls one by one: call number n waits for holds[n], when there is one
        self.holds = []
        # Records that came from the files and not from memory: JSON cannot hold a Marker, so the field comes back as text
        self.fromDisk = 0
        self.lock = threading.Lock()

    def write_batch(self, items):
        messages = [record.message for _, record in items]
        ids = [record.fields.get('event_id') for _, record in items]
        with self.lock:
            self.calls.append(messages)
            self.callIds.append(ids)
            self.fromDisk += sum(isinstance(record.fields.get('marker'), str) for _, record in items)
            number = len(self.calls) - 1
        if number < len(self.holds):
            self.holds[number].wait(WAIT_SECONDS)
        if self.delay:
            time.sleep(self.delay)
        if self.state == 'down':
            return False
        if self.state == 'raise':
            raise ConnectionError('the destination is down')
        with self.lock:
            if self.acceptLimit is not None and len(self.got) + len(messages) > self.acceptLimit:
                return False
            if any(message in self.refuse for message in messages):
                return SPLIT
            self.got.extend(messages)
            self.gotIds.extend(ids)

    def delivered(self):
        with self.lock:
            return list(self.got)


def spool_settings(base, **overrides):
    values = dict(path=base, id='batching', maxBytes=10 * 1024 ** 2, totalMaxBytes=100 * 1024 ** 2,
                  retryBackoffBase=0.01, retryBackoffMax=0.05)
    values.update(overrides)
    return values


class Marker:
    """A value that stays an object in memory and becomes text when a record is written to a file and read back."""


class SinkApi(unittest.TestCase):

    def test_the_defaults_deliver_one_record_at_a_time(self):
        sink = Sink(formatter=render)
        self.assertEqual((sink.batchSize, sink.batchInterval), (1, 0.0))

    def test_the_settings_are_kept(self):
        sink = GroupSink(batchSize=512, batchInterval=5.0)
        self.assertEqual((sink.batchSize, sink.batchInterval), (512, 5.0))

    def test_wrong_settings_are_refused(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                GroupSink(batchSize=bad)
        for bad in (1.5, '5', None, True):
            with self.assertRaises(TypeError):
                GroupSink(batchSize=bad)
        with self.assertRaises(ValueError):
            GroupSink(batchInterval=-0.1)
        for bad in ('1', None, True):
            with self.assertRaises(TypeError):
                GroupSink(batchInterval=bad)

    def test_a_group_size_above_one_needs_write_batch(self):
        class OneAtATime(Sink):
            def write(self, text, record):
                pass
        OneAtATime(batchSize=1)
        with self.assertRaises(TypeError):
            OneAtATime(batchSize=2)

    def test_the_settings_cannot_be_changed_afterwards(self):
        sink = GroupSink()
        for name in ('batchSize', 'batchInterval'):
            with self.assertRaises(AttributeError):
                setattr(sink, name, 3)

    def test_every_record_of_a_group_that_goes_through_is_delivered(self):
        sink = GroupSink()
        results = sink.deliver_batch([make_record(str(number)) for number in range(4)])
        self.assertEqual(results, [DELIVERED] * 4)
        self.assertEqual(sink.calls, [['0', '1', '2', '3']])
        self.assertEqual(sink.stats['processed'], 4)

    def test_an_empty_group_does_nothing(self):
        sink = GroupSink()
        self.assertEqual(sink.deliver_batch([]), [])
        self.assertEqual(sink.calls, [])

    def test_a_record_the_formatter_cannot_render_is_rejected_alone(self):
        sink = GroupSink()
        with contextlib.redirect_stderr(io.StringIO()):
            results = sink.deliver_batch([make_record('a'), make_record(POISON), make_record('c')])
        self.assertEqual(results, [DELIVERED, REJECTED, DELIVERED])
        self.assertEqual(sink.calls, [['a', 'c']])
        self.assertEqual(sink.stats['processed'], 2)
        self.assertEqual(sink.stats['failed'], 1)

    def test_a_group_of_records_that_cannot_be_rendered_is_not_sent(self):
        sink = GroupSink()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sink.deliver_batch([make_record(POISON)] * 3), [REJECTED] * 3)
        self.assertEqual(sink.calls, [])

    def test_false_and_an_exception_mean_try_again_for_the_whole_group(self):
        for state in ('down', 'raise'):
            sink = GroupSink(state=state)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(sink.deliver_batch([make_record('a'), make_record('b')]), [RETRY, RETRY])
            self.assertEqual((sink.stats['processed'], sink.stats['failed']), (0, 1))

    def test_a_failed_attempt_counts_once_whatever_the_size_of_the_group(self):
        sink = GroupSink(state='down')
        sink.deliver_batch([make_record(str(number)) for number in range(5)])
        self.assertEqual(sink.stats['failed'], 1)

    def test_a_group_the_destination_refuses_as_a_whole_is_split(self):
        sink = GroupSink(refuse=('bad',))
        self.assertEqual(sink.deliver_batch([make_record('a'), make_record('bad')]), [SPLIT, SPLIT])
        self.assertEqual(sink.deliver_batch([make_record('bad')]), [SPLIT])

    def test_a_formatter_failure_and_a_retry_in_one_group(self):
        sink = GroupSink(state='down')
        with contextlib.redirect_stderr(io.StringIO()):
            results = sink.deliver_batch([make_record('a'), make_record(POISON), make_record('c')])
        self.assertEqual(results, [RETRY, REJECTED, RETRY])

    def test_the_latency_is_the_time_of_a_call_and_not_of_a_record(self):
        sink = GroupSink(delay=0.05)
        sink.deliver_batch([make_record(str(number)) for number in range(10)])
        stats = sink.stats
        self.assertEqual(stats['processed'], 10)
        self.assertTrue(0.04 < stats['latency_mean'] < 0.5, stats['latency_mean'])
        self.assertEqual(stats['latency_mean'], stats['latency_max'])

    def test_emit_batch_never_raises(self):
        sink = GroupSink(state='raise')
        with contextlib.redirect_stderr(io.StringIO()):
            sink.emit_batch([make_record('a')])
        self.assertEqual(sink.stats['failed'], 1)

    def test_deliver_of_one_record_goes_through_write_batch(self):
        sink = GroupSink()
        self.assertEqual(sink.deliver(make_record('a')), DELIVERED)
        self.assertEqual(sink.calls, [['a']])

    def test_deliver_of_one_record_the_destination_refuses_is_rejected(self):
        sink = GroupSink(refuse=('bad',))
        self.assertEqual(sink.deliver(make_record('bad')), REJECTED)

    def test_deliver_of_one_record_with_the_destination_down_is_retry(self):
        self.assertEqual(GroupSink(state='down').deliver(make_record('a')), RETRY)

    def test_a_sink_that_does_not_send_groups_is_not_changed(self):
        calls = []

        class Plain(Sink):
            def write(self, text, record):
                calls.append(text)
        sink = Plain(formatter=render)
        self.assertEqual(sink.deliver(make_record('a')), DELIVERED)
        self.assertEqual(calls, ['a\n'])
        with self.assertRaises(NotImplementedError):
            sink.write_batch([('a', make_record())])


class ThreadedSink(unittest.TestCase):

    def setUp(self):
        self.loggers = []
        self.addCleanup(self._close)

    def _close(self):
        for logger in self.loggers:
            with contextlib.suppress(Exception):
                logger.clear_sinks(timeout=2.0)

    def make(self, sink, **arguments):
        logger = Logger('batch', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        arguments.setdefault('threadQueuePolicy', 'block')
        logger.add_sink('g', sink, threaded=True, **arguments)
        return logger

    def test_the_groups_have_the_size_asked_for_and_the_order_is_kept(self):
        sink = GroupSink(batchSize=5, batchInterval=30.0)
        logger = self.make(sink)
        for number in range(12):
            logger.info(str(number))
        wait_until(lambda: len(sink.delivered()) >= 10, what='two full groups')
        self.assertEqual(sink.calls[:2], [['0', '1', '2', '3', '4'], ['5', '6', '7', '8', '9']])
        logger.flush()
        self.assertEqual(sink.delivered(), [str(number) for number in range(12)])
        self.assertEqual(sink.calls[2], ['10', '11'])

    def test_a_group_that_is_not_full_waits_for_the_interval(self):
        sink = GroupSink(batchSize=100, batchInterval=0.4)
        logger = self.make(sink)
        started = time.monotonic()
        for number in range(3):
            logger.info(str(number))
        time.sleep(0.15)
        self.assertEqual(sink.calls, [])
        wait_until(lambda: len(sink.calls) == 1, what='the group')
        self.assertTrue(0.3 < time.monotonic() - started < 3.0)
        self.assertEqual(sink.calls, [['0', '1', '2']])

    def test_without_an_interval_what_is_waiting_goes_at_once_and_a_backlog_makes_groups(self):
        sink = GroupSink(batchSize=50, batchInterval=0.0, delay=0.05)
        logger = self.make(sink)
        for number in range(300):
            logger.info(str(number))
        logger.flush()
        self.assertEqual(sink.delivered(), [str(number) for number in range(300)])
        self.assertLess(len(sink.calls), 100)
        self.assertTrue(all(len(call) <= 50 for call in sink.calls))
        self.assertTrue(any(len(call) > 1 for call in sink.calls))

    def test_flush_does_not_wait_for_the_interval(self):
        sink = GroupSink(batchSize=100, batchInterval=60.0)
        logger = self.make(sink)
        logger.info('a')
        started = time.monotonic()
        logger.flush()
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(sink.delivered(), ['a'])

    def test_removing_the_sink_does_not_wait_for_the_interval_and_loses_nothing(self):
        sink = GroupSink(batchSize=100, batchInterval=60.0)
        logger = self.make(sink)
        for number in range(7):
            logger.info(str(number))
        started = time.monotonic()
        logger.remove_sink('g')
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(sink.delivered(), [str(number) for number in range(7)])

    def test_a_flush_with_nothing_waiting_returns_at_once(self):
        logger = self.make(GroupSink(batchSize=100, batchInterval=60.0))
        started = time.monotonic()
        logger.flush()
        self.assertLess(time.monotonic() - started, 5.0)

    def test_a_failing_destination_drops_the_group_and_the_worker_goes_on(self):
        sink = GroupSink(batchSize=3, batchInterval=0.0, state='raise')
        logger = self.make(sink)
        with contextlib.redirect_stderr(io.StringIO()):
            for number in range(3):
                logger.info(f'lost{number}')
            logger.flush()
        sink.state = 'up'
        logger.info('after')
        logger.flush()
        self.assertEqual(sink.delivered(), ['after'])

    def test_a_record_the_formatter_cannot_render_does_not_stop_the_others(self):
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        logger = self.make(sink)
        with contextlib.redirect_stderr(io.StringIO()):
            for message in ('a', POISON, 'c'):
                logger.info(message)
            logger.flush()
        self.assertEqual(sink.delivered(), ['a', 'c'])

    def test_many_threads_lose_nothing_and_each_keeps_its_order(self):
        sink = GroupSink(batchSize=25, batchInterval=0.01)
        logger = self.make(sink, threadQueueSize=64)

        def work(number):
            for index in range(200):
                logger.info(f'{number}-{index}')
        threads = [threading.Thread(target=work, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        logger.flush()
        got = sink.delivered()
        self.assertEqual(len(got), 1600)
        self.assertEqual(len(set(got)), 1600)
        for number in range(8):
            self.assertEqual([int(text.split('-')[1]) for text in got if text.startswith(f'{number}-')], list(range(200)))
        self.assertTrue(all(len(call) <= 25 for call in sink.calls))

    def test_with_the_logger_queue_in_front(self):
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        logger = Logger('batch', logToFile=False, logToStdout=False, enqueue=True)
        self.loggers.append(logger)
        logger.add_sink('g', sink, threaded=True, threadQueuePolicy='block')
        for number in range(100):
            logger.info(str(number))
        logger.flush()
        self.assertEqual(sink.delivered(), [str(number) for number in range(100)])

    def test_a_sink_that_is_not_threaded_gets_one_record_at_a_time(self):
        sink = GroupSink(batchSize=10, batchInterval=30.0)
        logger = Logger('batch', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        logger.add_sink('g', sink)
        for number in range(3):
            logger.info(str(number))
        self.assertEqual(sink.calls, [['0'], ['1'], ['2']])

    def test_the_stats_of_the_sink(self):
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        logger = self.make(sink)
        for number in range(25):
            logger.info(str(number))
        logger.flush()
        delivery = logger.sink_stats('g')['delivery']
        self.assertEqual((delivery['processed'], delivery['failed']), (25, 0))
        self.assertEqual(logger.sink_stats('g')['queue']['dropped'], 0)

    def test_a_program_that_ends_with_a_group_waiting_still_sends_it(self):
        script = textwrap.dedent(f"""
            import atexit, sys
            sys.path.insert(0, {TESTS_DIR!r})
            from test_batching import GroupSink
            from simple_log import Logger
            sink = GroupSink(batchSize=100, batchInterval=60.0)
            # Registered first, so that it runs last, after the logger has flushed
            atexit.register(lambda: print(sink.delivered()))
            logger = Logger('batch', logToFile=False, logToStdout=False)
            logger.add_sink('g', sink, threaded=True, threadQueuePolicy='block')
            for number in range(5):
                logger.info(str(number))
        """)
        started = time.monotonic()
        completed = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertLess(time.monotonic() - started, 50)
        self.assertEqual(completed.stdout.strip(), "['0', '1', '2', '3', '4']")


class SpoolCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='batchtest-')
        self.base = os.path.join(self.root, 'spools')
        self.loggers = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for logger in self.loggers:
            with contextlib.suppress(Exception):
                logger.clear_sinks(timeout=1.0)
        shutil.rmtree(self.root, ignore_errors=True)

    def make(self, sink=None, hintSize=1000, **overrides):
        logger = Logger('batch', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        sink = sink or GroupSink()
        logger.add_sink('g', sink, threaded=True, threadQueueSize=hintSize, spool=spool_settings(self.base, **overrides))
        return logger, sink

    def spool_stats(self, logger):
        return logger.sink_stats('g')['spool']


class TestSpoolInGroups(SpoolCase):

    def test_everything_is_delivered_in_order_in_groups_and_the_spool_ends_empty(self):
        sink = GroupSink(batchSize=20, batchInterval=0.05)
        logger, _ = self.make(sink)
        for number in range(200):
            logger.info(str(number))
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [str(number) for number in range(200)])
        self.assertTrue(all(len(call) <= 20 for call in sink.calls))
        self.assertLess(len(sink.calls), 100)
        self.assertEqual(self.spool_stats(logger)['depth'], 0)

    def test_the_interval_is_waited_for_and_a_flush_cuts_it(self):
        sink = GroupSink(batchSize=100, batchInterval=60.0)
        logger, _ = self.make(sink)
        for number in range(3):
            logger.info(str(number))
        time.sleep(0.2)
        self.assertEqual(sink.calls, [])
        started = time.monotonic()
        logger.flush(timeout=WAIT_SECONDS)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(sink.delivered(), ['0', '1', '2'])

    def test_removing_the_sink_does_not_wait_for_the_interval(self):
        sink = GroupSink(batchSize=100, batchInterval=60.0)
        logger, _ = self.make(sink)
        for number in range(4):
            logger.info(str(number))
        started = time.monotonic()
        logger.remove_sink('g', timeout=WAIT_SECONDS)
        self.assertLess(time.monotonic() - started, 10.0)
        self.assertEqual(sink.delivered(), ['0', '1', '2', '3'])

    def test_each_record_has_its_own_stable_event_id_that_does_not_change_when_it_is_sent_again(self):
        sink = GroupSink(batchSize=4, batchInterval=0.0, state='down')
        logger, _ = self.make(sink)
        for number in range(4):
            logger.info(str(number))
        wait_until(lambda: len(sink.calls) >= 3, what='three attempts')
        sink.state = 'up'
        logger.flush(timeout=WAIT_SECONDS)
        slot = self.spool_stats(logger)['slot']
        self.assertEqual(sink.gotIds, [f'{slot}-{number}' for number in range(1, 5)])
        idsOfMessage = {}
        for messages, ids in zip(sink.calls, sink.callIds):
            for message, eventId in zip(messages, ids):
                idsOfMessage.setdefault(message, set()).add(eventId)
        self.assertEqual({message: len(ids) for message, ids in idsOfMessage.items()}, {str(number): 1 for number in range(4)})

    def test_a_group_that_fails_is_sent_again_whole_and_nothing_after_it_goes_first(self):
        sink = GroupSink(batchSize=5, batchInterval=0.0, state='down')
        logger, _ = self.make(sink)
        for number in range(12):
            logger.info(str(number))
        wait_until(lambda: self.spool_stats(logger)['retries'] >= 3, what='retries')
        self.assertEqual(sink.delivered(), [])
        sink.state = 'up'
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [str(number) for number in range(12)])

    def test_a_failed_attempt_is_one_retry_whatever_the_size_of_the_group(self):
        sink = GroupSink(batchSize=50, batchInterval=0.0, state='down')
        logger, _ = self.make(sink)
        for number in range(50):
            logger.info(str(number))
        wait_until(lambda: len(sink.calls) >= 4, what='four attempts')
        sink.state = 'up'
        logger.flush(timeout=WAIT_SECONDS)
        retries = self.spool_stats(logger)['retries']
        self.assertLess(retries, 50)
        self.assertGreaterEqual(retries, 3)

    def test_a_record_that_cannot_be_rendered_is_parked_and_the_rest_of_the_group_goes(self):
        sink = GroupSink(batchSize=10, batchInterval=0.2)
        logger, _ = self.make(sink)
        with contextlib.redirect_stderr(io.StringIO()):
            for message in ('a', POISON, 'c', 'd'):
                logger.info(message)
            logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), ['a', 'c', 'd'])
        self.assertEqual(self.spool_stats(logger)['dead'], 1)
        self.assertEqual(self.spool_stats(logger)['depth'], 0)

    def test_a_formatter_failure_with_the_destination_down_waits_for_the_destination(self):
        sink = GroupSink(batchSize=10, batchInterval=0.2, state='down')
        logger, _ = self.make(sink)
        with contextlib.redirect_stderr(io.StringIO()):
            for message in ('a', POISON, 'c'):
                logger.info(message)
            wait_until(lambda: self.spool_stats(logger)['retries'] >= 2, what='retries')
            sink.state = 'up'
            logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), ['a', 'c'])
        self.assertEqual(self.spool_stats(logger)['dead'], 1)

    def _refused(self, messages, bad):
        # The group is full when the last message arrives, so it is sent whole, and the interval is never waited for
        sink = GroupSink(batchSize=len(messages), batchInterval=60.0, refuse=bad, state='down')
        logger, _ = self.make(sink)
        for message in messages:
            logger.info(message)
        wait_until(lambda: len(sink.calls) >= 1, what='the first attempt')
        sink.state = 'up'
        logger.flush(timeout=WAIT_SECONDS)
        return logger, sink

    def test_a_group_the_destination_refuses_is_split_until_the_bad_record_is_found(self):
        messages = [f'm{number}' for number in range(20)]
        for position in (0, 7, 19):
            with self.subTest(position=position):
                self.tearDown_loggers()
                bad = messages[position]
                logger, sink = self._refused(messages, (bad,))
                self.assertEqual(sink.delivered(), [message for message in messages if message != bad])
                self.assertEqual(self.spool_stats(logger)['dead'], 1)
                self.assertEqual(self.spool_stats(logger)['depth'], 0)

    def test_the_splitting_needs_few_calls(self):
        messages = [f'm{number}' for number in range(64)]
        logger, sink = self._refused(messages, ('m33',))
        halvings = [call for call in sink.calls if 'm33' in call and len(call) < 64]
        # One call for each level of halving: 32, 16, 8, 4, 2 and the record alone
        self.assertEqual([len(call) for call in halvings], [32, 16, 8, 4, 2, 1])

    def test_two_bad_records_are_both_found(self):
        messages = [f'm{number}' for number in range(16)]
        logger, sink = self._refused(messages, ('m3', 'm12'))
        self.assertEqual(sink.delivered(), [message for message in messages if message not in ('m3', 'm12')])
        self.assertEqual(self.spool_stats(logger)['dead'], 2)

    def test_a_group_of_bad_records_only_is_all_parked(self):
        logger, sink = self._refused(['bad1', 'bad2', 'bad3'], ('bad1', 'bad2', 'bad3'))
        self.assertEqual(sink.delivered(), [])
        self.assertEqual(self.spool_stats(logger)['dead'], 3)

    def test_the_good_records_around_a_bad_one_keep_their_order(self):
        messages = [f'm{number}' for number in range(30)]
        logger, sink = self._refused(messages, ('m10',))
        good = [message for message in messages if message != 'm10']
        self.assertEqual(sink.delivered(), good)

    def test_after_max_attempts_the_whole_group_is_parked(self):
        sink = GroupSink(batchSize=4, batchInterval=60.0, state='down')
        logger, _ = self.make(sink, maxAttempts=3)
        for number in range(4):
            logger.info(str(number))
        wait_until(lambda: self.spool_stats(logger)['dead'] == 4, what='the group to be parked')
        self.assertEqual(self.spool_stats(logger)['depth'], 0)
        self.assertEqual(len(sink.calls), 3)
        sink.state = 'up'
        logger.info('later')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), ['later'])

    def test_hints_that_were_dropped_are_found_in_the_files(self):
        sink = GroupSink(batchSize=10, batchInterval=0.0, delay=0.02)
        logger, _ = self.make(sink, hintSize=3)
        for number in range(300):
            logger.info(str(number))
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [str(number) for number in range(300)])

    def test_a_group_of_hints_with_a_gap_is_not_sent_before_the_records_in_the_gap(self):
        # Call 0 and call 1 are held. While call 0 waits, the queue of hints (size 2) takes records 2 and 3 and drops 4 and 5.
        # While call 1 waits, the queue has room again and takes record 6. The group that holds only record 6 comes after a gap,
        # and 4 and 5 must be read from the files and sent first
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        sink.holds = [threading.Event(), threading.Event()]
        logger, _ = self.make(sink, hintSize=2)
        logger.info('1')
        wait_until(lambda: len(sink.calls) == 1, what='the first call')
        for message in ('2', '3', '4', '5'):
            logger.info(message)
        sink.holds[0].set()
        wait_until(lambda: len(sink.calls) == 2, what='the second call')
        logger.info('6')
        sink.holds[1].set()
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), ['1', '2', '3', '4', '5', '6'])
        self.assertEqual(self.spool_stats(logger)['depth'], 0)

    def test_catching_up_from_the_files_sends_groups_as_large_as_the_sink_asks(self):
        # The first call is held while many records pile up and most of their hints are dropped. The worker then reads the files,
        # and a group of 300 must not be cut into groups of 100, the usual size of a read
        sink = GroupSink(batchSize=300, batchInterval=0.0)
        sink.holds = [threading.Event()]
        logger, _ = self.make(sink, hintSize=2)
        logger.info('0')
        wait_until(lambda: len(sink.calls) == 1, what='the first call')
        for number in range(1, 251):
            logger.info(str(number))
        sink.holds[0].set()
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [str(number) for number in range(251)])
        self.assertGreater(max(len(call) for call in sink.calls), 100)

    def test_a_steady_flow_is_sent_from_memory_and_not_read_back_from_the_files(self):
        sink = GroupSink(batchSize=5, batchInterval=0.0, delay=0.01)
        logger, _ = self.make(sink)
        marker = Marker()
        for _ in range(200):
            logger.info('m', marker=marker)
        logger.flush(timeout=WAIT_SECONDS * 2)
        self.assertEqual(len(sink.delivered()), 200)
        self.assertLess(sink.fromDisk, 40)

    def test_many_threads_lose_nothing(self):
        sink = GroupSink(batchSize=25, batchInterval=0.01)
        logger, _ = self.make(sink)

        def work(number):
            for index in range(150):
                logger.info(f'{number}-{index}')
        threads = [threading.Thread(target=work, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        logger.flush(timeout=WAIT_SECONDS * 2)
        got = sink.delivered()
        self.assertEqual(len(got), 1200)
        self.assertEqual(len(set(got)), 1200)
        for number in range(8):
            self.assertEqual([int(text.split('-')[1]) for text in got if text.startswith(f'{number}-')], list(range(150)))

    def test_the_stats(self):
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        logger, _ = self.make(sink)
        for number in range(40):
            logger.info(str(number))
        logger.flush(timeout=WAIT_SECONDS)
        stats = logger.sink_stats('g')
        self.assertEqual(stats['delivery']['processed'], 40)
        self.assertEqual((stats['spool']['depth'], stats['spool']['dead'], stats['spool']['lost']), (0, 0, 0))

    def tearDown_loggers(self):
        """Closes the loggers made so far, so a test can run the same situation more than once."""
        for logger in self.loggers:
            with contextlib.suppress(Exception):
                logger.clear_sinks(timeout=2.0)
        self.loggers.clear()
        shutil.rmtree(self.base, ignore_errors=True)


CRASH_SCRIPT = textwrap.dedent('''
    import os, sys, time
    testsDir, packageDir, base, host, count, limit = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6])
    sys.path.insert(0, testsDir)
    from test_batching import GroupSink, spool_settings
    from simple_log import Logger
    sink = GroupSink(host=host, batchSize=10, batchInterval=0.0, acceptLimit=limit)
    logger = Logger('batch', logToFile=False, logToStdout=False)
    logger.add_sink('g', sink, threaded=True, spool=spool_settings(base))
    for index in range(count):
        logger.info(f'm{index}')
    deadline = time.time() + 20
    # A group is delivered whole or not at all, so the destination stops at the last group that fits in the limit
    while time.time() < deadline and logger.sink_stats('g')['spool']['retries'] == 0:
        time.sleep(0.005)
    print(logger.sink_stats('g')['spool']['slot'], len(sink.delivered()), flush=True)
    os._exit(0)
''')


class TestLeftBehind(SpoolCase):

    def _crash(self, count, limit, host='g1'):
        completed = subprocess.run([sys.executable, '-c', CRASH_SCRIPT, TESTS_DIR, PACKAGE_DIR, self.base, host, str(count), str(limit)],
                                   capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        slot, delivered = completed.stdout.split()
        return slot, int(delivered)

    def test_a_slot_left_by_a_crash_is_sent_in_groups_and_nothing_is_missing(self):
        slot, delivered = self._crash(count=85, limit=30)
        self.assertTrue(0 < delivered <= 30, delivered)
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        logger, _ = self.make(sink)
        result = logger.adopt_orphans('g', timeout=WAIT_SECONDS)
        self.assertIsNotNone(result)
        got = sink.delivered()
        everything = [f'm{number}' for number in range(85)]
        # The records the crash left unacknowledged may come again, none may be missing, and the order is the original one
        start = everything.index(got[0])
        self.assertLessEqual(start, delivered)
        self.assertEqual(got, everything[start:])
        self.assertTrue(all(len(call) <= 10 for call in sink.calls))
        self.assertGreater(max(len(call) for call in sink.calls), 1)
        self.assertEqual(result['orphans_adopted'], 1)
        self.assertEqual(result['replayed'], len(got))
        self.assertNotIn(slot, [os.path.basename(path) for path in Spool.slots(self.base)])

    def test_with_adopt_orphans_on_the_sink_does_it_by_itself(self):
        self._crash(count=40, limit=0)
        sink = GroupSink(batchSize=10, batchInterval=0.0)
        logger, _ = self.make(sink, adoptOrphans=True, adoptInterval=0.05)
        wait_until(lambda: len(sink.delivered()) >= 40, what='the replay')
        self.assertEqual(sink.delivered(), [f'm{number}' for number in range(40)])

    def test_a_slot_made_for_another_destination_is_left_alone(self):
        slot, _ = self._crash(count=10, limit=0, host='other')
        sink = GroupSink(host='g1', batchSize=10, batchInterval=0.0)
        logger, _ = self.make(sink)
        with contextlib.redirect_stderr(io.StringIO()):
            result = logger.adopt_orphans('g', timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [])
        self.assertEqual(result['orphans_skipped'], 1)
        self.assertIn(slot, [os.path.basename(path) for path in Spool.slots(self.base)])

    def test_a_destination_that_is_down_leaves_the_slot_for_later(self):
        self._crash(count=20, limit=0)
        sink = GroupSink(batchSize=10, batchInterval=0.0, state='down')
        logger, _ = self.make(sink)
        result = logger.adopt_orphans('g', timeout=WAIT_SECONDS)
        self.assertEqual((sink.delivered(), result['replayed']), ([], 0))
        sink.state = 'up'
        result = logger.adopt_orphans('g', timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [f'm{number}' for number in range(20)])
        self.assertEqual(result['replayed'], 20)

    def test_a_bad_record_in_a_left_slot_is_parked_there_and_the_others_arrive(self):
        self._crash(count=20, limit=0)
        sink = GroupSink(batchSize=10, batchInterval=0.0, refuse=('m5',))
        logger, _ = self.make(sink)
        logger.adopt_orphans('g', timeout=WAIT_SECONDS)
        self.assertEqual(sink.delivered(), [f'm{number}' for number in range(20) if number != 5])


class TestOneAtATimeIsUnchanged(SpoolCase):

    def test_a_sink_with_a_group_size_of_one_never_uses_the_group_calls(self):
        calls = []

        class Single(Sink):
            SPOOL_DESTINATION = ('host',)
            host = 'single'

            def __init__(inner):
                super().__init__(formatter=render)
                inner.got = []

            def write(inner, text, record):
                inner.got.append(record.message)

            def deliver_batch(inner, records):
                calls.append(records)
                return super().deliver_batch(records)

        sink = Single()
        logger, _ = self.make(sink)
        for number in range(50):
            logger.info(str(number))
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.got, [str(number) for number in range(50)])
        self.assertEqual(calls, [])

    def test_a_threaded_sink_with_a_group_size_of_one_never_uses_the_group_calls(self):
        calls = []

        class Single(Sink):
            def __init__(inner):
                super().__init__(formatter=render)
                inner.got = []

            def write(inner, text, record):
                inner.got.append(record.message)

            def deliver_batch(inner, records):
                calls.append(records)

        sink = Single()
        logger = Logger('batch', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        logger.add_sink('g', sink, threaded=True, threadQueuePolicy='block')
        for number in range(50):
            logger.info(str(number))
        logger.flush()
        self.assertEqual(sink.got, [str(number) for number in range(50)])
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
