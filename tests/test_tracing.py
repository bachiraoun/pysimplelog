"""Tests of the reading of the active trace: the reader, the sink flag, where the logger reads, and what the sinks get.

Most tests use a small fake of the OpenTelemetry API, so nothing needs to be installed. The tests of the real API are
skipped when the package ``opentelemetry-api`` is missing.

Run from the repo root::

    python3 -m unittest tests.test_tracing -v
"""
import contextlib
import importlib.util
import io
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import tracing  # noqa: E402
from simple_log import Logger  # noqa: E402
from record import TraceInfo  # noqa: E402
from sinks import Sink, StreamSink, ConsoleSink  # noqa: E402
from standard_logging import redirect_standard_logging, restore_standard_logging  # noqa: E402

TRACE_ID = 0x0af7651916cd43dd8448eb211c80319c
SPAN_ID = 0xb7ad6b7169203331
TRACE_TEXT = '0af7651916cd43dd8448eb211c80319c'
SPAN_TEXT = 'b7ad6b7169203331'
WAIT_SECONDS = 15.0
HAS_REAL_API = importlib.util.find_spec('opentelemetry') is not None and importlib.util.find_spec('opentelemetry.trace') is not None


class FakeSpanContext:
    def __init__(self, traceId=TRACE_ID, spanId=SPAN_ID, traceFlags=1, isValid=True):
        self.trace_id, self.span_id, self.trace_flags, self.is_valid = traceId, spanId, traceFlags, isValid


class FakeApi:
    """A stand-in for ``opentelemetry.trace``: each thread has its own active span, and every read is counted."""

    def __init__(self):
        self.local = threading.local()
        self.reads = []
        self.lock = threading.Lock()
        self.isBroken = False

    def set_span(self, spanContext):
        self.local.context = spanContext

    def get_current_span(self):
        with self.lock:
            self.reads.append(threading.get_ident())
        if self.isBroken:
            raise RuntimeError('the API is broken')
        spanContext = getattr(self.local, 'context', FakeSpanContext(0, 0, 0, False))
        return types.SimpleNamespace(get_span_context=lambda: spanContext)


class TracingCase(unittest.TestCase):
    """Installs the fake API for one test and puts everything back."""

    def setUp(self):
        self.api = FakeApi()
        trace = types.ModuleType('opentelemetry.trace')
        trace.get_current_span = self.api.get_current_span
        package = types.ModuleType('opentelemetry')
        package.trace = trace
        patcher = mock.patch.dict(sys.modules, {'opentelemetry': package, 'opentelemetry.trace': trace})
        patcher.start()
        self.addCleanup(patcher.stop)
        self._reset_reader()
        self.addCleanup(self._reset_reader)
        self.loggers = []
        self.addCleanup(self._close_loggers)
        self.api.set_span(FakeSpanContext())

    @staticmethod
    def _reset_reader():
        tracing._getCurrentSpan = None

    def _close_loggers(self):
        for logger in self.loggers:
            with contextlib.suppress(Exception):
                logger.clear_sinks(timeout=1.0)

    def make_logger(self, **arguments):
        logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
        self.loggers.append(logger)
        return logger


class Capture(Sink):
    """A sink that keeps the records it gets. It asks for the trace when told to."""

    def __init__(self, captureTrace=False):
        super().__init__(formatter=lambda record: record.message, captureTrace=captureTrace)
        self.records = []
        self.lock = threading.Lock()

    def write(self, text, record):
        with self.lock:
            self.records.append(record)

    def traces(self):
        with self.lock:
            return [record.trace for record in self.records]


