"""Delivery guarantees of the pipeline: queue policies, metrics, concurrency, shutdown and sink failure.

Run from the repo root::

    python3 -m unittest tests.test_delivery -v

Every saturation scenario uses a gating sink whose ``write`` waits on a ``threading.Event``, so a queue
is filled on demand and the tests never depend on sleeping for a particular state.
"""
import io
import os
import queue
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from SimpleLog import Logger  # noqa: E402
from queues import BoundedQueue, QueueFull, validate_queue_policy  # noqa: E402
from sinks import Sink  # noqa: E402

# Seconds a test may wait for a state that must be reached, wide enough for a loaded machine
WAIT_SECONDS = 5.0


class GateSink(Sink):
    """A sink that keeps every record text and blocks in ``write`` until the gate is opened."""

    def __init__(self, isOpen=False):
        super().__init__(formatter='{message}')
        self.gate = threading.Event()
        self.texts = []
        self.entered = threading.Event()
        if isOpen:
            self.gate.set()

    def write(self, text, record):
        self.entered.set()
        self.gate.wait(WAIT_SECONDS)
        self.texts.append(text.strip())


class RaisingSink(Sink):
    """A sink whose ``write`` always fails."""

    def __init__(self):
        super().__init__(formatter='{message}')

    def write(self, text, record):
        raise OSError('disk gone')


def make_logger(**kwargs):
    """Returns a Logger without built-in outputs, so only the sinks added by a test receive records."""
    return Logger('delivery', logToStdout=False, logToFile=False, **kwargs)


def silence_stderr():
    """Swaps standard error for a buffer and returns the buffer with the stream to restore."""
    buffer, previous = io.StringIO(), sys.stderr
    sys.stderr = buffer
    return buffer, previous


class TestBoundedQueue(unittest.TestCase):

    def setUp(self):
        # Drops print their warning, which would clutter the test report
        self.hiddenStderr, self.savedStderr = silence_stderr()

    def tearDown(self):
        sys.stderr = self.savedStderr

    def test_validate_policy(self):
        for policy in ('block', 'drop_newest', 'drop_oldest', 'reject'):
            self.assertEqual(validate_queue_policy(policy), policy)
        with self.assertRaises(ValueError):
            validate_queue_policy('drop')
        with self.assertRaises(TypeError):
            validate_queue_policy(None)

    def test_arguments_are_validated(self):
        for badSize in (0, -1):
            with self.assertRaises(ValueError):
                BoundedQueue(badSize)
        for badSize in (1.5, True, '3'):
            with self.assertRaises(TypeError):
                BoundedQueue(badSize)
        with self.assertRaises(ValueError):
            BoundedQueue(1, 'block', -1)
        with self.assertRaises(TypeError):
            BoundedQueue(1, 'block', 'soon')

    def test_drop_newest_keeps_the_oldest(self):
        boundedQueue = BoundedQueue(2, 'drop_newest')
        results = [boundedQueue.put(item) for item in (1, 2, 3, 4)]
        self.assertEqual(results, [True, True, False, False])
        self.assertEqual([boundedQueue.get(), boundedQueue.get()], [1, 2])
        self.assertEqual(boundedQueue.stats()['dropped'], 2)

    def test_drop_oldest_keeps_the_newest(self):
        boundedQueue = BoundedQueue(2, 'drop_oldest')
        for item in (1, 2, 3, 4):
            self.assertTrue(boundedQueue.put(item))
        self.assertEqual([boundedQueue.get(), boundedQueue.get()], [3, 4])
        self.assertEqual(boundedQueue.stats()['dropped'], 2)

    def test_reject_raises_and_counts(self):
        boundedQueue = BoundedQueue(1, 'reject')
        boundedQueue.put('a')
        with self.assertRaises(QueueFull):
            boundedQueue.put('b')
        self.assertIsInstance(QueueFull(), queue.Full)
        stats = boundedQueue.stats()
        self.assertEqual((stats['rejected'], stats['dropped'], stats['depth']), (1, 0, 1))

    def test_block_waits_for_a_free_place(self):
        boundedQueue = BoundedQueue(1, 'block')
        boundedQueue.put('a')
        threading.Timer(0.1, boundedQueue.get).start()
        self.assertTrue(boundedQueue.put('b'))
        self.assertEqual(boundedQueue.stats()['dropped'], 0)

    def test_block_timeout_drops_the_new_item(self):
        boundedQueue = BoundedQueue(1, 'block', 0.05)
        boundedQueue.put('a')
        started = time.monotonic()
        buffer, previous = silence_stderr()
        try:
            self.assertFalse(boundedQueue.put('b'))
        finally:
            sys.stderr = previous
        self.assertGreaterEqual(time.monotonic() - started, 0.04)
        self.assertEqual(boundedQueue.stats()['dropped'], 1)

    def test_one_warning_for_a_run_of_drops_and_a_new_one_after_a_recovery(self):
        boundedQueue = BoundedQueue(1, 'drop_newest', name='test queue')
        buffer, previous = silence_stderr()
        try:
            boundedQueue.put('a')
            for _ in range(5):
                boundedQueue.put('x')
            boundedQueue.get()
            boundedQueue.put('b')     # a free place: the run of drops is over
            for _ in range(5):
                boundedQueue.put('x')
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('WARNING'), 2)

    def test_join_waits_for_task_done(self):
        boundedQueue = BoundedQueue()
        boundedQueue.put('a')
        self.assertFalse(boundedQueue.join(0.05))
        boundedQueue.get()
        boundedQueue.task_done()
        self.assertTrue(boundedQueue.join(0.05))

    def test_get_timeout_raises_empty(self):
        with self.assertRaises(queue.Empty):
            BoundedQueue().get(timeout=0.01)

    def test_policy_and_size_change_at_runtime(self):
        boundedQueue = BoundedQueue(1, 'reject')
        boundedQueue.put('a')
        boundedQueue.set_policy('drop_newest')
        self.assertFalse(boundedQueue.put('b'))
        boundedQueue.set_max_size(None)
        self.assertTrue(boundedQueue.put('c'))


