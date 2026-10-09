"""Tests of the everyday calls: ``{}`` formatting, ``opt()`` (lazy values, exceptions, caller depth) and the pretty console layout.

Run from the repo root::

    python3 -m unittest tests.test_experience -v
"""
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import ConsoleFormatter, stream_supports_color  # noqa: E402
from sinks import StreamSink  # noqa: E402


def make_logger(level='info', **arguments):
    """Returns a logger with no console and no file, and a JSON output that keeps what it gets in a stream."""
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add(stream, format='json', level=level)
    return logger, stream


def lines(stream):
    """Returns the records written to a stream as dictionaries."""
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class TestBraceFormatting(unittest.TestCase):

    def test_positional_values_fill_the_places_in_order(self):
        logger, stream = make_logger()
        logger.info("User {} logged in from {}", 7, "Paris")
        self.assertEqual(lines(stream)[0]['message'], "User 7 logged in from Paris")

    def test_numbered_places_can_repeat_a_value(self):
        logger, stream = make_logger()
        logger.info("{0} then {1} then {0}", "a", "b")
        self.assertEqual(lines(stream)[0]['message'], "a then b then a")

    def test_named_values_fill_the_places_and_stay_fields(self):
        logger, stream = make_logger()
        logger.info("Processing order {order_id}", order_id=123)
        record = lines(stream)[0]
        self.assertEqual(record['message'], "Processing order 123")
        self.assertEqual(record['fields'], {'order_id': 123})

    def test_positional_and_named_values_mix(self):
        logger, stream = make_logger()
        logger.info("User {} logged in", 7, user_id=7, service="auth")
        record = lines(stream)[0]
        self.assertEqual(record['message'], "User 7 logged in")
        self.assertEqual(record['fields'], {'user_id': 7, 'service': 'auth'})

    def test_positional_values_are_not_stored_as_fields(self):
        logger, stream = make_logger()
        logger.info("Value {}", 5)
        self.assertNotIn('fields', lines(stream)[0])

    def test_a_message_with_braces_and_no_values_is_written_as_it_is(self):
        logger, stream = make_logger()
        logger.info("the set is {1, 2} and the key {name}")
        self.assertEqual(lines(stream)[0]['message'], "the set is {1, 2} and the key {name}")

    def test_a_template_that_does_not_fit_its_values_never_raises(self):
        logger, stream = make_logger()
        logger.info("two places {} {}", 1)
        logger.info("a name that is missing {missing}", other=1)
        written = [record['message'] for record in lines(stream)]
        self.assertEqual(written[0], "two places {} {}")
        self.assertEqual(written[1], "a name that is missing {missing}")

    def test_a_place_cannot_reach_inside_a_value(self):
        logger, stream = make_logger()
        logger.info("name is {0.name}", logger)
        self.assertEqual(lines(stream)[0]['message'], "name is {0.name}")

    def test_a_format_spec_is_applied(self):
        logger, stream = make_logger()
        logger.info("Took {:.2f} seconds", 1.23456)
        self.assertEqual(lines(stream)[0]['message'], "Took 1.23 seconds")

    def test_the_message_and_the_fields_stay_coherent_in_one_record(self):
        logger, stream = make_logger()
        with logger.context(request_id="r-1"):
            logger.info("User {} logged in", 7, user_id=7, service="auth")
        record = lines(stream)[0]
        self.assertEqual(record['message'], "User 7 logged in")
        self.assertEqual(record['fields'], {'user_id': 7, 'service': 'auth'})
        self.assertEqual(record['context'], {'request_id': 'r-1'})
        self.assertEqual(record['severity'], 'INFO')


