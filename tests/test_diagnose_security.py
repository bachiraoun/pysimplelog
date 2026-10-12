"""What a diagnostic traceback shows, and whether the redaction controls still hold for it on every output.

Run from the repo root::

    python3 -m unittest tests.test_diagnose_security -v

A diagnostic traceback (``diagnose='summary'`` or ``'full'``) adds the values of the variables on each line of code. This file checks
that those values cannot bypass ``redact_fields``, ``redact_patterns`` and ``Secret``, on the text, pretty, template, JSON, SIEM and
OTLP outputs, and what the traceback does with chained errors, missing source files, values that cannot be printed and long values.

* TestEveryOutput -- the same failure, written by six outputs, with the secret in different places
* TestContainersAndObjects -- secrets inside dictionaries, lists and the text of objects in ``full`` mode
* TestWhatTheTracebackShows -- the limits of the redaction, chains, missing source, failing ``repr`` and long values

Every secret is built from parts, so that the value is not written in the source line that a traceback quotes.
"""
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from processors import redact_fields, redact_patterns  # noqa: E402
from secret import Secret  # noqa: E402
from sinks import CallbackSink  # noqa: E402
from contrib import siem_sink  # noqa: E402
from contrib.otlp_encoder import OtlpLogEncoder  # noqa: E402

PASSWORD = "hunt" + "er2"
SECRET_VALUE = "sec" + "ret-value-31"
MODES = ('summary', 'full')
# The layouts a person reads, the JSON a machine reads, and the two network formats
SURFACES = ('text', 'pretty', 'template', 'json', 'siem', 'otlp')
LAYOUTS = (('text', 'text'), ('pretty', 'pretty'), ('template', '{message}\n{exception}'), ('json', 'json'))


class FakeTransport:
    """Keeps every message that the SIEM sink sends."""

    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)

    def close(self):
        pass


class HolderWithRepr:
    """An object whose own text holds a password, as the representation of a configuration object can."""

    def __repr__(self):
        return "Holder(password='" + PASSWORD + "')"


class SpacedHolder:
    """An object whose own text holds a double-quoted password with a space in it."""

    def __repr__(self):
        return 'Holder(password="two words")'


class BadRepr:
    """An object that cannot be printed, with a password in the message of its error."""

    def __repr__(self):
        raise RuntimeError("repr failed with " + PASSWORD)


def fail_with_sensitive_variable():
    password = PASSWORD
    return password + 1


def fail_with_secret_object():
    wrapped = Secret(SECRET_VALUE)
    return wrapped + 1


def fail_with_container():
    settings = {"host": "db", "password": PASSWORD}
    return settings["host"] + 1


def fail_with_object():
    holder = HolderWithRepr()
    return holder + 1


def fail_with_nested_container():
    settings = {"name": "app", "database": {"host": "db", "password": PASSWORD}}
    return settings["name"] + 1


def fail_with_list_of_containers():
    servers = [{"host": "a"}, {"host": "b", "api_key": PASSWORD}]
    return servers + 1


def fail_with_large_container():
    big = {f"key{index}": index for index in range(200)}
    big["password"] = PASSWORD
    return big + 1


def fail_with_number_keys():
    settings = {1: "one", 2: "two"}
    return settings + 1


def fail_with_spaced_object():
    holder = SpacedHolder()
    return holder + 1


def fail_with_message():
    raise ValueError("login password=" + PASSWORD)


def check(value):
    raise ValueError("rejected")


def fail_with_literal_in_source():
    check("plain-literal-value")


def fail_with_shaped_literal_in_source():
    check("password=shaped-literal-99")


def inner_step(password):
    return password + 1


def fail_with_cause():
    try:
        inner_step(PASSWORD)
    except TypeError as error:
        raise RuntimeError("outer failed") from error


def fail_with_context():
    try:
        inner_step(PASSWORD)
    except TypeError:
        raise RuntimeError("outer failed")


def fail_without_source():
    namespace = {}
    exec(compile("def broken(password):\n    return password + 1\n", "<generated>", "exec"), namespace)
    namespace['broken'](PASSWORD)


def fail_with_bad_repr():
    item = BadRepr()
    return item + 1


def fail_with_long_text():
    text = "x" * 500
    return text + 1


