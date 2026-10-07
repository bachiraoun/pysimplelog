"""Tests of the ambient context: nesting, restore, threads, asynchronous tasks, bind, and where the values show up.

Run from the repo root::

    python3 -m unittest tests.test_context -v
"""
import asyncio
import concurrent.futures
import contextvars
import io
import json
import logging
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from simple_log import Logger  # noqa: E402
from formatters import JsonFormatter  # noqa: E402
from log_context import context, current_context, CURRENT_CONTEXT  # noqa: E402
from sinks import StreamSink  # noqa: E402
from standard_logging import redirect_standard_logging, restore_standard_logging  # noqa: E402


def make_logger(**arguments):
    stream = io.StringIO()
    logger = Logger('app', logToFile=False, logToStdout=False, **arguments)
    logger.add_sink('capture', StreamSink(stream, formatter=JsonFormatter()))
    return logger, stream


def contexts(stream):
    return [json.loads(line).get('context', {}) for line in stream.getvalue().splitlines()]


class TestScopes(unittest.TestCase):

    def test_outside_every_block_it_is_empty(self):
        self.assertEqual(dict(current_context()), {})

    def test_inside_a_block_the_values_are_there_and_after_it_they_are_gone(self):
        with context(a=1, b='two'):
            self.assertEqual(dict(current_context()), {'a': 1, 'b': 'two'})
        self.assertEqual(dict(current_context()), {})

    def test_blocks_nest_and_the_inner_value_wins_until_it_ends(self):
        with context(a=1, b=1):
            with context(b=2, c=3):
                self.assertEqual(dict(current_context()), {'a': 1, 'b': 2, 'c': 3})
            self.assertEqual(dict(current_context()), {'a': 1, 'b': 1})

    def test_the_outer_value_is_back_after_an_exception(self):
        with context(a=1):
            with self.assertRaises(RuntimeError):
                with context(a=2):
                    raise RuntimeError('boom')
            self.assertEqual(current_context()['a'], 1)
        self.assertEqual(dict(current_context()), {})

    def test_a_scope_cannot_be_entered_twice_at_once(self):
        scope = context(a=1)
        with scope:
            with self.assertRaises(RuntimeError):
                scope.__enter__()
            self.assertEqual(current_context()['a'], 1)
        self.assertEqual(dict(current_context()), {})

    def test_a_scope_can_be_used_again_after_it_ended(self):
        scope = context(a=1)
        for _ in range(3):
            with scope:
                self.assertEqual(current_context()['a'], 1)
            self.assertEqual(dict(current_context()), {})

    def test_the_view_cannot_be_changed(self):
        with context(a=1):
            with self.assertRaises(TypeError):
                current_context()['b'] = 2

    def test_a_view_taken_earlier_does_not_change_later(self):
        with context(a=1):
            before = dict(current_context())
            with context(b=2):
                pass
            self.assertEqual(dict(current_context()), before)

    def test_values_of_any_type(self):
        marker = object()
        with context(number=1.5, nothing=None, thing=marker, items=[1, 2]):
            self.assertIs(current_context()['thing'], marker)
            self.assertIsNone(current_context()['nothing'])

    def test_no_values_is_allowed(self):
        with context():
            self.assertEqual(dict(current_context()), {})

    def test_a_great_many_scopes_leave_nothing_behind(self):
        for number in range(2000):
            with context(n=number):
                with context(m=number):
                    pass
        self.assertEqual(dict(current_context()), {})
        self.assertEqual(len(CURRENT_CONTEXT.get()), 0)

    def test_deep_nesting(self):
        scopes = [context(**{f'k{depth}': depth}) for depth in range(200)]
        for scope in scopes:
            scope.__enter__()
        self.assertEqual(len(current_context()), 200)
        for scope in reversed(scopes):
            scope.__exit__(None, None, None)
        self.assertEqual(dict(current_context()), {})

    def test_a_block_ended_in_another_context_does_not_raise(self):
        # An asynchronous generator can end its block in a context other than the one it began in. The test runs in a copy
        # of the context so that what the library leaves behind in that case cannot reach the other tests
        outcome = []

        def generator():
            with context(inside=1):
                yield

        def body():
            run = generator()
            next(run)
            try:
                contextvars.copy_context().run(run.close)
            except Exception as error:
                outcome.append(error)

        contextvars.copy_context().run(body)
        self.assertEqual(outcome, [])


