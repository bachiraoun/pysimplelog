"""What ``catch()`` does with an error: when it logs and carries on, when it lets the error go, and what it writes.

Run from the repo root::

    python3 -m unittest tests.test_catch -v

* TestLogging -- the decorator and the ``with`` block, one record with the whole traceback, methods, bound values, threads
* TestWhatPassesThrough -- exits and interruptions are not errors to log and carry on from
* TestTextOfTheError -- a line break in the text of an error cannot forge a log line, on any output
* TestWhenLoggingFails -- an error that cannot be printed or logged is not hidden
* TestKnownLimits -- an ``async def`` function and a generator are not covered by the decorator
"""
import asyncio
import contextlib
import io
import json
import os
import sys
import threading
import traceback
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from default_logger import _DefaultLogger  # noqa: E402
from sinks import CallbackSink  # noqa: E402
from contrib import siem_sink  # noqa: E402
from contrib.otlp_encoder import OtlpLogEncoder  # noqa: E402

WAIT_SECONDS = 30.0


class FakeTransport:
    """Keeps every message that the SIEM sink sends."""

    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)

    def close(self):
        pass


class UnprintableError(Exception):
    """An error whose text cannot be made."""

    def __str__(self):
        raise RuntimeError("str failed")


def make_logger():
    """Returns a logger that only keeps its records, and the list they are kept in."""
    records = []
    logger = Logger('catching', logToFile=False, logToStdout=False)
    logger.add(CallbackSink(lambda text, record: records.append(record)))
    return logger, records


