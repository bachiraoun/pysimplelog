"""A bounded queue with explicit overflow policies, and the counters that make every loss visible."""

import collections
import queue
import sys
import threading
import time

try:
    from .forking import register_for_fork_reset
except ImportError:
    from forking import register_for_fork_reset

QUEUE_POLICIES = ('block', 'drop_newest', 'drop_oldest', 'reject')


class QueueFull(queue.Full):
    """Raised when a record is put in a full queue whose policy is ``reject``."""


def validate_queue_policy(policy):
    """
    Checks a queue overflow policy and returns it.

    ``block`` makes the caller wait for a free place, for at most the block timeout when there is one, and
    drops the new record if the timeout ends. ``drop_newest`` throws the new record away. ``drop_oldest`` throws the
    record that has waited longest away and keeps the new one. ``reject`` makes the caller's log call raise
    :class:`QueueFull`. Every record that is thrown away or rejected is counted.

    :Parameters:
        #. policy (str): One of ``block``, ``drop_newest``, ``drop_oldest`` or ``reject``.

    :Returns:
        #. policy (str): The checked policy.

    :Raises:
        #. TypeError: If policy is not a string.
        #. ValueError: If policy is a string but not one of the four.
    """
    if not isinstance(policy, str):
        raise TypeError(f"the queue policy must be a string, one of {QUEUE_POLICIES}")
    if policy not in QUEUE_POLICIES:
        raise ValueError(f"the queue policy must be one of {QUEUE_POLICIES}, got {policy!r}")
    return policy