class TestReader(TracingCase):

    def test_a_valid_span_gives_its_identifiers_in_hexadecimal(self):
        self.assertTrue(tracing.trace_api_available())
        self.assertEqual(tracing.read_current_trace(), TraceInfo(TRACE_TEXT, SPAN_TEXT, 1))

    def test_small_numbers_are_padded_to_the_full_length(self):
        self.api.set_span(FakeSpanContext(traceId=1, spanId=2, traceFlags=0))
        tracing.trace_api_available()
        trace = tracing.read_current_trace()
        self.assertEqual(trace, TraceInfo('0' * 31 + '1', '0' * 15 + '2', 0))
        self.assertEqual((len(trace.traceId), len(trace.spanId)), (32, 16))

    def test_the_largest_numbers(self):
        self.api.set_span(FakeSpanContext(traceId=2 ** 128 - 1, spanId=2 ** 64 - 1, traceFlags=255))
        tracing.trace_api_available()
        self.assertEqual(tracing.read_current_trace(), TraceInfo('f' * 32, 'f' * 16, 255))

    def test_flags_that_are_an_int_subclass_become_an_int(self):
        class Flags(int):
            pass
        self.api.set_span(FakeSpanContext(traceFlags=Flags(1)))
        tracing.trace_api_available()
        self.assertIs(type(tracing.read_current_trace().flags), int)

    def test_a_span_that_is_not_valid_gives_none(self):
        self.api.set_span(FakeSpanContext(isValid=False))
        tracing.trace_api_available()
        self.assertIsNone(tracing.read_current_trace())

    def test_no_active_span_gives_none(self):
        self.api.local = threading.local()
        tracing.trace_api_available()
        self.assertIsNone(tracing.read_current_trace())

    def test_an_api_that_raises_gives_none_and_does_not_raise(self):
        tracing.trace_api_available()
        self.api.isBroken = True
        self.assertIsNone(tracing.read_current_trace())

    def test_nothing_is_read_before_the_api_was_looked_for(self):
        self.assertIsNone(tracing.read_current_trace())
        self.assertEqual(self.api.reads, [])

    def test_a_missing_api_is_reported_and_looked_for_again_next_time(self):
        with mock.patch.dict(sys.modules, {'opentelemetry': None, 'opentelemetry.trace': None}):
            self.assertFalse(tracing.trace_api_available())
            self.assertIsNone(tracing.read_current_trace())
        self.assertTrue(tracing.trace_api_available())

    def test_the_reader_is_the_same_object_from_one_look_to_the_next(self):
        tracing.trace_api_available()
        first = tracing._getCurrentSpan
        tracing.trace_api_available()
        self.assertIs(tracing._getCurrentSpan, first)


class TestSinkFlag(unittest.TestCase):

    def test_the_default_is_off(self):
        self.assertFalse(Sink().captureTrace)
        self.assertFalse(StreamSink(io.StringIO()).captureTrace)
        self.assertFalse(ConsoleSink().captureTrace)

    def test_a_sink_can_ask(self):
        self.assertTrue(Capture(captureTrace=True).captureTrace)

    def test_only_a_boolean_is_accepted(self):
        for bad in (1, 0, 'yes', None):
            with self.assertRaises(TypeError):
                Sink(captureTrace=bad)

    def test_it_cannot_be_changed_afterwards(self):
        sink = Capture()
        with self.assertRaises(AttributeError):
            sink.captureTrace = True

    def test_the_built_in_sinks_of_a_logger_never_ask(self):
        logger = Logger('app', logToFile=False, logToStdout=True, stdout=io.StringIO())
        self.assertGreater(len(logger.sinks), 0)
        self.assertTrue(all(not handler.captureTrace for handler in logger.sinks.values()))