class TestThreadedSinkPolicies(unittest.TestCase):

    def _saturate(self, policy):
        """Fills a threaded sink whose worker is held by the gate, then returns the logger and the sink."""
        logger, sink = make_logger(), GateSink()
        logger.add_sink('gate', sink, threaded=True, threadQueueSize=3, threadQueuePolicy=policy)
        logger.info('first')
        self.assertTrue(sink.entered.wait(WAIT_SECONDS))   # the worker now holds 'first' and is frozen
        return logger, sink

    def test_drop_newest_keeps_the_oldest_records(self):
        logger, sink = self._saturate('drop_newest')
        buffer, previous = silence_stderr()
        try:
            for index in range(10):
                logger.info(f'm{index}')
        finally:
            sys.stderr = previous
        stats = logger.sink_stats('gate')['queue']
        sink.gate.set()
        logger.flush()
        self.assertEqual(sink.texts, ['first', 'm0', 'm1', 'm2'])
        self.assertEqual(stats['dropped'], 7)
        self.assertEqual(buffer.getvalue().count('WARNING'), 1)

    def test_drop_oldest_keeps_the_newest_records(self):
        logger, sink = self._saturate('drop_oldest')
        buffer, previous = silence_stderr()
        try:
            for index in range(10):
                logger.info(f'm{index}')
        finally:
            sys.stderr = previous
        sink.gate.set()
        logger.flush()
        self.assertEqual(sink.texts, ['first', 'm7', 'm8', 'm9'])
        self.assertEqual(logger.sink_stats('gate')['queue']['dropped'], 7)

    def test_reject_raises_after_the_other_sinks_have_the_record(self):
        logger, gated, other = make_logger(), GateSink(), GateSink(isOpen=True)
        logger.add_sink('gate', gated, threaded=True, threadQueueSize=1, threadQueuePolicy='reject')
        logger.add_sink('other', other)
        logger.info('first')
        self.assertTrue(gated.entered.wait(WAIT_SECONDS))
        logger.info('queued')
        with self.assertRaises(QueueFull):
            logger.info('refused')
        self.assertEqual(other.texts, ['first', 'queued', 'refused'])
        self.assertEqual(logger.sink_stats('gate')['queue']['rejected'], 1)
        gated.gate.set()
        logger.flush()

    def test_block_with_timeout_drops_and_counts(self):
        logger, sink = make_logger(), GateSink()
        logger.add_sink('gate', sink, threaded=True, threadQueueSize=1, threadQueuePolicy='block',
                        threadBlockTimeout=0.05)
        logger.info('first')
        self.assertTrue(sink.entered.wait(WAIT_SECONDS))
        logger.info('queued')
        buffer, previous = silence_stderr()
        try:
            logger.info('late')
        finally:
            sys.stderr = previous
        self.assertEqual(logger.sink_stats('gate')['queue']['dropped'], 1)
        sink.gate.set()
        logger.flush()
        self.assertEqual(sink.texts, ['first', 'queued'])

    def test_arguments_are_validated(self):
        logger = make_logger()
        with self.assertRaises(ValueError):
            logger.add_sink('a', GateSink(), threaded=True, threadQueuePolicy='drop')
        with self.assertRaises(ValueError):
            logger.add_sink('b', GateSink(), threaded=True, threadBlockTimeout=-1)
        with self.assertRaises(TypeError):
            logger.add_sink('c', GateSink(), threaded=True, threadBlockTimeout='soon')
        self.assertNotIn('a', logger.sinks)


