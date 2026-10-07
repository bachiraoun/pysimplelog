"""Tests of the immutable record: creation, read-only views, copies, pickling and validation.

Run from the repo root::

    python3 -m unittest tests.test_record -v
"""
import copy
import os
import pickle
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from record import LogRecord, ExceptionInfo, CallerInfo, validate_record, EMPTY_MAPPING  # noqa: E402

TIMESTAMP = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone.utc)


def make_record(**changes):
    values = dict(timestamp=TIMESTAMP, severity='INFO', logType='info', level=10.0, logger='orders', message='hello',
                  processId=1, threadId=2, threadName='main')
    values.update(changes)
    return LogRecord.create(**values)


class TestCreate(unittest.TestCase):

    def test_every_value_is_kept(self):
        exception = ExceptionInfo('ValueError', 'bad', 'trace')
        caller = CallerInfo('a.py', 3, 'run', 'pkg.a')
        record = make_record(fields={'a': 1}, context={'b': 2}, exception=exception, caller=caller)
        self.assertEqual((record.timestamp, record.severity, record.logType, record.level), (TIMESTAMP, 'INFO', 'info', 10.0))
        self.assertEqual((record.logger, record.message, record.processId, record.threadId, record.threadName),
                         ('orders', 'hello', 1, 2, 'main'))
        self.assertEqual((dict(record.fields), dict(record.context)), ({'a': 1}, {'b': 2}))
        self.assertIs(record.exception, exception)
        self.assertIs(record.caller, caller)

    def test_a_missing_fields_context_exception_and_caller_are_empty(self):
        record = make_record()
        self.assertEqual((len(record.fields), len(record.context)), (0, 0))
        self.assertIs(record.fields, EMPTY_MAPPING)
        self.assertIs(record.context, EMPTY_MAPPING)
        self.assertIsNone(record.exception)
        self.assertIsNone(record.caller)

    def test_a_level_can_be_none(self):
        self.assertIsNone(make_record(level=None).level)

    def test_the_positional_order_is_the_documented_one(self):
        record = LogRecord.create(TIMESTAMP, 'WARN', 'warn', 20.0, 'x', 'm', 5, 6, 't')
        self.assertEqual(tuple(record)[:9], (TIMESTAMP, 'WARN', 'warn', 20.0, 'x', 'm', 5, 6, 't'))
        self.assertEqual(LogRecord._fields, ('timestamp', 'severity', 'logType', 'level', 'logger', 'message', 'processId',
                                             'threadId', 'threadName', 'fields', 'context', 'exception', 'caller'))


class TestImmutable(unittest.TestCase):

    def test_no_attribute_can_be_set(self):
        record = make_record()
        for name in LogRecord._fields:
            with self.assertRaises(AttributeError, msg=name):
                setattr(record, name, 'x')

    def test_no_attribute_can_be_added_or_deleted(self):
        record = make_record()
        with self.assertRaises(AttributeError):
            record.extra = 1
        with self.assertRaises(AttributeError):
            del record.message

    def test_fields_and_context_are_read_only(self):
        record = make_record(fields={'a': 1}, context={'b': 2})
        for mapping in (record.fields, record.context):
            with self.assertRaises(TypeError):
                mapping['new'] = 1
            with self.assertRaises(TypeError):
                del mapping[next(iter(mapping))]
            with self.assertRaises(AttributeError):
                mapping.update({'x': 1})
            with self.assertRaises(AttributeError):
                mapping.clear()

    def test_the_empty_views_are_read_only_too(self):
        for mapping in (make_record().fields, make_record().context):
            with self.assertRaises(TypeError):
                mapping['x'] = 1

    def test_replace_gives_a_new_record_and_leaves_the_old_one(self):
        record = make_record(fields={'a': 1})
        changed = record._replace(message='other', level=30.0)
        self.assertIsNot(changed, record)
        self.assertEqual((record.message, record.level), ('hello', 10.0))
        self.assertEqual((changed.message, changed.level, changed.logger), ('other', 30.0, 'orders'))
        self.assertIs(changed.fields, record.fields)

    def test_the_view_follows_the_dictionary_it_was_given(self):
        # Documented: the view is not a copy, so the dictionary must not be changed afterwards
        source = {'a': 1}
        record = make_record(fields=source)
        source['a'] = 2
        self.assertEqual(record.fields['a'], 2)