class TestWhereTheLoggerReads(TracingCase):

    def test_nothing_is_read_when_no_sink_asks(self):
        logger = self.make_logger()
        logger.add_sink('quiet', Capture())
        tracing.trace_api_available()
        for _ in range(20):
            logger.info('x')
        self.assertEqual(self.api.reads, [])

    def test_a_sink_that_asks_gets_the_trace(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        logger.info('x')
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])
        self.assertEqual(logger.lastRecord.trace, TraceInfo(TRACE_TEXT, SPAN_TEXT, 1))

    def test_every_sink_gets_the_same_record_and_the_quiet_one_is_not_changed(self):
        logger = self.make_logger()
        quiet, stream = Capture(), io.StringIO()
        traced = Capture(captureTrace=True)
        logger.add_sink('quiet', quiet)
        logger.add_sink('traced', traced)
        logger.add_sink('json', StreamSink(stream))
        logger.info('x', k=1)
        self.assertIs(quiet.records[0], traced.records[0])
        self.assertNotIn(TRACE_TEXT, stream.getvalue())
        self.assertNotIn(SPAN_TEXT, stream.getvalue())

    def test_every_call_reads_the_span_of_its_own_moment(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        logger.info('one')
        self.api.set_span(FakeSpanContext(traceId=5, spanId=6, traceFlags=0))
        logger.info('two')
        self.api.set_span(FakeSpanContext(isValid=False))
        logger.info('three')
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1), TraceInfo('0' * 31 + '5', '0' * 15 + '6', 0), None])

    def test_removing_the_sink_stops_the_reads_and_adding_it_again_starts_them(self):
        # A quiet sink stays active, otherwise no record is built and the flag could not be seen
        logger = self.make_logger()
        logger.add_sink('quiet', Capture())
        logger.add_sink('traced', Capture(captureTrace=True))
        logger.info('a')
        self.assertEqual(len(self.api.reads), 1)
        logger.remove_sink('traced')
        logger.info('b')
        self.assertEqual(len(self.api.reads), 1)
        logger.add_sink('traced', Capture(captureTrace=True))
        logger.info('c')
        self.assertEqual(len(self.api.reads), 2)

    def test_clearing_the_sinks_stops_the_reads(self):
        # The console sink is not removed by clear_sinks, so records are still built
        logger = Logger('app', logToFile=False, logToStdout=True, stdout=io.StringIO())
        self.loggers.append(logger)
        logger.add_sink('traced', Capture(captureTrace=True))
        logger.info('a')
        self.assertEqual(len(self.api.reads), 1)
        logger.clear_sinks()
        logger.info('b')
        self.assertEqual(len(self.api.reads), 1)

    def test_the_reads_go_on_while_one_of_two_asking_sinks_is_left(self):
        logger = self.make_logger()
        first, second = Capture(captureTrace=True), Capture(captureTrace=True)
        logger.add_sink('a', first)
        logger.add_sink('b', second)
        logger.remove_sink('a')
        logger.info('x')
        self.assertEqual(second.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])

    def test_a_switched_off_sink_alone_makes_the_logger_read_nothing(self):
        # No sink is active, so the record is not even built
        logger = self.make_logger()
        logger.add_sink('traced', Capture(captureTrace=True), enabled=False)
        logger.info('x')
        self.assertEqual(self.api.reads, [])

    def test_a_switched_off_sink_next_to_an_active_one_still_makes_the_logger_read(self):
        # Known and accepted: tracking the switch would add code, and the read costs a few microseconds
        logger = self.make_logger()
        logger.add_sink('traced', Capture(captureTrace=True), enabled=False)
        logger.add_sink('quiet', Capture())
        logger.info('x')
        self.assertEqual(len(self.api.reads), 1)

    def test_one_logger_asking_does_not_make_another_read(self):
        asking, other = self.make_logger(), self.make_logger()
        asking.add_sink('traced', Capture(captureTrace=True))
        other.add_sink('quiet', Capture())
        reads = len(self.api.reads)
        other.info('x')
        self.assertEqual(len(self.api.reads), reads)

    def test_a_logger_with_a_failing_api_still_logs(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        self.api.isBroken = True
        logger.info('still here')
        self.assertEqual([record.message for record in sink.records], ['still here'])
        self.assertEqual(sink.traces(), [None])

    def test_a_processor_can_replace_the_trace(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        other = TraceInfo('1' * 32, '2' * 16, 0)
        logger.add_processor(lambda record: record._replace(trace=other))
        logger.info('x')
        self.assertEqual(sink.traces(), [other])

    def test_a_filter_sees_the_trace(self):
        logger = self.make_logger()
        logger.add_sink('traced', Capture(captureTrace=True))
        seen = []
        logger.add_filter(lambda record: seen.append(record.trace) or True)
        logger.info('x')
        self.assertEqual(seen, [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])


class TestEveryWayToLog(TracingCase):

    def _setup(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        return logger, sink

    def test_the_bound_logger(self):
        logger, sink = self._setup()
        logger.bind(a=1).warn('x')
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])

    def test_every_log_type(self):
        logger, sink = self._setup()
        for logType in ('debug', 'info', 'warn', 'error', 'critical'):
            logger.log(logType, logType)
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)] * 5)

    def test_force_log(self):
        logger, _ = self._setup()
        seen = []
        logger.add_processor(lambda record: seen.append(record.trace) or record)
        logger.force_log('info', 'forced', sinks=[])
        self.assertEqual(seen, [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])

    def test_an_exception_record(self):
        logger, sink = self._setup()
        try:
            raise ValueError('boom')
        except ValueError:
            logger.error('failed', exc_info=True)
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])
        self.assertEqual(sink.records[0].exception.typeName, 'ValueError')

    def test_the_standard_logging_bridge(self):
        logger, sink = self._setup()
        name = f'tracing.{uuid.uuid4().hex}'
        handler = redirect_standard_logging(logger, name=name, loggerLevel=logging.INFO)
        self.addCleanup(restore_standard_logging, handler)
        standard = logging.getLogger(name)
        standard.propagate = False
        standard.info('from the library')
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])


