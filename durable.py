"""Delivery of the records of one sink from a disk spool: in order, retried until they go through, never lost silently."""

import os
import queue
import sys
import threading
from types import MappingProxyType

try:
    from .queues import BoundedQueue, QueueFull
    from .record import LogRecord
    from .forking import register_for_fork_reset
    from .sinks import DELIVERED, REJECTED, ensure_spoolable
    from .spool import Spool, SpoolError, SpoolBusyError, SpoolMismatchError, target_id
except ImportError:
    from queues import BoundedQueue, QueueFull
    from record import LogRecord
    from forking import register_for_fork_reset
    from sinks import DELIVERED, REJECTED, ensure_spoolable
    from spool import Spool, SpoolError, SpoolBusyError, SpoolMismatchError, target_id

# Records read from the files in one go when the worker has to catch up
CATCH_UP_BATCH = 100
# Records of other slots sent in one go when the sink is idle, and for one explicit request
ADOPT_IDLE_BUDGET = 500
ADOPT_REQUEST_BUDGET = 1000
# Delivered records after which they are acknowledged even if more hints are waiting
ACK_RUN = 256


class _Stop:
    """The marker that tells the worker to end."""


class _AdoptRequest:
    """A request, made by a caller, to send what other slots hold, with the event that tells the caller it is over."""

    def __init__(self):
        self.done = threading.Event()
        self.result = None


def resolve_target_id(handler, config):
    """
    Returns the identity of the receiver of a spooled sink.

    :Parameters:
        #. handler (Sink): The sink.
        #. config (SpoolConfig): Its spool settings. A *target* in them is the destination, otherwise the sink says it.

    :Returns:
        #. targetId (str): The identity, see :func:`pysimplelog.spool.target_id`.

    :Raises:
        #. TypeError: If the sink cannot be spooled, or does not say where it sends and no *target* was given.
    """
    sinkClass = type(handler).__qualname__
    if config.target is not None:
        ensure_spoolable(handler)
        return target_id(sinkClass, target=config.target)
    return target_id(sinkClass, **handler.spool_destination())


