"""Test suite for pysimplelog.contrib.siem (transport + sink + wiring).

Run from the repo root with:
    python3 -m pytest tests/test_siem_sink.py -v

Coverage map
------------
TestSeverityMap        -- name overrides + Informational default for unknown types
TestRFC5424Formatter   -- header shape, NILVALUE handling, SD escaping, newline collapse
TestCircuitBreaker      -- open/closed/probe transitions
TestSiemForwardSink     -- enqueue/deliver, drop-oldest overflow, retry+backoff, callbacks
TestAttachDetach        -- single-sink wiring against a real pysimplelog Logger
TestTCPSyslogTransport  -- RFC 6587 octet-counting against a local TCP server
TestUDPSyslogTransport  -- datagram delivery against a local UDP socket
TestHTTPTransport       -- POST body/headers against a local HTTP server
"""
import http.server
import io
import json
import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from SimpleLog import Logger  # noqa: E402
from contrib import siem_sink  # noqa: E402
from contrib import siem_transport  # noqa: E402


def make_logger(**kwargs):
    defaults = dict(name='test', logToFile=False, logToStdout=True)
    defaults.update(kwargs)
    buf = io.StringIO()
    defaults.setdefault('stdout', buf)
    return Logger(**defaults), buf


class _FakeTransport:
    """Records every payload handed to send(); can be told to fail on demand."""

    def __init__(self, fail_times=0):
        self.sent = []
        self.fail_times = fail_times
        self.closed = False

    def send(self, payload):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError('simulated failure')
        self.sent.append(payload)

    def close(self):
        self.closed = True


# ═══════════════════════════════════════════════════════════════════════════
# SeverityMap
# ═══════════════════════════════════════════════════════════════════════════

class TestSeverityMap(unittest.TestCase):

    def test_name_overrides(self):
        smap = siem_sink.SeverityMap()
        self.assertEqual(smap.resolve('debug', 0), 7)
        self.assertEqual(smap.resolve('INFO', 10), 6)   # case-insensitive
        self.assertEqual(smap.resolve('warn', 20), 4)
        self.assertEqual(smap.resolve('error', 30), 3)
        self.assertEqual(smap.resolve('critical', 100), 2)

    def test_unknown_type_defaults_to_informational(self):
        smap = siem_sink.SeverityMap()
        # no guessing from the numeric level -- always Informational unless overridden
        self.assertEqual(smap.resolve('my_custom_type', 5), 6)
        self.assertEqual(smap.resolve('my_custom_type', 500), 6)
        self.assertEqual(smap.resolve('my_custom_type', None), 6)

    def test_custom_overrides_win(self):
        smap = siem_sink.SeverityMap(overrides={'noisy': 7})
        self.assertEqual(smap.resolve('noisy', 100), 7)


# ═══════════════════════════════════════════════════════════════════════════
# RFC5424Formatter
# ═══════════════════════════════════════════════════════════════════════════

class TestRFC5424Formatter(unittest.TestCase):

    def test_basic_shape_and_pri(self):
        fmt = siem_sink.RFC5424Formatter(appName='myapp', facility=siem_sink.FACILITY_LOCAL0, hostname='host1')
        out = fmt.format('hello world', 'error', severity=3)
        # facility 16 * 8 + severity 3 == 131
        self.assertTrue(out.startswith('<131>1 '))
        self.assertIn(' host1 myapp ', out)
        self.assertTrue(out.endswith('hello world'))

    def test_nilvalue_when_structured_data_disabled(self):
        fmt = siem_sink.RFC5424Formatter(includeStructuredData=False)
        out = fmt.format('msg', 'info', 6)
        parts = out.split(' ')
        # PRI VERSION TS HOST APP PID MSGID SD MSG...
        self.assertEqual(parts[6], '-')

    def test_structured_data_escaping(self):
        fmt = siem_sink.RFC5424Formatter()
        out = fmt.format('msg', 'weird]type"with\\stuff', 5)
        self.assertIn('\\]', out)
        self.assertIn('\\"', out)
        self.assertIn('\\\\', out)

    def test_collapse_newlines_default(self):
        fmt = siem_sink.RFC5424Formatter()
        out = fmt.format('line1\nline2\r\nline3', 'error', 3)
        self.assertNotIn('\n', out)
        self.assertIn('line1\\nline2\\nline3', out)

    def test_preserve_newlines_when_disabled(self):
        fmt = siem_sink.RFC5424Formatter(collapseNewlines=False)
        out = fmt.format('line1\nline2', 'error', 3)
        self.assertIn('line1\nline2', out)

    def test_empty_hostname_falls_back_to_system_hostname(self):
        # An empty string means "use the system hostname", same as None.
        fmt = siem_sink.RFC5424Formatter(hostname='')
        self.assertEqual(fmt.hostname, socket.gethostname())

    def test_nil_safe_helper_handles_true_empties(self):
        self.assertEqual(siem_sink.RFC5424Formatter._nil_safe(''), '-')
        self.assertEqual(siem_sink.RFC5424Formatter._nil_safe(None), '-')
        self.assertEqual(siem_sink.RFC5424Formatter._nil_safe('host1'), 'host1')


