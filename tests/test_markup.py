"""Tests of the colour tags of a message, such as ``<red>failed</red>``: the parser, the console formatter, the logger switch and the formatter for the other outputs.

The tests that matter most are the ones that try to garble a text: random messages made of tags, brackets and
backslashes must always give a text that keeps everything that is not a tag, and never leaves a colour on at the end of a line.

Run from the repo root::

    python3 -m unittest tests.test_markup -v
"""
import glob
import io
import os
import random
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger, CONSOLE_SINK, FILE_SINK  # noqa: E402
from formatters import (ConsoleFormatter, MARKUP_STYLES, SGR_RESET, render_markup, without_markup,  # noqa: E402
                        resolve_formatter)
from record import LogRecord  # noqa: E402
from sinks import CallbackSink  # noqa: E402

RED = MARKUP_STYLES['red']
BOLD = MARKUP_STYLES['bold']
GREEN = MARKUP_STYLES['green']
ANSI = re.compile('\x1b\\[[0-9;]*m')
# What a tag looks like, whether or not it is one of ours
TAG_LIKE = re.compile(r'\\?</?[a-z]*>')


def strip_codes(text):
    """Returns the text without its colour codes."""
    return ANSI.sub('', text)


def make_record(message, **changes):
    values = dict(timestamp=datetime(2026, 10, 6, 13, 31, 52, tzinfo=timezone(timedelta(hours=-5))), severity='INFO',
                  logType='info', level=20.0, logger='orders', message=message, processId=1, threadId=1,
                  threadName='main')
    values.update(changes)
    return LogRecord.create(**values)


def is_subsequence(small, big):
    """Tells whether every character of *small* is in *big*, in the same order."""
    iterator = iter(big)
    return all(character in iterator for character in small)


