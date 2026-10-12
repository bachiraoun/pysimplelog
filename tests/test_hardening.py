"""The protections against forged log lines, huge formats, slow patterns, unsafe network settings and open log files.

Run from the repo root::

    python3 -m unittest tests.test_hardening -v

Each protection has tests that fail on the code as it was before the protection existed:

* TestFilledValues, TestDataAndTraceback -- a value cannot start a new line in the log
* TestFormatLimits, TestMessageLimit -- no format or message can make a huge text
* TestJwtPattern -- the token pattern takes time in proportion to the text
* TestNetworkChecks, TestHttpTransportRules, TestCleartextWarning -- what a transport accepts and what it says
* TestSyslogHeader -- the application and host names of a syslog header
* TestFileModes -- the permissions of log files and of their compressed copies
* TestControlCharacters, TestSensitiveNames -- the escaped characters and the hidden names
"""
import contextlib
import http.server
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger, DEFAULT_MAX_MESSAGE_SIZE  # noqa: E402
from message_format import render_message  # noqa: E402
from formatters import escape_control_characters, indent_block, indent_continuation_lines  # noqa: E402
from processors import TEXT_PATTERNS, DEFAULT_SENSITIVE_NAMES, redact_fields  # noqa: E402
from record import LogRecord  # noqa: E402
from sinks import StreamSink, FileSink  # noqa: E402
from contrib import siem_sink, siem_transport  # noqa: E402
from contrib.network_checks import is_local_host  # noqa: E402

# A name that tries to end its own line and start another one that looks real
FORGED = "bob\n2026-10-11 08:00:00 - t <INFO> admin logged in"
# Seconds a test waits for something that must happen
WAIT_SECONDS = 15.0
# Largest size of a file in megabytes: about two thousand bytes, some twenty records
SMALL_FILE_MEGABYTES = 0.002


def make_logger(formatter='text', **options):
    """Returns a logger with one sink in the given layout, and the buffer the sink writes to."""
    buffer = io.StringIO()
    logger = Logger('t', logToStdout=False, logToFile=False, **options)
    logger.add_sink('s', StreamSink(buffer, formatter=formatter))
    return logger, buffer


def make_record(text):
    return LogRecord.create(datetime.now(timezone.utc), 'INFO', 'info', 10.0, 'test', text, 1, 1, 'MainThread')


def wait_until(condition, what, timeout=WAIT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def compression_threads():
    return [thread for thread in threading.enumerate() if thread.name == 'pysimplelog-file-compress' and thread.is_alive()]


class PlainObject:
    """An object whose text has a line break in it, as an error with user input in its message has."""

    def __str__(self):
        return "first\nsecond"


class TestFilledValues(unittest.TestCase):

    def lines_of(self, layout, message, *args, **fields):
        logger, buffer = make_logger(layout)
        logger.info(message, *args, **fields)
        return buffer.getvalue().splitlines()

    def test_a_string_value_cannot_start_a_new_line(self):
        for layout in ('text', 'pretty'):
            with self.subTest(layout=layout):
                lines = self.lines_of(layout, "login failed for {}", FORGED)
                self.assertEqual(len(lines), 1)
                self.assertIn("bob\\n2026-10-11", lines[0])

    def test_the_message_itself_is_not_escaped_only_values_are(self):
        # Pins the limit that the documentation warns about: text you do not control belongs in a value, never in the message
        for layout in ('text', 'pretty'):
            with self.subTest(layout=layout):
                lines = self.lines_of(layout, FORGED)
                self.assertEqual(len(lines), 2)
                self.assertTrue(lines[1].startswith("2026-10-11"))

    def test_a_keyword_value_cannot_start_a_new_line(self):
        for layout in ('text', 'pretty'):
            with self.subTest(layout=layout):
                lines = self.lines_of(layout, "login failed for {user}", user=FORGED)
                self.assertEqual(len(lines), 1)

    def test_the_text_of_an_error_cannot_start_a_new_line(self):
        lines = self.lines_of('text', "failed: {}", ValueError("a\nb"))
        self.assertEqual(len(lines), 1)
        self.assertIn("a\\nb", lines[0])

    def test_the_text_of_any_object_cannot_start_a_new_line(self):
        lines = self.lines_of('text', "got {}", PlainObject())
        self.assertEqual(len(lines), 1)
        self.assertIn("first\\nsecond", lines[0])

    def test_a_conversion_to_repr_is_safe_too(self):
        lines = self.lines_of('text', "got {!r}", "a\nb")
        self.assertEqual(len(lines), 1)

    def test_an_escape_character_in_a_value_is_written_as_text(self):
        lines = self.lines_of('text', "got {}", "\x1b[31mred")
        self.assertEqual(len(lines), 1)
        self.assertNotIn("\x1b", lines[0])
        self.assertIn("\\x1b[31mred", lines[0])

    def test_numbers_none_and_format_specs_are_left_alone(self):
        lines = self.lines_of('text', "{} {} {:.2f} {:>5}", 5, None, Decimal("3.14159"), "ab")
        self.assertTrue(lines[0].endswith("5 None 3.14    ab"))

    def test_the_template_keeps_its_own_line_breaks(self):
        lines = self.lines_of('text', "first\nsecond {}", 7)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1], "second 7")

    def test_the_fields_of_the_record_keep_the_raw_value(self):
        logger, buffer = make_logger('json')
        logger.info("hi {user}", user=FORGED)
        record = json.loads(buffer.getvalue())
        self.assertEqual(record['fields']['user'], FORGED)
        self.assertEqual(record['message'], "hi " + FORGED.replace("\n", "\\n"))