# ═══════════════════════════════════════════════════════════════════════════
# CircuitBreaker
# ═══════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker(unittest.TestCase):

    def test_closed_by_default(self):
        cb = siem_sink.CircuitBreaker(failureThreshold=3, resetTimeout=10.0)
        self.assertTrue(cb.allow())

    def test_opens_after_threshold(self):
        cb = siem_sink.CircuitBreaker(failureThreshold=2, resetTimeout=10.0)
        cb.record_failure()
        self.assertTrue(cb.allow())
        cb.record_failure()
        self.assertFalse(cb.allow())

    def test_success_resets(self):
        cb = siem_sink.CircuitBreaker(failureThreshold=1, resetTimeout=10.0)
        cb.record_failure()
        self.assertFalse(cb.allow())
        cb.record_success()
        self.assertTrue(cb.allow())

    def test_probe_allowed_after_reset_timeout(self):
        cb = siem_sink.CircuitBreaker(failureThreshold=1, resetTimeout=0.05)
        cb.record_failure()
        self.assertFalse(cb.allow())
        time.sleep(0.08)
        self.assertTrue(cb.allow())


# ═══════════════════════════════════════════════════════════════════════════
# SiemForwardSink
# ═══════════════════════════════════════════════════════════════════════════

class TestSiemForwardSink(unittest.TestCase):
    """SiemForwardSink now delivers synchronously -- no internal queue or
    thread of its own. Non-blocking behaviour comes entirely from
    pysimplelog core's opt-in threaded=True sink support, which attach()
    turns on by default (see TestAttachDetach below, and the generic
    queue-overflow/no-leak coverage in test_logger.py).
    """

    def test_write_record_delivers_immediately(self):
        transport = _FakeTransport()
        sink = siem_sink.SiemForwardSink(transport)
        sink.write_record('boom\n', 'error', 30)
        self.assertEqual(len(transport.sent), 1)
        self.assertIn(b'boom', transport.sent[0])
        self.assertEqual(sink.stats['sent'], 1)

    def test_plain_write_fallback_defaults_to_informational(self):
        transport = _FakeTransport()
        sink = siem_sink.SiemForwardSink(transport)
        sink.write('no type info\n')   # base write() contract -- logType unknown
        self.assertIn(b'severity="6"', transport.sent[0])

    def test_retry_then_success(self):
        transport = _FakeTransport(fail_times=1)
        sink = siem_sink.SiemForwardSink(transport, retryBackoffBase=0.01, maxRetries=2,
                                          breakerFailureThreshold=5)
        sink.write_record('retry-me\n', 'warn', 20)
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(sink.stats['errors'], 1)
        self.assertEqual(sink.stats['sent'], 1)

    def test_on_drop_and_on_error_callbacks(self):
        transport = _FakeTransport(fail_times=99)
        dropped = []
        errors = []
        sink = siem_sink.SiemForwardSink(
            transport, retryBackoffBase=0.01, maxRetries=0,
            breakerFailureThreshold=99, onDrop=dropped.append,
            onError=lambda exc, item: errors.append((str(exc), item)),
        )
        sink.write_record('will-fail\n', 'error', 30)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(sink.stats['dropped'], 1)

    def test_context_manager_closes(self):
        transport = _FakeTransport()
        with siem_sink.SiemForwardSink(transport) as sink:
            sink.write_record('hi\n', 'debug', 0)
        self.assertTrue(transport.closed)


# ═══════════════════════════════════════════════════════════════════════════
# attach() / detach() against a real Logger
# ═══════════════════════════════════════════════════════════════════════════

