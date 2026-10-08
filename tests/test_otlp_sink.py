"""Tests of the OTLP sink: the settings, one group, every kind of answer, the logger with its groups and its spool, and a restart.

The receiver is the fake one of test_otlp_transport. The tests that need the official protobuf parser or the real OpenTelemetry API
are skipped when they are not installed.

Run from the repo root::

    python3 -m unittest tests.test_otlp_sink -v
"""
import contextlib
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import warnings
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from contrib import otlp_sink  # noqa: E402
from contrib.otlp_sink import OtlpLogSink, attach  # noqa: E402
from contrib.otlp_encoder import OtlpLogEncoder, OtlpSeverityMap  # noqa: E402
from contrib.otlp_transport import OtlpResponse  # noqa: E402
from simple_log import Logger  # noqa: E402
from record import LogRecord, TraceInfo, ExceptionInfo, CallerInfo  # noqa: E402
from sinks import DELIVERED, RETRY, REJECTED, SPLIT  # noqa: E402
from spool import Spool  # noqa: E402
from test_otlp_transport import FakeReceiver, Answer  # noqa: E402
from test_tracing import TracingCase, FakeSpanContext  # noqa: E402

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
WAIT_SECONDS = 15.0
TOKEN = 'secret-token-1234'
TRACE = TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1)
FAST = dict(maxRetries=2, retryBackoffBase=0.01, retryBackoffMax=0.02, batchInterval=0.0)