class TestLazyValues(unittest.TestCase):

    def setUp(self):
        self.calls = []

    def expensive(self):
        self.calls.append(1)
        return 42

    def test_the_function_is_not_called_when_the_level_is_below_every_output(self):
        logger, stream = make_logger(level='info')
        logger.opt(lazy=True).debug("Result: {}", self.expensive)
        self.assertEqual(self.calls, [])
        self.assertEqual(stream.getvalue(), '')

    def test_the_function_is_not_called_when_no_output_is_left(self):
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.opt(lazy=True).error("Result: {}", self.expensive)
        self.assertEqual(self.calls, [])

    def test_the_function_is_not_called_when_the_namespace_is_disabled(self):
        import namespaces
        logger, stream = make_logger()
        namespaces.disable("app")
        try:
            logger.opt(lazy=True).info("Result: {}", self.expensive)
        finally:
            namespaces.enable("app")
        self.assertEqual(self.calls, [])
        self.assertEqual(stream.getvalue(), '')

    def test_the_function_is_called_once_and_its_value_written_when_the_record_is_written(self):
        logger, stream = make_logger()
        logger.opt(lazy=True).info("Result: {}", self.expensive)
        self.assertEqual(self.calls, [1])
        self.assertEqual(lines(stream)[0]['message'], "Result: 42")

    def test_the_function_is_called_once_for_many_outputs(self):
        logger, first = make_logger()
        second = io.StringIO()
        logger.add(second, format='json')
        logger.opt(lazy=True).info("Result: {}", self.expensive)
        self.assertEqual(self.calls, [1])
        self.assertEqual(lines(first)[0]['message'], lines(second)[0]['message'])

    def test_the_function_is_not_called_for_the_output_whose_level_is_too_high(self):
        logger, quiet = make_logger(level='error')
        loud = io.StringIO()
        logger.add(loud, format='json', level='debug')
        logger.opt(lazy=True).info("Result: {}", self.expensive)
        self.assertEqual(self.calls, [1])
        self.assertEqual(quiet.getvalue(), '')
        self.assertEqual(len(lines(loud)), 1)

    def test_the_function_is_called_in_the_calling_thread_with_the_logger_queue(self):
        import threading
        names = []

        def function():
            names.append(threading.current_thread().name)
            return 1

        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False, enqueue=True)
        try:
            logger.add(stream, format='json')
            logger.opt(lazy=True).info("Result: {}", function)
            logger.flush()
        finally:
            logger.clear_sinks()
        self.assertEqual(names, [threading.current_thread().name])
        self.assertEqual(lines(stream)[0]['message'], "Result: 1")

    def test_the_function_is_not_called_with_the_logger_queue_when_the_level_is_off(self):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False, enqueue=True)
        try:
            logger.add(stream, format='json', level='error')
            logger.opt(lazy=True).info("Result: {}", self.expensive)
            logger.flush()
        finally:
            logger.clear_sinks()
        self.assertEqual(self.calls, [])

    def test_the_function_is_not_called_in_a_threaded_sink_for_a_record_below_its_level(self):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add(stream, format='json', level='error', threaded=True)
        try:
            logger.opt(lazy=True).info("Result: {}", self.expensive)
            logger.flush()
        finally:
            logger.clear_sinks()
        self.assertEqual(self.calls, [])

    def test_a_value_that_is_not_a_function_is_used_as_it_is(self):
        logger, stream = make_logger()
        logger.opt(lazy=True).info("Result: {}", 5)
        self.assertEqual(lines(stream)[0]['message'], "Result: 5")

    def test_without_lazy_a_function_is_written_as_a_value(self):
        logger, stream = make_logger()
        logger.info("Result: {}", self.expensive)
        self.assertEqual(self.calls, [])
        self.assertTrue(lines(stream)[0]['message'].startswith("Result: "))

    def test_a_function_that_raises_never_breaks_the_log_call(self):
        logger, stream = make_logger()

        def broken():
            raise RuntimeError("no value")

        logger.opt(lazy=True).info("Result: {}", broken)
        self.assertEqual(len(lines(stream)), 1)


