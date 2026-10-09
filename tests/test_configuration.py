"""Tests of the setup: ``add()``, diagnostic exceptions, the ``PYSIMPLELOG_*`` variables and ``disable()`` / ``enable()``.

Run from the repo root::

    python3 -m unittest tests.test_configuration -v
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
import namespaces  # noqa: E402
from simple_log import Logger  # noqa: E402
from default_logger import _DefaultLogger  # noqa: E402
from environment import read_environment  # noqa: E402
from sink_options import parse_size, parse_duration  # noqa: E402
from sinks import Sink, FileSink  # noqa: E402
from secret import Secret  # noqa: E402

# Built from parts so that the value is not written in the source line a traceback quotes
PASSWORD_VALUE = "hunter" + "2"
TOKEN_VALUE = "abc-token" + "-value"

ENV_NAMES = ('PYSIMPLELOG_LEVEL', 'PYSIMPLELOG_FORMAT', 'PYSIMPLELOG_COLOR', 'PYSIMPLELOG_NAMESPACE_DISABLE')


def quiet_logger(name='app', **arguments):
    """Returns a logger with no console and no file."""
    return Logger(name, logToFile=False, logToStdout=False, **arguments)


def lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class EnvironmentCase(unittest.TestCase):
    """A test case that starts and ends with none of the PYSIMPLELOG_ variables set and no namespace disabled."""

    def setUp(self):
        self.saved = {name: os.environ.pop(name, None) for name in ENV_NAMES}
        self.disabled = []

    def tearDown(self):
        for name in self.disabled:
            namespaces.enable(name)
        for name, value in self.saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value

    def disable(self, name, **arguments):
        self.disabled.append(name)
        namespaces.disable(name, **arguments)


class TestAdd(unittest.TestCase):

    def test_sizes_are_read_in_megabytes(self):
        self.assertEqual(parse_size("500 MB"), 500.0)
        self.assertEqual(parse_size("1 GB"), 1024.0)
        self.assertEqual(parse_size("512 KB"), 0.5)
        self.assertEqual(parse_size("500mb"), 500.0)
        self.assertEqual(parse_size(10), 10.0)

    def test_durations_are_read_in_seconds(self):
        self.assertEqual(parse_duration("30 days"), 30 * 86400.0)
        self.assertEqual(parse_duration("2 hours"), 7200.0)
        self.assertEqual(parse_duration("1 week"), 7 * 86400.0)
        self.assertEqual(parse_duration("90 seconds"), 90.0)

    def test_a_size_or_a_duration_with_a_wrong_unit_is_refused(self):
        with self.assertRaises(ValueError):
            parse_size("5 days")
        with self.assertRaises(ValueError):
            parse_size("big")
        with self.assertRaises(ValueError):
            parse_duration("5 MB")
        with self.assertRaises(ValueError):
            parse_duration("soon")
        with self.assertRaises(TypeError):
            parse_size(None)
        with self.assertRaises(TypeError):
            parse_size(True)

    def test_a_path_makes_a_file_that_gets_the_records(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = quiet_logger()
            name = logger.add(os.path.join(folder, "app.log"))
            logger.info("to the file")
            logger.remove(name)
            files = os.listdir(folder)
            self.assertEqual(len(files), 1)
            with open(os.path.join(folder, files[0])) as handle:
                self.assertIn("to the file", handle.read())

    def test_rotation_and_retention_in_plain_words(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = quiet_logger()
            name = logger.add(os.path.join(folder, "app.log"), rotation="1 KB", retention=3)
            for number in range(200):
                logger.info("a line that is long enough to fill the file quickly {}", number)
            logger.remove(name)
            files = [file for file in os.listdir(folder) if file.startswith("app")]
            self.assertGreater(len(files), 1)
            self.assertLessEqual(len(files), 4)

    def test_the_json_format_writes_one_object_per_line(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = quiet_logger()
            name = logger.add(os.path.join(folder, "app.jsonl"), format="json")
            logger.info("first", order_id=1)
            logger.info("second")
            logger.remove(name)
            with open(os.path.join(folder, os.listdir(folder)[0])) as handle:
                records = [json.loads(line) for line in handle.read().splitlines()]
            self.assertEqual([record['message'] for record in records], ["first", "second"])
            self.assertEqual(records[0]['fields'], {'order_id': 1})

    def test_a_stream_a_function_and_a_sink_are_accepted(self):
        stream = io.StringIO()
        received = []

        class Mine(Sink):
            def write(self, text, record):
                received.append(('sink', record.message))

        logger = quiet_logger()
        logger.add(stream)
        logger.add(lambda text, record: received.append(('function', record.message)))
        logger.add(Mine())
        logger.info("hello")
        self.assertIn("hello", stream.getvalue())
        self.assertEqual(sorted(received), [('function', 'hello'), ('sink', 'hello')])

    def test_the_level_picks_the_records_of_an_output(self):
        logger = quiet_logger()
        errors, everything = io.StringIO(), io.StringIO()
        logger.add(errors, level="ERROR")
        logger.add(everything, level="debug")
        logger.info("quiet")
        logger.error("loud")
        self.assertNotIn("quiet", errors.getvalue())
        self.assertIn("loud", errors.getvalue())
        self.assertIn("quiet", everything.getvalue())

    def test_a_filter_picks_the_records_of_an_output(self):
        logger = quiet_logger()
        stream = io.StringIO()
        logger.add(stream, filter=lambda record: record.fields.get("keep") is True)
        logger.info("dropped")
        logger.info("kept", keep=True)
        self.assertNotIn("dropped", stream.getvalue())
        self.assertIn("kept", stream.getvalue())

    def test_each_add_gives_a_name_and_remove_stops_the_output(self):
        logger = quiet_logger()
        first, second = io.StringIO(), io.StringIO()
        nameOne = logger.add(first)
        nameTwo = logger.add(second)
        self.assertNotEqual(nameOne, nameTwo)
        logger.remove(nameOne)
        logger.info("after")
        self.assertEqual(first.getvalue(), '')
        self.assertIn("after", second.getvalue())

    def test_a_chosen_name_is_returned_and_cannot_be_used_twice(self):
        logger = quiet_logger()
        self.assertEqual(logger.add(io.StringIO(), name="audit"), "audit")
        with self.assertRaises(Exception):
            logger.add(io.StringIO(), name="audit")

    def test_wrong_calls_are_refused_with_a_clear_error(self):
        logger = quiet_logger()
        with self.assertRaises(TypeError):
            logger.add(io.StringIO(), rotation="1 MB")
        with self.assertRaises(TypeError):
            logger.add(12345)
        with self.assertRaises(TypeError):
            logger.add(FileSink("x"), format="json")
        with self.assertRaises(ValueError):
            logger.add(io.StringIO(), level="LOUD")
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                logger.add(os.path.join(folder, "app.log"), rotation="fast")

    def test_a_failed_add_leaves_no_output_behind(self):
        logger = quiet_logger()
        before = list(logger.sink_stats())
        with self.assertRaises(ValueError):
            logger.add(io.StringIO(), level="LOUD")
        self.assertEqual(list(logger.sink_stats()), before)


def failing_charge(password, token, count):
    """Fails on a line that uses the three variables, which are the ones a diagnosis shows."""
    return password + token + count


def failing_with_user(user, amount):
    return user + amount


class TestDiagnose(unittest.TestCase):

    def make(self, diagnose, **arguments):
        stream = io.StringIO()
        logger = quiet_logger(diagnose=diagnose, **arguments)
        logger.add(stream, format='json')
        return logger, stream

    def exception_text(self, logger, stream, call):
        try:
            call()
        except Exception:
            logger.exception("failed")
        return lines(stream)[0]['exception']['stacktrace']

    def test_it_is_off_by_default_and_shows_no_values(self):
        logger, stream = self.make(False)
        text = self.exception_text(logger, stream, lambda: failing_with_user("ann", 5))
        self.assertNotIn("amount = 5", text)
        self.assertEqual(logger.diagnose, False)

    def test_summary_shows_the_variables_of_the_failing_line(self):
        logger, stream = self.make('summary')
        text = self.exception_text(logger, stream, lambda: failing_with_user("ann", 5))
        self.assertIn("user = 'ann'", text)
        self.assertIn("amount = 5", text)
        self.assertIn("TypeError", text)

    def test_full_shows_the_repr_of_containers_and_summary_only_their_size(self):
        def call():
            items = [1, 2, 3]
            return items + 5

        summary, summaryStream = self.make('summary')
        full, fullStream = self.make('full')
        self.assertIn("items = <list len=3>", self.exception_text(summary, summaryStream, call))
        self.assertIn("items = [1, 2, 3]", self.exception_text(full, fullStream, call))

    def test_sensitive_names_are_never_shown(self):
        for mode in ('summary', 'full'):
            logger, stream = self.make(mode)
            text = self.exception_text(logger, stream, lambda: failing_charge(PASSWORD_VALUE, TOKEN_VALUE, 3))
            self.assertNotIn(PASSWORD_VALUE, text)
            self.assertNotIn(TOKEN_VALUE, text)
            self.assertIn("password = <redacted>", text)
            self.assertIn("token = <redacted>", text)
            self.assertIn("count = 3", text)

    def test_names_added_by_the_caller_are_hidden_too(self):
        def call():
            ssn = "078-05-1120"
            return ssn + 5

        logger, stream = self.make('summary', diagnoseRedact=('ssn',))
        text = self.exception_text(logger, stream, call)
        self.assertNotIn("078-05-1120", text)
        self.assertIn("ssn = <redacted>", text)

    def test_a_name_that_contains_a_sensitive_word_is_hidden(self):
        def call():
            api_key_value = "sk-live-123"
            return api_key_value + 5

        logger, stream = self.make('summary')
        text = self.exception_text(logger, stream, call)
        self.assertNotIn("sk-live-123", text)

    def test_a_secret_is_never_shown_even_under_a_harmless_name(self):
        def call():
            harmless = Secret("top-value")
            return harmless + 5

        logger, stream = self.make('full')
        text = self.exception_text(logger, stream, call)
        self.assertNotIn("top-value", text)

    def test_the_variables_of_chained_exceptions_are_shown_and_hidden_the_same_way(self):
        def call():
            try:
                failing_charge(PASSWORD_VALUE, TOKEN_VALUE, 3)
            except TypeError as error:
                amount = 5
                raise ValueError(amount) from error

        logger, stream = self.make('summary')
        text = self.exception_text(logger, stream, call)
        self.assertNotIn(PASSWORD_VALUE, text)
        self.assertNotIn(TOKEN_VALUE, text)
        self.assertIn("password = <redacted>", text)
        self.assertIn("direct cause", text)

    def test_the_diagnosis_reaches_the_message_of_no_other_field(self):
        logger, stream = self.make('summary')
        self.exception_text(logger, stream, lambda: failing_charge(PASSWORD_VALUE, TOKEN_VALUE, 3))
        record = lines(stream)[0]
        self.assertEqual(record['exception']['type'], 'TypeError')
        self.assertNotIn("<redacted>", record['message'])

    def test_it_can_be_turned_on_and_off_while_running(self):
        logger, stream = self.make(False)
        logger.set_diagnose('summary')
        text = self.exception_text(logger, stream, lambda: failing_with_user("ann", 5))
        self.assertIn("amount = 5", text)
        logger.set_diagnose(False)
        stream.truncate(0)
        stream.seek(0)
        text = self.exception_text(logger, stream, lambda: failing_with_user("ann", 5))
        self.assertNotIn("amount = 5", text)

    def test_a_value_it_cannot_show_never_loses_the_traceback(self):
        class Broken:
            def __repr__(self):
                raise RuntimeError("no repr")

            def __add__(self, other):
                raise TypeError("cannot add")

        def call():
            broken = Broken()
            return broken + 1

        logger, stream = self.make('full')
        text = self.exception_text(logger, stream, call)
        self.assertIn("TypeError: cannot add", text)

    def test_true_means_summary(self):
        self.assertEqual(quiet_logger(diagnose=True).diagnose, 'summary')
        logger = quiet_logger()
        logger.set_diagnose(True)
        self.assertEqual(logger.diagnose, 'summary')

    def test_only_false_true_summary_and_full_are_accepted(self):
        for wrong in ('verbose', 1, None):
            with self.assertRaises(ValueError):
                quiet_logger(diagnose=wrong)


class TestEnvironment(EnvironmentCase):

    def test_nothing_set_gives_nothing(self):
        self.assertEqual(read_environment(), {})

    def test_the_three_variables_are_read(self):
        os.environ['PYSIMPLELOG_LEVEL'] = 'WARNING'
        os.environ['PYSIMPLELOG_FORMAT'] = 'json'
        os.environ['PYSIMPLELOG_COLOR'] = 'never'
        self.assertEqual(read_environment(),
                         {'stdoutMinLevel': 'WARNING', 'consoleFormatter': 'json', 'consoleColor': 'never'})

    def test_a_numeric_level_is_a_number(self):
        os.environ['PYSIMPLELOG_LEVEL'] = '30'
        self.assertEqual(read_environment()['stdoutMinLevel'], 30.0)

    def test_empty_and_blank_variables_are_ignored(self):
        os.environ['PYSIMPLELOG_LEVEL'] = ''
        os.environ['PYSIMPLELOG_FORMAT'] = '   '
        self.assertEqual(read_environment(), {})

    def test_the_color_is_case_insensitive(self):
        os.environ['PYSIMPLELOG_COLOR'] = 'ALWAYS'
        self.assertEqual(read_environment()['consoleColor'], 'always')

    def test_a_template_is_a_valid_format(self):
        os.environ['PYSIMPLELOG_FORMAT'] = '{timestamp} {message}'
        self.assertEqual(read_environment()['consoleFormatter'], '{timestamp} {message}')

    def test_a_wrong_format_names_the_variable(self):
        os.environ['PYSIMPLELOG_FORMAT'] = 'no-such-layout'
        with self.assertRaises(ValueError) as caught:
            read_environment()
        self.assertIn('PYSIMPLELOG_FORMAT', str(caught.exception))

    def test_a_wrong_color_names_the_variable(self):
        os.environ['PYSIMPLELOG_COLOR'] = 'purple'
        with self.assertRaises(ValueError) as caught:
            read_environment()
        self.assertIn('PYSIMPLELOG_COLOR', str(caught.exception))

    def test_a_logger_ignores_the_environment_unless_asked(self):
        os.environ['PYSIMPLELOG_LEVEL'] = 'error'
        self.assertNotEqual(Logger('a', logToFile=False).stdoutMinLevel, 30.0)

    def test_a_logger_that_asks_takes_the_environment(self):
        os.environ['PYSIMPLELOG_LEVEL'] = 'error'
        os.environ['PYSIMPLELOG_COLOR'] = 'never'
        logger = Logger('a', logToFile=False, env=True)
        self.assertEqual(logger.stdoutMinLevel, 30.0)
        self.assertEqual(logger.consoleColor, 'never')

    def test_precedence_explicit_then_environment_then_default(self):
        os.environ['PYSIMPLELOG_LEVEL'] = 'error'
        os.environ['PYSIMPLELOG_COLOR'] = 'never'
        explicit = Logger('a', logToFile=False, env=True, stdoutMinLevel=10, consoleColor='always')
        self.assertEqual(explicit.stdoutMinLevel, 10)
        self.assertEqual(explicit.consoleColor, 'always')
        fromEnvironment = Logger('a', logToFile=False, env=True)
        self.assertEqual(fromEnvironment.consoleColor, 'never')
        os.environ.pop('PYSIMPLELOG_COLOR')
        self.assertEqual(Logger('a', logToFile=False, env=True).consoleColor, 'auto')

    def test_a_wrong_level_in_the_environment_names_the_variable(self):
        os.environ['PYSIMPLELOG_LEVEL'] = 'LOUD'
        with self.assertRaises(ValueError) as caught:
            Logger('a', logToFile=False, env=True)
        self.assertIn('PYSIMPLELOG_LEVEL', str(caught.exception))

    def test_the_shared_logger_uses_the_environment_and_pretty_by_default(self):
        plain = _DefaultLogger()
        self.assertEqual(plain.instance.stdoutMinLevel, plain.instance.stdoutMinLevel)
        os.environ['PYSIMPLELOG_LEVEL'] = 'critical'
        shared = _DefaultLogger()
        self.assertEqual(shared.instance.stdoutMinLevel, 100.0)

    def test_the_variables_are_read_once_when_the_logger_is_made(self):
        os.environ['PYSIMPLELOG_LEVEL'] = 'error'
        logger = Logger('a', logToFile=False, env=True)
        os.environ['PYSIMPLELOG_LEVEL'] = 'debug'
        self.assertEqual(logger.stdoutMinLevel, 30.0)


class TestEnableAndDisable(EnvironmentCase):

    def setUp(self):
        super().setUp()
        self.stream = io.StringIO()

    def logger(self, name):
        logger = quiet_logger(name)
        logger.add(self.stream, format='json')
        return logger

    def test_a_disabled_name_is_silent(self):
        self.disable("payments")
        self.logger("payments").error("hidden")
        self.assertEqual(self.stream.getvalue(), '')

    def test_the_whole_branch_below_the_name_is_silent(self):
        self.disable("payments")
        self.logger("payments.stripe").error("hidden")
        self.logger("payments.stripe.webhooks").error("hidden")
        self.assertEqual(self.stream.getvalue(), '')

    def test_a_name_that_only_starts_the_same_is_not_silenced(self):
        self.disable("pay")
        self.logger("payments").error("shown")
        self.logger("pay.sub").error("hidden")
        self.assertEqual([record['message'] for record in lines(self.stream)], ["shown"])

    def test_a_branch_is_not_silenced_by_a_name_below_it(self):
        self.disable("payments.stripe")
        self.logger("payments").error("shown")
        self.logger("payments.db").error("shown too")
        self.logger("payments.stripe").error("hidden")
        self.assertEqual(len(lines(self.stream)), 2)

    def test_enable_brings_the_records_back(self):
        self.disable("payments")
        logger = self.logger("payments")
        logger.error("hidden")
        namespaces.enable("payments")
        logger.error("shown")
        self.assertEqual([record['message'] for record in lines(self.stream)], ["shown"])

    def test_it_applies_to_loggers_made_before_and_after(self):
        before = self.logger("payments")
        self.disable("payments")
        after = self.logger("payments")
        before.error("hidden")
        after.error("hidden")
        self.assertEqual(self.stream.getvalue(), '')

    def test_other_loggers_are_not_affected(self):
        self.disable("payments")
        self.logger("orders").error("shown")
        self.assertEqual(len(lines(self.stream)), 1)

    def test_force_log_is_not_affected(self):
        self.disable("payments")
        logger = self.logger("payments")
        logger.force_log("error", "forced")
        logger.error("hidden")
        self.assertEqual([record['message'] for record in lines(self.stream)], ["forced"])

    def test_enable_of_a_name_never_disabled_does_nothing(self):
        namespaces.enable("never.disabled")
        self.logger("never.disabled").error("shown")
        self.assertEqual(len(lines(self.stream)), 1)

    def test_a_wrong_name_is_refused(self):
        for bad in ("", "a..b", ".a", "a."):
            with self.assertRaises(ValueError):
                namespaces.disable(bad)
        with self.assertRaises(TypeError):
            namespaces.disable(5)
        with self.assertRaises(TypeError):
            namespaces.disable("a", env="yes")

    def test_env_true_writes_the_variable_and_enable_removes_it(self):
        self.disable("urllib3", env=True)
        self.assertIn("urllib3", os.environ['PYSIMPLELOG_NAMESPACE_DISABLE'].split(','))
        namespaces.enable("urllib3", env=True)
        self.assertNotIn("PYSIMPLELOG_NAMESPACE_DISABLE", os.environ)

    def test_the_standard_logging_bridge_obeys_it(self):
        import logging
        from standard_logging import redirect_standard_logging, restore_standard_logging
        logger = quiet_logger("bridge")
        logger.add(self.stream, format='json')
        handler = redirect_standard_logging(logger, name="payments.stripe", loggerLevel=logging.DEBUG)
        try:
            self.disable("payments")
            logging.getLogger("payments.stripe").error("hidden")
        finally:
            restore_standard_logging(handler)
        self.assertEqual(self.stream.getvalue(), '')

    def run_child(self, environment):
        code = ("import sys; sys.path.insert(0, %r)\n"
                "import io, namespaces\n"
                "from simple_log import Logger\n"
                "stream = io.StringIO()\n"
                "logger = Logger('payments.stripe', logToFile=False, logToStdout=False)\n"
                "logger.add(stream)\n"
                "logger.error('x')\n"
                "print(repr(stream.getvalue()))\n") % PACKAGE_DIR
        env = {key: value for key, value in os.environ.items() if key != 'PYSIMPLELOG_NAMESPACE_DISABLE'}
        env.update(environment)
        done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def test_a_program_started_with_the_variable_has_the_names_disabled(self):
        self.assertEqual(self.run_child({'PYSIMPLELOG_NAMESPACE_DISABLE': 'payments, urllib3'}), "''")

    def test_a_program_started_without_the_variable_logs(self):
        self.assertIn("x", self.run_child({}))



class TestLevelsAsWords(unittest.TestCase):

    def test_the_constructor_takes_a_log_type_key_or_name(self):
        for word in ('warn', 'WARNING', 'Warning'):
            logger = Logger('app', logToFile=False, logToStdout=False, stdoutMinLevel=word)
            self.assertEqual(logger.stdoutMinLevel, 20.0)
        logger = Logger('app', logToFile=False, logToStdout=False, stdoutMinLevel='info', stdoutMaxLevel='CRITICAL',
                        fileMinLevel='debug', fileMaxLevel='error')
        self.assertEqual((logger.stdoutMinLevel, logger.stdoutMaxLevel), (10.0, 100.0))
        self.assertEqual((logger.fileMinLevel, logger.fileMaxLevel), (0.0, 30.0))

    def test_a_word_picks_what_the_console_writes(self):
        console = io.StringIO()
        logger = Logger('app', logToFile=False, stdout=console, stdoutMinLevel='warn')
        logger.info('quiet')
        logger.error('loud')
        self.assertNotIn('quiet', console.getvalue())
        self.assertIn('loud', console.getvalue())

    def test_numbers_still_work(self):
        logger = Logger('app', logToFile=False, logToStdout=False, stdoutMinLevel=15)
        self.assertEqual(logger.stdoutMinLevel, 15.0)

    def test_the_setters_take_words_too(self):
        logger = quiet_logger()
        logger.set_minimum_level('ERROR')
        logger.set_maximum_level('critical')
        self.assertEqual((logger.stdoutMinLevel, logger.stdoutMaxLevel), (30.0, 100.0))

    def test_an_unknown_word_is_refused(self):
        with self.assertRaises(ValueError):
            Logger('app', logToFile=False, logToStdout=False, stdoutMinLevel='loud')
        with self.assertRaises(ValueError):
            quiet_logger().set_minimum_level('loud')

    def test_a_minimum_above_the_maximum_is_still_refused(self):
        with self.assertRaises(ValueError):
            Logger('app', logToFile=False, logToStdout=False, stdoutMinLevel='error', stdoutMaxLevel='info')


class TestConsoleLayout(unittest.TestCase):

    def test_a_logger_writes_the_column_layout_by_default(self):
        console = io.StringIO()
        logger = Logger('api.users', logToFile=False, stdout=console)
        logger.warning('Retry 2/3')
        self.assertIn('| WARNING  | api.users | Retry 2/3', console.getvalue())

    def test_the_text_layout_is_still_available(self):
        console = io.StringIO()
        logger = Logger('api.users', logToFile=False, stdout=console, consoleFormatter='text')
        logger.warning('Retry 2/3')
        self.assertIn('api.users <WARNING> Retry 2/3', console.getvalue())

    def test_the_environment_replaces_the_default_layout(self):
        saved = os.environ.get('PYSIMPLELOG_FORMAT')
        os.environ['PYSIMPLELOG_FORMAT'] = 'json'
        try:
            console = io.StringIO()
            logger = Logger('app', logToFile=False, stdout=console, env=True)
            logger.info('x')
        finally:
            os.environ.pop('PYSIMPLELOG_FORMAT', None)
            if saved is not None:
                os.environ['PYSIMPLELOG_FORMAT'] = saved
        self.assertEqual(json.loads(console.getvalue())['message'], 'x')

    def test_the_log_file_keeps_the_text_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = Logger('app', logToStdout=False, logFile=os.path.join(folder, 'app.log'))
            logger.warning('to the file')
            logger.flush()
            logger.clear_sinks()
            text = ''
            for name in os.listdir(folder):
                with open(os.path.join(folder, name)) as handle:
                    text += handle.read()
        self.assertIn('app <WARNING> to the file', text)


class TestRelativePaths(unittest.TestCase):

    def setUp(self):
        self.start = os.getcwd()
        self.folder = os.path.realpath(tempfile.mkdtemp(prefix='paths-'))
        os.makedirs(os.path.join(self.folder, 'first'))
        os.makedirs(os.path.join(self.folder, 'second'))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        os.chdir(self.start)
        import shutil
        shutil.rmtree(self.folder, ignore_errors=True)

    def write_after_moving(self, logger):
        os.chdir(os.path.join(self.folder, 'first'))
        logger.info('one ' * 50)
        os.chdir(os.path.join(self.folder, 'second'))
        for number in range(30):
            logger.info('after the move {} {}', number, 'x' * 100)
        logger.flush()
        logger.clear_sinks()
        return sorted(os.listdir(os.path.join(self.folder, 'first'))), sorted(os.listdir(os.path.join(self.folder, 'second')))

    def test_a_file_added_with_a_relative_path_stays_where_it_started(self):
        os.chdir(os.path.join(self.folder, 'first'))
        logger = quiet_logger()
        logger.add('logs/app.log', rotation='1 KB')
        first, second = self.write_after_moving(logger)
        self.assertEqual(first, ['logs'])
        self.assertEqual(second, [])

    def test_the_built_in_file_stays_where_it_started(self):
        os.chdir(os.path.join(self.folder, 'first'))
        logger = Logger('app', logToStdout=False, logToFile=True, logFile='logs/app.log', logFileMaxSize=0.001)
        first, second = self.write_after_moving(logger)
        self.assertEqual(first, ['logs'])
        self.assertEqual(second, [])

    def test_the_built_in_file_that_is_switched_on_later_stays_where_it_started(self):
        os.chdir(os.path.join(self.folder, 'first'))
        logger = Logger('app', logToStdout=False, logToFile=False, logFile='logs/app.log', logFileMaxSize=0.001)
        os.chdir(os.path.join(self.folder, 'second'))
        logger.set_log_to_file_flag(True)
        logger.info('written after the switch')
        logger.flush()
        logger.clear_sinks()
        self.assertEqual(sorted(os.listdir(os.path.join(self.folder, 'first'))), ['logs'])
        self.assertEqual(sorted(os.listdir(os.path.join(self.folder, 'second'))), [])

    def test_the_path_of_a_sink_is_absolute(self):
        os.chdir(self.folder)
        sink = FileSink('logs/app')
        self.assertTrue(os.path.isabs(sink.path))
        self.assertEqual(os.path.dirname(sink.path), os.path.join(self.folder, 'logs'))
        sink.close()


if __name__ == '__main__':
    unittest.main()