class TestThreadsAndTasks(unittest.TestCase):

    def test_a_plain_thread_starts_empty(self):
        seen = []
        with context(a=1):
            thread = threading.Thread(target=lambda: seen.append(dict(current_context())))
            thread.start()
            thread.join(5)
        self.assertEqual(seen, [{}])

    def test_a_thread_given_a_copy_of_the_context_sees_it(self):
        seen = []
        with context(a=1):
            copied = contextvars.copy_context()
            thread = threading.Thread(target=lambda: copied.run(lambda: seen.append(dict(current_context()))))
            thread.start()
            thread.join(5)
        self.assertEqual(seen, [{'a': 1}])

    def test_threads_keep_their_own_values(self):
        failures = []
        barrier = threading.Barrier(8)

        def work(number):
            with context(worker=number):
                barrier.wait(5)
                for _ in range(200):
                    if current_context().get('worker') != number:
                        failures.append(number)
                with context(inner=number):
                    if dict(current_context()) != {'worker': number, 'inner': number}:
                        failures.append(number)

        threads = [threading.Thread(target=work, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(failures, [])
        self.assertEqual(dict(current_context()), {})

    def test_a_thread_pool_does_not_inherit_unless_asked(self):
        with context(a=1):
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                plain = pool.submit(lambda: dict(current_context())).result(5)
                copied = pool.submit(contextvars.copy_context().run, lambda: dict(current_context())).result(5)
        self.assertEqual((plain, copied), ({}, {'a': 1}))

    def test_tasks_keep_their_own_values(self):
        async def task_with_inner(number, results):
            with context(task=number):
                await asyncio.sleep(0.01 * (5 - number))
                with context(inner=number):
                    await asyncio.sleep(0.01)
                    results.append((number, current_context()['task'], current_context()['inner']))

        async def main():
            results = []
            await asyncio.gather(*(task_with_inner(number, results) for number in range(5)))
            return results

        results = asyncio.run(main())
        self.assertEqual(sorted(results), [(number, number, number) for number in range(5)])

    def test_a_task_inherits_the_values_at_the_moment_it_starts(self):
        async def child(results):
            await asyncio.sleep(0.02)
            results.append(dict(current_context()))

        async def main():
            results = []
            with context(a=1):
                task = asyncio.ensure_future(child(results))
            await task
            return results

        self.assertEqual(asyncio.run(main()), [{'a': 1}])

    def test_to_thread_carries_the_values(self):
        async def main():
            with context(a=1):
                return await asyncio.to_thread(lambda: dict(current_context()))
        self.assertEqual(asyncio.run(main()), {'a': 1})


class TestInTheRecords(unittest.TestCase):

    def test_the_values_are_in_the_context_of_the_record_and_not_in_its_fields(self):
        logger, stream = make_logger()
        with context(request_id='r1'):
            logger.info('hello', order=5)
        line = json.loads(stream.getvalue())
        self.assertEqual(line['context'], {'request_id': 'r1'})
        self.assertEqual(line['fields'], {'order': 5})

    def test_outside_a_block_there_is_no_context_key(self):
        logger, stream = make_logger()
        logger.info('hello')
        self.assertNotIn('context', json.loads(stream.getvalue()))

    def test_every_logger_and_every_sink_sees_it(self):
        first, firstStream = make_logger()
        second, secondStream = make_logger()
        other = io.StringIO()
        first.add_sink('second', StreamSink(other, formatter=JsonFormatter()))
        with context(a=1):
            first.info('one')
            second.warn('two')
        self.assertEqual(contexts(firstStream) + contexts(secondStream) + contexts(other), [{'a': 1}] * 3)

    def test_the_logger_method_opens_the_same_kind_of_block(self):
        logger, stream = make_logger()
        with logger.context(a=1):
            logger.info('one')
        logger.info('two')
        self.assertEqual(contexts(stream), [{'a': 1}, {}])

    def test_every_log_type_carries_it(self):
        logger, stream = make_logger()
        with context(a=1):
            for logType in ('debug', 'info', 'warn', 'error', 'critical'):
                logger.log(logType, 'm')
        self.assertEqual(contexts(stream), [{'a': 1}] * 5)

    def test_the_values_are_taken_when_the_call_is_made_not_when_it_is_written(self):
        logger, stream = make_logger(enqueue=True)
        with context(a=1):
            logger.info('queued')
        logger.flush()
        self.assertEqual(contexts(stream), [{'a': 1}])

    def test_a_threaded_logger_does_not_mix_up_the_threads(self):
        logger, stream = make_logger(enqueue=True)

        def work(number):
            with context(worker=number):
                for index in range(50):
                    logger.info(f'{number}-{index}')

        threads = [threading.Thread(target=work, args=(number,)) for number in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        logger.flush()
        for line in stream.getvalue().splitlines():
            parsed = json.loads(line)
            self.assertEqual(parsed['message'].split('-')[0], str(parsed['context']['worker']))
        self.assertEqual(len(stream.getvalue().splitlines()), 300)

    def test_a_change_of_a_value_after_the_call_does_not_reach_the_record(self):
        logger, stream = make_logger()
        items = [1]
        with context(items=items):
            logger.info('m')
        self.assertEqual(contexts(stream), [{'items': [1]}])


class TestBind(unittest.TestCase):

    def test_bound_values_are_in_the_context(self):
        logger, stream = make_logger()
        logger.bind(user='ann').info('m')
        self.assertEqual(contexts(stream), [{'user': 'ann'}])

    def test_bound_and_block_values_merge_and_the_bound_one_wins(self):
        logger, stream = make_logger()
        with context(user='block', request='r1'):
            logger.bind(user='bound').info('m')
        self.assertEqual(contexts(stream), [{'user': 'bound', 'request': 'r1'}])

    def test_bind_does_not_change_the_block_afterwards(self):
        logger, stream = make_logger()
        with context(a=1):
            logger.bind(b=2).info('one')
            logger.info('two')
        self.assertEqual(contexts(stream), [{'a': 1, 'b': 2}, {'a': 1}])

    def test_binding_twice_adds_and_the_later_wins(self):
        logger, stream = make_logger()
        logger.bind(a=1, b=1).bind(b=2, c=3).info('m')
        self.assertEqual(contexts(stream), [{'a': 1, 'b': 2, 'c': 3}])

    def test_the_original_logger_is_not_bound(self):
        logger, stream = make_logger()
        logger.bind(a=1)
        logger.info('m')
        self.assertEqual(contexts(stream), [{}])

    def test_a_bound_logger_called_from_two_threads_does_not_mix(self):
        logger, stream = make_logger()
        bound = [logger.bind(who=number) for number in range(4)]

        def work(number):
            for _ in range(100):
                bound[number].info(str(number))

        threads = [threading.Thread(target=work, args=(number,)) for number in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        for line in stream.getvalue().splitlines():
            parsed = json.loads(line)
            self.assertEqual(parsed['message'], str(parsed['context']['who']))
        self.assertEqual(dict(current_context()), {})


class TestStandardLoggingBridge(unittest.TestCase):

    def test_the_records_of_the_standard_library_carry_the_block_values(self):
        logger, stream = make_logger()
        handler = redirect_standard_logging(logger, name='context.bridge.test', loggerLevel=logging.INFO)
        try:
            with context(request_id='r9'):
                logging.getLogger('context.bridge.test').info('from the library')
            logging.getLogger('context.bridge.test').info('outside')
        finally:
            restore_standard_logging(handler)
        self.assertEqual(contexts(stream), [{'request_id': 'r9'}, {}])


if __name__ == '__main__':
    unittest.main()