class TestDataAndTraceback(unittest.TestCase):

    def log_error(self, layout, message):
        logger, buffer = make_logger(layout)
        try:
            raise ValueError(message)
        except ValueError:
            logger.error("boom", exc_info=True)
        return buffer.getvalue()

    def test_the_lines_of_data_after_the_first_are_indented(self):
        data = "line one\n2026-10-11 08:00:00 - t <INFO> admin logged in\r\nthird fourth"
        for layout in ('text', 'pretty', '{message}\n{data}'):
            with self.subTest(layout=layout):
                logger, buffer = make_logger(layout)
                logger.info("report", data=data)
                lines = buffer.getvalue().splitlines()
                self.assertEqual(lines[1], "line one")
                self.assertEqual(len(lines), 5)
                self.assertTrue(all(line.startswith('    ') for line in lines[2:]))

    def test_the_data_of_one_line_is_left_alone(self):
        logger, buffer = make_logger('text')
        logger.info("report", data="just one line")
        self.assertEqual(buffer.getvalue().splitlines()[1], "just one line")

    def test_an_error_message_cannot_forge_a_line(self):
        for layout in ('text', 'pretty'):
            with self.subTest(layout=layout):
                lines = self.log_error(layout, FORGED).splitlines()
                self.assertGreater(len(lines), 2)
                self.assertTrue(all(line.startswith('    ') for line in lines[1:]))

    def test_the_exception_of_a_template_is_indented_on_every_line(self):
        lines = self.log_error('{exception}', FORGED).splitlines()
        self.assertTrue(all(line.startswith('    ') for line in lines))

    def test_json_keeps_the_raw_data_and_the_raw_traceback(self):
        logger, buffer = make_logger('json')
        try:
            raise ValueError(FORGED)
        except ValueError:
            logger.error("boom", data="a\nb", exc_info=True)
        record = json.loads(buffer.getvalue())
        self.assertEqual(record['fields']['data'], "a\nb")
        self.assertTrue(record['exception']['stacktrace'].startswith("Traceback"))

    def test_the_helpers_indent_every_kind_of_line_break(self):
        self.assertEqual(indent_continuation_lines("one"), "one")
        self.assertEqual(indent_continuation_lines(""), "")
        self.assertEqual(indent_continuation_lines("a\nb"), "a\n    b")
        self.assertEqual(indent_continuation_lines("a\r\nb c\x85d"), "a\n    b\n    c\n    d")
        self.assertEqual(indent_block("a\nb"), "    a\n    b")
        self.assertEqual(indent_block("a"), "    a")


