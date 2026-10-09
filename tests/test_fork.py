"""A process that was forked from one with threads, locks and connections: nothing hangs, no record is lost.

Run from the repo root::

    python3 -m unittest tests.test_fork -v

A fork copies the locks in the state they had, and a lock that another thread held then is held for ever in the copy. It does
not copy the threads, so a queue that a worker thread was to empty is never emptied. Every case here starts a real child with
``os.fork`` and gives it an alarm, so a hang shows as a failure and not as a test run that never ends.
"""
import io
import json
import multiprocessing
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from simple_log import Logger  # noqa: E402
from sinks import Sink, StreamSink, FileSink  # noqa: E402
from contrib import siem_sink, siem_transport  # noqa: E402

# Seconds a child may take before it is taken to be stuck
CHILD_SECONDS = 8
WAIT_SECONDS = 15.0


class Keep(Sink):
    """Keeps what it is given, with the process that gave it. A closed gate holds the writes of the process that made it."""

    owner = os.getpid()

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)
        self.got = []
        self.gate = None

    def write(self, text, record):
        if self.gate is not None and os.getpid() == self.owner:
            self.gate.wait(WAIT_SECONDS)
        self.got.append((os.getpid(), record.message))

    def in_this_process(self):
        return [message for pid, message in self.got if pid == os.getpid()]


def in_child(work):
    """
    Runs *work* in a forked child with an alarm, and returns what it returned (JSON-able), or ``'HUNG'``.

    :Parameters:
        #. work (callable): Called in the child, with no argument.
    """
    readEnd, writeEnd = os.pipe()
    pid = os.fork()
    if pid == 0:
        signal.alarm(CHILD_SECONDS)
        try:
            outcome = json.dumps({'value': work()})
        except BaseException as error:
            outcome = json.dumps({'error': repr(error)})
        os.write(writeEnd, outcome.encode())
        os._exit(0)
    os.close(writeEnd)
    _, status = os.waitpid(pid, 0)
    data = os.read(readEnd, 100000)
    os.close(readEnd)
    if os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGALRM:
        return 'HUNG'
    decoded = json.loads(data)
    if 'error' in decoded:
        raise AssertionError(f"the child failed: {decoded['error']}")
    return decoded['value']