class TestOptException(unittest.TestCase):

    def test_exception_true_records_the_exception_being_handled(self):
        logger, stream = make_logger()
        try:
            int("x")
        except ValueError:
            logger.opt(exception=True).error("Payment calculation failed")
        exception = lines(stream)[0]['exception']
        self.assertEqual(exception['type'], 'ValueError')
        self.assertIn("invalid literal", exception['message'])
        self.assertIn("Traceback", exception['stacktrace'])

    def test_exception_with_an_object_records_that_exception(self):
        logger, stream = make_logger()
        error = KeyError("missing")
        logger.opt(exception=error).error("Lookup failed")
        self.assertEqual(lines(stream)[0]['exception']['type'], 'KeyError')

    def test_the_logger_exception_call_is_the_same_as_opt_exception(self):
        logger, stream = make_logger()
        try:
            1 / 0
        except ZeroDivisionError:
            logger.exception("first")
            logger.opt(exception=True).error("second")
        first, second = lines(stream)
        self.assertEqual(first['exception']['type'], second['exception']['type'])
        self.assertEqual(first['exception']['message'], second['exception']['message'])

    def test_chained_exceptions_are_all_in_the_traceback(self):
        logger, stream = make_logger()
        try:
            try:
                1 / 0
            except ZeroDivisionError as error:
                raise ValueError("wrapped") from error
        except ValueError:
            logger.exception("failed")
        text = lines(stream)[0]['exception']['stacktrace']
        self.assertIn("ZeroDivisionError", text)
        self.assertIn("direct cause", text)
        self.assertIn("ValueError: wrapped", text)

    def test_an_exception_of_the_context_is_chained_too(self):
        logger, stream = make_logger()
        try:
            try:
                1 / 0
            except ZeroDivisionError:
                raise ValueError("while handling")
        except ValueError:
            logger.exception("failed")
        text = lines(stream)[0]['exception']['stacktrace']
        self.assertIn("During handling of the above exception", text)

    def test_the_fields_and_the_context_are_kept_with_the_exception(self):
        logger, stream = make_logger()
        with logger.context(request_id="r-9"):
            try:
                1 / 0
            except ZeroDivisionError:
                logger.exception("failed", order_id=5)
        record = lines(stream)[0]
        self.assertEqual(record['fields'], {'order_id': 5})
        self.assertEqual(record['context'], {'request_id': 'r-9'})
        self.assertEqual(record['exception']['type'], 'ZeroDivisionError')

    def test_exception_true_with_no_exception_being_handled_records_none(self):
        logger, stream = make_logger()
        logger.opt(exception=True).error("nothing is being handled")
        self.assertNotIn('exception', lines(stream)[0])

    def test_the_text_layout_writes_the_traceback(self):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False)
        logger.add(stream)
        try:
            1 / 0
        except ZeroDivisionError:
            logger.exception("failed")
        self.assertIn("ZeroDivisionError: division by zero", stream.getvalue())


class TestCallerDepth(unittest.TestCase):

    def test_without_depth_the_caller_is_the_line_that_called_the_logger(self):
        logger, stream = make_logger(callerInfo=True)

        def helper():
            logger.info("inside the helper")

        helper()
        caller = lines(stream)[0]['caller']
        self.assertEqual(caller['function'], 'helper')

    def test_depth_one_names_the_caller_of_the_wrapper(self):
        logger, stream = make_logger(callerInfo=True)

        def wrapper(message):
            logger.opt(depth=1).info(message)

        def application_code():
            wrapper("from the application")

        application_code()
        caller = lines(stream)[0]['caller']
        self.assertEqual(caller['function'], 'application_code')
        self.assertEqual(caller['module'], __name__)
        self.assertTrue(caller['file'].endswith('test_experience.py'))

    def test_the_line_number_is_the_line_of_the_wrapper_call(self):
        logger, stream = make_logger(callerInfo=True)

        def wrapper():
            logger.opt(depth=1).info("x")

        wrapper(); expected = sys._getframe().f_lineno  # noqa: E702
        self.assertEqual(lines(stream)[0]['caller']['line'], expected)

    def test_depth_two_goes_up_two_wrappers(self):
        logger, stream = make_logger(callerInfo=True)

        def inner():
            logger.opt(depth=2).info("x")

        def middle():
            inner()

        def outer():
            middle()

        outer()
        self.assertEqual(lines(stream)[0]['caller']['function'], 'outer')

    def test_depth_works_with_a_bound_logger(self):
        logger, stream = make_logger(callerInfo=True)
        bound = logger.bind(service="auth")

        def wrapper():
            bound.opt(depth=1).info("x")

        def application_code():
            wrapper()

        application_code()
        self.assertEqual(lines(stream)[0]['caller']['function'], 'application_code')

    def test_depth_works_when_the_sink_is_threaded(self):
        stream = io.StringIO()
        logger = Logger('app', logToFile=False, logToStdout=False, callerInfo=True)
        logger.add(stream, format='json', threaded=True)

        def wrapper():
            logger.opt(depth=1).info("x")

        def application_code():
            wrapper()

        try:
            application_code()
            logger.flush()
        finally:
            logger.clear_sinks()
        self.assertEqual(lines(stream)[0]['caller']['function'], 'application_code')

    def test_depth_works_when_a_processor_reads_the_caller(self):
        seen = []
        logger, stream = make_logger(callerInfo=True)

        def processor(record):
            seen.append(record.caller.function)
            return record

        logger.add_processor(processor)

        def wrapper():
            logger.opt(depth=1).info("x")

        def application_code():
            wrapper()

        application_code()
        self.assertEqual(seen, ['application_code'])

    def test_a_depth_that_is_negative_or_not_a_number_is_refused(self):
        logger, _ = make_logger()
        with self.assertRaises(ValueError):
            logger.opt(depth=-1)
        with self.assertRaises(ValueError):
            logger.opt(depth=True)