class BoundedQueue:
    """
    A thread-safe first-in first-out queue that says what happens when it is full.

    Nothing is lost without being counted: :meth:`stats` gives the number of records that were queued, thrown away
    and rejected, and how many wait now. One warning is written to the standard error stream for each run of lost
    records.

    :Parameters:
        #. maxSize (None, int): Largest number of waiting records. None means no limit.
        #. policy (str): What a full queue does with a new record, see :func:`validate_queue_policy`.
        #. blockTimeout (None, int, float): Seconds the ``block`` policy waits for a free place. None waits as long
           as it takes.
        #. name (str): How the queue is called in the warning.
        #. warn (bool): False to write no warning when records are thrown away. They are still counted. For a queue whose
           records are kept somewhere else, so that throwing one away loses nothing.

    :Raises:
        #. TypeError: If an argument has the wrong type.
        #. ValueError: If maxSize or blockTimeout is not positive, or policy is not one of the four.
    """

    def __init__(self, maxSize=None, policy='block', blockTimeout=None, name='queue', warn=True):
        self.__condition = threading.Condition()
        self.__items = collections.deque()
        self.__unfinished = 0
        self.__queued = 0
        self.__dropped = 0
        self.__rejected = 0
        self.__isDropping = False
        self.__name = name
        self.__warn = warn
        self.__maxSize = None
        self.__policy = None
        self.__blockTimeout = None
        self.set_max_size(maxSize)
        self.set_policy(policy)
        self.set_block_timeout(blockTimeout)
        register_for_fork_reset(self)

    def _reset_after_fork(self):
        """Gives a forked process a lock of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        self.__condition = threading.Condition()

    def set_max_size(self, maxSize):
        """
        Changes the largest number of waiting records. The next put uses it.

        :Parameters:
            #. maxSize (None, int): The new size, or None for no limit.

        :Raises:
            #. TypeError: If maxSize is not an integer or None.
            #. ValueError: If maxSize is not positive.
        """
        if maxSize is not None:
            if not isinstance(maxSize, int) or isinstance(maxSize, bool):
                raise TypeError("the queue size must be a positive integer or None")
            if maxSize <= 0:
                raise ValueError(f"the queue size must be a positive integer, got {maxSize}")
        with self.__condition:
            self.__maxSize = maxSize
            # A bigger queue can free callers that were waiting
            self.__condition.notify_all()

    def set_policy(self, policy):
        """
        Changes what a full queue does with a new record. The next put that finds the queue full uses it.

        :Parameters:
            #. policy (str): The new policy, see :func:`validate_queue_policy`.

        :Raises:
            #. TypeError: If policy is not a string.
            #. ValueError: If policy is not one of the four.
        """
        policy = validate_queue_policy(policy)
        with self.__condition:
            self.__policy = policy

    def set_block_timeout(self, blockTimeout):
        """
        Changes the seconds the ``block`` policy waits for a free place.

        :Parameters:
            #. blockTimeout (None, int, float): The new timeout, or None to wait as long as it takes.

        :Raises:
            #. TypeError: If blockTimeout is not a number or None.
            #. ValueError: If blockTimeout is not positive.
        """
        if blockTimeout is not None:
            if not isinstance(blockTimeout, (int, float)) or isinstance(blockTimeout, bool):
                raise TypeError("the block timeout must be a positive number or None")
            if blockTimeout <= 0:
                raise ValueError(f"the block timeout must be positive, got {blockTimeout}")
        with self.__condition:
            self.__blockTimeout = blockTimeout

    def put(self, item):
        """
        Puts an item in the queue, or does what the policy says when the queue is full.

        :Parameters:
            #. item (object): The item to queue.

        :Returns:
            #. isQueued (bool): True when the item is in the queue. False when the item was thrown away, because the
               policy is ``drop_newest``, or ``block`` and the timeout ended. Under ``drop_oldest`` the new item is queued
               and True is returned, the record that was thrown away is counted.

        :Raises:
            #. QueueFull: If the queue is full and the policy is ``reject``.
        """
        with self.__condition:
            if self.__maxSize is None or len(self.__items) < self.__maxSize:
                self._append(item)
                self.__isDropping = False
                return True
            policy = self.__policy
            if policy == 'reject':
                self.__rejected += 1
                raise QueueFull(f"the {self.__name} is full")
            if policy == 'drop_newest':
                self._count_drop()
                return False
            if policy == 'drop_oldest':
                self.__items.popleft()
                self.__unfinished -= 1
                self._count_drop()
                self._append(item)
                return True
            deadline = None if self.__blockTimeout is None else time.monotonic() + self.__blockTimeout
            while self.__maxSize is not None and len(self.__items) >= self.__maxSize:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self._count_drop()
                    return False
                self.__condition.wait(remaining)
            self._append(item)
            self.__isDropping = False
            return True

    def put_last(self, item):
        """
        Puts an item at the end of the queue whatever the policy and the size, to tell the worker to stop.

        :Parameters:
            #. item (object): The item to queue.
        """
        with self.__condition:
            self._append(item)

    def get(self, timeout=None):
        """
        Takes the oldest item, waiting until there is one.

        :Parameters:
            #. timeout (None, int, float): Seconds to wait. None waits as long as it takes.

        :Returns:
            #. item (object): The oldest item. Call :meth:`task_done` when it has been dealt with.

        :Raises:
            #. queue.Empty: If the timeout ended with no item.
        """
        with self.__condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while len(self.__items) == 0:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise queue.Empty
                self.__condition.wait(remaining)
            item = self.__items.popleft()
            # A free place can let a blocked caller in
            self.__condition.notify_all()
            return item

    def get_batch(self, limit, linger, isMarker, timeout=None):
        """
        Takes the oldest item, waiting until there is one, then takes the items that follow it, up to a limit.

        After the first item, it waits at most *linger* seconds, counted from the first item, for the rest of the
        group to arrive. What is already waiting is taken at once, so a queue with a backlog gives full groups without
        waiting. A marker, such as the item that stops a worker, ends the wait and is not part of the group: it is returned
        apart, so that the caller delivers the group first and then deals with it.

        Every item taken, the marker too, needs its own :meth:`task_done`.

        :Parameters:
            #. limit (int): Largest number of items in the group.
            #. linger (int, float): Seconds to wait for the group to fill after its first item. 0 takes what is waiting.
            #. isMarker (callable): ``f(item) -> bool``, True for an item that ends the group.
            #. timeout (None, int, float): Seconds to wait for the first item. None waits as long as it takes.

        :Returns:
            #. items (list): The group, oldest first. Empty when the first item was a marker.
            #. marker (object, None): The marker that ended the group, or None.

        :Raises:
            #. queue.Empty: If the timeout ended with no item.
        """
        with self.__condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while len(self.__items) == 0:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise queue.Empty
                self.__condition.wait(remaining)
            first = self.__items.popleft()
            if isMarker(first):
                self.__condition.notify_all()
                return [], first
            items, marker = [first], None
            groupDeadline = time.monotonic() + linger
            while len(items) < limit:
                if len(self.__items) > 0:
                    item = self.__items.popleft()
                    if isMarker(item):
                        marker = item
                        break
                    items.append(item)
                    continue
                remaining = groupDeadline - time.monotonic()
                if remaining <= 0:
                    break
                # The places freed so far can let blocked callers in, before this wait
                self.__condition.notify_all()
                self.__condition.wait(remaining)
            self.__condition.notify_all()
            return items, marker

    def task_done(self):
        """Says that an item taken with :meth:`get` has been dealt with, so :meth:`join` can end."""
        with self.__condition:
            self.__unfinished -= 1
            if self.__unfinished <= 0:
                self.__condition.notify_all()

    def join(self, timeout=None):
        """
        Waits until every queued item has been taken and dealt with.

        :Parameters:
            #. timeout (None, int, float): Seconds to wait. None waits as long as it takes.

        :Returns:
            #. isDone (bool): True when nothing is left, False when the timeout ended first.
        """
        with self.__condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.__unfinished > 0:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self.__condition.wait(remaining)
            return True

    @property
    def depth(self):
        """Number of records waiting now."""
        with self.__condition:
            return len(self.__items)

    @property
    def policy(self):
        """What a full queue does with a new record."""
        return self.__policy

    @property
    def maxSize(self):
        """Largest number of waiting records, None when there is no limit."""
        return self.__maxSize

    @property
    def blockTimeout(self):
        """Seconds the ``block`` policy waits for a free place, None when it waits as long as it takes."""
        return self.__blockTimeout

    def stats(self):
        """
        Returns the counters of the queue.

        :Returns:
            #. stats (dict): ``policy``, ``capacity`` (None without limit), ``depth`` (records waiting now),
               ``queued`` (records accepted so far, under ``drop_oldest`` the new record counts as accepted), ``dropped`` (records thrown away so far, under ``drop_oldest`` the evicted old ones) and ``rejected``
               (records refused with :class:`QueueFull` so far).
        """
        with self.__condition:
            return {'policy': self.__policy, 'capacity': self.__maxSize, 'depth': len(self.__items),
                    'queued': self.__queued, 'dropped': self.__dropped, 'rejected': self.__rejected}

    def _append(self, item):
        """Adds an item at the end, the condition is held by the caller."""
        self.__items.append(item)
        self.__unfinished += 1
        self.__queued += 1
        self.__condition.notify_all()

    def _count_drop(self):
        """Counts a record that was thrown away, and warns once for each run of them. The condition is held."""
        self.__dropped += 1
        if not self.__isDropping:
            self.__isDropping = True
            if not self.__warn:
                return
            try:
                sys.stderr.write(f"pysimplelog WARNING: the {self.__name} is full, records are being dropped "
                                 f"(policy {self.__policy}, {self.__dropped} dropped so far)\n")
            except (OSError, ValueError):
                # The error stream is closed or broken, the count is still there
                pass