class TestEnqueueMode(unittest.TestCase):

    def test_reject_counts_and_stays_usable(self):
        logger, sink = make_logger(enqueue=True, maxQueueSize=2, queueFullPolicy='reject'), GateSink()
        logger.add_sink('gate', sink)
        refused = 0
        for _ in range(10):
            try:
                logger.info('x')
            except QueueFull:
                refused += 1
        self.assertGreater(refused, 0)
        self.assertEqual(logger.queueStats['rejected'], refused)
        sink.gate.set()
        logger.flush()
        self.assertEqual(logger.queueStats['depth'], 0)

    def test_drop_oldest_accounts_for_every_record(self):
        logger, sink = make_logger(enqueue=True, maxQueueSize=3, queueFullPolicy='drop_oldest'), GateSink()
        logger.add_sink('gate', sink)
        buffer, previous = silence_stderr()
        try:
            for index in range(20):
                logger.info(f'm{index}')
        finally:
            sys.stderr = previous
        sink.gate.set()
        logger.flush()
        stats = logger.queueStats
        self.assertEqual(stats['queued'], 20)
        self.assertEqual(logger.droppedMessages, stats['dropped'])
        self.assertEqual(len(sink.texts) + stats['dropped'], 20)
        self.assertEqual(sink.texts[-1], 'm19')

    def test_queueStats_is_none_without_enqueue_mode(self):
        self.assertIsNone(make_logger().queueStats)

    def test_policy_changes_at_runtime(self):
        logger, sink = make_logger(enqueue=True, maxQueueSize=1, queueFullPolicy='reject'), GateSink()
        logger.add_sink('gate', sink)
        logger.info('a')
        self.assertTrue(sink.entered.wait(WAIT_SECONDS))   # the worker holds 'a', the queue is empty
        logger.info('b')
        with self.assertRaises(QueueFull):
            logger.info('c')
        logger.set_queue_full_policy('drop_newest')
        buffer, previous = silence_stderr()
        try:
            logger.info('d')
        finally:
            sys.stderr = previous
        self.assertEqual(logger.queueStats['dropped'], 1)
        sink.gate.set()
        logger.flush()


class TestSinkStats(unittest.TestCase):

    def test_stats_of_every_sink(self):
        logger, sink = make_logger(), GateSink(isOpen=True)
        logger.add_sink('plain', sink)
        logger.add_sink('threaded', GateSink(isOpen=True), threaded=True)
        logger.info('x')
        logger.flush()
        everything = logger.sink_stats()
        self.assertIn('plain', everything)
        self.assertIn('threaded', everything)
        self.assertIsNone(everything['plain']['queue'])
        self.assertEqual(everything['threaded']['queue']['queued'], 1)
        self.assertEqual(everything['plain']['delivery']['processed'], 1)
        self.assertGreaterEqual(everything['plain']['delivery']['latency_max'], 0.0)
        self.assertIsNotNone(everything['plain']['delivery']['latency_mean'])

    def test_filtered_records_are_counted(self):
        logger, sink = make_logger(), GateSink(isOpen=True)
        logger.add_sink('s', sink)
        logger.set_sink_filter('s', lambda record: record.message != 'skip')
        logger.info('skip')
        logger.info('keep')
        self.assertEqual(logger.sink_stats('s')['filtered'], 1)
        self.assertEqual(sink.texts, ['keep'])

    def test_unknown_sink_raises(self):
        with self.assertRaises(ValueError):
            make_logger().sink_stats('ghost')

    def test_latency_is_none_before_any_record(self):
        logger = make_logger()
        logger.add_sink('s', GateSink(isOpen=True))
        self.assertIsNone(logger.sink_stats('s')['delivery']['latency_mean'])