class TestFormatLimits(unittest.TestCase):

    def test_a_huge_width_or_precision_gives_the_plain_value(self):
        started = time.perf_counter()
        text = render_message("{x:>200000000}|{y:.2000000000f}|{z:>9}", (), {'x': 1, 'y': 1.5, 'z': 7})
        self.assertEqual(text, "1|1.5|        7")
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_a_width_given_by_another_value_is_checked_too(self):
        self.assertEqual(render_message("{0:{1}}", (5, 300000000), {}), "5")

    def test_a_width_just_under_the_limit_still_works(self):
        self.assertEqual(len(render_message("{x:>9999}", (), {'x': 1})), 9999)
        self.assertEqual(render_message("{x:>10000}", (), {'x': 1}), "1")

    def test_the_other_protections_of_the_formatter_still_hold(self):
        self.assertEqual(render_message("{0.real}", (5,), {}), "{0.real}")
        self.assertEqual(render_message("{0[0]}", ([1],), {}), "{0[0]}")


class TestMessageLimit(unittest.TestCase):

    def logged(self, length, **options):
        logger, buffer = make_logger('text', **options)
        logger.info("x" * length)
        return logger, buffer.getvalue().rstrip('\n')

    def test_the_default_is_ten_thousand_characters(self):
        logger, _ = make_logger('text')
        self.assertEqual(DEFAULT_MAX_MESSAGE_SIZE, 10000)
        self.assertEqual(logger.logMessageMaxSize, 10000)

    def test_a_message_of_exactly_the_limit_is_kept(self):
        _, line = self.logged(10000)
        self.assertTrue(line.endswith("x" * 10000))
        self.assertNotIn("[truncated]", line)

    def test_a_longer_message_is_cut_and_marked(self):
        _, line = self.logged(10001)
        self.assertTrue(line.endswith("x" * 10000 + "[truncated]"))

    def test_none_removes_the_limit(self):
        logger, line = self.logged(20000, maxMessageSize=None)
        self.assertIsNone(logger.logMessageMaxSize)
        self.assertTrue(line.endswith("x" * 20000))

    def test_another_limit_can_be_chosen(self):
        _, line = self.logged(100, maxMessageSize=50)
        self.assertTrue(line.endswith("x" * 50 + "[truncated]"))


class TestJwtPattern(unittest.TestCase):

    def slowest_of_three(self, text):
        pattern = re.compile(TEXT_PATTERNS['jwt'])
        timings = []
        for _ in range(3):
            started = time.perf_counter()
            pattern.sub('X', text)
            timings.append(time.perf_counter() - started)
        return min(timings)

    def test_the_time_grows_in_proportion_to_the_text(self):
        # Text of this shape took time in proportion to the square of its length: four times the text took sixteen times as long
        small = self.slowest_of_three("eyJ-" * 6000)
        large = self.slowest_of_three("eyJ-" * 24000)
        self.assertLess(large / max(small, 0.001), 10)

    def test_a_token_is_still_found_with_its_surroundings(self):
        pattern = re.compile(TEXT_PATTERNS['jwt'])
        self.assertEqual(pattern.search("tok=eyJabc.def.ghi; x").group('secret'), "eyJabc.def.ghi")
        self.assertEqual(pattern.search("Bearer eyJa.b.c").group('secret'), "eyJa.b.c")

    def test_the_middle_of_a_longer_word_is_not_a_token(self):
        pattern = re.compile(TEXT_PATTERNS['jwt'])
        self.assertIsNone(pattern.search("abceyJabc.def.ghi"))


class TestAssignmentPattern(unittest.TestCase):

    def secret_of(self, text):
        match = re.compile(TEXT_PATTERNS['assignment']).search(text)
        return None if match is None else match.group('secret')

    def test_a_value_in_single_or_double_quotes_is_found(self):
        self.assertEqual(self.secret_of("Holder(password='abc123')"), "abc123")
        self.assertEqual(self.secret_of('Holder(password="abc123")'), "abc123")

    def test_a_quoted_value_may_hold_spaces(self):
        self.assertEqual(self.secret_of('login password="two words" ok'), "two words")

    def test_an_unquoted_value_stops_at_a_closing_bracket(self):
        self.assertEqual(self.secret_of("call(password=abc123)"), "abc123")
        self.assertEqual(self.secret_of("token: abc123, next"), "abc123")

    def test_a_quote_that_is_never_closed_does_not_hide_the_next_lines(self):
        self.assertEqual(self.secret_of('password="abc\nnext line'), "abc")

    def test_an_empty_quoted_value_has_nothing_to_hide(self):
        self.assertIsNone(self.secret_of("password=''"))

    def test_the_time_grows_in_proportion_to_the_text(self):
        pattern = re.compile(TEXT_PATTERNS['assignment'])
        timings = {}
        for repeats in (1500, 6000):
            text = "password " * repeats
            started = time.perf_counter()
            pattern.sub('X', text)
            timings[repeats] = time.perf_counter() - started
        self.assertLess(timings[6000] / max(timings[1500], 0.001), 10)