def wait_until(condition, timeout=WAIT_SECONDS, what='the condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def make_record(message='m', **changes):
    values = dict(timestamp=datetime(2026, 10, 6, 18, 31, 52, 123456, tzinfo=timezone.utc), severity='INFO', logType='info', level=10.0,
                  logger='orders', message=message, processId=1, threadId=2, threadName='main')
    values.update(changes)
    return LogRecord.create(**values)


def group(count, prefix='m'):
    return [make_record(f'{prefix}{number}') for number in range(count)]


def log_records(request):
    """The OTLP log records of one request the fake receiver kept, as dictionaries."""
    body = json.loads(request['body'])
    return [item for scope in body['resourceLogs'][0]['scopeLogs'] for item in scope['logRecords']]


def messages_of(receiver):
    return [item['body']['stringValue'] for request in list(receiver.requests) for item in log_records(request)]


def attributes_of(logRecord):
    return {item['key']: item['value'] for item in logRecord['attributes']}


class SinkCase(unittest.TestCase):

    def setUp(self):
        self.receiver = FakeReceiver()
        self.addCleanup(self.receiver.stop)
        self.sinks = []
        self.addCleanup(self._close)

    def _close(self):
        for sink in self.sinks:
            sink.close()

    def make(self, **settings):
        for name, value in FAST.items():
            settings.setdefault(name, value)
        settings.setdefault('captureTrace', False)
        sink = OtlpLogSink(self.receiver.url, **settings)
        self.sinks.append(sink)
        return sink


class TestSettings(unittest.TestCase):

    def test_the_defaults_are_the_ones_of_the_opentelemetry_sdks(self):
        sink = OtlpLogSink('http://127.0.0.1:1', captureTrace=False)
        self.assertEqual((sink.batchSize, sink.batchInterval), (512, 1.0))

    def test_capture_trace_follows_the_package_when_it_is_not_given(self):
        for available in (True, False):
            with mock.patch.object(otlp_sink, 'trace_api_available', return_value=available):
                self.assertEqual(OtlpLogSink('http://127.0.0.1:1').captureTrace, available)

    def test_capture_trace_can_be_forced_either_way_without_looking_for_the_package(self):
        with mock.patch.object(otlp_sink, 'trace_api_available', side_effect=AssertionError('must not look')):
            self.assertTrue(OtlpLogSink('http://127.0.0.1:1', captureTrace=True).captureTrace)
            self.assertFalse(OtlpLogSink('http://127.0.0.1:1', captureTrace=False).captureTrace)

    def test_capture_trace_must_be_a_boolean_or_none(self):
        for bad in (1, 'yes', 0):
            with self.assertRaises(TypeError):
                OtlpLogSink('http://127.0.0.1:1', captureTrace=bad)

    def test_the_retry_settings(self):
        OtlpLogSink('http://127.0.0.1:1', captureTrace=False, maxRetries=0)
        for bad in (-1,):
            with self.assertRaises(ValueError):
                OtlpLogSink('http://127.0.0.1:1', maxRetries=bad)
        for bad in (1.5, '2', True, None):
            with self.assertRaises(TypeError):
                OtlpLogSink('http://127.0.0.1:1', maxRetries=bad)
        for name in ('retryBackoffBase', 'retryBackoffMax'):
            for bad in (0, -1):
                with self.assertRaises(ValueError):
                    OtlpLogSink('http://127.0.0.1:1', **{name: bad})
            for bad in ('1', None, True):
                with self.assertRaises(TypeError):
                    OtlpLogSink('http://127.0.0.1:1', **{name: bad})
        with self.assertRaises(ValueError):
            OtlpLogSink('http://127.0.0.1:1', retryBackoffBase=5, retryBackoffMax=1)

    def test_the_group_settings_are_checked_by_the_sink_base(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                OtlpLogSink('http://127.0.0.1:1', batchSize=bad)
        with self.assertRaises(TypeError):
            OtlpLogSink('http://127.0.0.1:1', batchSize='5')
        with self.assertRaises(ValueError):
            OtlpLogSink('http://127.0.0.1:1', batchInterval=-1)

    def test_a_wrong_endpoint_or_header_is_refused(self):
        for endpoint in ('', 'localhost:4318', 'ftp://x', 'http://user:pw@host', 'http://host?token=x'):
            with self.assertRaises(ValueError):
                OtlpLogSink(endpoint)
        with self.assertRaises(ValueError):
            OtlpLogSink('http://127.0.0.1:1', headers={'Content-Type': 'text/plain'})
        with self.assertRaises(TypeError):
            OtlpLogSink('http://127.0.0.1:1', headers={'a': 1})

    def test_a_wrong_resource_or_severity_map_is_refused(self):
        with self.assertRaises(TypeError):
            OtlpLogSink('http://127.0.0.1:1', resource=[('a', 'b')])
        with self.assertRaises(TypeError):
            OtlpLogSink('http://127.0.0.1:1', severityMap={'a': 1})

    def test_the_address_and_the_destination_leave_the_token_out(self):
        sink = OtlpLogSink('https://Collector.example.org:4318/otel', headers={'Authorization': f'Bearer {TOKEN}'}, captureTrace=False)
        self.assertEqual(sink.url, 'https://collector.example.org:4318/otel/v1/logs')
        self.assertEqual(sink.spool_destination(), {'protocol': 'https', 'host': 'collector.example.org', 'port': 4318, 'path': '/otel/v1/logs'})
        for text in (sink.url, str(sink.spool_destination()), str(sink.stats)):
            self.assertNotIn(TOKEN, text)

    def test_two_tokens_make_one_destination(self):
        first = OtlpLogSink('http://127.0.0.1:1', headers={'Authorization': 'one'}, captureTrace=False)
        second = OtlpLogSink('http://127.0.0.1:1', headers={'Authorization': 'two'}, captureTrace=False)
        self.assertEqual(first.spool_destination(), second.spool_destination())

    def test_the_stats_start_at_zero(self):
        stats = OtlpLogSink('http://127.0.0.1:1', captureTrace=False).stats
        for name in ('sent', 'batches', 'bytes', 'partial_rejected', 'retries', 'refused', 'errors', 'processed', 'failed'):
            self.assertEqual(stats[name], 0, name)
        self.assertIsNone(stats['last_status'])

    def test_a_formatter_set_on_the_sink_changes_nothing_in_what_is_sent(self):
        receiver = FakeReceiver()
        self.addCleanup(receiver.stop)
        sink = OtlpLogSink(receiver.url, captureTrace=False)
        self.addCleanup(sink.close)
        sink.deliver_batch(group(1))
        sink.set_formatter('text')
        sink.deliver_batch(group(1))
        first, second = (json.loads(request['body']) for request in receiver.requests)
        for body in (first, second):
            for scope in body['resourceLogs'][0]['scopeLogs']:
                for item in scope['logRecords']:
                    item.pop('observedTimeUnixNano')
        self.assertEqual(first['resourceLogs'][0]['scopeLogs'], second['resourceLogs'][0]['scopeLogs'])


class TestOneGroup(SinkCase):

    def test_a_group_is_one_request_with_every_record_in_order(self):
        sink = self.make()
        self.assertEqual(sink.deliver_batch(group(25)), [DELIVERED] * 25)
        self.assertEqual(self.receiver.count(), 1)
        self.assertEqual(messages_of(self.receiver), [f'm{number}' for number in range(25)])

    def test_the_stats_after_a_group(self):
        sink = self.make()
        sink.deliver_batch(group(10))
        stats = sink.stats
        self.assertEqual((stats['sent'], stats['batches'], stats['processed'], stats['failed'], stats['last_status']), (10, 1, 10, 0, 200))
        self.assertEqual(stats['bytes'], len(self.receiver.requests[0]['body']))

    def test_the_body_is_the_one_of_the_encoder(self):
        records = [make_record('a', fields={'k': 1}, context={'c': 'x'}), make_record('b', logType='error', severity='ERROR')]
        sink = self.make(resource={'service.name': 'orders'}, scopeVersion='6.0.0')
        sink.deliver_batch(records)
        sent = json.loads(self.receiver.requests[0]['body'])
        expected = OtlpLogEncoder(resource={'service.name': 'orders'}, scopeVersion='6.0.0').encode_request(records, 1)
        for body in (sent, expected):
            for item in body['resourceLogs'][0]['scopeLogs'][0]['logRecords']:
                item.pop('observedTimeUnixNano', None)
        self.assertEqual(sent, expected)

    def test_the_observed_time_is_the_time_of_sending(self):
        sink = self.make()
        before = time.time_ns()
        sink.deliver_batch(group(2))
        after = time.time_ns()
        times = {int(item['observedTimeUnixNano']) for item in log_records(self.receiver.requests[0])}
        self.assertEqual(len(times), 1)
        self.assertTrue(before <= times.pop() <= after)

    def test_headers_and_gzip_are_used(self):
        sink = self.make(headers={'Authorization': f'Bearer {TOKEN}'}, compress=True)
        sink.deliver_batch(group(3))
        request = self.receiver.requests[0]
        self.assertEqual((request['headers']['authorization'], request['headers']['content-encoding']), (f'Bearer {TOKEN}', 'gzip'))
        self.assertEqual(len(log_records(request)), 3)

    def test_the_stable_identifier_becomes_the_record_uid(self):
        sink = self.make()
        sink.deliver_batch([make_record('a', fields={'event_id': 'slot-1'})])
        self.assertEqual(attributes_of(log_records(self.receiver.requests[0])[0])['log.record.uid'], {'stringValue': 'slot-1'})
        other = self.make(eventIdField='eid')
        other.deliver_batch([make_record('a', fields={'eid': 'x-9', 'event_id': 'ignored'})])
        attributes = attributes_of(log_records(self.receiver.requests[1])[0])
        self.assertEqual(attributes['log.record.uid'], {'stringValue': 'x-9'})
        self.assertEqual(attributes['event_id'], {'stringValue': 'ignored'})

    def test_the_trace_and_the_severity_map_are_used(self):
        sink = self.make(severityMap=OtlpSeverityMap({'audit': 11}))
        sink.deliver_batch([make_record('a', logType='audit', severity='AUDIT', trace=TRACE)])
        item = log_records(self.receiver.requests[0])[0]
        self.assertEqual((item['severityNumber'], item['traceId'], item['spanId'], item['flags']), (11, TRACE.traceId, TRACE.spanId, 1))

    def test_a_record_with_everything(self):
        record = make_record('failed', logType='error', severity='ERROR', fields={'order_id': 5, 'ratio': float('nan')},
                             context={'service': 'checkout'}, exception=ExceptionInfo('ValueError', 'bad', 'Traceback...'),
                             caller=CallerInfo('db.py', 9, 'connect', 'orders.db'), trace=TRACE)
        self.assertEqual(self.make().deliver_batch([record]), [DELIVERED])
        attributes = attributes_of(log_records(self.receiver.requests[0])[0])
        self.assertEqual(attributes['code.function.name'], {'stringValue': 'orders.db.connect'})
        self.assertEqual(attributes['ratio'], {'doubleValue': 'NaN'})
        self.assertEqual(attributes['exception.type'], {'stringValue': 'ValueError'})

    def test_a_partial_success_counts_the_refused_records_and_is_not_sent_again(self):
        sink = self.make()
        body = json.dumps({'partialSuccess': {'rejectedLogRecords': '4', 'errorMessage': 'too old'}}).encode()
        self.receiver.script.append(Answer(body=body))
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(sink.deliver_batch(group(10)), [DELIVERED] * 10)
        self.assertEqual(self.receiver.count(), 1)
        stats = sink.stats
        self.assertEqual((stats['sent'], stats['partial_rejected'], stats['retries']), (10, 4, 0))
        self.assertIn('refused 4 records', error.getvalue())
        self.assertIn('too old', error.getvalue())

    def test_a_partial_success_cannot_refuse_more_records_than_the_group_has(self):
        sink = self.make()
        self.receiver.script.append(Answer(body=json.dumps({'partialSuccess': {'rejectedLogRecords': 999}}).encode()))
        with contextlib.redirect_stderr(io.StringIO()):
            sink.deliver_batch(group(3))
        self.assertEqual(sink.stats['partial_rejected'], 3)

    def test_a_different_partial_success_message_warns_again_and_there_is_a_limit(self):
        sink = self.make()
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for number in range(30):
                body = json.dumps({'partialSuccess': {'rejectedLogRecords': 1, 'errorMessage': f'reason {number}'}}).encode()
                self.receiver.script.append(Answer(body=body))
                sink.deliver_batch(group(1))
        self.assertEqual(error.getvalue().count('WARNING'), otlp_sink.MAX_PARTIAL_MESSAGES)

    def test_the_same_partial_success_warns_once(self):
        sink = self.make()
        body = json.dumps({'partialSuccess': {'rejectedLogRecords': 1, 'errorMessage': 'same'}}).encode()
        self.receiver.script.extend([Answer(body=body)] * 3)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for _ in range(3):
                sink.deliver_batch(group(2))
        self.assertEqual(error.getvalue().count('WARNING'), 1)

    def test_an_empty_group_sends_nothing(self):
        self.assertEqual(self.make().deliver_batch([]), [])
        self.assertEqual(self.receiver.count(), 0)

    def test_one_record_through_the_ordinary_path(self):
        sink = self.make()
        self.assertEqual(sink.deliver(make_record('single')), DELIVERED)
        self.assertEqual(messages_of(self.receiver), ['single'])

    @unittest.skipUnless(hasattr(__import__('test_otlp_encoder'), 'HAS_OFFICIAL_ENCODER') and __import__('test_otlp_encoder').HAS_OFFICIAL_ENCODER,
                         'the official protobuf parser is not installed')
    def test_the_official_parser_reads_what_was_sent(self):
        import base64
        from google.protobuf import json_format
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
        self.make(resource={'service.name': 'orders'}).deliver_batch([make_record('a', trace=TRACE), make_record('b')])
        body = json.loads(self.receiver.requests[0]['body'])
        item = body['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]
        for key in ('traceId', 'spanId'):
            item[key] = base64.b64encode(bytes.fromhex(item[key])).decode()
        message = json_format.ParseDict(body, ExportLogsServiceRequest())
        self.assertEqual(len(message.resource_logs[0].scope_logs[0].log_records), 2)


class TestFailures(SinkCase):

    def test_every_retryable_status_is_tried_again_at_once_and_then_given_back(self):
        for status in (429, 502, 503, 504):
            with self.subTest(status=status):
                receiver = FakeReceiver()
                self.addCleanup(receiver.stop)
                sink = OtlpLogSink(receiver.url, captureTrace=False, **FAST)
                self.addCleanup(sink.close)
                receiver.rule = lambda request, status=status: Answer(status=status)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(sink.deliver_batch(group(4)), [RETRY] * 4)
                self.assertEqual(receiver.count(), 3)
                stats = sink.stats
                self.assertEqual((stats['retries'], stats['failed'], stats['sent'], stats['last_status']), (2, 1, 0, status))

    def test_no_retries_asked_for_means_one_request(self):
        sink = self.make(maxRetries=0)
        self.receiver.rule = lambda request: Answer(status=503)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sink.deliver_batch(group(2)), [RETRY] * 2)
        self.assertEqual((self.receiver.count(), sink.stats['retries']), (1, 0))

    def test_a_receiver_that_comes_back_during_the_retries(self):
        sink = self.make(maxRetries=3)
        self.receiver.script.extend([Answer(status=503), Answer(status=502)])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sink.deliver_batch(group(5)), [DELIVERED] * 5)
        stats = sink.stats
        self.assertEqual((self.receiver.count(), stats['retries'], stats['sent'], stats['failed']), (3, 2, 5, 0))

    def test_no_answer_at_all_is_retried_too(self):
        receiver = FakeReceiver()
        port = receiver.port
        receiver.stop()
        sink = OtlpLogSink(f'http://127.0.0.1:{port}', captureTrace=False, **FAST)
        self.addCleanup(sink.close)
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(sink.deliver_batch(group(2)), [RETRY] * 2)
        self.assertEqual((sink.stats['retries'], sink.stats['last_status']), (2, None))
        self.assertIn('no answer', error.getvalue())
        self.assertIn('ConnectionRefusedError', error.getvalue())

    def test_the_wait_the_receiver_asked_for_is_given_between_the_retries(self):
        sink = self.make(maxRetries=1)
        self.receiver.script.extend([Answer(status=503, headers={'Retry-After': '0.3'})])
        started = time.monotonic()
        self.assertEqual(sink.deliver_batch(group(1)), [DELIVERED])
        self.assertGreaterEqual(time.monotonic() - started, 0.28)

    def test_the_wait_is_also_given_when_the_retries_are_over_so_the_next_try_is_not_early(self):
        sink = self.make(maxRetries=0)
        self.receiver.script.append(Answer(status=503, headers={'Retry-After': '0.3'}))
        started = time.monotonic()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sink.deliver_batch(group(1)), [RETRY])
        self.assertGreaterEqual(time.monotonic() - started, 0.28)

    def test_the_waits_without_a_request_grow_and_are_cut_and_have_jitter(self):
        sink = self.make(maxRetries=4, retryBackoffBase=0.1, retryBackoffMax=0.35)
        waits = []

        class Spy:
            def wait(self, seconds=None):
                waits.append(seconds)
                return False

            def set(self):
                pass
        sink._closing = Spy()
        self.receiver.rule = lambda request: Answer(status=503)
        with mock.patch.object(random, 'uniform', return_value=1.0) as uniform:
            with contextlib.redirect_stderr(io.StringIO()):
                sink.deliver_batch(group(1))
        self.assertEqual([round(wait, 6) for wait in waits], [0.1, 0.2, 0.35, 0.35])
        uniform.assert_called_with(0.8, 1.2)

    def test_the_jitter_stays_within_twenty_percent(self):
        sink = self.make(maxRetries=1, retryBackoffBase=1.0, retryBackoffMax=1.0)
        waits = []

        class Spy:
            def wait(self, seconds=None):
                waits.append(seconds)
                return False

            def set(self):
                pass
        sink._closing = Spy()
        self.receiver.rule = lambda request: Answer(status=503)
        for _ in range(40):
            with contextlib.redirect_stderr(io.StringIO()):
                sink.deliver_batch(group(1))
        self.assertTrue(all(0.8 <= wait <= 1.2 for wait in waits))
        self.assertGreater(len(set(waits)), 5)

    def test_a_payload_the_receiver_refuses_is_a_split(self):
        for status in (400, 413, 422):
            with self.subTest(status=status):
                sink = self.make()
                self.receiver.script.append(Answer(status=status))
                before = self.receiver.count()
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(sink.deliver_batch(group(6)), [SPLIT] * 6)
                self.assertEqual(self.receiver.count(), before + 1)
                self.assertEqual((sink.stats['refused'], sink.stats['retries']), (1, 0))
                self.assertIn('smaller groups', error.getvalue())

    def test_one_record_the_receiver_refuses_is_rejected(self):
        sink = self.make()
        self.receiver.script.append(Answer(status=400))
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(sink.deliver_batch(group(1)), [SPLIT])
            self.receiver.script.append(Answer(status=400))
            self.assertEqual(sink.deliver(make_record('x')), REJECTED)
        self.assertIn('given up on', error.getvalue())

    def test_any_other_answer_is_not_retried_at_once_and_is_warned_about(self):
        for status in (401, 403, 404, 405, 415, 500, 301):
            with self.subTest(status=status):
                receiver = FakeReceiver()
                self.addCleanup(receiver.stop)
                sink = OtlpLogSink(receiver.url, captureTrace=False, headers={'Authorization': f'Bearer {TOKEN}'}, **FAST)
                self.addCleanup(sink.close)
                receiver.rule = lambda request, status=status: Answer(status=status, body=b'{"detail": "secret-detail-in-the-answer"}')
                error = io.StringIO()
                with contextlib.redirect_stderr(error):
                    self.assertEqual(sink.deliver_batch(group(3)), [RETRY] * 3)
                self.assertEqual(receiver.count(), 1)
                stats = sink.stats
                self.assertEqual((stats['errors'], stats['retries'], stats['last_status']), (1, 0, status))
                self.assertIn(f'status {status}', error.getvalue())
                self.assertNotIn(TOKEN, error.getvalue())
                self.assertNotIn('secret-detail', error.getvalue())

    def test_one_warning_for_a_run_of_failures_and_a_new_one_after_a_success(self):
        sink = self.make(maxRetries=0)
        self.receiver.rule = lambda request: Answer(status=503)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for _ in range(6):
                sink.deliver_batch(group(1))
        self.assertEqual(error.getvalue().count('WARNING'), 1)
        self.receiver.rule = None
        sink.deliver_batch(group(1))
        self.receiver.rule = lambda request: Answer(status=503)
        with contextlib.redirect_stderr(error):
            sink.deliver_batch(group(1))
        self.assertEqual(error.getvalue().count('WARNING'), 2)

    def test_a_different_failure_warns_again_in_the_same_run(self):
        sink = self.make(maxRetries=0)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.receiver.script.extend([Answer(status=503), Answer(status=429), Answer(status=503)])
            for _ in range(3):
                sink.deliver_batch(group(1))
        self.assertEqual(error.getvalue().count('WARNING'), 2)

    def test_closing_ends_a_wait_between_retries_at_once(self):
        sink = self.make(maxRetries=3)
        self.receiver.rule = lambda request: Answer(status=503, headers={'Retry-After': '120'})
        results = []
        with contextlib.redirect_stderr(io.StringIO()):
            thread = threading.Thread(target=lambda: results.append(sink.deliver_batch(group(2))))
            thread.start()
            wait_until(lambda: self.receiver.count() >= 1, what='the first request')
            started = time.monotonic()
            sink.close()
            thread.join(10)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(results, [[RETRY, RETRY]])
        self.assertEqual(self.receiver.count(), 1)
        # It gave up at the wait. It did not go round the loop again for each of the retries that were left
        self.assertEqual(sink.stats['retries'], 1)

    def test_closing_twice_and_sending_after_a_close(self):
        sink = self.make()
        sink.close()
        sink.close()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sink.deliver_batch(group(1)), [RETRY])
        self.assertEqual(self.receiver.count(), 0)

    def test_a_group_that_cannot_be_encoded_is_a_split_and_never_an_endless_retry(self):
        sink = self.make()
        error = io.StringIO()
        with mock.patch.object(sink._encoder, 'encode', side_effect=RuntimeError('secret-in-error')), contextlib.redirect_stderr(error):
            self.assertEqual(sink.deliver_batch(group(3)), [SPLIT] * 3)
        self.assertEqual((sink.stats['errors'], self.receiver.count()), (1, 0))
        self.assertIn('RuntimeError', error.getvalue())
        self.assertNotIn('secret-in-error', error.getvalue())

    def test_a_value_that_makes_the_encoder_fail_for_one_record_is_found_by_splitting(self):
        # The sink gives the group back as SPLIT, and the delivery worker halves it. Here the halves are made by hand
        sink = self.make()
        original = sink._encoder.encode

        def encode(records, observed):
            if any(record.message == 'poison' for record in records):
                raise RuntimeError('cannot encode')
            return original(records, observed)
        records = group(4) + [make_record('poison')] + group(3, 'z')
        with mock.patch.object(sink._encoder, 'encode', side_effect=encode), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sink.deliver_batch(records), [SPLIT] * 8)
            self.assertEqual(sink.deliver_batch(records[:4]), [DELIVERED] * 4)
            self.assertEqual(sink.deliver_batch(records[4:5]), [SPLIT])

    def test_the_warning_names_the_address_and_never_the_token(self):
        sink = self.make(headers={'Authorization': f'Bearer {TOKEN}'}, maxRetries=0)
        self.receiver.rule = lambda request: Answer(status=503)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            sink.deliver_batch(group(1))
        self.assertIn(self.receiver.url, error.getvalue())
        self.assertNotIn(TOKEN, error.getvalue())