class TestAttachDetach(unittest.TestCase):

    def test_attach_routes_only_selected_log_types(self):
        logger, _ = make_logger()
        transport = _FakeTransport()
        sink = siem_sink.attach(logger, transport,
                                 logTypeFlags={'error': True, 'critical': True},
                                 defaultFlag=False)
        try:
            logger.error('bad thing')
            logger.info('ignored, not selected')
            logger.flush(timeout=2.0)
            self.assertEqual(len(transport.sent), 1)
            self.assertIn(b'bad thing', transport.sent[0])
        finally:
            siem_sink.detach(logger, sink)

    def test_severity_matches_log_type(self):
        logger, _ = make_logger()
        transport = _FakeTransport()
        sink = siem_sink.attach(logger, transport)
        try:
            logger.critical('meltdown')
            logger.flush(timeout=2.0)
            # facility default LOCAL0 (16) * 8 + severity(critical)=2 -> 130
            self.assertTrue(transport.sent[0].startswith(b'<130>1 '))
        finally:
            siem_sink.detach(logger, sink)

    def test_attach_registers_a_single_sink(self):
        logger, _ = make_logger()
        transport = _FakeTransport()
        sink = siem_sink.attach(logger, transport)
        try:
            self.assertIn('siem', logger.sinks)
        finally:
            siem_sink.detach(logger, sink)

    def test_detach_removes_the_sink(self):
        logger, _ = make_logger()
        transport = _FakeTransport()
        sink = siem_sink.attach(logger, transport)
        siem_sink.detach(logger, sink)
        self.assertNotIn('siem', logger.sinks)
        # re-attaching under the same name must not raise "already registered"
        sink2 = siem_sink.attach(logger, _FakeTransport())
        siem_sink.detach(logger, sink2)

    def test_new_log_type_added_after_attach_is_excluded_by_default(self):
        logger, _ = make_logger()
        transport = _FakeTransport()
        sink = siem_sink.attach(logger, transport,
                                 logTypeFlags={'error': True}, defaultFlag=False)
        try:
            logger.add_log_type('shiny_new_type', name='SHINY', level=42)
            logger.log('shiny_new_type', 'should stay out')
            logger.error('should get through')
            logger.flush(timeout=2.0)
            self.assertEqual(len(transport.sent), 1)
            self.assertIn(b'should get through', transport.sent[0])
        finally:
            siem_sink.detach(logger, sink)


    def test_attach_defaults_to_threaded(self):
        logger, _ = make_logger()
        transport = _FakeTransport()
        sink = siem_sink.attach(logger, transport)
        try:
            self.assertTrue(logger.sinks['siem'].threaded)
        finally:
            siem_sink.detach(logger, sink)


# ═══════════════════════════════════════════════════════════════════════════
# TCPSyslogTransport
# ═══════════════════════════════════════════════════════════════════════════