@unittest.skipUnless(hasattr(os, 'fork'), 'needs fork')
class TestDelivery(unittest.TestCase):

    def _logger(self, **options):
        logger = Logger('fork', logToFile=False, logToStdout=False, **options)
        self.addCleanup(lambda: logger.clear_sinks(timeout=0.5))
        return logger

    def test_a_threaded_sink_delivers_in_a_child_in_the_calling_thread(self):
        logger, sink = self._logger(), Keep()
        logger.add_sink('k', sink, threaded=True)
        logger.info('before')
        logger.flush()
        child = in_child(lambda: (logger.info('from the child'), time.sleep(0.05), sink.in_this_process())[2])
        self.assertEqual(child, ['from the child'])
        logger.info('after')
        logger.flush()
        self.assertEqual([m for p, m in sink.got if p == os.getpid()], ['before', 'after'])

    def test_the_enqueue_mode_delivers_in_a_child_in_the_calling_thread(self):
        logger, sink = self._logger(enqueue=True), Keep()
        logger.add_sink('k', sink)
        logger.info('before')
        logger.flush()
        child = in_child(lambda: (logger.info('from the child'), logger.force_log('info', 'forced', sinks=[]),
                                  time.sleep(0.05), sink.in_this_process())[3])
        self.assertEqual(child, ['from the child'])
        logger.info('after')
        logger.flush()
        self.assertEqual([m for p, m in sink.got if p == os.getpid()], ['before', 'after'])

    def test_flushing_and_closing_in_a_child_do_not_wait_for_a_worker_that_is_not_there(self):
        logger, sink = self._logger(enqueue=True), Keep()
        sink.gate = threading.Event()
        self.addCleanup(sink.gate.set)
        logger.add_sink('k', sink, threaded=True)
        # The parent has records in both queues at the moment of the fork, and nobody to take them out in the child
        for index in range(3):
            logger.info(f'held {index}')
        time.sleep(0.2)

        def work():
            started = time.monotonic()
            logger.flush(timeout=5)
            logger.remove_sink('k', timeout=5)
            logger._flush_atexit_logfile()
            return time.monotonic() - started

        elapsed = in_child(work)
        self.assertNotEqual(elapsed, 'HUNG')
        self.assertLess(elapsed, 2.0)

    def test_flushing_the_queue_of_the_enqueue_mode_in_a_child_does_not_wait_for_its_worker(self):
        logger, sink = self._logger(enqueue=True), Keep()
        sink.gate = threading.Event()
        self.addCleanup(sink.gate.set)
        logger.add_sink('k', sink)                  # not threaded: the worker of the logger is the one held, with records behind it
        for index in range(3):
            logger.info(f'held {index}')
        time.sleep(0.2)

        def work():
            started = time.monotonic()
            logger.flush(timeout=5)
            return time.monotonic() - started

        elapsed = in_child(work)
        self.assertNotEqual(elapsed, 'HUNG')
        self.assertLess(elapsed, 2.0)

    def test_the_parent_goes_on_unharmed(self):
        logger, sink = self._logger(), Keep()
        logger.add_sink('k', sink, threaded=True)
        for index in range(3):
            in_child(lambda: logger.info('child'))
            logger.info(f'parent {index}')
        logger.flush()
        self.assertEqual([m for p, m in sink.got if p == os.getpid()], [f'parent {index}' for index in range(3)])

    def test_a_process_made_by_multiprocessing_with_fork_delivers_through_a_file_sink(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = self._logger()
            logger.add_sink('f', FileSink(os.path.join(folder, 'out'), formatter=lambda record: record.message), threaded=True)

            def work():
                logger.info('from a multiprocessing child')

            process = multiprocessing.get_context('fork').Process(target=work)
            process.start()
            process.join(WAIT_SECONDS)
            self.assertEqual(process.exitcode, 0)
            logger.clear_sinks(timeout=1)
            with open(os.path.join(folder, 'out_0.log'), encoding='utf-8') as stream:
                self.assertIn('from a multiprocessing child', stream.read())


@unittest.skipUnless(hasattr(os, 'fork'), 'needs fork')
class TestLocksHeldAtTheMomentOfTheFork(unittest.TestCase):
    """A thread of the parent holds a lock of the package while the fork happens: the child must not hang on it."""

    def _hold(self, lock):
        """Starts a thread that holds *lock* until the test ends, so that it is held by a thread the child will not have."""
        acquired, release = threading.Event(), threading.Event()

        def holder():
            with lock:
                acquired.set()
                release.wait(WAIT_SECONDS)

        thread = threading.Thread(target=holder, daemon=True)
        thread.start()
        self.assertTrue(acquired.wait(WAIT_SECONDS))
        self.addCleanup(lambda: (release.set(), thread.join(2)))

    def test_the_stats_lock_of_a_sink(self):
        sink = Keep()
        self._hold(sink._Sink__statsLock)
        self.assertEqual(in_child(lambda: (sink.emit(__import__('record').LogRecord.create(
            __import__('datetime').datetime.now(__import__('datetime').timezone.utc), 'INFO', 'info', 10, 'l', 'm', 1, 1, 't')),
            sink.stats['processed'])[1]), 1)

    def test_the_write_lock_of_a_stream_sink(self):
        buffer = io.StringIO()
        sink = StreamSink(buffer, formatter=lambda record: record.message)
        self._hold(sink._StreamSink__writeLock)
        logger = Logger('fork', logToFile=False, logToStdout=False)
        logger.add_sink('s', sink)
        self.assertEqual(in_child(lambda: (logger.info('x'), buffer.getvalue())[1]), 'x\n')

    def test_the_lock_of_a_file_sink(self):
        with tempfile.TemporaryDirectory() as folder:
            sink = FileSink(os.path.join(folder, 'out'), formatter=lambda record: record.message)
            self.addCleanup(sink.close)                      # cleanups run last first, so the lock is let go before this
            self._hold(sink._FileSink__lock)
            logger = Logger('fork', logToFile=False, logToStdout=False)
            logger.add_sink('f', sink)
            self.assertEqual(in_child(lambda: (logger.info('x'), 'done')[1]), 'done')

    def test_the_processor_and_filter_locks_of_a_logger(self):
        def failing(record):
            raise ValueError('a processor or a filter that fails takes the lock to count itself')

        logger = Logger('fork', logToFile=False, logToStdout=False)
        logger.add_sink('k', Keep())
        logger.add_processor(failing)
        logger.add_filter(failing)
        self._hold(logger._Logger__processorLock)
        self._hold(logger._Logger__filterLock)

        def work():
            sys.stderr = io.StringIO()
            logger.info('x')
            return 'done'

        self.assertEqual(in_child(work), 'done')

    def test_the_lock_of_a_queue(self):
        from queues import BoundedQueue
        boundedQueue = BoundedQueue(5)
        self._hold(boundedQueue._BoundedQueue__condition)
        self.assertEqual(in_child(lambda: (boundedQueue.put('a'), boundedQueue.stats()['depth'])[1]), 1)

    def test_the_lock_of_a_spool_and_of_the_delivery_of_a_sink(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = Logger('fork', logToFile=False, logToStdout=False)
            self.addCleanup(lambda: logger.clear_sinks(timeout=0.5))
            sink = Keep()
            sink.SPOOL_DESTINATION = ('host',)
            sink.host = 'h'
            logger.add_sink('c', sink, threaded=True, spool={'path': folder, 'id': 'f', 'maxBytes': 10 ** 7, 'totalMaxBytes': 10 ** 8})
            durable = logger._Logger__sinks['c'].durable
            self._hold(durable._DurableDelivery__lock)
            self._hold(durable._DurableDelivery__spool._Spool__condition)
            self._hold(durable._DurableDelivery__hints._BoundedQueue__condition)
            stats = in_child(lambda: (logger.info('x'), logger.sink_stats('c')['spool']['unspooled'])[1])
            self.assertEqual(stats, 1)


@unittest.skipUnless(hasattr(os, 'fork'), 'needs fork')
class TestSiemAfterFork(unittest.TestCase):

    def test_a_child_does_not_share_the_connection_of_its_parent(self):
        with mock_ssl_free():
            transport = siem_transport.TCPSyslogTransport('localhost', 9)
        transport._sock = socket.socket()                 # stands for the open connection of the parent
        self.addCleanup(transport._sock.close)
        self.assertEqual(in_child(lambda: transport._sock is None), True)
        self.assertIsNotNone(transport._sock)             # the parent keeps its own

    def test_the_locks_of_the_forwarder_and_its_breaker(self):
        transport = siem_transport.TCPSyslogTransport('localhost', 9)
        sink = siem_sink.SiemForwardSink(transport)
        logger = Logger('fork', logToFile=False, logToStdout=False)
        logger.add_sink('siem', sink)
        self.addCleanup(lambda: logger.clear_sinks(timeout=0.5))      # runs after the locks are let go
        for lock in (sink._statsLock, sink._breaker._lock, transport._lock):
            acquired, release = threading.Event(), threading.Event()

            def holder(lock=lock, acquired=acquired, release=release):
                with lock:
                    acquired.set()
                    release.wait(WAIT_SECONDS)

            thread = threading.Thread(target=holder, daemon=True)
            thread.start()
            acquired.wait(WAIT_SECONDS)
            self.addCleanup(lambda release=release, thread=thread: (release.set(), thread.join(2)))

        def work():
            logger.error('x')
            return sink.stats['sent'] + sink.stats['dropped'] + sink.stats['errors'] >= 1

        self.assertEqual(in_child(work), True)


class mock_ssl_free:
    """Makes a TCP transport without the cost of an SSL context, which the transport only builds when TLS is on."""

    def __enter__(self):
        return self

    def __exit__(self, *exceptions):
        return False


if __name__ == '__main__':
    unittest.main()