class LoggerCase(unittest.TestCase):

    def setUp(self):
        self.receiver = FakeReceiver()
        self.addCleanup(self.receiver.stop)
        self.root = tempfile.mkdtemp(prefix='otlptest-')
        self.loggers = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for logger in self.loggers:
            with contextlib.suppress(Exception):
                logger.clear_sinks(timeout=2.0)
        shutil.rmtree(self.root, ignore_errors=True)

    def logger(self, **arguments):
        logger = Logger('orders', logToFile=False, logToStdout=False, **arguments)
        self.loggers.append(logger)
        return logger

    def spool(self, **overrides):
        values = dict(path=os.path.join(self.root, 'spool'), id='otlp-test', maxBytes=10 * 1024 ** 2, totalMaxBytes=100 * 1024 ** 2,
                      retryBackoffBase=0.01, retryBackoffMax=0.05)
        values.update(overrides)
        return values

    def attach(self, logger, **settings):
        for name, value in dict(FAST, captureTrace=False).items():
            settings.setdefault(name, value)
        return attach(logger, self.receiver.url, **settings)


class TestAttach(LoggerCase):

    def test_it_registers_one_threaded_sink_and_returns_it(self):
        logger = self.logger()
        sink = self.attach(logger)
        self.assertIsInstance(sink, OtlpLogSink)
        self.assertIs(logger.sinks['otlp'], sink)
        stats = logger.sink_stats('otlp')
        self.assertIsNotNone(stats['queue'])
        self.assertEqual(stats['queue']['capacity'], 10000)
        self.assertEqual(stats['queue']['policy'], 'drop_oldest')

    def test_the_name_the_queue_and_the_options_are_forwarded(self):
        logger = self.logger()
        self.attach(logger, sinkName='collector', threadQueueSize=77, threadQueuePolicy='block', minLevel=20.0, logTypeFlags={'error': True},
                    defaultFlag=False)
        stats = logger.sink_stats('collector')['queue']
        self.assertEqual((stats['capacity'], stats['policy']), (77, 'block'))
        logger.info('too low')
        logger.error('kept')
        logger.flush()
        self.assertEqual(messages_of(self.receiver), ['kept'])

    def test_the_settings_go_to_the_sink(self):
        logger = self.logger()
        sink = self.attach(logger, batchSize=7, batchInterval=0.25, compress=True, headers={'X-Tenant': 't1'})
        self.assertEqual((sink.batchSize, sink.batchInterval), (7, 0.25))
        logger.info('x')
        logger.flush()
        request = self.receiver.requests[0]
        self.assertEqual((request['headers']['x-tenant'], request['headers']['content-encoding']), ('t1', 'gzip'))

    def test_a_wrong_setting_adds_nothing_and_leaves_nothing_open(self):
        logger = self.logger()
        before = set(logger.sinks)
        for settings in ({'endpoint': 'nope'}, {'maxRetries': -1}):
            with self.assertRaises((ValueError, TypeError)):
                attach(logger, settings.pop('endpoint', self.receiver.url), **settings)
        with self.assertRaises((TypeError, ValueError)):
            attach(logger, self.receiver.url, sinkName='x', threadQueueSize=0)
        self.assertEqual(set(logger.sinks), before)

    def test_a_name_already_used_is_refused_and_the_old_sink_stays(self):
        logger = self.logger()
        first = self.attach(logger)
        with self.assertRaises(ValueError):
            self.attach(logger)
        self.assertIs(logger.sinks['otlp'], first)
        logger.info('still works')
        logger.flush()
        self.assertEqual(messages_of(self.receiver), ['still works'])

    def test_removing_the_sink_sends_what_it_holds(self):
        logger = self.logger()
        self.attach(logger, batchSize=100, batchInterval=60.0)
        for number in range(7):
            logger.info(str(number))
        started = time.monotonic()
        logger.remove_sink('otlp')
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(7)])

    def test_a_spool_is_forwarded(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool())
        logger.info('x')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertIsNotNone(logger.sink_stats('otlp')['spool'])
        self.assertEqual(logger.sink_stats('otlp')['spool']['depth'], 0)