class TestLogging(unittest.TestCase):

    def test_a_decorated_function_logs_the_error_and_the_program_continues(self):
        logger, records = make_logger()

        @logger.catch
        def risky():
            raise ValueError("something went wrong")

        self.assertIsNone(risky())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].message, "An exception was caught: something went wrong")
        self.assertEqual(records[0].severity, 'ERROR')

    def test_the_record_has_the_whole_traceback(self):
        logger, records = make_logger()
        with logger.catch():
            raise KeyError("missing")
        self.assertEqual(records[0].exception.typeName, 'KeyError')
        self.assertIn("Traceback (most recent call last)", records[0].exception.stacktrace)
        self.assertIn("raise KeyError", records[0].exception.stacktrace)

    def test_a_block_without_an_error_logs_nothing(self):
        logger, records = make_logger()
        with logger.catch():
            pass
        self.assertEqual(records, [])

    def test_the_message_and_the_log_type_can_be_chosen(self):
        logger, records = make_logger()
        with logger.catch(logType='critical', message='The payment failed'):
            raise ValueError("card declined")
        self.assertEqual(records[0].message, "The payment failed: card declined")
        self.assertEqual(records[0].severity, 'CRITICAL')

    def test_the_error_is_raised_again_once_and_logged_once(self):
        logger, records = make_logger()

        @logger.catch(reraise=True)
        def risky():
            raise ValueError("again")

        try:
            risky()
        except ValueError as error:
            caught = error
        self.assertEqual(len(records), 1)
        # The frame of the function that failed is still on the error
        frames = [frame.name for frame in traceback.extract_tb(caught.__traceback__)]
        self.assertIn('risky', frames)

    def test_the_decorator_keeps_the_name_and_the_documentation(self):
        logger, _ = make_logger()

        @logger.catch
        def documented():
            """Does something."""

        self.assertEqual(documented.__name__, 'documented')
        self.assertEqual(documented.__doc__, "Does something.")

    def test_methods_and_static_methods_are_covered(self):
        logger, records = make_logger()

        class Worker:
            @logger.catch
            def run(self):
                raise ValueError("method")

            @staticmethod
            @logger.catch
            def run_static():
                raise ValueError("static")

        Worker().run()
        Worker.run_static()
        self.assertEqual([record.message[-6:] for record in records], ["method", "static"])

    def test_the_arguments_and_the_result_pass_through(self):
        logger, records = make_logger()

        @logger.catch
        def add(first, second=1):
            return first + second

        self.assertEqual(add(2, second=5), 7)
        self.assertEqual(records, [])

    def test_the_text_of_the_error_with_braces_is_written_as_it_is(self):
        logger, records = make_logger()
        with logger.catch():
            raise ValueError("value {0} and {name} and {")
        self.assertEqual(records[0].message, "An exception was caught: value {0} and {name} and {")

    def test_a_bound_logger_adds_its_values_to_the_record(self):
        logger, records = make_logger()
        with logger.bind(job="nightly").catch():
            raise ValueError("bound")
        self.assertEqual(records[0].context.get('job'), "nightly")

    def test_an_inner_block_catches_and_the_outer_one_sees_nothing(self):
        logger, records = make_logger()
        with logger.catch(message="outer"):
            with logger.catch(message="inner"):
                raise ValueError("deep")
        self.assertEqual([record.message.split(':')[0] for record in records], ["inner"])

    def test_an_inner_block_that_raises_again_is_caught_by_the_outer_one(self):
        logger, records = make_logger()
        with logger.catch(message="outer"):
            with logger.catch(message="inner", reraise=True):
                raise ValueError("deep")
        self.assertEqual([record.message.split(':')[0] for record in records], ["inner", "outer"])

    def test_the_shared_logger_has_catch_too(self):
        records = []
        # The shared logger keeps the console stream it finds when it is made, so it is made inside the redirect
        with contextlib.redirect_stdout(io.StringIO()):
            shared = _DefaultLogger()
            shared.add(CallbackSink(lambda text, record: records.append(record)))
            with shared.catch():
                raise ValueError("shared")
        self.assertEqual(len(records), 1)

    def test_many_threads_catch_without_losing_a_record(self):
        logger, records = make_logger()
        threads, perThread = 8, 50

        @logger.catch
        def fail(index):
            raise ValueError(f"thread {index}")

        def work(index):
            for _ in range(perThread):
                fail(index)

        workers = [threading.Thread(target=work, args=(index,)) for index in range(threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(WAIT_SECONDS)
        self.assertEqual(len(records), threads * perThread)

    def test_an_error_is_dropped_by_the_console_and_file_when_its_type_is_switched_off_but_user_sinks_still_get_it(self):
        logger, records = make_logger()
        logger.set_log_type_flags('error', stdoutFlag=False, fileFlag=False)
        with logger.catch():
            raise ValueError("hidden")
        self.assertEqual(len(records), 1)


class TestWhatPassesThrough(unittest.TestCase):

    def test_an_exit_goes_through_and_nothing_is_logged(self):
        logger, records = make_logger()
        with self.assertRaises(SystemExit):
            with logger.catch():
                sys.exit(3)
        self.assertEqual(records, [])

    def test_an_interruption_goes_through_and_nothing_is_logged(self):
        logger, records = make_logger()
        with self.assertRaises(KeyboardInterrupt):
            with logger.catch():
                raise KeyboardInterrupt()
        self.assertEqual(records, [])

    def test_the_end_of_a_generator_goes_through(self):
        logger, records = make_logger()
        with self.assertRaises(GeneratorExit):
            with logger.catch():
                raise GeneratorExit()
        self.assertEqual(records, [])

    def test_the_cancellation_of_a_task_goes_through(self):
        logger, records = make_logger()

        async def cancelled():
            with logger.catch():
                raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(cancelled())
        self.assertEqual(records, [])

    def test_a_decorated_function_can_still_exit_the_program(self):
        logger, records = make_logger()

        @logger.catch
        def stop():
            sys.exit(1)

        with self.assertRaises(SystemExit):
            stop()
        self.assertEqual(records, [])

    def test_an_ordinary_error_next_to_them_is_still_caught(self):
        logger, records = make_logger()
        with logger.catch():
            raise OSError("disk")
        self.assertEqual(len(records), 1)


FORGED_LINE = "2026-01-01 00:00:00 - catching <INFO> admin logged in"


class TestTextOfTheError(unittest.TestCase):

    def outputs(self):
        """Logs an error whose text has a line break and a forged line, and returns what each output wrote."""
        logger = Logger('catching', logToFile=False, logToStdout=False)
        streams = {'text': io.StringIO(), 'json': io.StringIO()}
        logger.add(streams['text'], format='text')
        logger.add(streams['json'], format='json')
        transport = FakeTransport()
        sink = siem_sink.attach(logger, transport, threaded=False)
        records = []
        logger.add(CallbackSink(lambda text, record: records.append(record)))
        with logger.catch():
            raise ValueError(f"first\n{FORGED_LINE}")
        siem_sink.detach(logger, sink)
        found = {name: stream.getvalue() for name, stream in streams.items()}
        found['siem'] = b''.join(transport.sent).decode('utf-8')
        found['otlp'] = OtlpLogEncoder().encode(records).decode('utf-8')
        return found

    def test_the_forged_line_is_not_a_line_of_its_own_in_the_text_log(self):
        text = self.outputs()['text']
        for line in text.split('\n'):
            self.assertFalse(line.startswith('2026-01-01'), f"a forged line starts a line: {line!r}")
        self.assertIn("first\\n2026-01-01", text.split('\n')[0])

    def test_every_output_has_the_error_and_no_output_has_a_line_of_its_own_for_the_forgery(self):
        found = self.outputs()
        for name, text in found.items():
            with self.subTest(output=name):
                self.assertIn("first", text)
                self.assertNotIn(f"\n{FORGED_LINE}", text)

    def test_the_json_record_is_one_line_with_the_text_in_a_string(self):
        lines = self.outputs()['json'].strip().split('\n')
        self.assertEqual(len(lines), 1)
        self.assertIn("admin logged in", json.loads(lines[0])['message'])


class TestWhenLoggingFails(unittest.TestCase):

    def test_an_error_whose_text_cannot_be_made_is_still_logged_with_a_placeholder(self):
        logger, records = make_logger()
        with logger.catch():
            raise UnprintableError()
        self.assertEqual(len(records), 1)
        self.assertIn("<UnprintableError could not be printed>", records[0].message)

    def test_an_unknown_log_type_raises_the_original_error_and_warns(self):
        logger, records = make_logger()
        warning = io.StringIO()
        with contextlib.redirect_stderr(warning):
            with self.assertRaises(ValueError) as context:
                with logger.catch(logType='nope'):
                    raise ValueError("the real error")
        self.assertEqual(str(context.exception), "the real error")
        self.assertIn("pysimplelog WARNING: catch() could not log ValueError", warning.getvalue())
        self.assertEqual(records, [])

    def test_a_closed_error_stream_does_not_hide_the_original_error(self):
        logger, _ = make_logger()
        closed = io.StringIO()
        closed.close()
        with contextlib.redirect_stderr(closed):
            with self.assertRaises(ValueError):
                with logger.catch(logType='nope'):
                    raise ValueError("still raised")

    def test_a_failing_sink_does_not_stop_the_program(self):
        logger = Logger('catching', logToFile=False, logToStdout=False)

        def broken(text, record):
            raise RuntimeError("sink down")

        logger.add(CallbackSink(broken))
        # The logger warns on the error stream about the sink, which is not what is checked here
        with contextlib.redirect_stderr(io.StringIO()):
            with logger.catch():
                raise ValueError("logged nowhere")


class TestKnownLimits(unittest.TestCase):

    def test_an_error_in_an_async_function_is_not_caught_by_the_decorator(self):
        # The decorator wraps the call that makes the coroutine. The body runs later, outside it
        logger, records = make_logger()

        @logger.catch
        async def fails():
            raise ValueError("in the coroutine")

        with self.assertRaises(ValueError):
            asyncio.run(fails())
        self.assertEqual(records, [])

    def test_a_block_inside_an_async_function_does_catch(self):
        logger, records = make_logger()

        async def fails():
            with logger.catch():
                raise ValueError("inside")

        asyncio.run(fails())
        self.assertEqual(len(records), 1)

    def test_an_error_in_a_generator_is_not_caught_by_the_decorator(self):
        logger, records = make_logger()

        @logger.catch
        def numbers():
            yield 1
            raise ValueError("in the generator")

        with self.assertRaises(ValueError):
            list(numbers())
        self.assertEqual(records, [])


if __name__ == '__main__':
    unittest.main()