class TestRenderMarkup(unittest.TestCase):
    """The tags and what they become."""

    def test_a_message_without_a_bracket_is_returned_as_it_is(self):
        text = "plain text, 100% sure, a > b"
        self.assertIs(render_markup(text, True), text)
        self.assertIs(render_markup(text, False), text)

    def test_empty_text(self):
        self.assertEqual(render_markup('', True), '')

    def test_one_colour(self):
        self.assertEqual(render_markup("<red>failed</red> to connect", True), f"{RED}failed{SGR_RESET} to connect")

    def test_with_colours_off_the_tags_are_removed(self):
        self.assertEqual(render_markup("<red>failed</red> to connect", False), "failed to connect")

    def test_every_style_has_a_code_and_removes_cleanly(self):
        for name, code in MARKUP_STYLES.items():
            with self.subTest(name=name):
                self.assertEqual(render_markup(f"<{name}>x</{name}>", True), f"{code}x{SGR_RESET}")
                self.assertEqual(render_markup(f"<{name}>x</{name}>", False), "x")

    def test_a_style_that_is_never_closed_ends_with_the_message(self):
        self.assertEqual(render_markup("<red>failed", True), f"{RED}failed{SGR_RESET}")
        self.assertEqual(render_markup("<red>failed", False), "failed")

    def test_the_shortcut_closes_the_last_style(self):
        self.assertEqual(render_markup("<red>a</>b", True), f"{RED}a{SGR_RESET}b")

    def test_the_shortcut_closes_one_style_at_a_time(self):
        self.assertEqual(render_markup("<bold><red>a</>b</>c", True),
                         f"{BOLD}{RED}a{SGR_RESET}{BOLD}b{SGR_RESET}c")

    def test_nested_styles_come_back_after_an_inner_one_closes(self):
        self.assertEqual(render_markup("<bold><red>a</red>b</bold>c", True),
                         f"{BOLD}{RED}a{SGR_RESET}{BOLD}b{SGR_RESET}c")

    def test_closing_an_outer_style_keeps_the_inner_one_on(self):
        self.assertEqual(render_markup("<red>a<bold>b</red>c</bold>d", True),
                         f"{RED}a{BOLD}b{SGR_RESET}{BOLD}c{SGR_RESET}d")

    def test_closing_an_outer_style_leaves_the_inner_one_on_to_the_end(self):
        # The text after </red> is still bold, as the message never closes it
        self.assertEqual(render_markup("<red>a<bold>b</red>c", True), f"{RED}a{BOLD}b{SGR_RESET}{BOLD}c{SGR_RESET}")

    def test_the_same_style_twice_closes_the_last_one_first(self):
        self.assertEqual(render_markup("<red>a<red>b</red>c</red>d", True),
                         f"{RED}a{RED}b{SGR_RESET}{RED}c{SGR_RESET}d")

    def test_closing_takes_the_last_style_of_that_name(self):
        # Told apart by the order of the codes written again after the reset
        self.assertEqual(render_markup("<red><bold><red>a</red>b", True),
                         f"{RED}{BOLD}{RED}a{SGR_RESET}{RED}{BOLD}b{SGR_RESET}")

    def test_unknown_tags_are_text(self):
        for text in ("<unknown>x</unknown>", "<>x", "x</>", "<RED>x</RED>", "<Red>x", "<red >x", "< red>x", "<red/>x",
                     "<1>x", "<red2>x", "<red-bold>x"):
            with self.subTest(text=text):
                self.assertEqual(render_markup(text, True), text)
                self.assertEqual(render_markup(text, False), text)

    def test_comparisons_and_arrows_are_text(self):
        for text in ("a < b and c > d", "x -> y", "<- back", "1 << 2", "if a<b>c", "a<b", "b>a", "<<red>>"):
            with self.subTest(text=text):
                expected = text.replace("<red>", "")
                self.assertEqual(render_markup(text, False), expected)

    def test_a_closing_tag_with_nothing_to_close_is_text(self):
        self.assertEqual(render_markup("a</red>b", True), "a</red>b")
        self.assertEqual(render_markup("a</red>b", False), "a</red>b")
        self.assertEqual(render_markup("<green>a</red>b</green>", False), "a</red>b")

    def test_a_closing_tag_of_another_style_is_text_and_does_not_close(self):
        self.assertEqual(render_markup("<red>a</blue>b</red>", True), f"{RED}a</blue>b{SGR_RESET}")

    def test_a_backslash_keeps_a_tag_as_text(self):
        self.assertEqual(render_markup("\\<red>x\\</red>", True), "<red>x</red>")
        self.assertEqual(render_markup("\\<red>x\\</red>", False), "<red>x</red>")

    def test_an_escaped_tag_does_not_open_a_style(self):
        self.assertEqual(render_markup("\\<red>x</red>", True), "<red>x</red>")

    def test_a_backslash_before_something_that_is_not_a_tag_stays(self):
        for text in ("C:\\<dir>", "\\<unknown>", "a\\b", "\\\\", "path\\"):
            with self.subTest(text=text):
                self.assertEqual(render_markup(text, True), text)

    def test_two_backslashes_keep_one_and_escape_the_tag(self):
        self.assertEqual(render_markup("\\\\<red>x", True), "\\<red>x")

    def test_line_breaks_end_and_restart_the_styles(self):
        self.assertEqual(render_markup("<red>a\nb</red>c", True), f"{RED}a{SGR_RESET}\n{RED}b{SGR_RESET}c")

    def test_a_line_break_outside_any_style_is_untouched(self):
        self.assertEqual(render_markup("a\n<red>b</red>\nc", True), f"a\n{RED}b{SGR_RESET}\nc")

    def test_a_style_open_over_several_lines_never_leaves_a_line_coloured(self):
        text = render_markup("<red>a\nb\nc", True)
        for line in text.split('\n'):
            self.assertTrue(line.endswith(SGR_RESET), line)

    def test_windows_line_breaks(self):
        self.assertEqual(strip_codes(render_markup("<red>a\r\nb</red>", True)), "a\r\nb")

    def test_unicode_and_emoji_are_kept(self):
        text = "<green>caf\u00e9 \u4e2d\u6587 \U0001F600</green>"
        self.assertEqual(render_markup(text, False), "caf\u00e9 \u4e2d\u6587 \U0001F600")
        self.assertEqual(strip_codes(render_markup(text, True)), "caf\u00e9 \u4e2d\u6587 \U0001F600")

    def test_a_tag_next_to_another(self):
        self.assertEqual(render_markup("<red></red><green></green>", False), "")
        self.assertEqual(render_markup("<red><green>x", False), "x")

    def test_text_that_looks_like_a_code_is_not_changed(self):
        # The escape character is not a tag, and this function does not clean values, it only reads tags
        self.assertEqual(render_markup("a\x1b[31mb<red>c", False), "a\x1b[31mbc")

    def test_a_very_long_message_with_many_tags(self):
        text = "<red>word</red> " * 20000
        self.assertEqual(render_markup(text, False), "word " * 20000)
        self.assertEqual(strip_codes(render_markup(text, True)), "word " * 20000)

    def test_a_very_deep_nesting_ends_cleanly(self):
        text = "<red>" * 5000 + "x"
        rendered = render_markup(text, True)
        self.assertTrue(rendered.endswith(SGR_RESET))
        self.assertEqual(strip_codes(rendered), "x")

    def test_many_unclosed_brackets_do_not_slow_it_down(self):
        text = "<" * 100000 + "reD" + ">" * 100000 + "</" * 50000
        self.assertEqual(render_markup(text, True), text)

    def test_the_text_must_be_a_string(self):
        for value in (None, 5, b"<red>", ["<red>"]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    render_markup(value, True)


class TestNeverGarbled(unittest.TestCase):
    """Random messages made of everything that can go wrong. What is not a tag is never lost and no colour ever leaks."""

    PIECES = ["<red>", "</red>", "<bold>", "</bold>", "<green>", "</green>", "</>", "<", ">", "/", "\\", "\\<red>", "\\</red>",
              "<RED>", "<unknown>", "a", "b ", " ", "\n", "\r\n", "x=1", "\u00e9", "%s", "{}", "<<", ">>", "<red", "red>"]

    def messages(self, count=3000):
        generator = random.Random(20261012)
        for _ in range(count):
            yield ''.join(generator.choice(self.PIECES) for _ in range(generator.randint(0, 14)))

    def test_without_colours_there_is_no_code(self):
        for message in self.messages():
            self.assertNotIn('\x1b', render_markup(message, False), repr(message))

    def test_removing_the_codes_gives_the_text_of_colours_off(self):
        for message in self.messages():
            self.assertEqual(strip_codes(render_markup(message, True)), render_markup(message, False), repr(message))

    def test_nothing_that_is_not_a_tag_is_lost(self):
        for message in self.messages():
            rest = TAG_LIKE.sub('', message)
            self.assertTrue(is_subsequence(rest, render_markup(message, False)), repr(message))

    def test_nothing_is_added(self):
        for message in self.messages():
            self.assertLessEqual(len(render_markup(message, False)), len(message), repr(message))

    def test_a_line_that_has_a_code_ends_with_a_reset(self):
        for message in self.messages():
            for line in render_markup(message, True).split('\n'):
                codes = ANSI.findall(line)
                if len(codes) > 0:
                    self.assertEqual(codes[-1], SGR_RESET, repr((message, line)))

    def test_the_codes_come_in_a_valid_order(self):
        # Every style that is started is ended, whatever the message does
        for message in self.messages():
            started = 0
            for code in ANSI.findall(render_markup(message, True)):
                if code == SGR_RESET:
                    started = 0
                else:
                    started += 1
            self.assertEqual(started, 0, repr(message))

    def test_a_message_with_no_valid_tag_is_unchanged(self):
        valid = re.compile(r'</?(?:%s)?>' % '|'.join(MARKUP_STYLES))
        for message in self.messages():
            if valid.search(message) is None:
                self.assertEqual(render_markup(message, True), message)
                self.assertEqual(render_markup(message, False), message)

    def test_it_never_raises(self):
        generator = random.Random(7)
        alphabet = "<>/\\\n\r abredgnluwyzo\u00e9\x1b\x00"
        for _ in range(3000):
            text = ''.join(generator.choice(alphabet) for _ in range(generator.randint(0, 30)))
            render_markup(text, True)
            render_markup(text, False)


class TestConsoleFormatterMarkup(unittest.TestCase):
    """The pretty layout with the switch."""

    def test_off_by_default_the_message_is_not_read(self):
        text = ConsoleFormatter(colors=True)(make_record("<red>failed</red>"))
        self.assertIn("<red>failed</red>", text)

    def test_on_with_colours(self):
        text = ConsoleFormatter(colors=True, markup=True)(make_record("<red>failed</red> now"))
        self.assertIn(f"{RED}failed{SGR_RESET} now", text)
        self.assertNotIn("<red>", text)

    def test_on_without_colours_removes_the_tags(self):
        text = ConsoleFormatter(colors=False, markup=True)(make_record("<red>failed</red> now"))
        self.assertIn("| failed now", text)
        self.assertNotIn('\x1b', text)

    def test_the_rest_of_the_line_is_not_coloured_by_an_open_style(self):
        text = ConsoleFormatter(colors=True, markup=True)(make_record("<red>failed", fields={'order': 7}))
        message, _, rest = text.partition("failed")
        self.assertTrue(rest.startswith(SGR_RESET))
        self.assertIn("order=7", rest)

    def test_the_fields_and_the_context_are_not_read_as_tags(self):
        record = make_record("done", fields={'note': '<red>'}, context={'who': '<bold>'})
        text = ConsoleFormatter(colors=True, markup=True)(record)
        self.assertIn("note=<red>", text)
        self.assertIn("who=<bold>", text)

    def test_the_traceback_is_not_read_as_tags(self):
        record = make_record("failed")
        from record import ExceptionInfo
        record = make_record("failed", exception=ExceptionInfo('ValueError', '<red>', 'Traceback\nValueError: <red>'))
        text = ConsoleFormatter(colors=True, markup=True)(record)
        self.assertIn("ValueError: <red>", text)

    def test_the_severity_colour_is_the_same_with_and_without_markup(self):
        record = make_record("plain message")
        self.assertEqual(ConsoleFormatter(colors=True, markup=True)(record), ConsoleFormatter(colors=True)(record))

    def test_the_switch_must_be_a_boolean(self):
        for value in (1, "yes", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    ConsoleFormatter(markup=value)

    def test_a_message_that_is_all_tags(self):
        text = ConsoleFormatter(colors=False, markup=True)(make_record("<red></red>"))
        self.assertTrue(text.endswith("| "))


class TestWithoutMarkup(unittest.TestCase):
    """The formatter for the outputs that are not the console."""

    def test_the_text_layout_loses_the_tags(self):
        text = without_markup("text")(make_record("<red>failed</red> to connect"))
        self.assertIn("failed to connect", text)
        self.assertNotIn("<red>", text)

    def test_the_json_layout_loses_the_tags(self):
        text = without_markup(None)(make_record("<red>failed</red>"))
        self.assertIn('"message":"failed"', text)

    def test_a_template_and_a_function(self):
        self.assertEqual(without_markup("{message}!")(make_record("<bold>x</bold>")), "x!")
        self.assertEqual(without_markup(lambda record: record.message.upper())(make_record("<bold>x</bold>")), "X")

    def test_a_text_that_is_not_a_tag_is_kept(self):
        self.assertEqual(without_markup("{message}")(make_record("a < b and <unknown>")), "a < b and <unknown>")

    def test_the_record_itself_is_not_changed(self):
        record = make_record("<red>x</red>")
        without_markup("text")(record)
        self.assertEqual(record.message, "<red>x</red>")

    def test_an_escaped_tag_gives_the_tag(self):
        self.assertEqual(without_markup("{message}")(make_record("\\<red>")), "<red>")

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            without_markup("not a layout")
        with self.assertRaises(TypeError):
            without_markup(5)
        with self.assertRaises(TypeError):
            without_markup("text")("not a record")

    def test_it_is_a_formatter_the_logger_accepts(self):
        self.assertTrue(callable(resolve_formatter(without_markup("text"))))


class TestLoggerSwitch(unittest.TestCase):
    """The switch of the logger and what the console and a file get."""

    def make_logger(self, **options):
        stream = io.StringIO()
        logger = Logger(name="markup", stdout=stream, logToFile=False, **options)
        return logger, stream

    def test_off_by_default(self):
        logger, stream = self.make_logger(consoleColor='always')
        logger.info("<red>failed</red>")
        self.assertIn("<red>failed</red>", stream.getvalue())
        self.assertFalse(logger.consoleMarkup)

    def test_on_with_colour_always(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        logger.info("<red>failed</red>")
        self.assertIn(f"{RED}failed{SGR_RESET}", stream.getvalue())
        self.assertTrue(logger.consoleMarkup)

    def test_on_with_colour_never_removes_the_tags(self):
        logger, stream = self.make_logger(consoleColor='never', consoleMarkup=True)
        logger.info("<red>failed</red> now")
        self.assertIn("| failed now", stream.getvalue())
        self.assertNotIn('\x1b', stream.getvalue())

    def test_on_with_colour_auto_and_no_terminal_removes_the_tags(self):
        # A StringIO is not a terminal, so a pipe or a CI log is plain
        logger, stream = self.make_logger(consoleColor='auto', consoleMarkup=True)
        logger.info("<red>failed</red> now")
        self.assertIn("| failed now", stream.getvalue())
        self.assertNotIn('\x1b', stream.getvalue())

    def test_the_arguments_are_filled_before_the_tags_are_read(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        logger.info("<red>{}</red> failed", "db")
        self.assertIn(f"{RED}db{SGR_RESET} failed", stream.getvalue())

    def test_a_value_with_a_tag_is_read_too_but_cannot_add_an_escape_character(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        logger.info("user said {}", "<red>hi\x1b[31m</red>")
        output = stream.getvalue()
        self.assertEqual(output.count('\x1b[31m'), 1)
        self.assertIn("\\x1b", output)

    def test_the_other_log_types_work(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        logger.error("<bold>stop</bold>")
        logger.warning("<green>careful</green>")
        self.assertIn(f"{BOLD}stop{SGR_RESET}", stream.getvalue())
        self.assertIn(f"{GREEN}careful{SGR_RESET}", stream.getvalue())

    def test_a_style_left_open_does_not_reach_the_next_record(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        logger.info("<red>first")
        logger.info("second")
        first, second = stream.getvalue().splitlines()
        self.assertTrue(first.endswith(SGR_RESET))
        self.assertNotIn(RED, second)

    def test_a_multiline_message(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        logger.info("<red>one\ntwo</red>")
        for line in stream.getvalue().splitlines():
            codes = ANSI.findall(line)
            if len(codes) > 0:
                self.assertEqual(codes[-1], SGR_RESET)

    def test_a_message_with_percent_and_braces_next_to_tags(self):
        logger, stream = self.make_logger(consoleColor='never', consoleMarkup=True)
        logger.info("<red>100%</red> {} <bold>{{ok}}</bold>", "x")
        self.assertIn("100% x {ok}", stream.getvalue())

    def test_it_needs_the_pretty_layout(self):
        for layout in ('text', None, "{message}", lambda record: record.message):
            with self.subTest(layout=layout):
                with self.assertRaises(ValueError):
                    Logger(name="markup", logToFile=False, consoleMarkup=True, consoleFormatter=layout)

    def test_the_layout_cannot_be_changed_to_another_while_it_is_on(self):
        logger, _ = self.make_logger(consoleMarkup=True)
        with self.assertRaises(ValueError):
            logger.set_sink_formatter(CONSOLE_SINK, 'text')
        # Still working after the refusal
        logger.set_sink_formatter(CONSOLE_SINK, 'pretty')

    def test_without_the_switch_the_layout_can_change(self):
        logger, _ = self.make_logger()
        logger.set_sink_formatter(CONSOLE_SINK, 'text')

    def test_the_switch_must_be_a_boolean(self):
        for value in (1, "yes", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    Logger(name="markup", logToFile=False, consoleMarkup=value)

    def test_the_environment_layout_is_checked_too(self):
        previous = os.environ.get('PYSIMPLELOG_FORMAT')
        os.environ['PYSIMPLELOG_FORMAT'] = 'json'
        try:
            with self.assertRaises(ValueError):
                Logger(name="markup", logToFile=False, consoleMarkup=True, env=True)
        finally:
            if previous is None:
                del os.environ['PYSIMPLELOG_FORMAT']
            else:
                os.environ['PYSIMPLELOG_FORMAT'] = previous

    def test_the_file_keeps_the_tags_and_without_markup_removes_them(self):
        base = tempfile.mktemp(suffix='.log')
        logger = Logger(name="markup", stdout=io.StringIO(), logToFile=True, logFile=base, consoleMarkup=True)
        try:
            logger.info("<red>kept</red> in the file")
            logger.set_sink_formatter(FILE_SINK, without_markup("text"))
            logger.info("<red>cleaned</red> in the file")
            logger.flush()
            with open(logger.logFileName, encoding='utf-8') as handle:
                text = handle.read()
        finally:
            # Windows cannot delete a file that is still open
            logger.sinks[FILE_SINK].close()
            for path in glob.glob(base.replace('.log', '') + '*.log'):
                os.unlink(path)
        self.assertIn("<red>kept</red> in the file", text)
        self.assertIn("cleaned in the file", text)
        self.assertNotIn("<red>cleaned", text)

    def test_the_switch_does_not_touch_the_other_sinks(self):
        logger, stream = self.make_logger(consoleColor='always', consoleMarkup=True)
        seen = []
        logger.add(CallbackSink(lambda text, record: seen.append(text), formatter="{message}"))
        logger.info("<red>x</red>")
        self.assertEqual(seen, ["<red>x</red>"])


if __name__ == '__main__':
    unittest.main()
