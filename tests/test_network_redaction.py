"""Hiding network addresses: URLs, web addresses, hosts with a port, and IPv4 and IPv6 addresses with their port.

Run from the repo root::

    python3 -m unittest tests.test_network_redaction -v

A fast test lets most texts pass without the full patterns. The random cases check that this test never lets through a text
the patterns would change, and that one pass over the text gives what the patterns give one after the other.
"""
import os
import random
import re
import sys
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from processors import (hide_network, redact_network, NETWORK_PATTERNS, NETWORK_REGEX, NETWORK_REPLACEMENTS,  # noqa: E402
                        NETWORK_CANDIDATE_REGEX)
from record import LogRecord  # noqa: E402
from datetime import datetime, timezone  # noqa: E402


def one_pass(text):
    """What the patterns give, with no test in front of them."""
    return NETWORK_REGEX.sub(lambda match: NETWORK_REPLACEMENTS[match.lastgroup], text)


def one_after_the_other(text):
    """The patterns applied one after the other, each over the whole text."""
    for _, source, replacement in NETWORK_PATTERNS:
        text = re.sub(source, replacement, text)
    return text


class TestWhatIsHidden(unittest.TestCase):

    CASES = (
        ('Worker@192.168.1.197[44602]:6032', 'Worker@<ip>[44602]:6032'),
        ('Refused 192.168.1.197', 'Refused <ip>'),
        ('peer 10.0.0.1:6002 closed', 'peer <ip> closed'),
        ('see https://host.example.com:8443/x?y=1', 'see <url>/x?y=1'),
        ('HTTP://UPPER.COM:80/a', '<url>/a'),
        ('ws://10.1.1.1:9000 and wss://chat.example.org', '<url> and <url>'),
        ('ftp://user@10.0.0.1:21/p', '<url>/p'),
        ('tcp://abc.def.lan:9', '<url>'),
        ('www.foo.com:80 and db.lan:5432', '<host> and <host>'),
        ('see www.example.org now', 'see <host> now'),
        ('my-host.lan:8080', '<host>'),
        ('at [::1]:80', 'at <ip>'),
        ('addr fe80::1 ok', 'addr <ip> ok'),
        ('full 2001:db8:0:0:0:0:0:1 form', 'full <ip> form'),
        ('ab:cd:ef:01:23:45:67:89', '<ip>'),
        ('http://[::1]:8080/p', '<url>/p'),
        ('1.2.3.4 and 5.6.7.8:9', '<ip> and <ip>'),
        ('example.com:80 host.org:1 api.example.io:9000', '<host> <host> <host>'),
        ('see ui_run.py:407 and host.lan:22', 'see ui_run.py:407 and <host>'),
    )

    UNCHANGED = (
        '', 'plain text', '12:30:45 done', '2026-10-16 23:18:41.966 Err:186.595 v1.2:30 Gen:3361979',
        '@size_distribution/3 Gen:4031813 - Tr:3767942(93.455%) - Acc:394106(9.775%) - Rem:0.0(0.000%) - Err:223.178589',
        'version 3.4.5 of the thing', '1.2.3 is not an address', 'ratio 98.562% then 12.168%', 'file.txt:12', 'a.b:c',
        'x:8080', 'mailto:someone', 'key: value, other: 3.14',
        'ui_run.py:407', 'File MultiframeUtils.py:1128 failed', 'utils.js:12', 'data.json:5', 'engine.log:99', 'archive.tar.gz:3',
    )

    def test_each_kind_of_address_is_replaced_and_the_text_around_it_is_kept(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(hide_network(text), expected)

    def test_texts_that_look_like_addresses_but_are_not_are_left_alone(self):
        for text in self.UNCHANGED:
            with self.subTest(text=text):
                self.assertEqual(hide_network(text), text)

    def test_hiding_twice_gives_the_same_as_hiding_once(self):
        for text, _ in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(hide_network(hide_network(text)), hide_network(text))

    def test_a_text_with_many_addresses_hides_them_all(self):
        text = ' '.join(f'10.0.{number}.1:{6000 + number}' for number in range(200))
        self.assertEqual(hide_network(text), ' '.join(['<ip>'] * 200))

    def test_the_full_ipv6_spelling_without_any_double_colon_is_not_skipped_by_the_fast_test(self):
        text = '1:2:3:4:5:6:7:8'
        self.assertIsNone(NETWORK_CANDIDATE_REGEX.search(text))              # the regular expression alone would not see it
        self.assertEqual(hide_network(text), '<ip>')                          # the count of colons does


class TestTheFastTestAndTheSingleRegex(unittest.TestCase):

    FRAGMENTS = (
        '192.168.1.197', '10.0.0.1:6002', '999.999.999.999', '1.2.3', '1.2.3.4.5', 'https://host.example.com:8443/x', 'http://[::1]:80/',
        'www.foo.com', 'www.foo.com:80', 'db.lan:5432', 'a.b:1', 'x-.lan:80', 'ui_run.py:407', 'archive.tar.gz:3', '::1', 'fe80::1', '[::1]:80', '2001:db8:0:0:0:0:0:1',
        '1:2:3:4:5:6:7:8', '12:30:45', '23:18:41.966', 'Err:186.595', 'v1.2:30', '98.562%', 'Worker@', '[44602]', ':6032', 'tcp://a.b.lan:9',
        'ftp://u@h:21', 'word', 'another', 'x', ' ', ' - ', '/', '(', ')', 'é', '✓', '0.0', '8080', 'HTTP://U.COM', 'ws://1.1.1.1',
    )

    def random_text(self, generator, separators=('', ' ', ' ', '-', ':', '.')):
        return ''.join(generator.choice(self.FRAGMENTS) + generator.choice(separators) for _ in range(generator.randint(1, 12)))

    def test_the_fast_test_never_lets_through_a_text_the_patterns_would_change(self):
        generator = random.Random(20261019)
        for _ in range(30000):
            text = self.random_text(generator)
            self.assertEqual(hide_network(text), one_pass(text), repr(text))

    def test_one_pass_gives_what_the_patterns_give_one_after_the_other(self):
        generator = random.Random(7)
        for _ in range(30000):
            text = self.random_text(generator, separators=(' ', ', ', '; ', ' - '))       # an address glued to the next word is not a case
            self.assertEqual(one_pass(text), one_after_the_other(text), repr(text))

    def test_every_pattern_on_its_own_is_found_by_the_fast_test(self):
        generator = random.Random(3)
        for name, example in (('url', 'https://x.example.com:9/a'), ('www', 'www.example.com'), ('hostPort', 'example.com:80'),
                              ('ipv4', '1.2.3.4'), ('ipv6Bracket', '[fe80::1]:9'), ('ipv6', '2001:db8:0:0:0:0:0:1')):
            with self.subTest(name=name):
                for _ in range(200):
                    text = self.random_text(generator) + ' ' + example + ' ' + self.random_text(generator)
                    self.assertNotEqual(hide_network(text), text)

    def test_nothing_makes_it_raise(self):
        generator = random.Random(11)
        for _ in range(5000):
            text = ''.join(chr(generator.randint(0, 0x2FFF)) for _ in range(generator.randint(0, 60)))
            self.assertIsInstance(hide_network(text), str)

    def test_a_long_text_without_an_address_is_not_slow(self):
        text = 'Gen:4031813 - Tr:3767942(93.455%) ' * 20000                  # about 700 kilobytes
        import time
        started = time.monotonic()
        self.assertEqual(hide_network(text), text)
        self.assertLess(time.monotonic() - started, 5.0)


class TestTheProcessor(unittest.TestCase):

    def record(self, message, fields=None, exception=None):
        return LogRecord.create(timestamp=datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc), severity='INFO', logType='info', level=10.0,
                                logger='test', message=message, processId=1, threadId=2, threadName='main', fields=fields)

    def test_the_message_and_every_text_in_the_fields_are_cleaned(self):
        processor = redact_network()
        record = self.record('peer 10.0.0.1:80', fields={'url': 'http://x.example.com:81/a', 'nested': {'list': ['db.lan:5432', 7, None],
                                                                                                         'tuple': ('1.2.3.4',)}, 'count': 5})
        cleaned = processor(record)
        self.assertEqual(cleaned.message, 'peer <ip>')
        self.assertEqual(cleaned.fields['url'], '<url>/a')
        self.assertEqual(cleaned.fields['nested']['list'], ['<host>', 7, None])
        self.assertEqual(cleaned.fields['nested']['tuple'], ('<ip>',))
        self.assertEqual(cleaned.fields['count'], 5)

    def test_the_time_the_process_and_the_names_of_the_fields_are_not_touched(self):
        processor = redact_network()
        record = self.record('1.2.3.4', fields={'10.0.0.1': 'value'})
        cleaned = processor(record)
        self.assertEqual((cleaned.timestamp, cleaned.processId, cleaned.threadId), (record.timestamp, 1, 2))
        self.assertIn('10.0.0.1', cleaned.fields)                              # a key is a name, not a text to clean

    def test_a_record_with_nothing_to_hide_comes_back_equal(self):
        processor = redact_network()
        record = self.record('Gen:1 - Tr:2(98.562%)', fields={'a': 'b'})
        cleaned = processor(record)
        self.assertEqual((cleaned.message, dict(cleaned.fields)), (record.message, {'a': 'b'}))

    def test_it_works_as_a_processor_of_a_logger(self):
        from simple_log import Logger
        from sinks import Sink

        class Keep(Sink):
            def __init__(self):
                super().__init__(formatter=lambda record: record.message)
                self.lines = []

            def write(self, text, record):
                self.lines.append((text.strip(), dict(record.fields)))

        logger = Logger('redact', logToFile=False, logToStdout=False)
        sink = Keep()
        logger.add_sink('keep', sink)
        logger.add_processor(redact_network())
        logger.info('connect to 192.168.1.5:6002', peer='http://10.1.1.1:80/x')
        self.assertEqual(sink.lines, [('connect to <ip>', {'peer': '<url>/x'})])


if __name__ == '__main__':
    unittest.main()