class TestTheCallingThread(TracingCase):
    """The span belongs to the thread that logs. A sink that runs later, elsewhere, must still get the right one."""

    THREADS = 8
    PER_THREAD = 40

    def _log_from_threads(self, logger):
        def work(number):
            self.api.set_span(FakeSpanContext(traceId=number + 1, spanId=number + 1, traceFlags=number % 2))
            for index in range(self.PER_THREAD):
                logger.info(f'{number}-{index}')
        threads = [threading.Thread(target=work, args=(number,)) for number in range(self.THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        logger.flush()

    def _check(self, sink):
        self.assertEqual(len(sink.records), self.THREADS * self.PER_THREAD)
        for record in sink.records:
            number = int(record.message.split('-')[0])
            self.assertEqual(record.trace, TraceInfo(f'{number + 1:032x}', f'{number + 1:016x}', number % 2))

    def test_synchronous(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        self._log_from_threads(logger)
        self._check(sink)

    def test_with_the_logger_queue(self):
        logger = self.make_logger(enqueue=True)
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        self._log_from_threads(logger)
        self._check(sink)

    def test_with_a_threaded_sink(self):
        logger = self.make_logger()
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink, threaded=True, threadQueuePolicy='block')
        self._log_from_threads(logger)
        self._check(sink)

    def test_the_span_is_only_ever_read_by_the_threads_that_log(self):
        logger = self.make_logger(enqueue=True)
        logger.add_sink('traced', Capture(captureTrace=True), threaded=True, threadQueuePolicy='block')
        loggingThreads = set()

        def work(number):
            loggingThreads.add(threading.get_ident())
            for index in range(20):
                logger.info(f'{number}-{index}')
        threads = [threading.Thread(target=work, args=(number,)) for number in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        logger.flush()
        self.assertEqual(len(self.api.reads), 80)
        self.assertTrue(set(self.api.reads) <= loggingThreads)


class TestSpool(TracingCase):

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp(prefix='tracingtest-')
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_the_original_trace_is_delivered_after_a_replay(self):
        class Receiver(Sink):
            SPOOL_DESTINATION = ('host',)

            def __init__(inner):
                super().__init__(formatter=lambda record: record.message, captureTrace=True)
                inner.host, inner.up, inner.got = 'r1', False, []

            def write(inner, text, record):
                if not inner.up:
                    return False
                inner.got.append((record.message, record.trace))

        sink = Receiver()
        logger = self.make_logger()
        logger.add_sink('r', sink, threaded=True, spool=dict(path=self.root, id='tracing', maxBytes=10 ** 7, totalMaxBytes=10 ** 8,
                                                              retryBackoffBase=0.01, retryBackoffMax=0.05))
        for number in range(3):
            self.api.set_span(FakeSpanContext(traceId=number + 1, spanId=number + 1, traceFlags=1))
            logger.info(f'm{number}')
        # The span the process has when the receiver comes back is another one, and must not reach the old records
        self.api.set_span(FakeSpanContext(traceId=99, spanId=99, traceFlags=0))
        deadline = time.monotonic() + WAIT_SECONDS
        while logger.sink_stats('r')['spool']['retries'] == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        sink.up = True
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(sink.got, [(f'm{number}', TraceInfo(f'{number + 1:032x}', f'{number + 1:016x}', 1)) for number in range(3)])


class TestMissingApi(unittest.TestCase):

    def setUp(self):
        tracing._getCurrentSpan = None
        self.addCleanup(setattr, tracing, '_getCurrentSpan', None)
        patcher = mock.patch.dict(sys.modules, {'opentelemetry': None, 'opentelemetry.trace': None})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_one_warning_when_the_sink_is_added_and_the_records_go_without_trace(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks)
        sink = Capture(captureTrace=True)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            logger.add_sink('traced', sink)
            for _ in range(5):
                logger.info('x')
        self.assertEqual(error.getvalue().count('WARNING'), 1)
        self.assertIn('traced', error.getvalue())
        self.assertIn('opentelemetry-api', error.getvalue())
        self.assertEqual(sink.traces(), [None] * 5)

    def test_a_sink_that_does_not_ask_never_warns(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            logger.add_sink('quiet', Capture())
            logger.info('x')
        self.assertEqual(error.getvalue(), '')

    def test_nothing_raises(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks)
        with contextlib.redirect_stderr(io.StringIO()):
            logger.add_sink('traced', Capture(captureTrace=True), threaded=True)
            logger.info('x')
            logger.flush()


@unittest.skipUnless(HAS_REAL_API, 'the package opentelemetry-api is not installed')
class TestRealApi(unittest.TestCase):

    def setUp(self):
        tracing._getCurrentSpan = None
        self.addCleanup(setattr, tracing, '_getCurrentSpan', None)

    @staticmethod
    @contextlib.contextmanager
    def active_span(traceId, spanId, flags):
        from opentelemetry import context, trace
        spanContext = trace.SpanContext(trace_id=traceId, span_id=spanId, is_remote=False, trace_flags=trace.TraceFlags(flags))
        token = context.attach(trace.set_span_in_context(trace.NonRecordingSpan(spanContext)))
        try:
            yield
        finally:
            context.detach(token)

    def test_the_identifiers_of_a_real_span(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks)
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        with self.active_span(TRACE_ID, SPAN_ID, 1):
            logger.info('inside')
        logger.info('outside')
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1), None])

    def test_nested_spans_and_flags_zero(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks)
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        with self.active_span(TRACE_ID, SPAN_ID, 1):
            with self.active_span(TRACE_ID, 0x1111111111111111, 0):
                logger.info('inner')
            logger.info('outer')
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, '1111111111111111', 0), TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])

    def test_the_real_api_through_a_queue_and_a_thread(self):
        logger = Logger('app', logToFile=False, logToStdout=False, enqueue=True)
        self.addCleanup(logger.clear_sinks)
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink, threaded=True, threadQueuePolicy='block')
        with self.active_span(TRACE_ID, SPAN_ID, 1):
            logger.info('queued')
        logger.flush()
        self.assertEqual(sink.traces(), [TraceInfo(TRACE_TEXT, SPAN_TEXT, 1)])

    def test_a_valid_record_comes_out(self):
        from record import validate_record
        logger = Logger('app', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks)
        sink = Capture(captureTrace=True)
        logger.add_sink('traced', sink)
        with self.active_span(TRACE_ID, SPAN_ID, 1):
            logger.info('x')
        validate_record(sink.records[0])


if __name__ == '__main__':
    unittest.main()
