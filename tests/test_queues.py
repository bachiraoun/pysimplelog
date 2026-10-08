"""Tests of BoundedQueue on its own: the four policies, the counters, blocking, closing and many threads.

Run from the repo root::

    python3 -m unittest tests.test_queues -v
"""
import contextlib
import io
import os
import queue
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from queues import BoundedQueue, QueueFull, QUEUE_POLICIES, validate_queue_policy  # noqa: E402


def drain(boundedQueue):
    items = []
    while boundedQueue.depth > 0:
        items.append(boundedQueue.get(timeout=1))
        boundedQueue.task_done()
    return items


class TestValidation(unittest.TestCase):

    def test_the_four_policies(self):
        self.assertEqual(QUEUE_POLICIES, ('block', 'drop_newest', 'drop_oldest', 'reject'))
        for policy in QUEUE_POLICIES:
            self.assertEqual(validate_queue_policy(policy), policy)

    def test_bad_policies(self):
        for bad in (None, 1, b'block'):
            with self.assertRaises(TypeError):
                validate_queue_policy(bad)
        for bad in ('', 'Block', 'drop', 'drop-newest'):
            with self.assertRaises(ValueError):
                validate_queue_policy(bad)

    def test_bad_sizes(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                BoundedQueue(maxSize=bad)
        for bad in (1.5, '3', True):
            with self.assertRaises(TypeError):
                BoundedQueue(maxSize=bad)

    def test_bad_timeouts(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                BoundedQueue(maxSize=1, blockTimeout=bad)
        for bad in ('1', True):
            with self.assertRaises(TypeError):
                BoundedQueue(maxSize=1, blockTimeout=bad)

    def test_the_defaults(self):
        q = BoundedQueue()
        self.assertEqual((q.maxSize, q.policy, q.blockTimeout), (None, 'block', None))

    def test_a_failed_change_keeps_the_old_value(self):
        q = BoundedQueue(maxSize=3, policy='reject', blockTimeout=2)
        for call, bad in ((q.set_max_size, 0), (q.set_policy, 'nope'), (q.set_block_timeout, -1)):
            with self.assertRaises((TypeError, ValueError)):
                call(bad)
        self.assertEqual((q.maxSize, q.policy, q.blockTimeout), (3, 'reject', 2))


class TestOrderAndCounters(unittest.TestCase):

    def test_first_in_first_out(self):
        q = BoundedQueue(maxSize=10)
        for number in range(5):
            self.assertTrue(q.put(number))
        self.assertEqual(drain(q), [0, 1, 2, 3, 4])

    def test_no_limit_takes_everything(self):
        q = BoundedQueue(maxSize=None, policy='reject')
        for number in range(10000):
            q.put(number)
        self.assertEqual(q.stats()['depth'], 10000)
        self.assertEqual(q.stats()['dropped'] + q.stats()['rejected'], 0)

    def test_stats_keys_and_values(self):
        q = BoundedQueue(maxSize=2, policy='drop_newest', warn=False)
        for number in range(5):
            q.put(number)
        self.assertEqual(q.stats(), {'policy': 'drop_newest', 'capacity': 2, 'depth': 2, 'queued': 2, 'dropped': 3,
                                     'rejected': 0})

    def test_get_times_out_on_an_empty_queue(self):
        q = BoundedQueue(maxSize=1)
        started = time.monotonic()
        with self.assertRaises(queue.Empty):
            q.get(timeout=0.1)
        self.assertGreaterEqual(time.monotonic() - started, 0.09)

    def test_get_with_zero_timeout_does_not_wait(self):
        with self.assertRaises(queue.Empty):
            BoundedQueue().get(timeout=0)

    def test_put_last_ignores_the_size_and_the_policy(self):
        q = BoundedQueue(maxSize=1, policy='reject')
        q.put('a')
        q.put_last('stop')
        self.assertEqual(drain(q), ['a', 'stop'])

    def test_join_waits_for_task_done(self):
        q = BoundedQueue(maxSize=5)
        q.put(1)
        self.assertFalse(q.join(timeout=0.05))
        q.get()
        self.assertFalse(q.join(timeout=0.05))
        q.task_done()
        self.assertTrue(q.join(timeout=1))

    def test_join_on_an_empty_queue_returns_at_once(self):
        self.assertTrue(BoundedQueue().join(timeout=0))


class TestPolicies(unittest.TestCase):

    def test_drop_newest_keeps_the_old_ones(self):
        q = BoundedQueue(maxSize=3, policy='drop_newest', warn=False)
        results = [q.put(number) for number in range(6)]
        self.assertEqual(results, [True, True, True, False, False, False])
        self.assertEqual(drain(q), [0, 1, 2])
        self.assertEqual(q.stats()['dropped'], 3)

    def test_drop_oldest_keeps_the_new_ones_and_says_true(self):
        q = BoundedQueue(maxSize=3, policy='drop_oldest', warn=False)
        results = [q.put(number) for number in range(6)]
        self.assertTrue(all(results))
        self.assertEqual(drain(q), [3, 4, 5])
        self.assertEqual(q.stats()['dropped'], 3)
        self.assertEqual(q.stats()['queued'], 6)

    def test_drop_oldest_keeps_join_correct(self):
        q = BoundedQueue(maxSize=2, policy='drop_oldest', warn=False)
        for number in range(10):
            q.put(number)
        drain(q)
        self.assertTrue(q.join(timeout=1))

    def test_reject_raises_and_counts(self):
        q = BoundedQueue(maxSize=2, policy='reject')
        q.put(1)
        q.put(2)
        for _ in range(3):
            with self.assertRaises(QueueFull):
                q.put(3)
        self.assertEqual(q.stats()['rejected'], 3)
        self.assertEqual(drain(q), [1, 2])

    def test_queue_full_is_a_queue_dot_full(self):
        self.assertTrue(issubclass(QueueFull, queue.Full))

    def test_block_with_a_timeout_drops_the_new_one(self):
        q = BoundedQueue(maxSize=1, policy='block', blockTimeout=0.1, warn=False)
        q.put('a')
        started = time.monotonic()
        self.assertFalse(q.put('b'))
        self.assertGreaterEqual(time.monotonic() - started, 0.09)
        self.assertEqual(drain(q), ['a'])
        self.assertEqual(q.stats()['dropped'], 1)

    def test_block_waits_until_a_place_is_free(self):
        q = BoundedQueue(maxSize=1, policy='block')
        q.put('a')
        outcome = []
        thread = threading.Thread(target=lambda: outcome.append(q.put('b')))
        thread.start()
        time.sleep(0.1)
        self.assertTrue(thread.is_alive())
        self.assertEqual(q.get(), 'a')
        thread.join(2)
        self.assertEqual(outcome, [True])
        self.assertEqual(drain(q), ['b'])

    def test_a_bigger_size_frees_a_blocked_caller(self):
        q = BoundedQueue(maxSize=1, policy='block')
        q.put('a')
        outcome = []
        thread = threading.Thread(target=lambda: outcome.append(q.put('b')))
        thread.start()
        time.sleep(0.1)
        q.set_max_size(None)
        thread.join(2)
        self.assertEqual(outcome, [True])

    def test_changing_the_policy_applies_to_the_next_put(self):
        q = BoundedQueue(maxSize=1, policy='drop_newest', warn=False)
        q.put('a')
        self.assertFalse(q.put('b'))
        q.set_policy('drop_oldest')
        self.assertTrue(q.put('c'))
        q.set_policy('reject')
        with self.assertRaises(QueueFull):
            q.put('d')
        self.assertEqual(drain(q), ['c'])

    def test_a_smaller_size_does_not_lose_what_is_queued(self):
        q = BoundedQueue(maxSize=5, policy='drop_newest', warn=False)
        for number in range(5):
            q.put(number)
        q.set_max_size(2)
        self.assertFalse(q.put('x'))
        self.assertEqual(drain(q), [0, 1, 2, 3, 4])


class TestWarning(unittest.TestCase):

    def _put_many(self, q, count):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            for number in range(count):
                q.put(number)
        return error.getvalue()

    def test_one_warning_for_a_run_of_losses(self):
        q = BoundedQueue(maxSize=1, policy='drop_newest', name='the test queue')
        text = self._put_many(q, 50)
        self.assertEqual(text.count('WARNING'), 1)
        self.assertIn('the test queue', text)

    def test_a_new_run_warns_again(self):
        q = BoundedQueue(maxSize=1, policy='drop_newest')
        first = self._put_many(q, 5)
        drain(q)
        second = self._put_many(q, 5)
        self.assertEqual((first.count('WARNING'), second.count('WARNING')), (1, 1))

    def test_warn_false_stays_silent_and_still_counts(self):
        q = BoundedQueue(maxSize=1, policy='drop_newest', warn=False)
        self.assertEqual(self._put_many(q, 10), '')
        self.assertEqual(q.stats()['dropped'], 9)

    def test_a_broken_error_stream_does_not_lose_the_count(self):
        class Broken:
            def write(self, text):
                raise OSError('closed')
        q = BoundedQueue(maxSize=1, policy='drop_newest')
        q.put(0)
        with contextlib.redirect_stderr(Broken()):
            q.put(1)
        self.assertEqual(q.stats()['dropped'], 1)


class TestManyThreads(unittest.TestCase):

    def test_nothing_is_lost_or_doubled_under_block(self):
        q = BoundedQueue(maxSize=4, policy='block')
        producers, perProducer = 8, 500
        received = []
        lock = threading.Lock()

        def consume():
            while True:
                item = q.get()
                if item is None:
                    q.task_done()
                    return
                with lock:
                    received.append(item)
                q.task_done()

        consumers = [threading.Thread(target=consume) for _ in range(3)]
        for thread in consumers:
            thread.start()
        threads = [threading.Thread(target=lambda n=n: [q.put((n, i)) for i in range(perProducer)]) for n in range(producers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        for _ in consumers:
            q.put_last(None)
        for thread in consumers:
            thread.join(30)
        self.assertEqual(len(received), producers * perProducer)
        self.assertEqual(len(set(received)), producers * perProducer)
        for n in range(producers):
            sequence = [i for who, i in received if who == n]
            self.assertEqual(len(sequence), perProducer)
        self.assertEqual(q.stats()['dropped'], 0)

    def test_the_counters_add_up_under_drop_newest(self):
        q = BoundedQueue(maxSize=10, policy='drop_newest', warn=False)
        threads = [threading.Thread(target=lambda: [q.put(i) for i in range(1000)]) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        stats = q.stats()
        self.assertEqual(stats['queued'] + stats['dropped'], 6000)
        self.assertEqual((stats['queued'], stats['depth']), (10, 10))

    def test_the_counters_add_up_under_drop_oldest(self):
        q = BoundedQueue(maxSize=10, policy='drop_oldest', warn=False)
        threads = [threading.Thread(target=lambda: [q.put(i) for i in range(1000)]) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        stats = q.stats()
        self.assertEqual(stats['queued'], 6000)
        self.assertEqual(stats['queued'] - stats['dropped'], stats['depth'])
        self.assertEqual(stats['depth'], 10)

    def test_reject_counts_every_refusal(self):
        q = BoundedQueue(maxSize=5, policy='reject')
        refused = []

        def produce():
            count = 0
            for i in range(500):
                try:
                    q.put(i)
                except QueueFull:
                    count += 1
            refused.append(count)

        threads = [threading.Thread(target=produce) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(sum(refused), q.stats()['rejected'])
        self.assertEqual(sum(refused) + q.stats()['queued'], 2500)

    def test_many_blocked_producers_all_get_in_as_a_consumer_takes(self):
        q = BoundedQueue(maxSize=1, policy='block')
        q.put('first')
        results = []
        threads = [threading.Thread(target=lambda n=n: results.append(q.put(n))) for n in range(10)]
        for thread in threads:
            thread.start()
        time.sleep(0.1)
        taken = []
        for _ in range(11):
            taken.append(q.get(timeout=5))
            q.task_done()
        for thread in threads:
            thread.join(5)
        self.assertEqual(sorted(x for x in taken if x != 'first'), list(range(10)))
        self.assertTrue(all(results))


class TestGetBatch(unittest.TestCase):

    @staticmethod
    def is_marker(item):
        return item == 'MARK'

    def test_what_is_waiting_is_taken_at_once_up_to_the_limit(self):
        q = BoundedQueue()
        for number in range(10):
            q.put(number)
        started = time.monotonic()
        items, marker = q.get_batch(4, 5.0, self.is_marker)
        self.assertEqual((items, marker), ([0, 1, 2, 3], None))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(q.depth, 6)

    def test_a_group_smaller_than_the_limit_waits_for_the_linger_and_no_longer(self):
        q = BoundedQueue()
        q.put('a')
        started = time.monotonic()
        items, marker = q.get_batch(10, 0.2, self.is_marker)
        elapsed = time.monotonic() - started
        self.assertEqual((items, marker), (['a'], None))
        self.assertTrue(0.15 < elapsed < 1.5, elapsed)

    def test_the_linger_counts_from_the_first_item_and_not_from_each_one(self):
        q = BoundedQueue()
        q.put(0)

        def feed():
            for number in range(1, 20):
                time.sleep(0.03)
                q.put(number)
        thread = threading.Thread(target=feed)
        thread.start()
        started = time.monotonic()
        items, _ = q.get_batch(1000, 0.3, self.is_marker)
        elapsed = time.monotonic() - started
        thread.join(5)
        self.assertTrue(0.25 < elapsed < 1.0, elapsed)
        self.assertEqual(items, list(range(len(items))))
        self.assertGreater(len(items), 3)

    def test_the_group_ends_as_soon_as_it_is_full_without_waiting_for_the_linger(self):
        q = BoundedQueue()
        q.put(0)

        def feed():
            time.sleep(0.05)
            for number in range(1, 5):
                q.put(number)
        thread = threading.Thread(target=feed)
        thread.start()
        started = time.monotonic()
        items, _ = q.get_batch(5, 30.0, self.is_marker)
        thread.join(5)
        self.assertEqual(items, [0, 1, 2, 3, 4])
        self.assertLess(time.monotonic() - started, 3.0)

    def test_a_marker_ends_the_group_at_once_and_is_returned_apart(self):
        q = BoundedQueue()
        q.put('a')
        q.put('b')
        q.put('MARK')
        q.put('c')
        started = time.monotonic()
        items, marker = q.get_batch(10, 30.0, self.is_marker)
        self.assertEqual((items, marker), (['a', 'b'], 'MARK'))
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(q.get(), 'c')

    def test_a_marker_that_arrives_during_the_wait_ends_it(self):
        q = BoundedQueue()
        q.put('a')
        threading.Timer(0.1, lambda: q.put_last('MARK')).start()
        started = time.monotonic()
        items, marker = q.get_batch(10, 30.0, self.is_marker)
        self.assertEqual((items, marker), (['a'], 'MARK'))
        self.assertLess(time.monotonic() - started, 3.0)

    def test_a_marker_first_gives_an_empty_group(self):
        q = BoundedQueue()
        q.put_last('MARK')
        q.put('a')
        self.assertEqual(q.get_batch(10, 30.0, self.is_marker), ([], 'MARK'))
        self.assertEqual(q.get(), 'a')

    def test_the_first_item_is_waited_for_and_the_timeout_applies_to_it(self):
        q = BoundedQueue()
        started = time.monotonic()
        with self.assertRaises(queue.Empty):
            q.get_batch(10, 5.0, self.is_marker, timeout=0.1)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_a_group_of_one_with_no_linger_behaves_like_get(self):
        q = BoundedQueue()
        q.put('a')
        q.put('b')
        self.assertEqual(q.get_batch(1, 0, self.is_marker), (['a'], None))

    def test_every_item_taken_needs_its_task_done(self):
        q = BoundedQueue()
        for number in range(3):
            q.put(number)
        q.put_last('MARK')
        items, marker = q.get_batch(10, 0, self.is_marker)
        self.assertFalse(q.join(timeout=0.05))
        for _ in range(len(items) + 1):
            q.task_done()
        self.assertTrue(q.join(timeout=1))

    def test_producers_blocked_on_a_full_queue_get_in_while_a_group_waits_to_fill(self):
        q = BoundedQueue(maxSize=2, policy='block')
        q.put('a')
        q.put('b')
        results = []
        thread = threading.Thread(target=lambda: results.append(q.put('c')))
        thread.start()
        time.sleep(0.05)
        started = time.monotonic()
        items, _ = q.get_batch(10, 0.6, self.is_marker)
        thread.join(5)
        self.assertEqual((results, items), ([True], ['a', 'b', 'c']))
        self.assertLess(time.monotonic() - started, 3.0)

    def test_many_producers_and_a_group_worker_lose_nothing(self):
        q = BoundedQueue(maxSize=8, policy='block')
        received = []

        def consume():
            while True:
                items, marker = q.get_batch(7, 0.01, self.is_marker)
                received.extend(items)
                for _ in range(len(items) + (marker is not None)):
                    q.task_done()
                if marker is not None:
                    return

        consumer = threading.Thread(target=consume)
        consumer.start()
        threads = [threading.Thread(target=lambda n=n: [q.put((n, i)) for i in range(300)]) for n in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        q.put_last('MARK')
        consumer.join(30)
        self.assertEqual(len(received), 1800)
        self.assertEqual(len(set(received)), 1800)
        for n in range(6):
            self.assertEqual([i for who, i in received if who == n], list(range(300)))


if __name__ == '__main__':
    unittest.main()
