"""What a sink says about a delivery and about its destination, and the settings of a spool.

Run from the repo root::

    python3 -m unittest tests.test_sink_delivery -v
"""
import io
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import sinks as sinks_module  # noqa: E402
from sinks import (Sink, StreamSink, ConsoleSink, FileSink, CallbackSink, validate_flush_mode, sync_descriptor,  # noqa: E402
                   DELIVERED, RETRY, REJECTED)
from record import LogRecord  # noqa: E402
from spool import Spool, SpoolConfig, target_id  # noqa: E402
from contrib import siem_sink, siem_transport  # noqa: E402


def make_record(text='hello'):
    return LogRecord.create(datetime.now(timezone.utc), 'INFO', 'info', 10.0, 'test', text, 1, 1, 'MainThread')


class ScriptedSink(Sink):
    """A sink whose write does what the test says: return a value or raise an exception."""

    def __init__(self, outcome=None, formatter='{message}'):
        super().__init__(formatter=formatter)
        self.outcome = outcome
        self.written = []

    def write(self, text, record):
        self.written.append(text)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def capture_stderr():
    buffer, previous = io.StringIO(), sys.stderr
    sys.stderr = buffer
    return buffer, previous


class TestDeliver(unittest.TestCase):

    def test_a_write_that_returns_normally_is_delivered(self):
        for outcome in (None, True, 0, 1, 'sent', []):
            with self.subTest(outcome=outcome):
                sink = ScriptedSink(outcome)
                self.assertEqual(sink.deliver(make_record()), DELIVERED)
                self.assertEqual(sink.stats['processed'], 1)
                self.assertEqual(sink.stats['failed'], 0)

    def test_a_write_that_returns_false_is_a_retry_counted_without_a_warning(self):
        sink = ScriptedSink(False)
        buffer, previous = capture_stderr()
        try:
            self.assertEqual(sink.deliver(make_record()), RETRY)
            self.assertEqual(sink.deliver(make_record()), RETRY)
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue(), '')
        self.assertEqual((sink.stats['processed'], sink.stats['failed']), (0, 2))
        self.assertIsNone(sink.stats['last_error'])

    def test_a_write_that_raises_is_a_retry_with_one_warning_for_a_run(self):
        sink = ScriptedSink(OSError('disk gone'))
        buffer, previous = capture_stderr()
        try:
            for _ in range(3):
                self.assertEqual(sink.deliver(make_record()), RETRY)
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('WARNING'), 1)
        self.assertEqual(sink.stats['failed'], 3)
        self.assertIsInstance(sink.stats['last_error'], OSError)

    def test_a_formatter_that_raises_is_a_rejection_and_the_write_is_never_called(self):
        def broken(record):
            raise ValueError('cannot render')

        sink = ScriptedSink(None, formatter=broken)
        buffer, previous = capture_stderr()
        try:
            self.assertEqual(sink.deliver(make_record()), REJECTED)
        finally:
            sys.stderr = previous
        self.assertEqual(sink.written, [])
        self.assertEqual(sink.stats['failed'], 1)

    def test_a_failure_run_ends_with_a_delivery(self):
        sink = ScriptedSink(OSError('down'))
        buffer, previous = capture_stderr()
        try:
            sink.deliver(make_record())
            sink.outcome = None
            sink.deliver(make_record())
            sink.outcome = OSError('down again')
            sink.deliver(make_record())
        finally:
            sys.stderr = previous
        self.assertEqual(buffer.getvalue().count('WARNING'), 2)

    def test_emit_never_raises_and_returns_nothing(self):
        for outcome in (None, False, OSError('x'), RuntimeError('y')):
            with self.subTest(outcome=outcome):
                buffer, previous = capture_stderr()
                try:
                    self.assertIsNone(ScriptedSink(outcome).emit(make_record()))
                finally:
                    sys.stderr = previous

    def test_the_sinks_of_the_package_never_return_false_from_write(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            sinks = [StreamSink(stream), FileSink(os.path.join(folder, 'log')), CallbackSink(lambda text, record: False)]
            for sink in sinks:
                with self.subTest(sink=type(sink).__name__):
                    self.assertEqual(sink.deliver(make_record()), DELIVERED)
            sinks[1].close()

    def test_the_latency_is_kept_for_a_delivery(self):
        sink = ScriptedSink()
        sink.deliver(make_record())
        self.assertGreaterEqual(sink.stats['latency_max'], 0.0)
        self.assertIsNotNone(sink.stats['latency_mean'])


class TestSpoolDestination(unittest.TestCase):

    def test_a_sink_that_does_not_say_where_it_sends_is_refused_with_a_way_out(self):
        with self.assertRaises(TypeError) as caught:
            ScriptedSink().spool_destination()
        self.assertIn('SPOOL_DESTINATION', str(caught.exception))
        self.assertIn('as text', str(caught.exception))

    def test_the_names_a_sink_lists_give_its_destination(self):
        class WebhookSink(ScriptedSink):
            SPOOL_DESTINATION = ('host', 'port')

            def __init__(self):
                super().__init__()
                self.host, self.port, self.token = 'hooks.example.org', 443, 'secret'

        self.assertEqual(WebhookSink().spool_destination(), {'host': 'hooks.example.org', 'port': 443})

    def test_a_listed_name_the_sink_does_not_have_is_a_clear_error(self):
        class BrokenSink(ScriptedSink):
            SPOOL_DESTINATION = ('missing',)

        with self.assertRaises(TypeError) as caught:
            BrokenSink().spool_destination()
        self.assertIn('missing', str(caught.exception))

    def test_a_sink_that_writes_inside_this_process_cannot_be_spooled(self):
        with tempfile.TemporaryDirectory() as folder:
            sinks = [StreamSink(io.StringIO()), ConsoleSink(), FileSink(os.path.join(folder, 'log'))]
            for sink in sinks:
                with self.subTest(sink=type(sink).__name__):
                    with self.assertRaises(TypeError) as caught:
                        sink.spool_destination()
                    self.assertIn('only inside this process', str(caught.exception))


class TestTransportDestination(unittest.TestCase):

    def test_tcp_and_tls_and_udp(self):
        self.assertEqual(siem_transport.TCPSyslogTransport('SIEM.Example.org', 514).describe_destination(),
                         {'protocol': 'tcp', 'host': 'siem.example.org', 'port': 514})
        with mock.patch('ssl.create_default_context'):
            tls = siem_transport.TCPSyslogTransport('siem.example.org', 6514, useTls=True)
        self.assertEqual(tls.describe_destination(), {'protocol': 'tcps', 'host': 'siem.example.org', 'port': 6514})
        udp = siem_transport.UDPSyslogTransport('Siem.Example.org', 514)
        try:
            self.assertEqual(udp.describe_destination(), {'protocol': 'udp', 'host': 'siem.example.org', 'port': 514})
        finally:
            udp.close()

    def test_http_keeps_only_the_scheme_the_host_the_port_and_the_path(self):
        transport = siem_transport.HTTPTransport('https://user:hunter2@Collector.Example.org/api/events?token=SECRET#part')
        destination = transport.describe_destination()
        self.assertEqual(destination, {'protocol': 'https', 'host': 'collector.example.org', 'port': 443,
                                       'path': '/api/events'})
        for hidden in ('SECRET', 'hunter2', 'user', 'part'):
            self.assertNotIn(hidden, str(destination))

    def test_http_fills_in_the_default_port_and_path(self):
        self.assertEqual(siem_transport.HTTPTransport('http://collector.example.org').describe_destination(),
                         {'protocol': 'http', 'host': 'collector.example.org', 'port': 80, 'path': '/'})
        self.assertEqual(siem_transport.HTTPTransport('http://collector.example.org:8080/x').describe_destination()['port'],
                         8080)

    def test_a_changed_token_keeps_the_identity_and_a_changed_host_does_not(self):
        def identity(url):
            destination = siem_transport.HTTPTransport(url).describe_destination()
            return target_id('SiemForwardSink', **destination)

        reference = identity('https://collector.example.org/api?token=one')
        self.assertEqual(reference, identity('https://collector.example.org/api?token=two'))
        self.assertEqual(reference, identity('https://COLLECTOR.example.org/api'))
        self.assertNotEqual(reference, identity('https://other.example.org/api?token=one'))
        self.assertNotEqual(reference, identity('https://collector.example.org/other?token=one'))

    def test_the_console_transport_has_no_destination(self):
        with self.assertRaises(TypeError):
            siem_transport.ConsoleTransport(io.StringIO()).describe_destination()

    def test_the_sink_asks_its_transport(self):
        transport = siem_transport.TCPSyslogTransport('siem.example.org', 514)
        self.assertEqual(siem_sink.SiemForwardSink(transport).spool_destination(),
                         {'protocol': 'tcp', 'host': 'siem.example.org', 'port': 514})

    def test_a_transport_that_cannot_say_it_gives_a_clear_error(self):
        class OwnTransport:
            def send(self, payload):
                pass

            def close(self):
                pass

        with self.assertRaises(TypeError) as caught:
            siem_sink.SiemForwardSink(OwnTransport()).spool_destination()
        self.assertIn('OwnTransport', str(caught.exception))
        with self.assertRaises(TypeError):
            siem_sink.SiemForwardSink(siem_transport.ConsoleTransport(io.StringIO())).spool_destination()


class FailingTransport:
    """A transport that fails a given number of times and then works."""

    def __init__(self, failures):
        self.failures = failures
        self.sent = []

    def send(self, payload):
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError('simulated failure')
        self.sent.append(payload)

    def close(self):
        pass


class TestSiemSinkAnswer(unittest.TestCase):

    def _sink(self, transport, **options):
        defaults = dict(maxRetries=1, retryBackoffBase=0.001, retryBackoffMax=0.001)
        defaults.update(options)
        return siem_sink.SiemForwardSink(transport, **defaults)

    def test_a_sent_record_is_delivered(self):
        transport = FailingTransport(0)
        sink = self._sink(transport)
        self.assertEqual(sink.deliver(make_record()), DELIVERED)
        self.assertEqual(len(transport.sent), 1)

    def test_a_record_dropped_after_its_retries_is_a_retry_and_onDrop_is_still_called(self):
        drops = []
        sink = self._sink(FailingTransport(10), onDrop=drops.append)
        buffer, previous = capture_stderr()
        try:
            self.assertEqual(sink.deliver(make_record()), RETRY)
        finally:
            sys.stderr = previous
        self.assertEqual(len(drops), 1)
        self.assertEqual(buffer.getvalue(), '')
        self.assertEqual(sink.stats['dropped'], 1)
        self.assertEqual(sink.stats['failed'], 1)
        self.assertEqual(sink.stats['processed'], 0)

    def test_a_record_refused_by_an_open_breaker_is_a_retry(self):
        sink = self._sink(FailingTransport(100), maxRetries=0, breakerFailureThreshold=1, breakerResetTimeout=1000)
        buffer, previous = capture_stderr()
        try:
            self.assertEqual(sink.deliver(make_record()), RETRY)
            self.assertEqual(sink.deliver(make_record()), RETRY)      # now the breaker is open
        finally:
            sys.stderr = previous
        self.assertEqual(sink.stats['dropped'], 2)

    def test_a_record_that_goes_through_after_a_retry_is_delivered(self):
        transport = FailingTransport(1)
        sink = self._sink(transport, maxRetries=3)
        self.assertEqual(sink.deliver(make_record()), DELIVERED)
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(sink.stats['errors'], 1)

    def test_a_failing_callback_never_stops_the_answer(self):
        def explode(*arguments):
            raise RuntimeError('broken callback')

        sink = self._sink(FailingTransport(10), onDrop=explode, onError=explode)
        self.assertEqual(sink.deliver(make_record()), RETRY)


class TestFullSync(unittest.TestCase):

    def test_the_mode_is_accepted_and_checked(self):
        self.assertEqual(validate_flush_mode('fullsync'), 'fullsync')
        self.assertIn('fullsync', sinks_module.FLUSH_MODES)
        with self.assertRaises(ValueError):
            validate_flush_mode('fullsynch')

    def test_where_the_drive_cache_can_be_emptied_that_call_is_used(self):
        calls = []
        fake = mock.Mock()
        fake.fcntl = lambda descriptor, command: calls.append((descriptor, command))
        with mock.patch.object(sinks_module, '_FULLSYNC', 51), mock.patch.object(sinks_module, 'fcntl', fake), \
                mock.patch('os.fsync') as fsync:
            sync_descriptor(7, isFull=True)
        self.assertEqual(calls, [(7, 51)])
        fsync.assert_not_called()

    def test_without_that_call_plain_fsync_is_used(self):
        with mock.patch.object(sinks_module, '_FULLSYNC', None), mock.patch('os.fsync') as fsync:
            sync_descriptor(7, isFull=True)
        fsync.assert_called_once_with(7)

    def test_a_file_system_that_refuses_it_falls_back_to_fsync(self):
        def refuse(descriptor, command):
            raise OSError('not supported')

        fake = mock.Mock()
        fake.fcntl = refuse
        with mock.patch.object(sinks_module, '_FULLSYNC', 51), mock.patch.object(sinks_module, 'fcntl', fake), \
                mock.patch('os.fsync') as fsync:
            sync_descriptor(7, isFull=True)
        fsync.assert_called_once_with(7)

    def test_a_plain_fsync_never_uses_the_full_call(self):
        fake = mock.Mock()
        with mock.patch.object(sinks_module, '_FULLSYNC', 51), mock.patch.object(sinks_module, 'fcntl', fake), \
                mock.patch('os.fsync') as fsync:
            sync_descriptor(7)
        fsync.assert_called_once_with(7)
        fake.fcntl.assert_not_called()

    def test_the_sinks_write_with_it(self):
        with tempfile.TemporaryDirectory() as folder:
            sink = FileSink(os.path.join(folder, 'log'), flush='fullsync')
            self.assertEqual(sink.flushMode, 'fullsync')
            with mock.patch.object(sinks_module, 'sync_descriptor') as sync:
                sink.deliver(make_record())
            sync.assert_called_once()
            self.assertTrue(sync.call_args[0][1])
            sink.close()
            with open(os.path.join(folder, 'log_0.log'), encoding='utf-8') as stream:
                self.assertIn('hello', stream.read())

    def test_a_stream_without_a_descriptor_and_a_console_refuse_it(self):
        with self.assertRaises(ValueError):
            StreamSink(io.StringIO(), flush='fullsync')
        with self.assertRaises(ValueError):
            ConsoleSink(flush='fullsync')
        sink = StreamSink(io.StringIO())
        with self.assertRaises(ValueError):
            sink.set_flush_mode('fullsync')

    def test_a_real_file_works_with_every_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            for mode in (None, 'none', 'flush', 'fsync', 'fullsync'):
                with self.subTest(flush=mode):
                    sink = FileSink(os.path.join(folder, f'log-{mode}'), flush=mode)
                    self.assertEqual(sink.deliver(make_record()), DELIVERED)
                    sink.close()

    def test_a_spool_accepts_it(self):
        with tempfile.TemporaryDirectory() as folder:
            spool = Spool.create(os.path.join(folder, 'spools'), 'x', 'S', target_id('S', host='h'), 10 ** 6, 10 ** 7,
                                 flush='fullsync')
            try:
                with mock.patch('spool.sync_descriptor') as sync:
                    spool.append(make_record())
                    spool.sync()
                self.assertTrue(all(call.args[1] for call in sync.call_args_list))
                self.assertGreaterEqual(sync.call_count, 2)
            finally:
                spool.close()


class TestSpoolConfig(unittest.TestCase):

    REQUIRED = dict(path='/var/spool/app/siem', id='siem', maxBytes=1000, totalMaxBytes=5000)

    def test_the_defaults(self):
        config = SpoolConfig(**self.REQUIRED)
        self.assertEqual((config.policy, config.flush, config.ackEvery, config.ackInterval), ('drop_oldest', 'flush', 100, 1.0))
        self.assertEqual((config.maxAttempts, config.adoptOrphans, config.eventIdField, config.target),
                         (None, False, 'event_id', None))
        self.assertEqual((config.retryBackoffBase, config.retryBackoffMax, config.adoptInterval, config.adoptBatch),
                         (1.0, 60.0, 30.0, 100))

    def test_the_limits_have_no_default(self):
        for missing in ('path', 'id', 'maxBytes', 'totalMaxBytes'):
            arguments = {key: value for key, value in self.REQUIRED.items() if key != missing}
            with self.subTest(missing=missing):
                with self.assertRaises(TypeError):
                    SpoolConfig(**arguments)

    def test_a_dictionary_gives_the_same_settings(self):
        values = {**self.REQUIRED, 'policy': 'block', 'blockTimeout': 2.5, 'adoptOrphans': True, 'flush': 'fsync'}
        self.assertEqual(SpoolConfig.coerce(values), SpoolConfig(**values))

    def test_coerce_passes_a_config_and_none_through(self):
        config = SpoolConfig(**self.REQUIRED)
        self.assertIs(SpoolConfig.coerce(config), config)
        self.assertIsNone(SpoolConfig.coerce(None))

    def test_coerce_refuses_anything_else(self):
        for value in (42, 'path', ['path'], True):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    SpoolConfig.coerce(value)

    def test_an_unknown_key_is_named_and_the_valid_ones_are_listed(self):
        with self.assertRaises(TypeError) as caught:
            SpoolConfig.coerce({**self.REQUIRED, 'maxByte': 5, 'colour': 'red'})
        message = str(caught.exception)
        self.assertIn('colour', message)
        self.assertIn('maxByte', message)
        self.assertIn('totalMaxBytes', message)

    def test_a_path_object_is_accepted_and_kept_as_text(self):
        config = SpoolConfig(**{**self.REQUIRED, 'path': Path('/var/spool/app')})
        self.assertEqual(config.path, os.fspath(Path('/var/spool/app')))
        self.assertIsInstance(config.path, str)

    def test_none_means_no_flush_and_is_stored_as_the_word(self):
        self.assertEqual(SpoolConfig(**{**self.REQUIRED, 'flush': None}).flush, 'none')

    def test_every_wrong_value_is_found_when_the_object_is_made(self):
        bad = [({'path': ''}, TypeError), ({'path': 5}, TypeError), ({'id': ''}, TypeError), ({'id': None}, TypeError),
               ({'maxBytes': 0}, ValueError), ({'maxBytes': None}, TypeError), ({'maxBytes': 1.5}, TypeError),
               ({'maxBytes': True}, TypeError), ({'totalMaxBytes': -1}, ValueError), ({'segmentBytes': 0}, ValueError),
               ({'deadMaxBytes': 0}, ValueError), ({'ackEvery': 0}, ValueError), ({'adoptBatch': 0}, ValueError),
               ({'policy': 'drop'}, ValueError), ({'policy': None}, TypeError), ({'flush': 'always'}, ValueError),
               ({'blockTimeout': 0}, ValueError), ({'blockTimeout': 'soon'}, TypeError), ({'maxAge': -5}, ValueError),
               ({'ackInterval': 0}, ValueError), ({'retryBackoffBase': 0}, ValueError), ({'adoptInterval': 0}, ValueError),
               ({'retryBackoffBase': 10, 'retryBackoffMax': 5}, ValueError), ({'maxAttempts': 0}, ValueError),
               ({'maxAttempts': 2.5}, TypeError), ({'adoptOrphans': 1}, TypeError), ({'adoptOrphans': 'yes'}, TypeError),
               ({'target': ''}, TypeError), ({'target': 5}, TypeError), ({'eventIdField': ''}, TypeError),
               ({'eventIdField': 3}, TypeError)]
        for changes, error in bad:
            with self.subTest(changes=changes):
                with self.assertRaises(error):
                    SpoolConfig(**{**self.REQUIRED, **changes})

    def test_the_optional_values_can_be_switched_off_with_none(self):
        config = SpoolConfig(**{**self.REQUIRED, 'blockTimeout': None, 'maxAge': None, 'maxAttempts': None,
                                'eventIdField': None, 'target': None})
        self.assertIsNone(config.eventIdField)

    def test_the_settings_cannot_be_changed_afterwards(self):
        config = SpoolConfig(**self.REQUIRED)
        with self.assertRaises(FrozenInstanceError):
            config.maxBytes = 1
        with self.assertRaises(FrozenInstanceError):
            config.path = '/elsewhere'

    def test_equal_settings_are_equal_and_can_be_hashed(self):
        self.assertEqual(SpoolConfig(**self.REQUIRED), SpoolConfig(**self.REQUIRED))
        self.assertEqual(len({SpoolConfig(**self.REQUIRED), SpoolConfig(**self.REQUIRED)}), 1)


if __name__ == '__main__':
    unittest.main()
