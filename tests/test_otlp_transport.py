"""Tests of the OTLP/HTTP transport against a small fake receiver that runs in a thread of the test.

The receiver answers what each test scripts, and keeps every request it gets. TLS tests make a certificate with the ``openssl`` command
and are skipped where it is missing. The tests of the official protobuf parser are skipped when its packages are not installed.

Run from the repo root::

    python3 -m unittest tests.test_otlp_transport -v
"""
import contextlib
import gzip
import io
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from __pkginfo__ import __version__  # noqa: E402
from contrib import otlp_transport  # noqa: E402
from contrib.otlp_transport import (OtlpHttpTransport, OtlpResponse, OK, RETRY, REFUSED, ERROR, MAX_RETRY_AFTER,  # noqa: E402
                                    MAX_RESPONSE_BYTES, parse_retry_after)

IS_POSIX = os.name == 'posix'
BODY = b'{"resourceLogs":[]}'


class Answer:
    """What the fake receiver does with one request."""

    def __init__(self, status=200, body=b'{}', headers=None, contentType='application/json', delay=0.0, hang=False, drop=False,
                 garbage=None, closeSilently=False, closeHeader=False, shortBody=False):
        self.status, self.body, self.headers, self.contentType = status, body, dict(headers or {}), contentType
        self.delay, self.hang, self.drop, self.garbage = delay, hang, drop, garbage
        self.closeSilently, self.closeHeader, self.shortBody = closeSilently, closeHeader, shortBody


class FakeReceiver:
    """
    An OTLP/HTTP receiver. ``script`` is a list of Answer objects used in order, and an item can be a function of the request that
    returns an Answer. When the script is empty ``rule``, if set, is called with the request and returns an Answer, and otherwise
    every request gets a plain 200.
    """

    def __init__(self, context=None, port=0):
        self.requests = []
        self.script = []
        self.rule = None
        self.connections = 0
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def setup(self):
                super().setup()
                with receiver.lock:
                    receiver.connections += 1

            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(length)
                headers = {key.lower(): value for key, value in self.headers.items()}
                body = gzip.decompress(raw) if headers.get('content-encoding') == 'gzip' else raw
                with receiver.lock:
                    request = {'method': self.command, 'path': self.path, 'headers': headers, 'raw': raw, 'body': body}
                    receiver.requests.append(request)
                    choice = receiver.script.pop(0) if receiver.script else receiver.rule
                    answer = choice(request) if callable(choice) else choice
                    if answer is None:
                        answer = Answer()
                if answer.delay:
                    receiver.stopped.wait(answer.delay)
                if answer.hang:
                    receiver.stopped.wait(60)
                    self.close_connection = True
                    return
                if answer.drop:
                    self.close_connection = True
                    return
                if answer.garbage is not None:
                    self.wfile.write(answer.garbage)
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.send_response(answer.status)
                self.send_header('Content-Type', answer.contentType)
                self.send_header('Content-Length', str(len(answer.body) + (1000 if answer.shortBody else 0)))
                for key, value in answer.headers.items():
                    self.send_header(key, value)
                if answer.closeHeader:
                    self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(answer.body)
                self.wfile.flush()
                if answer.closeHeader or answer.closeSilently or answer.shortBody:
                    self.close_connection = True

            def log_message(self, *arguments):
                pass

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                # A client that does not trust the certificate closes the connection, which is the point of some tests
                pass

        self.server = Server(('127.0.0.1', port), Handler)
        if context is not None:
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        self.scheme = 'http' if context is None else 'https'
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"{self.scheme}://127.0.0.1:{self.port}"

    def stop(self):
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()

    def count(self):
        with self.lock:
            return len(self.requests)


class ReceiverCase(unittest.TestCase):

    def setUp(self):
        self.receiver = FakeReceiver()
        self.addCleanup(self.receiver.stop)
        self.transports = []
        self.addCleanup(self._close_transports)

    def _close_transports(self):
        for transport in self.transports:
            transport.close()

    def make(self, receiver=None, **settings):
        transport = OtlpHttpTransport((receiver or self.receiver).url, **settings)
        self.transports.append(transport)
        return transport

    def send(self, answer=None, transport=None, body=BODY):
        if answer is not None:
            self.receiver.script.append(answer)
        return (transport or self.make()).send(body)