class TestPrettyConsole(unittest.TestCase):

    def pretty(self, **arguments):
        stream = io.StringIO()
        logger = Logger('api.users', logToFile=False, logToStdout=False)
        logger.add(stream, format=ConsoleFormatter(**arguments))
        return logger, stream

    def test_the_layout_has_the_columns(self):
        logger, stream = self.pretty()
        logger.info("User authenticated")
        parts = [part.strip() for part in stream.getvalue().strip().split('|')]
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[1], 'INFO')
        self.assertEqual(parts[2], 'api.users')
        self.assertEqual(parts[3], 'User authenticated')

    def test_the_severity_column_has_a_fixed_width(self):
        logger, stream = self.pretty()
        logger.info("a")
        logger.error("b")
        first, second = stream.getvalue().splitlines()
        self.assertEqual(first.index('| api.users'), second.index('| api.users'))

    def test_the_pretty_name_gives_the_same_layout_as_the_formatter(self):
        stream = io.StringIO()
        logger = Logger('api.users', logToFile=False, logToStdout=False)
        logger.add(stream, format='pretty')
        logger.warning("Retry 2/3")
        self.assertIn("| WARNING  | api.users | Retry 2/3", stream.getvalue())

    def test_there_is_no_colour_by_default(self):
        logger, stream = self.pretty()
        logger.error("plain")
        self.assertNotIn('\x1b[', stream.getvalue())

    def test_colour_is_written_when_asked(self):
        logger, stream = self.pretty(colors=True)
        logger.error("coloured")
        self.assertIn('\x1b[', stream.getvalue())

    def test_a_stream_that_is_not_a_terminal_gets_no_colour(self):
        self.assertFalse(stream_supports_color(io.StringIO()))

    def test_no_color_variable_switches_colour_off_for_a_terminal(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        previous = os.environ.get('NO_COLOR')
        try:
            os.environ.pop('NO_COLOR', None)
            self.assertTrue(stream_supports_color(Terminal()) or os.environ.get('TERM') == 'dumb')
            os.environ['NO_COLOR'] = '1'
            self.assertFalse(stream_supports_color(Terminal()))
        finally:
            os.environ.pop('NO_COLOR', None)
            if previous is not None:
                os.environ['NO_COLOR'] = previous

    def test_utc_writes_a_trailing_z(self):
        logger, stream = self.pretty(utc=True)
        logger.info("x")
        first = stream.getvalue().split('|')[0].strip()
        self.assertTrue(first.endswith('Z'))

    def test_milliseconds_can_be_left_out(self):
        withMilliseconds = self.pretty()
        without = self.pretty(milliseconds=False)
        withMilliseconds[0].info("x")
        without[0].info("x")
        self.assertIn('.', withMilliseconds[1].getvalue().split('|')[0])
        self.assertNotIn('.', without[1].getvalue().split('|')[0])

    def test_the_fields_follow_the_message(self):
        logger, stream = self.pretty()
        logger.info("done", order_id=5)
        self.assertIn("done order_id=5", stream.getvalue())

    def test_a_chosen_colour_function_wins_over_the_severity_colour(self):
        logger, stream = self.pretty(colors=True, colorOf=lambda record: '\x1b[35m')
        logger.info("x")
        self.assertIn('\x1b[35m', stream.getvalue())

    def test_a_wrong_option_is_refused(self):
        with self.assertRaises(TypeError):
            ConsoleFormatter(colors="yes")
        with self.assertRaises(ValueError):
            ConsoleFormatter(traceback="short")


if __name__ == '__main__':
    unittest.main()
