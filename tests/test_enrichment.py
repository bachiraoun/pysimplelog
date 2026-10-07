"""Tests of the ready-made processor ``add_context`` and of the filters ``match_logger``, ``match_module`` and ``match_field``.

Run from the repo root::

    python3 -m unittest tests.test_enrichment -v
"""
import contextlib
import io
import json
import logging
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import JsonFormatter  # noqa: E402
from processors import add_context  # noqa: E402
from filters import match_logger, match_module, match_field  # noqa: E402
from record import LogRecord, CallerInfo  # noqa: E402
from sinks import StreamSink  # noqa: E402
from standard_logging import redirect_standard_logging, restore_standard_logging  # noqa: E402


def make_record(logger='app', fields=None, context=None, caller=None):
    return LogRecord.create(datetime(2026, 1, 1, tzinfo=timezone.utc), 'INFO', 'info', 10.0, logger, 'message', 1, 2, 'main',
                            fields=fields or {}, context=context or {}, caller=caller)


def make_logger(**arguments):
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()))
    return logger, stream


def lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class TestAddContext(unittest.TestCase):

    def test_static_values_reach_the_context_of_every_record(self):
        processor = add_context(service='orders', environment='test')
        first = processor(make_record())
        second = processor(make_record(context={'other': 1}))
        self.assertEqual(dict(first.context), {'service': 'orders', 'environment': 'test'})
        self.assertEqual(dict(second.context), {'other': 1, 'service': 'orders', 'environment': 'test'})

    def test_a_value_the_call_gave_wins(self):
        record = make_record(context={'service': 'from-the-call'})
        self.assertEqual(add_context(service='default')(record).context['service'], 'from-the-call')

    def test_a_function_is_called_for_every_record(self):
        counter = iter(range(100))
        processor = add_context(number=lambda: next(counter))
        self.assertEqual([processor(make_record()).context['number'] for _ in range(3)], [0, 1, 2])

    def test_a_function_is_not_called_when_the_name_is_already_there(self):
        calls = []
        processor = add_context(name=lambda: calls.append(1) or 'x')
        processor(make_record(context={'name': 'given'}))
        self.assertEqual(calls, [])

    def test_a_function_returning_none_adds_nothing_and_the_record_is_the_same_object(self):
        record = make_record()
        self.assertIs(add_context(request=lambda: None)(record), record)

    def test_a_record_that_has_everything_is_returned_as_it_is(self):
        record = make_record(context={'a': 1})
        self.assertIs(add_context(a=2)(record), record)

    def test_a_function_that_raises_is_left_out_and_reported_once_per_name(self):
        def broken():
            raise RuntimeError('boom')
        processor = add_context(bad=broken, good='yes')
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            results = [processor(make_record()) for _ in range(3)]
        self.assertTrue(all(dict(result.context) == {'good': 'yes'} for result in results))
        self.assertEqual(error.getvalue().count('boom'), 1)

    def test_the_original_record_is_never_changed(self):
        record = make_record(context={'a': 1})
        add_context(b=2)(record)
        self.assertEqual(dict(record.context), {'a': 1})

    def test_the_result_context_is_read_only(self):
        with self.assertRaises(TypeError):
            add_context(a=1)(make_record()).context['b'] = 2

    def test_no_value_is_refused(self):
        with self.assertRaises(ValueError):
            add_context()

    def test_in_a_logger_the_values_are_written_by_every_sink(self):
        logger, stream = make_logger(processors=[add_context(service='orders')])
        logger.info('hello', code=5)
        self.assertEqual(lines(stream)[0]['context'], {'service': 'orders'})

    def test_the_bind_values_win_in_a_logger(self):
        logger, stream = make_logger(processors=[add_context(service='orders', region='eu')])
        logger.bind(service='bound').info('hello')
        self.assertEqual(lines(stream)[0]['context'], {'service': 'bound', 'region': 'eu'})

    def test_the_records_of_the_standard_library_get_the_values_too(self):
        logger, stream = make_logger(processors=[add_context(service='orders')])
        handler = redirect_standard_logging(logger, level=logging.INFO, name='enrichment.test', loggerLevel=logging.INFO)
        try:
            logging.getLogger('enrichment.test').info('from the standard library')
        finally:
            restore_standard_logging(handler)
        self.assertEqual(lines(stream)[0]['context'], {'service': 'orders'})