class TestValueSemantics(unittest.TestCase):

    def test_equal_records_are_equal(self):
        self.assertEqual(make_record(fields={'a': 1}), make_record(fields={'a': 1}))
        self.assertNotEqual(make_record(fields={'a': 1}), make_record(fields={'a': 2}))
        self.assertNotEqual(make_record(), make_record(message='other'))

    def test_a_record_can_be_unpacked_and_indexed(self):
        record = make_record()
        self.assertEqual(record[5], 'hello')
        self.assertEqual(len(record), 13)
        timestamp, *_ = record
        self.assertEqual(timestamp, TIMESTAMP)

    def test_a_record_of_hashable_values_can_be_hashed_only_without_mappings(self):
        # A mapping view is not hashable, so a record is not either, which keeps it from being used as a key by mistake
        with self.assertRaises(TypeError):
            hash(make_record())

    def test_a_shallow_copy_is_equal(self):
        record = make_record(fields={'a': [1, 2]})
        self.assertEqual(copy.copy(record), record)

    def test_a_deep_copy_is_equal_and_shares_nothing(self):
        record = make_record(fields={'a': [1, 2]}, context={'b': {'c': 1}}, exception=ExceptionInfo('E', 'm', 't'),
                             caller=CallerInfo('a.py', 1, 'f', 'm'))
        copied = copy.deepcopy(record)
        self.assertEqual(copied, record)
        self.assertIsNot(copied.fields['a'], record.fields['a'])
        self.assertIsNot(copied.context['b'], record.context['b'])
        with self.assertRaises(TypeError):
            copied.fields['new'] = 1

    def test_timestamps_keep_the_microseconds_and_the_zone(self):
        zone = timezone(timedelta(hours=-5))
        record = make_record(timestamp=datetime(2026, 1, 1, 0, 0, 0, 1, tzinfo=zone))
        self.assertEqual(record.timestamp.microsecond, 1)
        self.assertEqual(record.timestamp.utcoffset(), timedelta(hours=-5))


class TestNestedTuples(unittest.TestCase):

    def test_exception_info_and_caller_info_are_immutable(self):
        exception = ExceptionInfo('E', 'm', 't')
        caller = CallerInfo('a.py', 1, 'f', 'm')
        with self.assertRaises(AttributeError):
            exception.message = 'x'
        with self.assertRaises(AttributeError):
            caller.line = 2

    def test_exception_info_allows_none_for_type_and_message(self):
        info = ExceptionInfo(None, None, 'only the text')
        self.assertEqual((info.typeName, info.message, info.stacktrace), (None, None, 'only the text'))

    def test_field_names(self):
        self.assertEqual(ExceptionInfo._fields, ('typeName', 'message', 'stacktrace'))
        self.assertEqual(CallerInfo._fields, ('fileName', 'line', 'function', 'moduleName'))