class TestWithTheLogger(LoggerCase):

    def test_what_is_logged_arrives_as_otlp(self):
        logger = self.logger(callerInfo=True)
        self.attach(logger, resource={'service.name': 'orders'})
        with logger.context(request_id='r-1'):
            logger.error('payment failed', order_id=5, amount=12.5)
        logger.flush()
        item = log_records(self.receiver.requests[0])[0]
        attributes = attributes_of(item)
        self.assertEqual((item['severityNumber'], item['severityText'], item['body']), (17, 'ERROR', {'stringValue': 'payment failed'}))
        self.assertEqual((attributes['order_id'], attributes['amount'], attributes['request_id']),
                         ({'intValue': '5'}, {'doubleValue': 12.5}, {'stringValue': 'r-1'}))
        self.assertIn('code.file.path', attributes)

    def test_an_exception_is_attached(self):
        logger = self.logger()
        self.attach(logger)
        try:
            raise KeyError('missing')
        except KeyError:
            logger.error('lookup failed', exc_info=True)
        logger.flush()
        attributes = attributes_of(log_records(self.receiver.requests[0])[0])
        self.assertEqual(attributes['exception.type'], {'stringValue': 'KeyError'})
        self.assertIn('Traceback', attributes['exception.stacktrace']['stringValue'])

    def test_every_log_type_has_its_severity(self):
        logger = self.logger()
        self.attach(logger)
        for logType in ('debug', 'info', 'warn', 'error', 'critical'):
            logger.log(logType, logType)
        logger.flush()
        numbers = [item['severityNumber'] for request in self.receiver.requests for item in log_records(request)]
        self.assertEqual(numbers, [5, 9, 13, 17, 21])

    def test_a_backlog_goes_out_in_full_groups(self):
        logger = self.logger()
        self.attach(logger, batchSize=100, batchInterval=0.05, threadQueuePolicy='block')
        for number in range(1000):
            logger.info(str(number))
        logger.flush()
        sizes = [len(log_records(request)) for request in self.receiver.requests]
        self.assertEqual(sum(sizes), 1000)
        self.assertTrue(all(size <= 100 for size in sizes))
        self.assertLess(len(sizes), 100)
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(1000)])

    def test_a_group_that_is_not_full_waits_for_the_interval(self):
        logger = self.logger()
        self.attach(logger, batchSize=100, batchInterval=0.4)
        started = time.monotonic()
        for number in range(3):
            logger.info(str(number))
        time.sleep(0.15)
        self.assertEqual(self.receiver.count(), 0)
        wait_until(lambda: self.receiver.count() == 1, what='the request')
        self.assertGreater(time.monotonic() - started, 0.3)

    def test_flush_does_not_wait_for_the_interval(self):
        logger = self.logger()
        self.attach(logger, batchSize=100, batchInterval=60.0)
        logger.info('x')
        started = time.monotonic()
        logger.flush()
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(self.receiver.count(), 1)

    def test_many_threads_lose_nothing_and_each_keeps_its_order(self):
        logger = self.logger()
        self.attach(logger, batchSize=50, batchInterval=0.01, threadQueuePolicy='block', threadQueueSize=200)

        def work(number):
            for index in range(150):
                logger.info(f'{number}-{index}')
        threads = [threading.Thread(target=work, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        logger.flush()
        got = messages_of(self.receiver)
        self.assertEqual(len(got), 1200)
        self.assertEqual(len(set(got)), 1200)
        for number in range(8):
            self.assertEqual([int(text.split('-')[1]) for text in got if text.startswith(f'{number}-')], list(range(150)))

    def test_with_the_queue_of_the_logger_in_front(self):
        logger = self.logger(enqueue=True)
        self.attach(logger, threadQueuePolicy='block')
        for number in range(200):
            logger.info(str(number))
        logger.flush()
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(200)])

    def test_the_stats_of_the_logger(self):
        logger = self.logger()
        self.attach(logger, batchInterval=0.0)
        for number in range(30):
            logger.info(str(number))
        logger.flush()
        delivery = logger.sink_stats('otlp')['delivery']
        self.assertEqual((delivery['sent'], delivery['processed'], delivery['failed'], delivery['last_status']), (30, 30, 0, 200))
        self.assertGreaterEqual(delivery['batches'], 1)

    def test_a_program_that_ends_with_a_group_waiting_still_sends_it(self):
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {PACKAGE_DIR!r})
            from simple_log import Logger
            from contrib.otlp_sink import attach
            logger = Logger('orders', logToFile=False, logToStdout=False)
            attach(logger, {self.receiver.url!r}, batchSize=100, batchInterval=60.0, captureTrace=False)
            for number in range(5):
                logger.info(str(number))
        """)
        started = time.monotonic()
        completed = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertLess(time.monotonic() - started, 50)
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(5)])

    @unittest.skipUnless(os.name == 'posix', 'fork exists on POSIX systems only')
    def test_a_forked_process_sends_by_itself(self):
        logger = self.logger()
        sink = OtlpLogSink(self.receiver.url, captureTrace=False, **FAST)
        logger.add_sink('otlp', sink)
        logger.info('parent one')
        read, write = os.pipe()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            pid = os.fork()
        if pid == 0:
            try:
                warnings.simplefilter('ignore')
                os.close(read)
                logger.info('child')
                os.write(write, b'ok')
            finally:
                os._exit(0)
        os.close(write)
        os.read(read, 10)
        os.close(read)
        os.waitpid(pid, 0)
        logger.info('parent two')
        self.assertEqual(messages_of(self.receiver), ['parent one', 'child', 'parent two'])
        self.assertEqual(self.receiver.connections, 2)


class TestTraceIdentifiers(LoggerCase, TracingCase):

    def setUp(self):
        TracingCase.setUp(self)
        LoggerCase.setUp(self)

    def test_the_identifiers_of_the_active_span_are_sent_by_default_when_the_package_is_there(self):
        logger = self.logger()
        sink = attach(logger, self.receiver.url, **FAST)
        self.assertTrue(sink.captureTrace)
        logger.info('traced')
        logger.flush()
        item = log_records(self.receiver.requests[0])[0]
        self.assertEqual((item['traceId'], item['spanId'], item['flags']), ('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1))

    def test_they_are_not_read_when_it_is_switched_off(self):
        logger = self.logger()
        attach(logger, self.receiver.url, captureTrace=False, **FAST)
        logger.info('x')
        logger.flush()
        self.assertEqual(self.api.reads, [])
        self.assertNotIn('traceId', log_records(self.receiver.requests[0])[0])

    def test_each_thread_sends_the_span_it_was_in(self):
        logger = self.logger(enqueue=True)
        attach(logger, self.receiver.url, threadQueuePolicy='block', **FAST)

        def work(number):
            self.api.set_span(FakeSpanContext(traceId=number + 1, spanId=number + 1, traceFlags=number % 2))
            for index in range(20):
                logger.info(f'{number}-{index}')
        threads = [threading.Thread(target=work, args=(number,)) for number in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        logger.flush()
        seen = 0
        for request in self.receiver.requests:
            for item in log_records(request):
                number = int(item['body']['stringValue'].split('-')[0])
                self.assertEqual((item['traceId'], item['spanId'], item['flags']), (f'{number + 1:032x}', f'{number + 1:016x}', number % 2))
                seen += 1
        self.assertEqual(seen, 120)


class TestWithASpool(LoggerCase):

    def test_an_outage_then_a_recovery_delivers_everything_in_order_and_once(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(), batchSize=20, maxRetries=0)
        self.receiver.rule = lambda request: Answer(status=503)
        for number in range(60):
            logger.info(str(number))
        wait_until(lambda: logger.sink_stats('otlp')['spool']['retries'] >= 3, what='retries')
        self.assertEqual(messages_of(self.receiver) and len({m for m in messages_of(self.receiver)}) <= 20, True)
        self.receiver.rule = None
        self.receiver.requests.clear()
        with contextlib.redirect_stderr(io.StringIO()):
            logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(60)])
        self.assertEqual(logger.sink_stats('otlp')['spool']['depth'], 0)

    def test_an_answer_nobody_retries_makes_the_records_wait_and_they_are_not_lost(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(), headers={'Authorization': f'Bearer {TOKEN}'})
        state = {'ok': False}
        self.receiver.rule = lambda request: Answer(status=200 if state['ok'] else 401)
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for number in range(5):
                logger.info(str(number))
            wait_until(lambda: logger.sink_stats('otlp')['spool']['retries'] >= 3, what='retries')
        self.assertEqual(logger.sink_stats('otlp')['spool']['dead'], 0)
        self.assertEqual(error.getvalue().count('status 401'), 1)
        self.assertNotIn(TOKEN, error.getvalue())
        state['ok'] = True
        self.receiver.requests.clear()
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(5)])

    def test_one_record_the_receiver_cannot_take_is_found_and_parked_and_the_others_arrive(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(), batchSize=64, batchInterval=60.0)
        self.receiver.rule = lambda request: Answer(status=400) if b'poison' in request['body'] else Answer()
        with contextlib.redirect_stderr(io.StringIO()):
            for number in range(20):
                logger.info('poison' if number == 7 else f'm{number}')
            logger.flush(timeout=WAIT_SECONDS)
        accepted = [text for request in self.receiver.requests if b'poison' not in request['body']
                    for text in [item['body']['stringValue'] for item in log_records(request)]]
        self.assertEqual(sorted(accepted, key=lambda text: int(text[1:])), [f'm{number}' for number in range(20) if number != 7])
        self.assertEqual(logger.sink_stats('otlp')['spool']['dead'], 1)
        self.assertEqual(logger.sink_stats('otlp')['spool']['depth'], 0)
        self.assertLessEqual(self.receiver.count(), 2 + 2 * 5 + 2)

    def test_a_partial_success_is_a_delivery_and_nothing_is_sent_again(self):
        logger = self.logger()
        # The group is full at the fifth record, so the five go in one request whatever the timing
        self.attach(logger, spool=self.spool(), batchSize=5, batchInterval=60.0)
        self.receiver.script.append(Answer(body=json.dumps({'partialSuccess': {'rejectedLogRecords': 2, 'errorMessage': 'x'}}).encode()))
        with contextlib.redirect_stderr(io.StringIO()):
            for number in range(5):
                logger.info(str(number))
            logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual(logger.sink_stats('otlp')['spool']['depth'], 0)
        self.assertEqual(logger.sink_stats('otlp')['delivery']['partial_rejected'], 2)
        self.assertEqual(sorted(messages_of(self.receiver)), [str(number) for number in range(5)])

    def test_the_stable_identifier_is_the_record_uid_and_does_not_change_when_a_group_is_sent_again(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(), maxRetries=0)
        self.receiver.script.extend([Answer(status=503)] * 3)
        with contextlib.redirect_stderr(io.StringIO()):
            for number in range(4):
                logger.info(str(number))
            logger.flush(timeout=WAIT_SECONDS)
        uids = {}
        for request in self.receiver.requests:
            for item in log_records(request):
                uids.setdefault(item['body']['stringValue'], set()).add(attributes_of(item)['log.record.uid']['stringValue'])
        self.assertEqual(sorted(uids), ['0', '1', '2', '3'])
        self.assertTrue(all(len(ids) == 1 for ids in uids.values()))
        self.assertEqual(len({next(iter(ids)) for ids in uids.values()}), 4)

    def test_the_identifier_needs_the_same_name_in_the_spool_and_in_the_sink(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(eventIdField='eid'))
        logger.info('x')
        logger.flush(timeout=WAIT_SECONDS)
        attributes = attributes_of(log_records(self.receiver.requests[0])[0])
        self.assertNotIn('log.record.uid', attributes)
        self.assertIn('eid', attributes)
        other = self.logger()
        self.receiver.requests.clear()
        self.attach(other, sinkName='second', eventIdField='eid', spool=self.spool(eventIdField='eid', path=os.path.join(self.root, 'second')))
        other.info('y')
        other.flush(timeout=WAIT_SECONDS)
        attributes = attributes_of(log_records(self.receiver.requests[0])[0])
        self.assertIn('log.record.uid', attributes)
        self.assertNotIn('eid', attributes)

    def test_the_token_is_in_no_file_of_the_spool(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(), headers={'Authorization': f'Bearer {TOKEN}'})
        self.receiver.rule = lambda request: Answer(status=503)
        for number in range(5):
            logger.info(str(number))
        wait_until(lambda: logger.sink_stats('otlp')['spool']['retries'] >= 2, what='retries')
        found = 0
        for folder, _, names in os.walk(self.root):
            for name in names:
                # The lock file is held by the spool, Windows refuses to read it, and it holds no record
                if name == 'lock':
                    continue
                with open(os.path.join(folder, name), 'rb') as stream:
                    self.assertNotIn(TOKEN.encode(), stream.read(), os.path.join(folder, name))
                found += 1
        self.assertGreater(found, 0)

    def test_two_sinks_with_one_spool_id_and_two_receivers_stay_apart(self):
        other = FakeReceiver()
        self.addCleanup(other.stop)
        logger = self.logger()
        self.attach(logger, spool=self.spool(), sinkName='first')
        attach(logger, other.url, sinkName='second', captureTrace=False, spool=self.spool(), **FAST)
        logger.info('to both')
        logger.flush(timeout=WAIT_SECONDS)
        self.assertEqual((messages_of(self.receiver), messages_of(other)), (['to both'], ['to both']))

    def test_compression_with_a_spool(self):
        logger = self.logger()
        self.attach(logger, spool=self.spool(), compress=True)
        for number in range(30):
            logger.info(str(number))
        logger.flush(timeout=WAIT_SECONDS)
        self.assertTrue(all(request['headers']['content-encoding'] == 'gzip' for request in self.receiver.requests))
        self.assertEqual(messages_of(self.receiver), [str(number) for number in range(30)])


CRASH_SCRIPT = textwrap.dedent('''
    import os, sys, time
    packageDir, port, base, count = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    sys.path.insert(0, packageDir)
    from simple_log import Logger
    from record import TraceInfo
    from contrib.otlp_sink import attach
    logger = Logger('orders', logToFile=False, logToStdout=False)
    logger.add_processor(lambda record: record._replace(trace=TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1)))
    attach(logger, f'http://127.0.0.1:{port}', captureTrace=False, maxRetries=0, batchInterval=0.0, timeout=2,
           spool=dict(path=base, id='otlp-test', maxBytes=10**7, totalMaxBytes=10**8, retryBackoffBase=0.01, retryBackoffMax=0.05))
    for index in range(count):
        logger.info(f'm{index}', n=index)
    deadline = time.time() + 20
    while time.time() < deadline and logger.sink_stats('otlp')['spool']['retries'] == 0:
        time.sleep(0.005)
    print(logger.sink_stats('otlp')['spool']['slot'], flush=True)
    os._exit(0)
''')


class TestRestart(LoggerCase):

    def test_records_left_by_a_crash_are_sent_by_the_next_run_with_their_original_trace(self):
        import socket
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        base = os.path.join(self.root, 'spool')
        completed = subprocess.run([sys.executable, '-c', CRASH_SCRIPT, PACKAGE_DIR, str(port), base, '25'], capture_output=True, text=True,
                                   timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        slot = completed.stdout.split()[0]
        self.assertIn(slot, [os.path.basename(path) for path in Spool.slots(base)])
        receiver = FakeReceiver(port=port)
        self.addCleanup(receiver.stop)
        logger = self.logger()
        attach(logger, receiver.url, captureTrace=False, **FAST, spool=self.spool(path=base))
        result = logger.adopt_orphans('otlp', timeout=WAIT_SECONDS)
        self.assertIsNotNone(result)
        self.assertEqual(result['orphans_adopted'], 1)
        got = messages_of(receiver)
        self.assertEqual(got, [f'm{number}' for number in range(25)])
        for request in receiver.requests:
            for item in log_records(request):
                self.assertEqual((item['traceId'], item['spanId']), ('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331'))
                self.assertIn('log.record.uid', attributes_of(item))
        self.assertNotIn(slot, [os.path.basename(path) for path in Spool.slots(base)])

    def test_a_slot_made_for_another_receiver_is_left_alone(self):
        import socket
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        base = os.path.join(self.root, 'spool')
        subprocess.run([sys.executable, '-c', CRASH_SCRIPT, PACKAGE_DIR, str(port), base, '5'], capture_output=True, text=True, timeout=120)
        logger = self.logger()
        self.attach(logger, spool=self.spool(path=base))
        with contextlib.redirect_stderr(io.StringIO()):
            result = logger.adopt_orphans('otlp', timeout=WAIT_SECONDS)
        self.assertEqual(self.receiver.count(), 0)
        self.assertEqual(result['orphans_skipped'], 1)


if __name__ == '__main__':
    unittest.main()