def render_everywhere(function, mode, processors=None):
    """Runs *function*, logs the error it raises, and returns what each output wrote, by the name of the output."""
    if processors is None:
        processors = [redact_fields(), redact_patterns()]
    logger = Logger('app', logToFile=False, logToStdout=False, diagnose=mode, processors=processors)
    streams = {}
    for surface, layout in LAYOUTS:
        streams[surface] = io.StringIO()
        logger.add(streams[surface], format=layout)
    transport = FakeTransport()
    sink = siem_sink.attach(logger, transport, threaded=False)
    records = []
    logger.add(CallbackSink(lambda text, record: records.append(record)))
    try:
        function()
    except Exception:
        logger.exception("failed")
    siem_sink.detach(logger, sink)
    outputs = {surface: stream.getvalue() for surface, stream in streams.items()}
    outputs['siem'] = b''.join(transport.sent).decode('utf-8')
    outputs['otlp'] = OtlpLogEncoder().encode(records).decode('utf-8')
    return outputs


class SecurityTestCase(unittest.TestCase):

    def assert_hidden(self, outputs, secrets):
        """Checks that no secret is in any output."""
        for surface in SURFACES:
            for secret in secrets:
                with self.subTest(surface=surface, secret=secret):
                    self.assertNotIn(secret, outputs[surface])