class TestMatchLogger(unittest.TestCase):

    def test_a_name_matches_itself_and_what_is_inside_it_but_not_a_longer_name(self):
        keep = match_logger('urllib3')
        self.assertTrue(keep(make_record(logger='urllib3')))
        self.assertTrue(keep(make_record(logger='urllib3.connectionpool')))
        self.assertFalse(keep(make_record(logger='urllib3x')))
        self.assertFalse(keep(make_record(logger='other')))

    def test_exclude_reverses_it(self):
        keep = match_logger('urllib3', 'asyncio', exclude=True)
        self.assertFalse(keep(make_record(logger='urllib3.connectionpool')))
        self.assertFalse(keep(make_record(logger='asyncio')))
        self.assertTrue(keep(make_record(logger='urllib3x')))

    def test_a_record_of_the_standard_bridge_is_matched_on_the_standard_name(self):
        record = make_record(logger='app', fields={'logger_name': 'urllib3.connectionpool'})
        self.assertTrue(match_logger('urllib3')(record))
        self.assertFalse(match_logger('app')(record))

    def test_in_a_logger_as_a_global_filter(self):
        logger, stream = make_logger()
        logger.add_filter(match_logger('app', exclude=True))
        logger.info('dropped')
        self.assertEqual(lines(stream), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            match_logger()
        for bad in ('', 1, None):
            with self.assertRaises(TypeError):
                match_logger(bad)
        with self.assertRaises(TypeError):
            match_logger('a', exclude=1)


class TestMatchModule(unittest.TestCase):

    def test_prefix_semantics(self):
        keep = match_module('app.billing')
        self.assertTrue(keep(make_record(caller=CallerInfo('f.py', 1, 'run', 'app.billing'))))
        self.assertTrue(keep(make_record(caller=CallerInfo('f.py', 1, 'run', 'app.billing.tax'))))
        self.assertFalse(keep(make_record(caller=CallerInfo('f.py', 1, 'run', 'app.billingx'))))

    def test_exclude(self):
        keep = match_module('app.billing', exclude=True)
        self.assertFalse(keep(make_record(caller=CallerInfo('f.py', 1, 'run', 'app.billing'))))
        self.assertTrue(keep(make_record(caller=CallerInfo('f.py', 1, 'run', 'app.users'))))

    def test_a_record_without_a_caller_is_always_kept(self):
        self.assertTrue(match_module('app')(make_record()))
        self.assertTrue(match_module('app', exclude=True)(make_record()))

    def test_in_a_logger_with_caller_information(self):
        logger, stream = make_logger(callerInfo=True)
        logger.add_filter(match_module(__name__, exclude=True))
        logger.info('written from this module')
        self.assertEqual(lines(stream), [])
        logger2, stream2 = make_logger(callerInfo=True)
        logger2.add_filter(match_module(__name__))
        logger2.info('kept')
        self.assertEqual(len(lines(stream2)), 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            match_module()
        with self.assertRaises(TypeError):
            match_module(3)
        with self.assertRaises(TypeError):
            match_module('a', exclude='no')


class TestMatchField(unittest.TestCase):

    def test_a_field_and_a_context_value_are_both_looked_at(self):
        keep = match_field('tenant', 'a', 'b')
        self.assertTrue(keep(make_record(fields={'tenant': 'a'})))
        self.assertTrue(keep(make_record(context={'tenant': 'b'})))
        self.assertFalse(keep(make_record(fields={'tenant': 'c'})))

    def test_a_field_that_does_not_match_does_not_hide_a_context_value_that_does(self):
        self.assertTrue(match_field('tenant', 'a')(make_record(fields={'tenant': 'c'}, context={'tenant': 'a'})))

    def test_a_missing_name_is_not_a_match(self):
        self.assertFalse(match_field('tenant', 'a')(make_record()))
        self.assertTrue(match_field('tenant', 'a', exclude=True)(make_record()))

    def test_exclude(self):
        keep = match_field('environment', 'test', exclude=True)
        self.assertFalse(keep(make_record(fields={'environment': 'test'})))
        self.assertTrue(keep(make_record(fields={'environment': 'production'})))

    def test_values_of_any_kind_are_compared_by_equality(self):
        keep = match_field('code', 5, None, [1, 2])
        self.assertTrue(keep(make_record(fields={'code': 5})))
        self.assertTrue(keep(make_record(fields={'code': None})))
        self.assertTrue(keep(make_record(fields={'code': [1, 2]})))
        self.assertTrue(keep(make_record(fields={'code': 5.0})))
        self.assertFalse(keep(make_record(fields={'code': {'unhashable': 1}})))

    def test_as_a_filter_of_one_sink_only(self):
        logger, stream = make_logger()
        other = io.StringIO()
        logger.add_sink('other', StreamSink(other, formatter=JsonFormatter()))
        logger.set_sink_filter('capture', match_field('category', 'security'))
        logger.info('security event', category='security')
        logger.info('other event', category='misc')
        self.assertEqual([line['message'] for line in lines(stream)], ['security event'])
        self.assertEqual(len(lines(other)), 2)

    def test_it_sees_what_a_processor_added(self):
        logger, stream = make_logger(processors=[add_context(environment='test')])
        logger.add_filter(match_field('environment', 'test', exclude=True))
        logger.info('hidden')
        self.assertEqual(lines(stream), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            match_field('a')
        for bad in ('', 1):
            with self.assertRaises(TypeError):
                match_field(bad, 1)
        with self.assertRaises(TypeError):
            match_field('a', 1, exclude=0)


if __name__ == '__main__':
    unittest.main()