class TestConcurrency(unittest.TestCase):

    THREADS = 8
    PER_THREAD = 1000

    def _run_threads(self, target):
        threads = [threading.Thread(target=target, args=(index,)) for index in range(self.THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT_SECONDS * 4)
            self.assertFalse(thread.is_alive(), 'a logging thread hung')

    def test_threaded_sink_with_block_loses_nothing(self):
        logger, sink = make_logger(), GateSink(isOpen=True)
        logger.add_sink('s', sink, threaded=True, threadQueueSize=64, threadQueuePolicy='block')
        self._run_threads(lambda index: [logger.info(f't{index}-{n}') for n in range(self.PER_THREAD)])
        logger.flush()
        self.assertEqual(len(sink.texts), self.THREADS * self.PER_THREAD)
        # Order inside one thread is the order it logged in
        for index in range(self.THREADS):
            own = [int(text.split('-')[1]) for text in sink.texts if text.startswith(f't{index}-')]
            self.assertEqual(own, sorted(own))

    def test_enqueue_mode_with_block_loses_nothing(self):
        logger, sink = make_logger(enqueue=True, maxQueueSize=64, queueFullPolicy='block'), GateSink(isOpen=True)
        logger.add_sink('s', sink)
        self._run_threads(lambda index: [logger.info('x') for _ in range(self.PER_THREAD)])
        logger.flush()
        self.assertEqual(len(sink.texts), self.THREADS * self.PER_THREAD)
        self.assertEqual(logger.droppedMessages, 0)

    def test_dropping_sink_accounts_for_every_record(self):
        logger, sink = make_logger(), GateSink(isOpen=True)
        logger.add_sink('s', sink, threaded=True, threadQueueSize=8, threadQueuePolicy='drop_newest')
        buffer, previous = silence_stderr()
        try:
            self._run_threads(lambda index: [logger.info('x') for _ in range(self.PER_THREAD)])
        finally:
            sys.stderr = previous
        logger.flush()
        stats = logger.sink_stats('s')
        total = self.THREADS * self.PER_THREAD
        self.assertEqual(stats['queue']['queued'] + stats['queue']['dropped'], total)
        self.assertEqual(len(sink.texts), stats['queue']['queued'])

    def test_sinks_added_and_removed_while_logging(self):
        logger, stop, errors = make_logger(), threading.Event(), []

        def log_forever(index):
            try:
                while not stop.is_set():
                    logger.info('x')
            except Exception as error:   # noqa: BLE001 - any failure is the thing under test
                errors.append(error)

        threads = [threading.Thread(target=log_forever, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for round in range(30):
            logger.add_sink('s', GateSink(isOpen=True), threaded=bool(round % 2))
            logger.remove_sink('s')
        stop.set()
        for thread in threads:
            thread.join(WAIT_SECONDS)
        self.assertEqual(errors, [])


class TestShutdown(unittest.TestCase):

    @staticmethod
    def _sink_threads():
        return [thread for thread in threading.enumerate() if thread.is_alive() and thread is not threading.main_thread()]

    def test_remove_sink_drains_and_stops_the_thread(self):
        before = len(self._sink_threads())
        logger, sink = make_logger(), GateSink(isOpen=True)
        logger.add_sink('s', sink, threaded=True)
        for index in range(200):
            logger.info(f'm{index}')
        logger.remove_sink('s')
        self.assertEqual(len(sink.texts), 200)
        self.assertEqual(len(self._sink_threads()), before)

    def test_clear_sinks_stops_every_thread(self):
        before = len(self._sink_threads())
        logger = make_logger()
        for index in range(5):
            logger.add_sink(f's{index}', GateSink(isOpen=True), threaded=True)
        logger.clear_sinks()
        self.assertEqual(len(self._sink_threads()), before)

    def test_remove_sink_gives_up_on_a_stuck_sink_after_the_timeout(self):
        logger, sink = make_logger(), GateSink()
        logger.add_sink('s', sink, threaded=True)
        logger.info('stuck')
        self.assertTrue(sink.entered.wait(WAIT_SECONDS))
        started = time.monotonic()
        logger.remove_sink('s', timeout=0.2)
        self.assertLess(time.monotonic() - started, WAIT_SECONDS)
        sink.gate.set()

    def test_flush_returns_within_its_timeout_when_a_sink_is_stuck(self):
        logger, sink = make_logger(enqueue=True), GateSink()
        logger.add_sink('s', sink)
        logger.info('stuck')
        self.assertTrue(sink.entered.wait(WAIT_SECONDS))
        started = time.monotonic()
        logger.flush(timeout=0.2)
        self.assertLess(time.monotonic() - started, WAIT_SECONDS)
        sink.gate.set()
        logger.flush()

    def test_flush_delivers_everything_queued(self):
        logger, sink = make_logger(enqueue=True), GateSink(isOpen=True)
        logger.add_sink('s', sink)
        for index in range(300):
            logger.info(f'm{index}')
        logger.flush()
        self.assertEqual(len(sink.texts), 300)


class TestSinkFailure(unittest.TestCase):

    def test_a_failing_sink_never_reaches_the_caller_or_the_other_sinks(self):
        logger, good = make_logger(), GateSink(isOpen=True)
        logger.add_sink('bad', RaisingSink())
        logger.add_sink('good', good)
        buffer, previous = silence_stderr()
        try:
            for index in range(5):
                logger.info(f'm{index}')
        finally:
            sys.stderr = previous
        self.assertEqual(good.texts, [f'm{index}' for index in range(5)])
        stats = logger.sink_stats('bad')['delivery']
        self.assertEqual((stats['failed'], stats['processed']), (5, 0))
        self.assertIsInstance(stats['last_error'], OSError)

    def test_one_warning_for_a_run_of_failures(self):
        logger = make_logger()
        logger.add_sink('bad', RaisingSink())
        buffer, previous = silence_stderr()
        try:
            for _ in range(10):
                logger.info('x')
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('WARNING'), 1)
        self.assertNotIn('Traceback', buffer.getvalue())

    def test_a_failing_threaded_sink_keeps_its_worker_alive(self):
        logger, good = make_logger(), GateSink(isOpen=True)
        logger.add_sink('bad', RaisingSink(), threaded=True)
        logger.add_sink('good', good, threaded=True)
        buffer, previous = silence_stderr()
        try:
            for index in range(50):
                logger.info(f'm{index}')
            logger.flush()
        finally:
            sys.stderr = previous
        self.assertEqual(len(good.texts), 50)
        self.assertEqual(logger.sink_stats('bad')['delivery']['failed'], 50)

    def test_a_failing_sink_in_enqueue_mode_does_not_stop_the_worker(self):
        logger, good = make_logger(enqueue=True), GateSink(isOpen=True)
        logger.add_sink('bad', RaisingSink())
        logger.add_sink('good', good)
        buffer, previous = silence_stderr()
        try:
            for index in range(20):
                logger.info(f'm{index}')
            logger.flush()
        finally:
            sys.stderr = previous
        self.assertEqual(len(good.texts), 20)

    def test_a_failing_formatter_counts_as_a_failure(self):
        class BadFormat(Sink):
            def __init__(self):
                super().__init__(formatter=self.explode)

            @staticmethod
            def explode(record):
                raise ValueError('cannot render')

            def write(self, text, record):
                raise AssertionError('must not be reached')

        logger = make_logger()
        logger.add_sink('s', BadFormat())
        buffer, previous = silence_stderr()
        try:
            logger.info('x')
        finally:
            sys.stderr = previous
        self.assertEqual(logger.sink_stats('s')['delivery']['failed'], 1)

    def test_a_sink_recovers_after_failures(self):
        class Flaky(Sink):
            def __init__(self):
                super().__init__(formatter='{message}')
                self.isBroken = True
                self.texts = []

            def write(self, text, record):
                if self.isBroken:
                    raise OSError('down')
                self.texts.append(text.strip())

        logger, flaky = make_logger(), Flaky()
        logger.add_sink('s', flaky)
        buffer, previous = silence_stderr()
        try:
            logger.info('lost')
            flaky.isBroken = False
            logger.info('kept')
            flaky.isBroken = True
            logger.info('lost again')
        finally:
            sys.stderr = previous
        self.assertEqual(flaky.texts, ['kept'])
        self.assertEqual(buffer.getvalue().count('WARNING'), 2)
        self.assertEqual(logger.sink_stats('s')['delivery']['processed'], 1)


if __name__ == '__main__':
    unittest.main()