class TestEveryOutput(SecurityTestCase):

    def test_every_output_received_the_error(self):
        # Without this, a test that checks that a secret is absent would pass for an output that wrote nothing
        outputs = render_everywhere(fail_with_sensitive_variable, 'full')
        for surface in SURFACES:
            with self.subTest(surface=surface):
                self.assertIn("failed", outputs[surface])
                self.assertIn("TypeError", outputs[surface])

    def test_a_variable_with_a_sensitive_name_is_hidden_in_both_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                outputs = render_everywhere(fail_with_sensitive_variable, mode)
                self.assert_hidden(outputs, (PASSWORD,))
                self.assertRegex(outputs['text'], r"password = (<redacted>|\[REDACTED\])")

    def test_a_secret_object_is_hidden_in_both_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assert_hidden(render_everywhere(fail_with_secret_object, mode), (SECRET_VALUE,))

    def test_the_message_of_an_exception_is_cleaned_by_the_patterns(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                outputs = render_everywhere(fail_with_message, mode)
                self.assert_hidden(outputs, (PASSWORD,))
                self.assertIn("password=[REDACTED]", outputs['text'])

    def test_the_safe_mode_shows_a_container_by_its_type_and_size(self):
        outputs = render_everywhere(fail_with_container, 'summary')
        self.assert_hidden(outputs, (PASSWORD,))
        self.assertIn("settings = <dict len=2>", outputs['text'])

    def test_the_safe_mode_shows_an_object_by_its_type(self):
        outputs = render_everywhere(fail_with_object, 'summary')
        self.assert_hidden(outputs, (PASSWORD,))
        self.assertIn("holder = <HolderWithRepr>", outputs['text'])

    def test_without_diagnostics_no_variable_is_shown(self):
        outputs = render_everywhere(fail_with_sensitive_variable, False)
        self.assert_hidden(outputs, (PASSWORD,))
        self.assertIn("TypeError", outputs['text'])
        self.assertNotIn("password =", outputs['text'])


class TestContainersAndObjects(SecurityTestCase):

    # A dictionary written by repr() is "'password': 'value'", with a quote between the name and the colon, which the text
    # patterns do not read. The value of a sensitive key is hidden when the container is written, as redact_fields does for the fields
    def test_a_sensitive_key_in_a_container_is_hidden_in_full_mode(self):
        self.assert_hidden(render_everywhere(fail_with_container, 'full'), (PASSWORD,))

    # An object writes itself as it likes, so only the text pattern for "name=value", which reads a quoted value, can clean it
    def test_an_assignment_in_the_repr_of_an_object_is_hidden_in_full_mode(self):
        self.assert_hidden(render_everywhere(fail_with_object, 'full'), (PASSWORD,))

    def test_a_sensitive_key_in_a_nested_dictionary_is_hidden(self):
        self.assert_hidden(render_everywhere(fail_with_nested_container, 'full'), (PASSWORD,))

    def test_a_sensitive_key_in_a_list_of_dictionaries_is_hidden(self):
        self.assert_hidden(render_everywhere(fail_with_list_of_containers, 'full'), (PASSWORD,))

    def test_the_other_keys_of_a_container_stay_visible(self):
        text = render_everywhere(fail_with_container, 'full')['text']
        self.assertIn("'host': 'db'", text)
        self.assertIn("'password': '<redacted>'", text)

    def test_a_container_with_many_keys_is_cut_before_the_last_key(self):
        outputs = render_everywhere(fail_with_large_container, 'full')
        self.assert_hidden(outputs, (PASSWORD,))
        self.assertIn("big = {'key0': 0", outputs['text'])

    def test_a_key_that_is_not_text_does_not_break_the_traceback(self):
        outputs = render_everywhere(fail_with_number_keys, 'full')
        self.assertIn("settings = {1: 'one'", outputs['text'])
        self.assertIn("TypeError", outputs['text'])

    def test_a_double_quoted_value_with_spaces_in_an_object_is_hidden(self):
        self.assert_hidden(render_everywhere(fail_with_spaced_object, 'full'), ("two", "words"))

    def test_the_safe_mode_is_not_changed(self):
        outputs = render_everywhere(fail_with_nested_container, 'summary')
        self.assertIn("settings = <dict len=2>", outputs['text'])


class TestWhatTheTracebackShows(SecurityTestCase):

    def test_a_literal_in_the_quoted_source_line_is_shown(self):
        # Python quotes the line of code of each frame, and only a text pattern can recognise a secret in it. This pins that limit
        outputs = render_everywhere(fail_with_literal_in_source, 'summary')
        self.assertIn("plain-literal-value", outputs['text'])
        self.assertIn("plain-literal-value", outputs['json'])

    def test_a_literal_shaped_like_an_assignment_is_hidden(self):
        outputs = render_everywhere(fail_with_shaped_literal_in_source, 'summary')
        self.assert_hidden(outputs, ("shaped-literal-99",))
        self.assertIn("password=[REDACTED]", outputs['text'])

    def test_an_explicit_chain_is_walked_and_every_frame_is_cleaned(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                outputs = render_everywhere(fail_with_cause, mode)
                self.assertIn("direct cause", outputs['text'])
                self.assertIn("RuntimeError: outer failed", outputs['text'])
                self.assertIn("TypeError", outputs['text'])
                self.assertRegex(outputs['text'], r"password = (<redacted>|\[REDACTED\])")
                self.assert_hidden(outputs, (PASSWORD,))

    def test_an_implicit_chain_is_walked_too(self):
        outputs = render_everywhere(fail_with_context, 'full')
        self.assertIn("During handling of the above exception", outputs['text'])
        self.assertRegex(outputs['text'], r"password = (<redacted>|\[REDACTED\])")
        self.assert_hidden(outputs, (PASSWORD,))

    def test_a_frame_without_source_gives_a_plain_traceback(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                outputs = render_everywhere(fail_without_source, mode)
                self.assertIn("TypeError", outputs['text'])
                self.assertIn("<generated>", outputs['text'])
                self.assert_hidden(outputs, (PASSWORD,))

    def test_a_value_that_cannot_be_printed_gives_a_placeholder_that_leaks_nothing(self):
        outputs = render_everywhere(fail_with_bad_repr, 'full')
        self.assertIn("item = <repr failed: RuntimeError>", outputs['text'])
        self.assert_hidden(outputs, (PASSWORD,))
        outputs = render_everywhere(fail_with_bad_repr, 'summary')
        self.assertIn("item = <BadRepr>", outputs['text'])
        self.assert_hidden(outputs, (PASSWORD,))

    def test_a_long_value_is_cut_in_both_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                text = render_everywhere(fail_with_long_text, mode)['text']
                self.assertIn("x" * 199, text)
                self.assertNotIn("x" * 300, text)
                self.assertRegex(text, r"text = 'x+\.\.\.")

    def test_the_variable_lines_are_only_in_the_diagnostic_modes(self):
        for mode, isShown in (('summary', True), ('full', True), (False, False)):
            with self.subTest(mode=mode):
                text = render_everywhere(fail_with_long_text, mode)['text']
                self.assertEqual(re.search(r"^\s+text = ", text, re.MULTILINE) is not None, isShown)


if __name__ == '__main__':
    unittest.main()