class TestSettings(unittest.TestCase):

    def test_the_address_the_requests_go_to(self):
        cases = {'http://localhost:4318': 'http://localhost:4318/v1/logs', 'https://Collector.Example.ORG:4318/': 'https://collector.example.org:4318/v1/logs',
                 'https://collector.example.org': 'https://collector.example.org:443/v1/logs',
                 'http://collector.example.org': 'http://collector.example.org:80/v1/logs',
                 'https://collector.example.org:4318/otel': 'https://collector.example.org:4318/otel/v1/logs',
                 'https://collector.example.org:4318/otel/': 'https://collector.example.org:4318/otel/v1/logs',
                 'https://collector.example.org:4318//': 'https://collector.example.org:4318/v1/logs',
                 '  http://localhost:4318  ': 'http://localhost:4318/v1/logs', 'http://[::1]:4318': 'http://[::1]:4318/v1/logs',
                 'http://127.0.0.1:1': 'http://127.0.0.1:1/v1/logs'}
        for endpoint, expected in cases.items():
            with self.subTest(endpoint=endpoint):
                self.assertEqual(OtlpHttpTransport(endpoint).url, expected)

    def test_wrong_endpoints_are_refused(self):
        for endpoint in ('', 'localhost:4318', '//localhost:4318', 'ftp://localhost', 'http://', 'https:///v1/logs',
                         'http://user:secret@localhost:4318', 'http://user@localhost', 'http://localhost:4318?token=x',
                         'http://localhost:4318/#fragment', 'http://localhost:notaport', 'http://localhost:99999', 'file:///etc/passwd'):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    OtlpHttpTransport(endpoint)

    def test_the_secret_of_a_refused_endpoint_is_not_in_the_message(self):
        with self.assertRaises(ValueError) as caught:
            OtlpHttpTransport('http://user:secret-password@localhost:4318')
        self.assertNotIn('secret-password', str(caught.exception))

    def test_an_endpoint_that_is_not_text_is_refused(self):
        for bad in (None, 4318, b'http://localhost', ['http://localhost']):
            with self.assertRaises(TypeError):
                OtlpHttpTransport(bad)

    def test_the_timeout(self):
        self.assertEqual(OtlpHttpTransport('http://localhost:1', timeout=3).url, 'http://localhost:1/v1/logs')
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                OtlpHttpTransport('http://localhost:1', timeout=bad)
        for bad in ('5', None, True):
            with self.assertRaises(TypeError):
                OtlpHttpTransport('http://localhost:1', timeout=bad)

    def test_compress_must_be_a_boolean(self):
        for bad in (1, 'yes', None):
            with self.assertRaises(TypeError):
                OtlpHttpTransport('http://localhost:1', compress=bad)

    def test_the_ssl_context_must_be_one(self):
        for bad in ('ctx', True, object()):
            with self.assertRaises(TypeError):
                OtlpHttpTransport('https://localhost:1', sslContext=bad)

    def test_headers_must_be_a_dictionary_of_text(self):
        for bad in ([('a', 'b')], 'a: b', 5):
            with self.assertRaises(TypeError):
                OtlpHttpTransport('http://localhost:1', headers=bad)
        for bad in ({1: 'a'}, {'a': 1}, {'a': None}, {b'a': 'b'}):
            with self.assertRaises(TypeError):
                OtlpHttpTransport('http://localhost:1', headers=bad)

    def test_headers_with_a_line_break_or_a_bad_name_are_refused(self):
        for headers in ({'X-A': 'one\\ntwo'.replace('\\n', '\n')}, {'X-A': 'one\r\nInjected: yes'}, {'X\nA': 'v'}, {'X A': 'v'},
                        {'X:A': 'v'}, {'': 'v'}, {'X-é': 'v'}, {'X-A': 'caf☃'}):
            with self.subTest(headers=headers):
                with self.assertRaises(ValueError):
                    OtlpHttpTransport('http://localhost:1', headers=headers)

    def test_the_headers_the_transport_sets_cannot_be_given_in_any_case(self):
        for name in ('Content-Type', 'content-type', 'CONTENT-ENCODING', 'Content-Length', 'Host', 'host', 'Connection', 'Transfer-Encoding'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    OtlpHttpTransport('http://localhost:1', headers={name: 'x'})

    def test_a_header_with_latin_1_characters_is_accepted(self):
        OtlpHttpTransport('http://localhost:1', headers={'X-Name': 'café'})

    def test_the_destination_is_the_address_without_the_headers(self):
        transport = OtlpHttpTransport('https://Collector.example.org:4318/otel', headers={'Authorization': 'Bearer secret-token'})
        self.assertEqual(transport.describe_destination(), {'protocol': 'https', 'host': 'collector.example.org', 'port': 4318,
                                                            'path': '/otel/v1/logs'})

    def test_two_tokens_make_the_same_destination_and_two_ports_do_not(self):
        first = OtlpHttpTransport('http://localhost:4318', headers={'Authorization': 'one'})
        second = OtlpHttpTransport('http://localhost:4318', headers={'Authorization': 'two'})
        third = OtlpHttpTransport('http://localhost:4319', headers={'Authorization': 'one'})
        self.assertEqual(first.describe_destination(), second.describe_destination())
        self.assertNotEqual(first.describe_destination(), third.describe_destination())

    def test_the_token_is_in_no_text_of_the_transport(self):
        transport = OtlpHttpTransport('http://localhost:4318', headers={'Authorization': 'Bearer secret-token'})
        for text in (repr(transport), str(transport), str(transport.describe_destination()), transport.url):
            self.assertNotIn('secret-token', text)

    def test_credentials_in_clear_text_to_another_machine_warn_once(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            OtlpHttpTransport('http://collector.example.org:4318', headers={'authorization': 'x'})
        self.assertEqual(error.getvalue().count('WARNING'), 1)
        self.assertIn('clear text', error.getvalue())
        self.assertNotIn('x\n', error.getvalue().replace('WARNING', ''))

    def test_no_warning_when_nothing_is_wrong(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            OtlpHttpTransport('https://collector.example.org', headers={'Authorization': 'x'})
            OtlpHttpTransport('http://collector.example.org')
            OtlpHttpTransport('http://collector.example.org', headers={'X-Other': 'x'})
            for host in ('localhost', '127.0.0.1', '[::1]', 'api.localhost', '127.9.9.9'):
                OtlpHttpTransport(f'http://{host}:4318', headers={'Authorization': 'x'})
        self.assertEqual(error.getvalue(), '')

    def test_the_body_must_be_bytes(self):
        transport = OtlpHttpTransport('http://127.0.0.1:1')
        for bad in ('{}', None, 5, ['a']):
            with self.assertRaises(TypeError):
                transport.send(bad)


class TestRetryAfter(unittest.TestCase):

    def test_seconds(self):
        self.assertEqual((parse_retry_after('7'), parse_retry_after(' 7 '), parse_retry_after('0'), parse_retry_after('2.5')), (7.0, 7.0, 0.0, 2.5))

    def test_a_negative_wait_is_zero_and_a_huge_one_is_cut(self):
        self.assertEqual((parse_retry_after('-5'), parse_retry_after('99999'), parse_retry_after('1e9')), (0.0, MAX_RETRY_AFTER, MAX_RETRY_AFTER))

    def test_what_is_not_a_wait_is_none(self):
        for value in (None, '', 'soon', 'inf', '-inf', 'nan', '1 2', 'Tomorrow'):
            self.assertIsNone(parse_retry_after(value), value)

    def test_an_http_date(self):
        self.assertEqual(parse_retry_after('Thu, 01 Jan 2026 00:00:30 GMT', now=1767225600.0), 30.0)
        self.assertEqual(parse_retry_after('Thu, 01 Jan 2026 00:00:00 GMT', now=1767225700.0), 0.0)
        self.assertEqual(parse_retry_after('Thu, 01 Jan 2026 02:00:00 GMT', now=1767225600.0), MAX_RETRY_AFTER)

    def test_an_http_date_in_a_zone_and_one_without_a_zone_mean_the_same_instant(self):
        now = 1767225600.0
        self.assertEqual(parse_retry_after('Thu, 01 Jan 2026 00:00:30 +0000', now=now), 30.0)
        self.assertEqual(parse_retry_after('Thu, 01 Jan 2026 00:00:30 -0000', now=now), 30.0)
        self.assertEqual(parse_retry_after('Thu, 01 Jan 2026 01:00:30 +0100', now=now), 30.0)

    def test_a_date_in_the_future_uses_the_clock(self):
        value = parse_retry_after('Fri, 01 Jan 2100 00:00:00 GMT')
        self.assertEqual(value, MAX_RETRY_AFTER)


class TestRequest(ReceiverCase):

    def test_the_request(self):
        self.assertEqual(self.send(), OtlpResponse(OK, 200))
        request = self.receiver.requests[0]
        self.assertEqual((request['method'], request['path']), ('POST', '/v1/logs'))
        self.assertEqual(request['headers']['content-type'], 'application/json')
        self.assertEqual(request['headers']['user-agent'], f'pysimplelog/{__version__}')
        self.assertEqual(request['headers']['content-length'], str(len(BODY)))
        self.assertNotIn('content-encoding', request['headers'])
        self.assertEqual(request['body'], BODY)

    def test_the_path_follows_the_prefix_of_the_endpoint(self):
        transport = OtlpHttpTransport(self.receiver.url + '/otel/', timeout=5)
        self.transports.append(transport)
        transport.send(BODY)
        self.assertEqual(self.receiver.requests[0]['path'], '/otel/v1/logs')

    def test_the_headers_given_are_sent(self):
        self.send(transport=self.make(headers={'Authorization': 'Bearer abc', 'X-Scope-OrgID': 'tenant-1'}))
        headers = self.receiver.requests[0]['headers']
        self.assertEqual((headers['authorization'], headers['x-scope-orgid']), ('Bearer abc', 'tenant-1'))

    def test_a_header_can_replace_the_user_agent(self):
        self.send(transport=self.make(headers={'User-Agent': 'mine/1'}))
        self.assertEqual(self.receiver.requests[0]['headers']['user-agent'], 'mine/1')

    def test_gzip(self):
        body = b'{"a":"' + b'x' * 20000 + b'"}'
        self.send(transport=self.make(compress=True), body=body)
        request = self.receiver.requests[0]
        self.assertEqual(request['headers']['content-encoding'], 'gzip')
        self.assertEqual(request['headers']['content-type'], 'application/json')
        self.assertEqual(request['body'], body)
        self.assertLess(len(request['raw']), len(body) // 10)
        self.assertEqual(request['headers']['content-length'], str(len(request['raw'])))

    def test_the_same_body_gives_the_same_compressed_bytes(self):
        transport = self.make(compress=True)
        transport.send(BODY * 50)
        transport.send(BODY * 50)
        self.assertEqual(self.receiver.requests[0]['raw'], self.receiver.requests[1]['raw'])
        # The time of the file is part of the gzip header, bytes 4 to 8, and it is left at zero
        self.assertEqual(self.receiver.requests[0]['raw'][4:8], b'\x00\x00\x00\x00')

    def test_a_large_body(self):
        body = b'[' + b','.join(b'"%d"' % number for number in range(600000)) + b']'
        self.assertGreater(len(body), 4 * 1024 ** 2)
        for compress in (False, True):
            self.assertEqual(self.send(transport=self.make(compress=compress), body=body).outcome, OK)
            self.assertEqual(self.receiver.requests[-1]['body'], body)

    def test_an_empty_body_is_sent(self):
        self.assertEqual(self.send(body=b'').outcome, OK)
        self.assertEqual(self.receiver.requests[0]['body'], b'')

    def test_a_bytearray_is_accepted(self):
        self.assertEqual(self.send(body=bytearray(BODY)).outcome, OK)
        self.assertEqual(self.receiver.requests[0]['body'], BODY)

    def test_every_send_is_one_request(self):
        transport = self.make()
        for _ in range(7):
            transport.send(BODY)
        self.assertEqual(self.receiver.count(), 7)


class TestAnswers(ReceiverCase):

    def test_every_status_has_its_outcome(self):
        expected = {200: OK, 201: OK, 202: OK, 204: OK, 299: OK,
                    429: RETRY, 502: RETRY, 503: RETRY, 504: RETRY,
                    400: REFUSED, 413: REFUSED, 422: REFUSED,
                    301: ERROR, 302: ERROR, 307: ERROR, 401: ERROR, 403: ERROR, 404: ERROR, 405: ERROR, 408: ERROR, 415: ERROR,
                    500: ERROR, 501: ERROR, 505: ERROR}
        transport = self.make()
        for status, outcome in expected.items():
            with self.subTest(status=status):
                self.receiver.script.append(Answer(status=status, body=b'' if status in (204,) else b'{}'))
                response = transport.send(BODY)
                self.assertEqual((response.outcome, response.status), (outcome, status))

    def test_a_redirect_is_not_followed(self):
        other = FakeReceiver()
        self.addCleanup(other.stop)
        response = self.send(Answer(status=307, headers={'Location': other.url + '/v1/logs'}))
        self.assertEqual(response.outcome, ERROR)
        self.assertEqual(other.count(), 0)

    def test_the_wait_asked_for_is_given_for_a_retry_only(self):
        response = self.send(Answer(status=503, headers={'Retry-After': '7'}))
        self.assertEqual((response.outcome, response.retryAfter), (RETRY, 7.0))
        response = self.send(Answer(status=429, headers={'Retry-After': '0'}))
        self.assertEqual(response.retryAfter, 0.0)
        response = self.send(Answer(status=503))
        self.assertIsNone(response.retryAfter)
        for status in (200, 400, 404):
            response = self.send(Answer(status=status, headers={'Retry-After': '30'}))
            self.assertIsNone(response.retryAfter, status)

    def test_the_wait_is_cut_and_a_bad_one_is_ignored(self):
        self.assertEqual(self.send(Answer(status=503, headers={'Retry-After': '100000'})).retryAfter, MAX_RETRY_AFTER)
        self.assertIsNone(self.send(Answer(status=503, headers={'Retry-After': 'later'})).retryAfter)
        self.assertEqual(self.send(Answer(status=503, headers={'Retry-After': 'Fri, 01 Jan 2100 00:00:00 GMT'})).retryAfter, MAX_RETRY_AFTER)

    def test_a_partial_success_counts_the_refused_records(self):
        body = json.dumps({'partialSuccess': {'rejectedLogRecords': '5', 'errorMessage': 'too old'}}).encode()
        response = self.send(Answer(body=body))
        self.assertEqual(response, OtlpResponse(OK, 200, None, 5, 'too old'))

    def test_the_count_can_be_a_number_or_text(self):
        for value, expected in (('12', 12), (12, 12), ('0', 0), (0, 0), (None, 0), ('', 0), (-3, 0), ('-3', 0)):
            body = json.dumps({'partialSuccess': {'rejectedLogRecords': value}}).encode()
            self.assertEqual(self.send(Answer(body=body)).rejected, expected, value)

    def test_a_message_without_a_count_is_kept_and_no_record_is_counted(self):
        body = json.dumps({'partialSuccess': {'errorMessage': 'a warning'}}).encode()
        response = self.send(Answer(body=body))
        self.assertEqual((response.outcome, response.rejected, response.message), (OK, 0, 'a warning'))

    def test_the_message_is_one_short_line(self):
        body = json.dumps({'partialSuccess': {'rejectedLogRecords': 1, 'errorMessage': 'line one\nline two\r\n\tforged WARNING ' + 'x' * 1000}}).encode()
        message = self.send(Answer(body=body)).message
        self.assertNotIn('\n', message)
        self.assertNotIn('\r', message)
        self.assertNotIn('\t', message)
        self.assertLessEqual(len(message), 200)
        self.assertTrue(message.startswith('line one line two forged WARNING'))
        self.assertTrue(message.endswith('...'))

    def test_what_is_not_a_partial_success_is_a_plain_success(self):
        for body in (b'', b'{}', b'not json', b'[]', b'null', b'{"partialSuccess": null}', b'{"partialSuccess": 5}', b'{"partialSuccess": []}',
                     b'\xff\xfe\x00', b'{"partialSuccess": {"rejectedLogRecords": {"a": 1}}}',
                     b'{"partialSuccess": {"rejectedLogRecords": "many"}}', b'{"partialSuccess": {"errorMessage": 5}}'):
            with self.subTest(body=body):
                response = self.send(Answer(body=body))
                self.assertEqual((response.outcome, response.status, response.rejected), (OK, 200, 0))

    def test_an_answer_in_protobuf_is_a_success(self):
        response = self.send(Answer(body=b'\x0a\x04\x08\x05\x12\x00', contentType='application/x-protobuf'))
        self.assertEqual((response.outcome, response.rejected), (OK, 0))

    def test_a_failure_with_a_body_does_not_put_the_body_in_the_result(self):
        response = self.send(Answer(status=400, body=b'{"message": "internal path /srv/secret-place"}'))
        self.assertEqual(response.outcome, REFUSED)
        self.assertNotIn('secret-place', repr(response))

    def test_a_very_long_answer_is_cut_and_the_connection_is_not_reused(self):
        transport = self.make()
        response = transport.send(BODY) if self.receiver.script.append(Answer(body=b'{"partialSuccess": {"rejectedLogRecords": 1}}' + b' ' * (MAX_RESPONSE_BYTES * 2))) is None else None
        self.assertEqual(response.outcome, OK)
        self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual(self.receiver.connections, 2)

    def test_an_error_is_a_value_and_never_an_exception(self):
        transport = self.make()
        for answer in (Answer(status=500), Answer(status=404), Answer(drop=True), Answer(garbage=b'NOT HTTP AT ALL\r\n\r\n'),
                       Answer(shortBody=True), Answer(status=503, headers={'Retry-After': '\x00bad'})):
            self.receiver.script.append(answer)
            self.assertIsInstance(transport.send(BODY), OtlpResponse)


class TestConnection(ReceiverCase):

    def test_one_connection_serves_many_requests(self):
        transport = self.make()
        for _ in range(20):
            self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual((self.receiver.count(), self.receiver.connections), (20, 1))

    def test_a_receiver_that_says_connection_close_gets_a_new_connection_next_time(self):
        transport = self.make()
        self.receiver.script.append(Answer(closeHeader=True))
        self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual(self.receiver.connections, 2)

    def test_a_connection_the_receiver_closed_without_saying_is_replaced_at_once(self):
        transport = self.make()
        self.receiver.script.append(Answer(closeSilently=True))
        self.assertEqual(transport.send(BODY).outcome, OK)
        response = transport.send(BODY)
        self.assertEqual(response.outcome, OK)
        self.assertEqual((self.receiver.count(), self.receiver.connections), (2, 2))

    def test_a_receiver_that_drops_every_request_is_tried_once_on_a_fresh_connection(self):
        transport = self.make()
        self.receiver.script.extend([Answer(drop=True)] * 10)
        response = transport.send(BODY)
        self.assertEqual(response.outcome, RETRY)
        self.assertIn(response.message, ('RemoteDisconnected', 'ConnectionResetError', 'BrokenPipeError'))
        self.assertEqual(self.receiver.count(), 1)

    def test_a_dropped_request_on_a_reused_connection_is_sent_again_once_and_not_more(self):
        transport = self.make()
        transport.send(BODY)
        self.receiver.script.extend([Answer(drop=True)] * 10)
        response = transport.send(BODY)
        self.assertEqual(response.outcome, RETRY)
        self.assertEqual(self.receiver.count(), 3)

    def test_a_refused_connection_is_a_retry_and_the_next_send_connects_again(self):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        # Windows reports a refused connection only after about 2 seconds, so the timeout must be longer
        transport = OtlpHttpTransport(f'http://127.0.0.1:{port}', timeout=5)
        self.transports.append(transport)
        response = transport.send(BODY)
        self.assertEqual((response.outcome, response.status, response.message), (RETRY, None, 'ConnectionRefusedError'))
        self.assertEqual(transport.send(BODY).outcome, RETRY)

    def test_a_receiver_that_never_answers_ends_at_the_timeout(self):
        transport = self.make(timeout=0.4)
        self.receiver.script.append(Answer(hang=True))
        started = time.monotonic()
        response = transport.send(BODY)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(response.outcome, RETRY)
        self.assertIn(response.message, ('TimeoutError', 'timeout'))
        self.assertEqual(transport.send(BODY).outcome, OK)

    def test_a_slow_receiver_that_answers_in_time_is_a_success(self):
        transport = self.make(timeout=3)
        self.receiver.script.append(Answer(delay=0.3))
        self.assertEqual(transport.send(BODY).outcome, OK)

    def test_an_answer_that_is_not_http_is_a_retry(self):
        response = self.send(Answer(garbage=b'NOT HTTP AT ALL\r\n\r\n'))
        self.assertEqual(response.outcome, RETRY)
        self.assertEqual(response.message, 'BadStatusLine')

    def test_an_answer_cut_short_keeps_the_meaning_of_its_status(self):
        # The status line was sent after the receiver handled the request, so a body that ends early changes nothing
        transport = self.make()
        self.assertEqual(self.send(Answer(status=200, body=b'{}', shortBody=True), transport=transport).outcome, OK)
        self.assertEqual(self.send(Answer(status=503, body=b'{}', shortBody=True), transport=transport).outcome, RETRY)
        self.assertEqual(self.send(Answer(status=400, body=b'{}', shortBody=True), transport=transport).outcome, REFUSED)
        self.assertEqual(self.send(transport=transport).outcome, OK)

    def test_a_connection_whose_answer_was_cut_short_is_not_kept(self):
        transport = self.make()
        self.assertEqual(self.send(Answer(status=200, body=b'{}', shortBody=True), transport=transport).outcome, OK)
        self.assertIsNone(transport._OtlpHttpTransport__connection)
        self.assertEqual(self.send(transport=transport).outcome, OK)
        self.assertIsNotNone(transport._OtlpHttpTransport__connection)

    def test_the_message_of_a_failure_is_the_class_of_the_error_only(self):
        transport = OtlpHttpTransport('http://user-visible-host.invalid:4318', timeout=2)
        response = transport.send(BODY)
        self.assertEqual(response.outcome, RETRY)
        self.assertNotIn('user-visible-host', response.message)

    def test_close_is_idempotent_and_a_send_after_it_does_not_try(self):
        transport = self.make()
        transport.send(BODY)
        transport.close()
        transport.close()
        self.assertEqual(transport.send(BODY), OtlpResponse(RETRY, message='closed'))
        self.assertEqual(self.receiver.count(), 1)

    def test_closing_a_transport_that_never_connected(self):
        self.make().close()

    def test_many_threads_share_one_connection(self):
        transport = self.make()
        outcomes, lock = [], threading.Lock()

        def work():
            for _ in range(25):
                response = transport.send(BODY)
                with lock:
                    outcomes.append(response.outcome)
        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(outcomes, [OK] * 200)
        self.assertEqual((self.receiver.count(), self.receiver.connections), (200, 1))

    def test_close_from_another_thread_while_sending(self):
        transport = self.make(timeout=5)
        self.receiver.script.append(Answer(delay=0.3))
        results = []
        thread = threading.Thread(target=lambda: results.append(transport.send(BODY)))
        thread.start()
        time.sleep(0.1)
        transport.close()
        thread.join(10)
        self.assertEqual(results[0].outcome, OK)
        self.assertEqual(transport.send(BODY).message, 'closed')

    @unittest.skipUnless(IS_POSIX, 'fork exists on POSIX systems only')
    def test_a_forked_process_opens_a_connection_of_its_own(self):
        transport = self.make()
        transport.send(BODY)
        self.assertEqual(self.receiver.connections, 1)
        read, write = os.pipe()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            pid = os.fork()
        if pid == 0:
            try:
                warnings.simplefilter('ignore')
                os.close(read)
                os.write(write, transport.send(BODY).outcome.encode())
            finally:
                os._exit(0)
        os.close(write)
        child = os.read(read, 100).decode()
        os.close(read)
        os.waitpid(pid, 0)
        self.assertEqual(child, OK)
        self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual(self.receiver.connections, 2)
        self.assertEqual(self.receiver.count(), 3)


def make_certificate(folder, name, names):
    """Makes a self-signed certificate and key with the openssl command, and returns the two paths. None when it cannot."""
    if shutil.which('openssl') is None:
        return None
    config = os.path.join(folder, f'{name}.cnf')
    with open(config, 'w') as stream:
        stream.write("[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=" + names[0] + "\n[ext]\n"
                     "subjectAltName=" + ','.join(names[1:]) + "\nbasicConstraints=CA:TRUE\n")
    cert, key = os.path.join(folder, f'{name}.pem'), os.path.join(folder, f'{name}.key')
    result = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert, '-days', '2',
                             '-config', config], capture_output=True)
    return (cert, key) if result.returncode == 0 and os.path.isfile(cert) else None


class TestTls(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix='otlptls-')
        cls.good = make_certificate(cls.folder, 'good', ['127.0.0.1', 'IP:127.0.0.1', 'DNS:localhost'])
        cls.other = make_certificate(cls.folder, 'other', ['other.example.org', 'DNS:other.example.org'])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def setUp(self):
        if self.good is None or self.other is None:
            self.skipTest('the openssl command is not available')
        self.receivers = []
        self.addCleanup(lambda: [receiver.stop() for receiver in self.receivers])

    def serve(self, paths):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*paths)
        receiver = FakeReceiver(context)
        self.receivers.append(receiver)
        return receiver

    def test_a_receiver_with_a_certificate_the_context_trusts(self):
        receiver = self.serve(self.good)
        transport = OtlpHttpTransport(receiver.url, sslContext=ssl.create_default_context(cafile=self.good[0]), headers={'Authorization': 'Bearer t'})
        self.addCleanup(transport.close)
        self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual(transport.send(BODY).outcome, OK)
        self.assertEqual((receiver.count(), receiver.connections), (2, 1))
        self.assertEqual(receiver.requests[0]['headers']['authorization'], 'Bearer t')
        self.assertEqual(receiver.requests[0]['body'], BODY)

    def test_a_certificate_nobody_trusts_is_a_retry_and_nothing_is_sent(self):
        receiver = self.serve(self.good)
        transport = OtlpHttpTransport(receiver.url, timeout=3)
        self.addCleanup(transport.close)
        response = transport.send(BODY)
        self.assertEqual((response.outcome, response.status), (RETRY, None))
        self.assertIn('SSL', response.message)
        self.assertEqual(receiver.count(), 0)

    def test_a_certificate_for_another_name_is_refused(self):
        receiver = self.serve(self.other)
        transport = OtlpHttpTransport(receiver.url, sslContext=ssl.create_default_context(cafile=self.other[0]), timeout=3)
        self.addCleanup(transport.close)
        response = transport.send(BODY)
        self.assertEqual(response.outcome, RETRY)
        self.assertIn('SSL', response.message)
        self.assertEqual(receiver.count(), 0)

    def test_https_to_a_port_that_speaks_plain_http_is_a_retry(self):
        plain = FakeReceiver()
        self.addCleanup(plain.stop)
        transport = OtlpHttpTransport(f'https://127.0.0.1:{plain.port}', timeout=3)
        self.addCleanup(transport.close)
        self.assertEqual(transport.send(BODY).outcome, RETRY)
        self.assertEqual(plain.count(), 0)

    def test_http_to_a_port_that_speaks_tls_is_a_retry_and_does_not_hang(self):
        receiver = self.serve(self.good)
        transport = OtlpHttpTransport(f'http://127.0.0.1:{receiver.port}', timeout=3)
        self.addCleanup(transport.close)
        started = time.monotonic()
        self.assertEqual(transport.send(BODY).outcome, RETRY)
        self.assertLess(time.monotonic() - started, 10)


PROTOBUF_PARSER = False
try:
    from google.protobuf import json_format
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    PROTOBUF_PARSER = True
except ImportError:
    pass


@unittest.skipUnless(PROTOBUF_PARSER, 'the official protobuf parser is not installed')
class TestWithTheEncoder(ReceiverCase):
    """The body the encoder makes goes through the transport, and the receiver reads it with the official parser."""

    def test_the_whole_way(self):
        import base64
        from contrib.otlp_encoder import OtlpLogEncoder
        from record import LogRecord, TraceInfo
        from datetime import datetime, timezone
        record = LogRecord.create(datetime(2026, 10, 6, 18, 31, 52, 123456, tzinfo=timezone.utc), 'ERROR', 'error', 30.0, 'orders', 'failed',
                                  4321, 7, 'worker', fields={'order_id': 5, 'event_id': 'slot-1'}, context={'service': 'checkout'},
                                  trace=TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1))
        for compress in (False, True):
            body = OtlpLogEncoder(resource={'service.name': 'orders'}).encode([record, record], 1790000000000000000)
            self.assertEqual(self.make(compress=compress).send(body).outcome, OK)
            received = json.loads(self.receiver.requests[-1]['body'])
            logRecord = received['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]
            for key in ('traceId', 'spanId'):
                logRecord[key] = base64.b64encode(bytes.fromhex(logRecord[key])).decode()
            message = json_format.ParseDict(received, ExportLogsServiceRequest())
            self.assertEqual(len(message.resource_logs[0].scope_logs[0].log_records), 2)


if __name__ == '__main__':
    unittest.main()