class TestTCPSyslogTransport(unittest.TestCase):

    def _start_echo_server(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(('127.0.0.1', 0))
        server_sock.listen(1)
        received = []
        ready = threading.Event()

        def _accept_once():
            ready.set()
            conn, _ = server_sock.accept()
            with conn:
                conn.settimeout(2.0)
                data = b''
                try:
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                except socket.timeout:
                    pass
                received.append(data)

        thread = threading.Thread(target=_accept_once, daemon=True)
        thread.start()
        ready.wait(timeout=2.0)
        port = server_sock.getsockname()[1]
        return server_sock, thread, received, port

    def test_octet_counting_framing(self):
        server_sock, thread, received, port = self._start_echo_server()
        try:
            transport = siem_transport.TCPSyslogTransport('127.0.0.1', port)
            payload = b'<130>1 2024-01-01T00:00:00.000Z host app 123 MSGID - hello'
            transport.send(payload)
            transport.close()
            thread.join(timeout=2.0)
            expected_prefix = ('%d ' % len(payload)).encode('ascii')
            self.assertEqual(received[0], expected_prefix + payload)
        finally:
            server_sock.close()


# ═══════════════════════════════════════════════════════════════════════════
# UDPSyslogTransport
# ═══════════════════════════════════════════════════════════════════════════

class TestUDPSyslogTransport(unittest.TestCase):

    def test_datagram_delivery(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_sock.bind(('127.0.0.1', 0))
        server_sock.settimeout(2.0)
        port = server_sock.getsockname()[1]
        try:
            transport = siem_transport.UDPSyslogTransport('127.0.0.1', port)
            transport.send(b'<134>1 msg')
            data, _ = server_sock.recvfrom(4096)
            self.assertEqual(data, b'<134>1 msg')
            transport.close()
        finally:
            server_sock.close()


# ═══════════════════════════════════════════════════════════════════════════
# HTTPTransport
# ═══════════════════════════════════════════════════════════════════════════

class _CapturingHandler(http.server.BaseHTTPRequestHandler):
    captured = []

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        _CapturingHandler.captured.append((dict(self.headers), body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # silence test output


class TestHTTPTransport(unittest.TestCase):

    def setUp(self):
        _CapturingHandler.captured = []
        self.server = http.server.HTTPServer(('127.0.0.1', 0), _CapturingHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2.0)
        self.server.server_close()

    def test_default_json_envelope(self):
        transport = siem_transport.HTTPTransport('http://127.0.0.1:%d/collect' % self.port)
        transport.send(b'<134>1 hello')
        headers, body = _CapturingHandler.captured[0]
        self.assertEqual(json.loads(body), {'event': '<134>1 hello'})

    def test_splunk_hec_helpers(self):
        headers = siem_transport.splunk_hec_headers('SECRET-TOKEN')
        builder = siem_transport.splunk_hec_payload_builder(sourcetype='pysimplelog', index='main')
        transport = siem_transport.HTTPTransport(
            'http://127.0.0.1:%d/services/collector/event' % self.port,
            headers=headers, payloadBuilder=builder,
        )
        transport.send(b'<134>1 hello')
        sent_headers, body = _CapturingHandler.captured[0]
        self.assertEqual(sent_headers['Authorization'], 'Splunk SECRET-TOKEN')
        payload = json.loads(body)
        self.assertEqual(payload['sourcetype'], 'pysimplelog')
        self.assertEqual(payload['index'], 'main')


# ═══════════════════════════════════════════════════════════════════════════
# ConsoleTransport
# ═══════════════════════════════════════════════════════════════════════════

class TestConsoleTransport(unittest.TestCase):

    def test_prints_decoded_payload_with_prefix(self):
        buf = io.StringIO()
        transport = siem_transport.ConsoleTransport(stream=buf, prefix='[TEST] ')
        transport.send(b'<134>1 hello world')
        self.assertEqual(buf.getvalue(), '[TEST] <134>1 hello world\n')

    def test_default_prefix(self):
        buf = io.StringIO()
        transport = siem_transport.ConsoleTransport(stream=buf)
        transport.send(b'msg')
        self.assertTrue(buf.getvalue().startswith('[SIEM] '))

    def test_default_stream_is_stdout(self):
        transport = siem_transport.ConsoleTransport()
        self.assertIs(transport.stream, sys.stdout)

    def test_close_is_a_harmless_noop(self):
        buf = io.StringIO()
        transport = siem_transport.ConsoleTransport(stream=buf)
        transport.close()   # must not raise, must not touch buf
        self.assertFalse(buf.closed)

    def test_never_raises_so_it_never_trips_the_circuit_breaker(self):
        buf = io.StringIO()
        sink = siem_sink.SiemForwardSink(siem_transport.ConsoleTransport(stream=buf))
        for _ in range(10):
            sink.write_record('steady stream\n', 'info', 10)
        self.assertEqual(sink.stats['sent'], 10)
        self.assertEqual(sink.stats['errors'], 0)

    def test_end_to_end_through_attach(self):
        logger, _ = make_logger()
        buf = io.StringIO()
        transport = siem_transport.ConsoleTransport(stream=buf)
        sink = siem_sink.attach(logger, transport)
        try:
            logger.error('boom')
            logger.flush(timeout=2.0)
            self.assertIn('boom', buf.getvalue())
            self.assertIn('[SIEM] ', buf.getvalue())
        finally:
            siem_sink.detach(logger, sink)

    def test_quick_attach_console_protocol(self):
        logger, _ = make_logger()
        buf = io.StringIO()
        sink = siem_sink.quick_attach(logger, protocol='console', stream=buf)
        try:
            logger.error('via quick_attach')
            logger.flush(timeout=2.0)
            self.assertIn('via quick_attach', buf.getvalue())
        finally:
            siem_sink.detach(logger, sink)

    def test_swapping_transport_requires_no_other_change(self):
        """Same attach() call, only the transport instance differs."""
        logger, _ = make_logger()
        buf = io.StringIO()
        devTransport = siem_transport.ConsoleTransport(stream=buf)
        prodTransport = _FakeTransport()

        for transport in (devTransport, prodTransport):
            sink = siem_sink.attach(logger, transport)
            try:
                logger.error('same call, different transport')
                logger.flush(timeout=2.0)
            finally:
                siem_sink.detach(logger, sink)

        self.assertIn('same call, different transport', buf.getvalue())
        self.assertEqual(len(prodTransport.sent), 1)


if __name__ == '__main__':
    unittest.main()