class TestValidate(unittest.TestCase):

    def test_a_good_record_passes(self):
        validate_record(make_record())
        validate_record(make_record(level=None, fields={'a': 1}, context={'b': 2}, exception=ExceptionInfo(None, None, 't'),
                                    caller=CallerInfo('a.py', 1, 'f', 'm')))

    def test_an_int_level_passes(self):
        validate_record(make_record(level=10))

    def test_what_is_not_a_record_is_refused(self):
        for bad in (None, {}, 'record', tuple(make_record())):
            with self.assertRaises(TypeError):
                validate_record(bad)

    def test_each_wrong_value_is_refused(self):
        bad_values = [
            ('timestamp', '2026-01-01'), ('timestamp', datetime(2026, 1, 1)), ('timestamp', None),
            ('severity', 1), ('logType', None), ('level', 'high'), ('level', True), ('logger', 1), ('message', b'bytes'),
            ('message', None), ('processId', 1.5), ('processId', True), ('threadId', '2'), ('threadName', 5),
            ('fields', [('a', 1)]), ('fields', {1: 'x'}), ('context', None), ('context', {2: 'x'}),
            ('exception', 'error'), ('exception', ExceptionInfo(1, 'm', 't')), ('exception', ExceptionInfo('E', 1, 't')),
            ('exception', ExceptionInfo('E', 'm', None)), ('caller', ('a.py', 1, 'f', 'm')),
            ('caller', CallerInfo(1, 1, 'f', 'm')), ('caller', CallerInfo('a.py', '1', 'f', 'm')),
            ('caller', CallerInfo('a.py', True, 'f', 'm')), ('caller', CallerInfo('a.py', 1, None, 'm')),
            ('caller', CallerInfo('a.py', 1, 'f', None)),
        ]
        for name, value in bad_values:
            with self.subTest(name=name, value=value):
                record = make_record()._replace(**{name: value})
                with self.assertRaises(TypeError):
                    validate_record(record)

    def test_a_plain_dict_is_accepted_as_a_mapping(self):
        validate_record(make_record()._replace(fields={'a': 1}))


class TestPickle(unittest.TestCase):

    def test_plain_tuples_survive_pickle(self):
        for original in (ExceptionInfo('E', 'm', 't'), CallerInfo('a.py', 1, 'f', 'm')):
            self.assertEqual(pickle.loads(pickle.dumps(original)), original)

    def test_a_record_survives_pickle_on_every_protocol(self):
        record = make_record(fields={'a': [1, 2], 'n': None}, context={'b': 'x'}, exception=ExceptionInfo('E', None, 't'),
                             caller=CallerInfo('a.py', 1, 'f', 'm'))
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                loaded = pickle.loads(pickle.dumps(record, protocol))
                self.assertEqual(loaded, record)
                self.assertIsInstance(loaded, LogRecord)

    def test_a_pickled_record_is_still_read_only(self):
        loaded = pickle.loads(pickle.dumps(make_record(fields={'a': 1}, context={'b': 2})))
        for mapping in (loaded.fields, loaded.context):
            with self.assertRaises(TypeError):
                mapping['x'] = 1
        with self.assertRaises(AttributeError):
            loaded.message = 'x'

    def test_an_empty_record_comes_back_with_the_shared_empty_views(self):
        loaded = pickle.loads(pickle.dumps(make_record()))
        self.assertIs(loaded.fields, EMPTY_MAPPING)
        self.assertIs(loaded.context, EMPTY_MAPPING)

    def test_the_zone_and_the_microseconds_survive(self):
        zone = timezone(timedelta(hours=5, minutes=30))
        record = make_record(timestamp=datetime(2026, 3, 4, 5, 6, 7, 891011, tzinfo=zone))
        loaded = pickle.loads(pickle.dumps(record))
        self.assertEqual((loaded.timestamp, loaded.timestamp.utcoffset()), (record.timestamp, timedelta(hours=5, minutes=30)))

    def test_a_field_that_cannot_be_pickled_still_fails_clearly(self):
        import threading
        with self.assertRaises(TypeError):
            pickle.dumps(make_record(fields={'lock': threading.Lock()}))

    def test_a_record_crosses_a_process_boundary(self):
        import multiprocessing
        record = make_record(fields={'a': 1}, context={'b': 2})
        context = multiprocessing.get_context('spawn')
        with context.Pool(1) as pool:
            echoed = pool.apply(echo_record, (record,))
        self.assertEqual(echoed, record)
        with self.assertRaises(TypeError):
            echoed.fields['x'] = 1


def echo_record(record):
    """Runs in another process and sends the record back."""
    return record


if __name__ == '__main__':
    unittest.main()
