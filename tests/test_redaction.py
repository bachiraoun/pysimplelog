"""Tests that secrets never reach an output: names, patterns, ``Secret`` values, diagnostic exceptions, JSON, SIEM, OTLP and the spool.

Run from the repo root::

    python3 -m unittest tests.test_redaction -v

Every secret is built from parts, so that the value is not written in the source line that a traceback quotes.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from processors import DEFAULT_SENSITIVE_NAMES, redact_fields, redact_patterns, hash_secrets  # noqa: E402
from secret import Secret  # noqa: E402
from sinks import Sink, CallbackSink  # noqa: E402
from contrib import siem_sink  # noqa: E402
from contrib.otlp_encoder import OtlpLogEncoder  # noqa: E402

PASSWORD = "hunt" + "er2"
TOKEN = "tok-" + "9f8e7d6c"
API_KEY = "sk-live-" + "abcdef123456"
COOKIE = "sessionid=" + "c0ffee99"
BEARER = "Bearer " + "eyJhbGciOi.payloadpart.signaturepart"
URL_PASSWORD = "pw" + "-in-url-77"
SECRET_VALUE = "sec" + "ret-value-31"
ALL_SECRETS = (PASSWORD, TOKEN, API_KEY, COOKIE, BEARER, URL_PASSWORD, SECRET_VALUE)


class FakeTransport:
    """Keeps every message that the SIEM sink sends."""

    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)

    def close(self):
        pass


class Unreachable(Sink):
    """A receiver that is down: every write fails, so the records stay in the spool."""

    SPOOL_DESTINATION = ('host',)
    host = 'down.example.org'

    def write(self, text, record):
        return False


def clean_logger(**arguments):
    """Returns a logger that hides sensitive names and sensitive shapes, with no console and no file."""
    processors = arguments.pop('processors', [redact_fields(), redact_patterns()])
    return Logger('app', logToFile=False, logToStdout=False, processors=processors, **arguments)


def risky_charge(password, count):
    return password + count


def assert_no_secret(testCase, text, secrets=ALL_SECRETS):
    for secret in secrets:
        testCase.assertNotIn(secret, text)


class TestFields(unittest.TestCase):

    def make(self, **arguments):
        stream = io.StringIO()
        logger = clean_logger(**arguments)
        logger.add(stream, format='json')
        return logger, stream

    def test_the_default_names_cover_the_common_secrets(self):
        for name in ('password', 'token', 'authorization', 'api_key', 'secret', 'cookie', 'credential'):
            self.assertIn(name, DEFAULT_SENSITIVE_NAMES)

    def test_a_password_field_is_hidden(self):
        logger, stream = self.make()
        logger.info("login", user="ann", password=PASSWORD)
        record = json.loads(stream.getvalue())
        self.assertEqual(record['fields']['password'], '[REDACTED]')
        self.assertEqual(record['fields']['user'], 'ann')
        assert_no_secret(self, stream.getvalue())

    def test_names_that_contain_a_sensitive_word_are_hidden(self):
        logger, stream = self.make()
        logger.info("call", access_token=TOKEN, refresh_token=TOKEN, user_password=PASSWORD, stripe_api_key=API_KEY)
        assert_no_secret(self, stream.getvalue())

    def test_the_case_and_the_dashes_of_a_name_do_not_matter(self):
        logger, stream = self.make()
        logger.info("call", **{"X-Api-Key": API_KEY, "PASSWORD": PASSWORD, "Access-Token": TOKEN})
        assert_no_secret(self, stream.getvalue())

    def test_an_authorization_header_inside_a_dictionary_is_hidden(self):
        logger, stream = self.make()
        logger.info("request", headers={"Authorization": BEARER, "Accept": "text/html"})
        record = json.loads(stream.getvalue())
        self.assertEqual(record['fields']['headers']['Accept'], 'text/html')
        assert_no_secret(self, stream.getvalue())

    def test_deeply_nested_values_are_hidden(self):
        logger, stream = self.make()
        logger.info("nested", config={"db": {"connections": [{"host": "h", "password": PASSWORD}]}})
        assert_no_secret(self, stream.getvalue())

    def test_the_context_is_hidden_too(self):
        logger, stream = self.make()
        with logger.context(access_token=TOKEN, request_id="r-1"):
            logger.info("inside")
        record = json.loads(stream.getvalue())
        self.assertEqual(record['context']['request_id'], 'r-1')
        assert_no_secret(self, stream.getvalue())

    def test_a_bound_value_is_hidden(self):
        logger, stream = self.make()
        logger.bind(api_key=API_KEY).info("bound")
        assert_no_secret(self, stream.getvalue())

    def test_cookies_and_credentials_are_hidden_by_default(self):
        logger, stream = self.make()
        logger.info("request", cookie=COOKIE, credentials={"user": "a", "pass": PASSWORD}, user_credential=PASSWORD,
                    headers={"Cookie": COOKIE, "Set-Cookie": COOKIE})
        assert_no_secret(self, stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())['fields']['headers']['Cookie'], '[REDACTED]')

    def test_a_name_that_only_looks_similar_is_not_hidden(self):
        logger, stream = self.make()
        logger.info("request", cooking_time=5, credits=3, session_count=2)
        self.assertEqual(json.loads(stream.getvalue())['fields'], {'cooking_time': 5, 'credits': 3, 'session_count': 2})

    def test_more_names_can_still_be_added(self):
        logger, stream = self.make(processors=[redact_fields(DEFAULT_SENSITIVE_NAMES + ('session',))])
        logger.info("request", session_id="abc123")
        self.assertNotIn("abc123", stream.getvalue())

    def test_the_replacement_text_can_be_chosen(self):
        stream = io.StringIO()
        logger = clean_logger(processors=[redact_fields(replacement="***")])
        logger.add(stream, format='json')
        logger.info("login", password=PASSWORD)
        self.assertEqual(json.loads(stream.getvalue())['fields']['password'], '***')

    def test_the_text_layout_hides_them_too(self):
        stream = io.StringIO()
        logger = clean_logger()
        logger.add(stream)
        logger.info("login", password=PASSWORD)
        self.assertNotIn(PASSWORD, stream.getvalue())
        self.assertIn("[REDACTED]", stream.getvalue())


class TestShapes(unittest.TestCase):

    def make(self):
        stream = io.StringIO()
        logger = clean_logger()
        logger.add(stream, format='json')
        return logger, stream

    def test_a_password_written_in_the_message_is_hidden(self):
        logger, stream = self.make()
        logger.info(f"connecting with password={PASSWORD}")
        message = json.loads(stream.getvalue())['message']
        self.assertEqual(message, "connecting with password=[REDACTED]")

    def test_a_password_inside_a_url_is_hidden_and_the_rest_stays(self):
        logger, stream = self.make()
        logger.info(f"fetching https://ann:{URL_PASSWORD}@example.org/path")
        message = json.loads(stream.getvalue())['message']
        self.assertEqual(message, "fetching https://ann:[REDACTED]@example.org/path")

    def test_a_bearer_token_in_the_message_is_hidden(self):
        logger, stream = self.make()
        logger.info(f"sent Authorization: {BEARER}")
        assert_no_secret(self, stream.getvalue())

    def test_a_secret_formatted_into_the_message_is_hidden(self):
        logger, stream = self.make()
        logger.info("using {}", f"password={PASSWORD}")
        assert_no_secret(self, stream.getvalue())

    def test_a_secret_in_a_text_field_is_hidden(self):
        logger, stream = self.make()
        logger.info("request", url=f"https://ann:{URL_PASSWORD}@example.org/")
        assert_no_secret(self, stream.getvalue())

    def test_a_secret_in_the_exception_message_is_hidden(self):
        logger, stream = self.make()
        try:
            raise ValueError(f"bad login password={PASSWORD}")
        except ValueError:
            logger.exception("failed")
        assert_no_secret(self, stream.getvalue())

    def test_your_own_pattern_is_applied(self):
        stream = io.StringIO()
        logger = clean_logger(processors=[redact_patterns(custom={"account": r"ACCT-\d{6}"})])
        logger.add(stream, format='json')
        logger.info("account ACCT-123456 was closed")
        self.assertNotIn("ACCT-123456", stream.getvalue())


class TestSecretValues(unittest.TestCase):

    def test_a_secret_prints_as_redacted_in_every_text(self):
        secret = Secret(SECRET_VALUE)
        for text in (str(secret), repr(secret), f"{secret}", "{}".format(secret), f"{secret:>20}"):
            self.assertNotIn(SECRET_VALUE, text)
            self.assertIn("[REDACTED]", text)

    def test_reveal_gives_the_value_back_to_the_code_that_may_use_it(self):
        self.assertEqual(Secret(SECRET_VALUE).reveal(), SECRET_VALUE)

    def test_a_secret_cannot_be_pickled_or_copied_into_the_open(self):
        import copy
        import pickle
        with self.assertRaises(TypeError):
            pickle.dumps(Secret(SECRET_VALUE))
        secret = Secret(SECRET_VALUE)
        self.assertIs(copy.copy(secret), secret)
        self.assertIs(copy.deepcopy(secret), secret)

    def test_a_secret_in_a_field_a_message_and_the_context_is_hidden(self):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add(stream, format='json')
        secret = Secret(SECRET_VALUE)
        with logger.context(owner=secret):
            logger.info("holding {}", secret, value=secret, nested={"list": [secret]})
        self.assertNotIn(SECRET_VALUE, stream.getvalue())

    def test_a_secret_in_a_text_layout_and_a_pretty_layout_is_hidden(self):
        text, pretty = io.StringIO(), io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add(text)
        logger.add(pretty, format='pretty')
        logger.info("holding {}", Secret(SECRET_VALUE), value=Secret(SECRET_VALUE))
        self.assertNotIn(SECRET_VALUE, text.getvalue())
        self.assertNotIn(SECRET_VALUE, pretty.getvalue())

    def test_hash_secrets_gives_the_same_code_for_the_same_secret(self):
        stream = io.StringIO()
        logger = clean_logger(processors=[hash_secrets(b"key-one")])
        logger.add(stream, format='json')
        logger.info("a", value=Secret(SECRET_VALUE))
        logger.info("b", value=Secret(SECRET_VALUE))
        logger.info("c", value=Secret(SECRET_VALUE + "x"))
        first, second, third = [json.loads(line)['fields']['value'] for line in stream.getvalue().splitlines()]
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertTrue(first.startswith("hmac:"))
        self.assertNotIn(SECRET_VALUE, stream.getvalue())

    def test_a_different_key_gives_a_different_code(self):
        codes = []
        for key in (b"key-one", b"key-two"):
            stream = io.StringIO()
            logger = clean_logger(processors=[hash_secrets(key)])
            logger.add(stream, format='json')
            logger.info("a", value=Secret(SECRET_VALUE))
            codes.append(json.loads(stream.getvalue())['fields']['value'])
        self.assertNotEqual(codes[0], codes[1])

    def test_a_code_made_without_a_key_changes_with_each_run_of_the_processor(self):
        codes = []
        for _ in range(2):
            stream = io.StringIO()
            logger = clean_logger(processors=[hash_secrets()])
            logger.add(stream, format='json')
            logger.info("a", value=Secret(SECRET_VALUE))
            codes.append(json.loads(stream.getvalue())['fields']['value'])
        self.assertNotEqual(codes[0], codes[1])


class TestDiagnosticExceptions(unittest.TestCase):

    def make(self, mode='summary', **arguments):
        stream = io.StringIO()
        logger = clean_logger(diagnose=mode, **arguments)
        logger.add(stream, format='json')
        return logger, stream

    def test_a_sensitive_variable_is_hidden_in_both_modes(self):
        for mode in ('summary', 'full'):
            logger, stream = self.make(mode)
            try:
                risky_charge(PASSWORD, 1)
            except TypeError:
                logger.exception("failed")
            text = json.loads(stream.getvalue())['exception']['stacktrace']
            # The variable is hidden by its name, and the text patterns may then rewrite the marker
            self.assertRegex(text, r"password = (<redacted>|\[REDACTED\])")
            self.assertIn("count = 1", text)

    def test_the_diagnosis_does_not_bypass_the_text_patterns(self):
        logger, stream = self.make()

        def call():
            line = "password=" + PASSWORD
            return line + 1

        try:
            call()
        except TypeError:
            logger.exception("failed")
        assert_no_secret(self, stream.getvalue(), (PASSWORD,))

    def test_a_cookie_variable_is_hidden(self):
        logger, stream = self.make('summary')

        def call():
            cookie = COOKIE
            return cookie + 1

        try:
            call()
        except TypeError:
            logger.exception("failed")
        self.assertNotIn(COOKIE, stream.getvalue())

    def test_a_secret_object_in_a_variable_is_hidden(self):
        logger, stream = self.make('full')

        def call():
            harmless = Secret(SECRET_VALUE)
            return harmless + 1

        try:
            call()
        except TypeError:
            logger.exception("failed")
        self.assertNotIn(SECRET_VALUE, stream.getvalue())

    def test_a_bearer_token_in_a_variable_is_hidden(self):
        logger, stream = self.make('full')

        def call():
            header = BEARER
            return header + 1

        try:
            call()
        except TypeError:
            logger.exception("failed")
        self.assertNotIn(BEARER, stream.getvalue())


class TestEveryOutput(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="redaction-")
        self.addCleanup(shutil.rmtree, self.folder, True)

    def log_everything(self, logger):
        with logger.context(access_token=TOKEN):
            logger.info(f"login password={PASSWORD}", api_key=API_KEY, headers={"Authorization": BEARER},
                        value=Secret(SECRET_VALUE))
            try:
                risky_charge(PASSWORD, 1)
            except TypeError:
                logger.exception("failed")

    def test_the_json_file_has_no_secret(self):
        logger = clean_logger(diagnose='summary')
        path = os.path.join(self.folder, "app.jsonl")
        name = logger.add(path, format="json")
        self.log_everything(logger)
        logger.remove(name)
        text = ''
        for file in os.listdir(self.folder):
            with open(os.path.join(self.folder, file)) as handle:
                text += handle.read()
        assert_no_secret(self, text, (TOKEN, API_KEY, SECRET_VALUE, BEARER))
        self.assertNotIn("password=" + PASSWORD, text)

    def test_the_siem_message_has_no_secret(self):
        transport = FakeTransport()
        logger = clean_logger(diagnose='summary')
        sink = siem_sink.attach(logger, transport, threaded=False)
        self.log_everything(logger)
        siem_sink.detach(logger, sink)
        self.assertGreater(len(transport.sent), 0)
        text = b''.join(transport.sent).decode('utf-8')
        assert_no_secret(self, text, (TOKEN, API_KEY, SECRET_VALUE, BEARER))
        self.assertNotIn("password=" + PASSWORD, text)

    def test_the_otlp_request_has_no_secret(self):
        records = []
        logger = clean_logger(diagnose='summary')
        logger.add(CallbackSink(lambda text, record: records.append(record)))
        self.log_everything(logger)
        self.assertEqual(len(records), 2)
        body = OtlpLogEncoder().encode(records).decode('utf-8')
        assert_no_secret(self, body, (TOKEN, API_KEY, SECRET_VALUE, BEARER))
        self.assertNotIn("password=" + PASSWORD, body)

    def test_the_spool_on_the_disk_has_no_secret(self):
        base = os.path.join(self.folder, "spool")
        logger = Logger('app', logToFile=False, logToStdout=False, diagnose='summary',
                        processors=[redact_fields(), redact_patterns(), hash_secrets(b"key")])
        settings = dict(path=base, id='redaction', maxBytes=10 ** 7, totalMaxBytes=10 ** 8,
                        retryBackoffBase=0.05, retryBackoffMax=0.1)
        logger.add_sink('down', Unreachable(formatter='json'), threaded=True, spool=settings)
        try:
            self.log_everything(logger)
            deadline = time.time() + 10
            while logger.sink_stats('down')['spool']['spooled'] < 2 and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(logger.sink_stats('down')['spool']['spooled'], 2)
            logger.sink_stats('down')
            found = b''
            for root, _, files in os.walk(base):
                for file in files:
                    with open(os.path.join(root, file), 'rb') as handle:
                        found += handle.read()
        finally:
            logger.clear_sinks(timeout=1.0)
        self.assertIn(b"login", found)
        text = found.decode('utf-8', 'replace')
        assert_no_secret(self, text, (TOKEN, API_KEY, SECRET_VALUE, BEARER))
        self.assertNotIn("password=" + PASSWORD, text)

    def test_the_standard_logging_bridge_goes_through_the_same_processors(self):
        import logging
        from standard_logging import redirect_standard_logging, restore_standard_logging
        stream = io.StringIO()
        logger = clean_logger()
        logger.add(stream, format='json')
        handler = redirect_standard_logging(logger, name="thirdparty.lib", loggerLevel=logging.DEBUG)
        try:
            logging.getLogger("thirdparty.lib").error(f"retrying with password={PASSWORD}", extra={"api_key": API_KEY})
        finally:
            restore_standard_logging(handler)
        self.assertNotIn(PASSWORD, stream.getvalue())
        self.assertNotIn(API_KEY, stream.getvalue())

    def test_a_processor_that_fails_drops_the_record_and_never_leaks_it(self):
        stream = io.StringIO()

        def broken(record):
            raise RuntimeError("cannot clean this record")

        logger = Logger('app', logToFile=False, logToStdout=False, processors=[broken])
        logger.add(stream, format='json')
        # The warning about the failed processor goes to the error stream, this test does not need to show it
        with contextlib.redirect_stderr(io.StringIO()):
            logger.info("login", password=PASSWORD)
        self.assertEqual(stream.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