class TestNetworkChecks(unittest.TestCase):

    def test_what_stays_on_this_machine(self):
        for host in ('localhost', 'api.localhost', '127.0.0.1', '::1'):
            with self.subTest(host=host):
                self.assertTrue(is_local_host(host))

    def test_what_leaves_this_machine(self):
        for host in ('example.org', '10.0.0.5', '192.168.1.1', '0.0.0.0'):
            with self.subTest(host=host):
                self.assertFalse(is_local_host(host))


class LocalServer:
    """A small web server on this machine that keeps what it was sent and answers as the test says."""

    def __init__(self, status=200, location=None):
        self.requests = []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.requests.append((self.command, self.path, self.headers.get('Authorization')))
                self.send_response(status)
                if location is not None:
                    self.send_header('Location', location)
                self.send_header('Content-Length', '0')
                self.end_headers()

            do_GET = do_POST

            def log_message(self, *arguments):
                pass

        self.server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server.server_port

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


class TestHttpTransportRules(unittest.TestCase):

    def start(self, **arguments):
        server = LocalServer(**arguments)
        self.addCleanup(server.stop)
        return server

    def test_only_http_and_https_addresses_with_a_host_are_accepted(self):
        for url in ('file:///etc/hosts', 'ftp://host/x', 'http://', 'collector', ''):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    siem_transport.HTTPTransport(url)

    def test_an_address_that_is_not_text_is_refused(self):
        for url in (None, 5, b'http://host/'):
            with self.subTest(url=url):
                with self.assertRaises(TypeError):
                    siem_transport.HTTPTransport(url)

    def test_a_user_name_or_a_password_in_the_address_is_refused(self):
        for url in ('https://user:pw@collector.example.org/x', 'https://user@collector.example.org/x'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    siem_transport.HTTPTransport(url)

    def test_the_safe_address_leaves_out_the_query(self):
        transport = siem_transport.HTTPTransport('https://collector.example.org/api?token=SECRETQ#part')
        self.assertEqual(transport._safe_address(), 'https://collector.example.org:443/api')

    def test_a_normal_answer_delivers_and_sends_the_headers(self):
        server = self.start()
        transport = siem_transport.HTTPTransport(f'http://127.0.0.1:{server.port}/p', headers={'Authorization': 'Splunk T'})
        transport.send(b'hello')
        self.assertEqual(server.requests, [('POST', '/p', 'Splunk T')])

    def test_a_redirect_is_an_error_and_is_not_followed(self):
        target = self.start()
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                origin = self.start(status=status, location=f'http://127.0.0.1:{target.port}/stolen')
                transport = siem_transport.HTTPTransport(f'http://127.0.0.1:{origin.port}/p',
                                                         headers={'Authorization': 'Splunk SECRET-TOKEN'})
                with self.assertRaises(urllib.error.HTTPError):
                    transport.send(b'hello')
        self.assertEqual(target.requests, [])

    def test_an_error_answer_does_not_show_the_query_of_the_address(self):
        server = self.start(status=500)
        transport = siem_transport.HTTPTransport(f'http://127.0.0.1:{server.port}/p?token=SECRETQ')
        with self.assertRaises(urllib.error.HTTPError) as caught:
            transport.send(b'hello')
        self.assertNotIn('SECRETQ', str(caught.exception))


class TestCleartextWarning(unittest.TestCase):

    def warning_of(self, make):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            transport = make()
        close = getattr(transport, 'close', None)
        if close is not None:
            close()
        return buffer.getvalue()

    def test_http_to_another_machine_warns_without_the_query(self):
        text = self.warning_of(lambda: siem_transport.HTTPTransport('http://collector.example.org/x?token=SECRETQ'))
        self.assertIn('without encryption', text)
        self.assertIn('http://collector.example.org:80/x', text)
        self.assertNotIn('SECRETQ', text)

    def test_https_and_this_machine_do_not_warn(self):
        for url in ('https://collector.example.org/x', 'http://127.0.0.1:8088/x', 'http://localhost/x'):
            with self.subTest(url=url):
                self.assertEqual(self.warning_of(lambda: siem_transport.HTTPTransport(url)), '')

    def test_tcp_without_encryption_to_another_machine_warns(self):
        text = self.warning_of(lambda: siem_transport.TCPSyslogTransport('collector.example.org', 514))
        self.assertIn('tcp://collector.example.org:514', text)

    def test_tcp_with_encryption_or_on_this_machine_does_not_warn(self):
        self.assertEqual(self.warning_of(lambda: siem_transport.TCPSyslogTransport('collector.example.org', 6514, useTls=True)), '')
        self.assertEqual(self.warning_of(lambda: siem_transport.TCPSyslogTransport('127.0.0.1', 514)), '')

    def test_udp_to_another_machine_warns_and_to_this_one_does_not(self):
        self.assertIn('udp://collector.example.org:514',
                      self.warning_of(lambda: siem_transport.UDPSyslogTransport('collector.example.org', 514)))
        self.assertEqual(self.warning_of(lambda: siem_transport.UDPSyslogTransport('127.0.0.1', 514)), '')

    def test_a_closed_error_stream_does_not_stop_the_transport(self):
        class Closed:
            def write(self, text):
                raise ValueError("I/O operation on closed file")

        with mock.patch.object(sys, 'stderr', Closed()):
            transport = siem_transport.HTTPTransport('http://collector.example.org/x')
        self.assertEqual(transport.url, 'http://collector.example.org/x')


class TestSyslogHeader(unittest.TestCase):

    def test_names_with_a_space_a_control_character_or_a_non_ascii_letter_are_refused(self):
        for name in ('my app', 'my\napp', 'café', 'tab\tname'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    siem_sink.RFC5424Formatter(appName=name)
                with self.assertRaises(ValueError):
                    siem_sink.RFC5424Formatter(hostname=name)

    def test_ordinary_names_are_accepted(self):
        formatter = siem_sink.RFC5424Formatter(appName='my-app_1.0', hostname='host1.example.org')
        self.assertEqual(formatter.hostname, 'host1.example.org')

    def test_an_empty_or_missing_host_name_falls_back_to_the_machine(self):
        for hostname in (None, ''):
            with self.subTest(hostname=hostname):
                with mock.patch.object(siem_sink.socket, 'gethostname', return_value='machine1'):
                    self.assertEqual(siem_sink.RFC5424Formatter(hostname=hostname).hostname, 'machine1')

    def test_a_machine_name_that_would_break_the_header_is_made_safe(self):
        with mock.patch.object(siem_sink.socket, 'gethostname', return_value='my hosté'):
            self.assertEqual(siem_sink.RFC5424Formatter().hostname, 'my_host_')


@unittest.skipIf(os.name == 'nt', 'file permissions do not work this way on Windows')
class TestFileModes(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='hardening-')
        self.sinks = []
        self.addCleanup(self._cleanup)
        # A mask that removes nothing, so that the mode asked for is the mode written. A test that needs a mask sets its own
        previous = os.umask(0)
        self.addCleanup(os.umask, previous)

    def _cleanup(self):
        for sink in self.sinks:
            sink.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_sink(self, **options):
        sink = FileSink(os.path.join(self.folder, 'app'), 'log', formatter=lambda record: record.message, **options)
        self.sinks.append(sink)
        return sink

    def mode_of(self, path):
        return os.stat(path).st_mode & 0o777

    def test_the_given_mode_is_used_for_a_new_file(self):
        for mode in (0o600, 0o640):
            with self.subTest(mode=oct(mode)):
                sink = self.make_sink(fileMode=mode)
                sink.emit(make_record("hello"))
                self.assertEqual(self.mode_of(sink.path), mode)
                os.remove(sink.path)

    def test_without_a_mode_the_mask_of_the_system_decides(self):
        os.umask(0o077)
        sink = self.make_sink()
        sink.emit(make_record("hello"))
        self.assertEqual(self.mode_of(sink.path), 0o600)

    def test_a_file_that_exists_keeps_its_mode(self):
        path = os.path.join(self.folder, 'app_0.log')
        with open(path, 'w') as handle:
            handle.write("old\n")
        os.chmod(path, 0o644)
        sink = self.make_sink(fileMode=0o600)
        sink.emit(make_record("hello"))
        self.assertEqual(sink.path, path)
        self.assertEqual(self.mode_of(path), 0o644)

    def test_a_wrong_mode_is_refused(self):
        for mode, error in ((True, TypeError), ('600', TypeError), (6.0, TypeError), (0o1000, ValueError), (-1, ValueError)):
            with self.subTest(mode=mode):
                with self.assertRaises(error):
                    FileSink(os.path.join(self.folder, 'refused'), fileMode=mode)

    def test_the_compressed_copy_has_the_mode_of_the_original(self):
        # With a mask that removes nothing, a copy made without the mode of the original would be open to every user
        sink = self.make_sink(fileMode=0o600, maxSize=SMALL_FILE_MEGABYTES, firstNumber=0, compress='gz')
        for index in range(60):
            sink.emit(make_record(f"r{index:05d}" + "x" * 90))
        wait_until(lambda: sink.stats['files_compressed'] >= 1, 'a compressed file')
        wait_until(lambda: compression_threads() == [], 'the compression thread to end')
        compressed =[name for name in os.listdir(self.folder) if name.endswith('.gz')]
        self.assertGreater(len(compressed), 0)
        for name in compressed:
            with self.subTest(name=name):
                self.assertEqual(self.mode_of(os.path.join(self.folder, name)), 0o600)
        self.assertEqual([name for name in os.listdir(self.folder) if name.endswith('.tmp')], [])


class TestControlCharacters(unittest.TestCase):

    def test_the_whole_range_of_c1_controls_is_escaped(self):
        for character, expected in (('\x80', '\\x80'), ('\x85', '\\x85'), ('\x9b', '\\x9b'), ('\x9f', '\\x9f'), ('\x7f', '\\x7f')):
            with self.subTest(character=expected):
                self.assertEqual(escape_control_characters(f"a{character}b"), f"a{expected}b")

    def test_the_tab_and_ordinary_text_are_kept(self):
        self.assertEqual(escape_control_characters("a\tb é中"), "a\tb é中")

    def test_a_field_with_a_c1_control_is_written_escaped(self):
        logger, buffer = make_logger('text')
        logger.info("x", user="a\x9bb")
        self.assertNotIn("\x9b", buffer.getvalue())
        self.assertIn("\\x9b", buffer.getvalue())


class TestDiagnoseAndEnvironment(unittest.TestCase):

    def test_diagnose_cannot_be_set_from_the_environment(self):
        # Diagnostics write the values of variables into every output, so only the code of the program may switch them on
        names = ('PYSIMPLELOG_DIAGNOSE', 'PYSIMPLELOG_LEVEL')
        saved = {name: os.environ.get(name) for name in names}
        self.addCleanup(lambda: [os.environ.pop(name, None) if value is None else os.environ.__setitem__(name, value)
                                 for name, value in saved.items()])
        os.environ['PYSIMPLELOG_DIAGNOSE'] = 'full'
        os.environ['PYSIMPLELOG_LEVEL'] = 'WARNING'
        logger = Logger('t', logToStdout=False, logToFile=False, env=True)
        self.assertFalse(logger.diagnose)


class TestSensitiveNames(unittest.TestCase):

    def test_the_added_names_are_in_the_default_list(self):
        for name in ('passwd', 'pwd', 'private_key'):
            self.assertIn(name, DEFAULT_SENSITIVE_NAMES)

    def test_their_values_are_hidden(self):
        logger, buffer = make_logger('json', processors=[redact_fields()])
        logger.info("db", db_passwd="a-value", PWD="b-value", my_private_key="c-value", host="h")
        fields = json.loads(buffer.getvalue())['fields']
        self.assertEqual(fields, {'db_passwd': '[REDACTED]', 'PWD': '[REDACTED]', 'my_private_key': '[REDACTED]', 'host': 'h'})


if __name__ == '__main__':
    unittest.main()