class DurableDelivery:
    """
    Keeps the records of one sink on disk, and delivers them from a worker thread of its own.

    A record is written to the spool in the thread that logs it, then a hint with the record is put in a small queue. The
    worker delivers the records in order, and acknowledges each one once the sink has it. When the hints run out of
    step with the spool, because the queue was full or a send failed, the worker reads the records from the files
    instead. Throwing a hint away therefore loses nothing: the record is on disk.

    A send that fails is tried again after a wait that doubles up to a limit, and nothing after it is sent first. A record
    the formatter cannot render, and one that failed *maxAttempts* times, are parked in the ``dead`` file.

    With *adoptOrphans*, the worker also sends what slots left behind by dead processes hold, when it is idle, but only
    slots made for the same spool id, sink class and target. :meth:`adopt_orphans` does it once, on request.

    None of the methods raises an exception into the caller, except :class:`QueueFull` when the spool is full and its
    policy is ``reject``, which the application chose.

    :Parameters:
        #. handler (Sink): The sink the records are delivered to.
        #. config (SpoolConfig): The spool settings.
        #. targetId (str): The identity of the receiver, see :func:`resolve_target_id`.
        #. hintSize (int): Capacity of the queue of hints.
    """

    def __init__(self, handler, config, targetId, hintSize):
        self.__handler = handler
        self.__config = config
        self.__targetId = targetId
        self.__sinkClass = type(handler).__qualname__
        self.__pid = os.getpid()
        self.__counters = {'retries': 0, 'unspooled': 0, 'errors': 0, 'orphans_adopted': 0, 'replayed': 0}
        self.__skippedSlots = set()
        self.__warned = set()
        self.__lock = threading.Lock()
        self.__stop = threading.Event()
        self.__hasMoreToAdopt = False
        # The next sequence number the worker has to deliver, and the last one it delivered without acknowledging yet
        self.__next = 1
        self.__pendingSeq = None
        self.__pendingCount = 0
        self.__spool = Spool.create(config.path, config.id, self.__sinkClass, targetId, **self._spool_options())
        self.__hints = BoundedQueue(hintSize, 'drop_newest', None, name='delivery queue', warn=False)
        self.__thread = threading.Thread(target=self._run, name='pysimplelog-durable-worker', daemon=True)
        self.__thread.start()
        register_for_fork_reset(self)

    def _reset_after_fork(self):
        """Gives a forked process a lock of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        self.__lock = threading.Lock()

    def _is_child(self):
        """True in a process that was forked from the one that made this object: the spool and the worker are not its own."""
        return os.getpid() != self.__pid

    def _spool_options(self):
        """Returns the settings the spool takes, from the settings of the sink."""
        config = self.__config
        return dict(maxBytes=config.maxBytes, totalMaxBytes=config.totalMaxBytes, segmentBytes=config.segmentBytes,
                    policy=config.policy, blockTimeout=config.blockTimeout, maxAge=config.maxAge,
                    deadMaxBytes=config.deadMaxBytes, flush=config.flush, ackEvery=config.ackEvery,
                    ackInterval=config.ackInterval)

    # ------------------------------------------------------------------ the logging thread

    def submit(self, record):
        """
        Keeps a record on disk and hands it to the worker.

        Anything that goes wrong with the spool, a full disk, a folder that vanished, is counted and reported once, and never
        raised. In a forked child the spool and the worker of the parent are not usable, so the record is delivered at once
        by the calling thread, without the spool, and counted as ``unspooled``.

        :Parameters:
            #. record (LogRecord): The record.

        :Raises:
            #. QueueFull: If the spool is full and its policy is ``reject``.
        """
        if self._is_child():
            self._count('unspooled')
            self._warn_once('child', "this process was forked from the one that owns the spool: its records are sent at once, "
                            "without the spool. Make the logger in the new process to give it a spool of its own")
            self.__handler.deliver(record)
            return
        try:
            seq = self.__spool.append(record)
        except QueueFull:
            raise
        except SpoolError as error:
            self._count('errors')
            self._warn_once(type(error).__name__, f"a record could not be kept in the spool: {error}")
            return
        except Exception as error:
            self._count('errors')
            self._warn_once(type(error).__name__, f"a record could not be kept in the spool: {type(error).__name__}: {error}")
            return
        if seq is not None:
            # A hint that does not fit is dropped and counted: the record is on disk and the worker finds it there
            self.__hints.put((seq, record))

    def flush(self, timeout):
        """
        Waits until every record is delivered, or the time runs out.

        :Parameters:
            #. timeout (int, float): Seconds to wait.

        :Returns:
            #. isEmpty (bool): True when nothing is waiting any more.
        """
        if self._is_child():
            return False
        try:
            return self.__spool.wait_empty(timeout)
        except SpoolError:
            return False

    def stop(self, timeout):
        """
        Delivers what it can in *timeout* seconds, then ends the worker and closes the spool.

        What is not delivered stays on disk for the next run, or for another process that adopts it.

        :Parameters:
            #. timeout (int, float): Seconds to wait for the delivery, and again for the worker to end.
        """
        if self._is_child():
            # The worker and the files belong to the parent, which stops and closes them
            return
        self.flush(timeout)
        self.__stop.set()
        self.__hints.put_last(_Stop())
        self.__thread.join(timeout=timeout)
        self.__spool.close()

    def adopt_orphans(self, timeout):
        """
        Sends what slots left behind by dead processes hold, once, in the worker thread.

        :Parameters:
            #. timeout (int, float): Seconds to wait for the worker to be done.

        :Returns:
            #. result (dict, None): ``replayed`` (records sent), ``orphans_adopted`` (slots emptied) and
               ``orphans_skipped`` (slots made for something else, left alone), as counts since the sink was added.
               None when the worker was not done in time.
        """
        if self._is_child():
            return None
        request = _AdoptRequest()
        self.__hints.put_last(request)
        if not request.done.wait(timeout):
            return None
        return request.result

    def stats(self):
        """
        Returns what the spool holds and what the delivery did.

        :Returns:
            #. stats (dict): Everything :meth:`pysimplelog.spool.Spool.stats` gives, and ``retries`` (sends that failed and
               were tried again), ``unspooled`` (records sent without the spool, by a forked child),
               ``errors`` (records not kept because the spool failed), ``replayed`` (records sent from other
               slots), ``orphans_adopted`` (other slots emptied), ``orphans_skipped`` (other slots left alone) and
               ``slot`` (the name of the slot, which is also the start of the id of each record).
        """
        with self.__lock:
            counters = dict(self.__counters)
            skipped = len(self.__skippedSlots)
        return {**self.__spool.stats(), **counters, 'orphans_skipped': skipped,
                'slot': os.path.basename(self.__spool.path)}

    def maintain(self):
        """
        Does the housekeeping of the spool, see :meth:`pysimplelog.spool.Spool.maintain`. Nothing is sent.

        :Returns:
            #. result (dict, None): What the spool did, or None in a forked child, which does not own it.
        """
        if self._is_child():
            return None
        try:
            return self.__spool.maintain()
        except SpoolError:
            return None

    def queue_stats(self):
        """Returns the counters of the queue of hints. A hint that was dropped lost no record."""
        return self.__hints.stats()

    # ------------------------------------------------------------------ the worker thread

    def _run(self):
        """The loop of the worker: serve the hints, and when idle send what other slots hold."""
        while True:
            timeout = None
            if self.__config.adoptOrphans:
                timeout = 0 if self.__hasMoreToAdopt else self.__config.adoptInterval
            try:
                hint = self.__hints.get(timeout=timeout)
            except queue.Empty:
                self._guarded(self._ack_pending)
                self._guarded(lambda: self._adopt_idle())
                continue
            try:
                if isinstance(hint, _Stop):
                    self._guarded(self._ack_pending)
                    return
                if isinstance(hint, _AdoptRequest):
                    self._guarded(self._ack_pending)
                    self._guarded(lambda: self._adopt_on_request(hint))
                    hint.done.set()
                    continue
                self._guarded(lambda: self._serve(*hint))
                # A run of records is acknowledged once, when the hints run out or the run is long. The position on disk is only
                # saved now and then anyway, so a crash resends the same records either way
                if self.__hints.depth == 0 or self.__pendingCount >= ACK_RUN:
                    self._guarded(self._ack_pending)
                # Hints that were dropped, or sends that failed for a while, leave records that no hint speaks for
                if self.__hints.depth == 0 and self.__spool.depth > 0:
                    self._guarded(self._catch_up)
            finally:
                self.__hints.task_done()

    def _guarded(self, work):
        """Runs a piece of work and keeps the worker alive whatever happens in it."""
        try:
            work()
        except SpoolError as error:
            # The spool is closed under the worker when the sink is removed, which is the end and not an error
            if not self.__stop.is_set():
                self._count('errors')
                self._warn_once(type(error).__name__, f"the delivery of the spool failed: {error}")
        except Exception as error:
            self._count('errors')
            self._warn_once(type(error).__name__, f"the delivery of the spool failed: {type(error).__name__}: {error}")

    def _serve(self, seq, record):
        """Delivers a record that was handed over, or catches up from the files when it is not the next one."""
        if seq < self.__next:
            return
        if seq == self.__next:
            self._deliver_in_order(self.__spool, seq, record, isOnce=False, isDeferred=True)
            return
        self._catch_up()

    def _catch_up(self):
        """Reads the undelivered records from the files and delivers them in order, until none is left."""
        spool = self.__spool
        self._ack_pending()
        while not self.__stop.is_set():
            records, upTo = spool.read_batch(limit=CATCH_UP_BATCH)
            if len(records) == 0:
                if upTo > spool.acked:
                    # What is left cannot be read, and is already counted as corrupt or lost
                    spool.ack(upTo)
                self.__next = max(self.__next, spool.acked + 1)
                return
            for seq, record in records:
                if not self._deliver_in_order(spool, seq, record, isOnce=False, isDeferred=True):
                    self._ack_pending()
                    return
            self._ack_pending()

    def _ack_pending(self):
        """Acknowledges the run of records that were delivered and not acknowledged yet."""
        if self.__pendingSeq is not None:
            seq, self.__pendingSeq, self.__pendingCount = self.__pendingSeq, None, 0
            self.__spool.ack(seq)

    def _deliver_in_order(self, spool, seq, record, isOnce, isDeferred=False):
        """
        Delivers one record, and acknowledges it.

        :Parameters:
            #. spool (Spool): The spool the record is in.
            #. seq (int): Its sequence number.
            #. record (LogRecord): The record.
            #. isOnce (bool): True to try only once and give up the turn when it fails, as when sending what another slot
               holds, so that a dead receiver never blocks the records of this process.
            #. isDeferred (bool): True to leave the acknowledgement to :meth:`_ack_pending`, which does one for a whole run.
               Only for the spool of this sink.

        :Returns:
            #. isDone (bool): True when the record is delivered or parked, False when it is still waiting.
        """
        config = self.__config
        attempts = 0
        while not self.__stop.is_set():
            result = self.__handler.deliver(self._with_event_id(spool, seq, record))
            if result == DELIVERED:
                if isDeferred:
                    self.__pendingSeq = seq
                    self.__pendingCount += 1
                    self.__next = seq + 1
                else:
                    spool.ack(seq)
                return True
            if result == REJECTED:
                self._park(spool, seq, record, 'the formatter could not render the record', isDeferred)
                return True
            attempts += 1
            self._count('retries')
            if config.maxAttempts is not None and attempts >= config.maxAttempts:
                self._park(spool, seq, record, f"not delivered after {attempts} attempts", isDeferred)
                return True
            if isOnce:
                return False
            if isDeferred:
                # The records before this one are delivered, they must not wait for the end of the outage to be acknowledged
                self._ack_pending()
            wait = min(config.retryBackoffBase * (2 ** min(attempts - 1, 30)), config.retryBackoffMax)
            if self.__stop.wait(wait):
                break
        return False

    def _park(self, spool, seq, record, reason, isDeferred):
        """Puts a record that cannot be delivered in the ``dead`` file, which also acknowledges it and everything before."""
        spool.give_up(seq, record, reason)
        if isDeferred:
            self.__next = seq + 1

    def _with_event_id(self, spool, seq, record):
        """Returns the record with the id that is the same each time this record is sent, so a receiver can tell a repeat."""
        name = self.__config.eventIdField
        if name is None or name in record.fields:
            return record
        eventId = f"{os.path.basename(spool.path)}-{seq}"
        return LogRecord(record.timestamp, record.severity, record.logType, record.level, record.logger, record.message,
                         record.processId, record.threadId, record.threadName,
                         MappingProxyType({**record.fields, name: eventId}), record.context, record.exception, record.caller)

    # ------------------------------------------------------------------ other slots

    def _adopt_idle(self):
        """Sends a batch of what other slots hold, when the sink has nothing else to do."""
        self.__hasMoreToAdopt = self._adopt(ADOPT_IDLE_BUDGET)

    def _adopt_on_request(self, request):
        """Sends what other slots hold until nothing is left or a send fails, then fills in the answer."""
        while not self.__stop.is_set() and self._adopt(ADOPT_REQUEST_BUDGET):
            pass
        with self.__lock:
            request.result = {'replayed': self.__counters['replayed'],
                              'orphans_adopted': self.__counters['orphans_adopted'],
                              'orphans_skipped': len(self.__skippedSlots)}

    def _adopt(self, budget):
        """
        Looks at the other slots of the base folder, oldest first, and sends their records.

        A slot that another process holds is skipped. A slot made for another spool id, sink class or target is left
        alone, and counted. An empty slot is deleted.

        :Parameters:
            #. budget (int): The largest number of records to send now.

        :Returns:
            #. hasMore (bool): True when the budget ran out and more is probably waiting.
        """
        for slotPath in Spool.slots(self.__config.path):
            if self.__stop.is_set():
                return False
            if slotPath == self.__spool.path:
                continue
            try:
                orphan = Spool.open(slotPath, self.__config.id, self.__sinkClass, self.__targetId,
                                    **self._spool_options())
            except SpoolBusyError:
                continue
            except SpoolMismatchError:
                with self.__lock:
                    self.__skippedSlots.add(slotPath)
                self._warn_once(('skip', slotPath), f"the spool slot {os.path.basename(slotPath)} was made for another "
                                "spool id, sink class or target, it is left alone")
                continue
            except (SpoolError, OSError) as error:
                self._count('errors')
                self._warn_once(type(error).__name__, f"a spool slot could not be opened: {error}")
                continue
            try:
                outcome, sent = self._drain(orphan, budget)
            finally:
                orphan.close()
            budget -= sent
            if outcome == 'failed':
                return False
            if outcome == 'budget' or budget <= 0:
                return True
        return False

    def _drain(self, orphan, budget):
        """
        Sends the records of another slot, in order, at most *budget* of them.

        :Returns:
            #. outcome (str): ``done`` when the slot is empty, ``budget`` when the budget ran out, ``failed`` when a send
               failed and the rest must wait.
            #. sent (int): The number of records delivered.
        """
        sent = 0
        while sent < budget:
            records, upTo = orphan.read_batch(limit=min(CATCH_UP_BATCH, budget - sent))
            if len(records) == 0:
                if upTo > orphan.acked:
                    orphan.ack(upTo)
                break
            for seq, record in records:
                if not self._deliver_in_order(orphan, seq, record, isOnce=True):
                    return 'failed', sent
                sent += 1
                self._count('replayed')
        else:
            return 'budget', sent
        if sent > 0:
            self._count('orphans_adopted')
        return 'done', sent

    # ------------------------------------------------------------------ small helpers

    def _count(self, name):
        """Adds one to a counter."""
        with self.__lock:
            self.__counters[name] += 1

    def _warn_once(self, key, text):
        """Writes a warning the first time something happens, and never again for the same thing."""
        with self.__lock:
            if key in self.__warned:
                return
            self.__warned.add(key)
        try:
            sys.stderr.write(f"pysimplelog WARNING: {text}\n")
        except (OSError, ValueError):
            # The error stream is closed or broken, the count is still there
            pass
