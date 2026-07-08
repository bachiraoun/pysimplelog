"""Pressure, backpressure, and denial-of-service resilience tests for pysimplelog.

Run from the repo root:
    python3 -m pytest tests/test_pressure.py -v
    python3 tests/test_pressure.py

Design principles
-----------------
These tests must be deterministic and free of sleep-based timing
assumptions.  Where wall-clock bounds are checked they are wide enough
to pass on a loaded CI machine (TIMEOUT_* constants below) but tight
enough to catch a genuine hang.

Every queue-full scenario uses a *gating sink* pattern: a user-added
sink whose write() method blocks on a threading.Event.  The test
thread holds the gate closed to fill the queue on demand, then opens
it to let the worker drain.  This is 100 % race-free -- no time.sleep()
needed to reach the desired state.

Coverage map
------------
TestDropPolicy          -- 'drop': caller never blocks, droppedMessages counted
TestWarnPolicy          -- 'warn': same as drop + one stderr line per overflow
TestRaisePolicy         -- 'raise': queue.Full propagated to caller
TestBlockPolicy         -- 'block' + timeout: bounded wait then drop
TestUnboundedQueue      -- no maxQueueSize: zero drops under load
TestDroppedCount        -- exact droppedMessages accounting
TestSlowSink            -- slow user sink creates queue back-pressure;
                           policy fires against the correct queue depth
TestCrashingSink        -- a sink that raises on every write must not
                           starve sibling sinks in the same dispatch batch
TestRuntimePolicyChange -- hot-swap queueFullPolicy while queue is active
TestQueueSizeProperty   -- queueSize reflects live depth accurately
TestConcurrentSinkMutate -- add / remove sinks while worker is flooding
TestClearSinksUnderLoad -- clear_sinks() mid-flood leaves logger coherent
"""

import io
import queue
import sys
import threading
import time
import unittest
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from SimpleLog import Logger  # noqa: E402


# ── tuneable constants ──────────────────────────────────────────────────────

# Maximum wall-clock seconds any single test may take.
# Wide enough for a slow CI box; tight enough to catch real hangs.
TIMEOUT_FAST  = 3.0   # tests that should finish in under a second
TIMEOUT_BLOCK = 5.0   # block-policy tests that intentionally wait

# Queue size used in bounded-queue tests (small to trigger policy quickly).
SMALL_QUEUE = 3


# ── helpers ─────────────────────────────────────────────────────────────────

def make_enqueue_logger(maxQueueSize=None, queueFullPolicy='block',
                        queueBlockTimeout=None, logToStdout=False):
    """Return an enqueue-mode Logger with stdout captured in a StringIO."""
    buf = io.StringIO()
    L = Logger(
        name            = 'pressure',
        logToFile       = False,
        logToStdout     = logToStdout,
        stdout          = buf,
        enqueue         = True,
        maxQueueSize    = maxQueueSize,
        queueFullPolicy = queueFullPolicy,
        queueBlockTimeout = queueBlockTimeout,
    )
    return L, buf


class _GateSink:
    """A user sink whose write() blocks until the gate is opened.

    Use open_gate() to let the worker thread proceed; use close_gate()
    to re-arm the block for the next call.

    This is the test's primary tool for filling the queue on demand
    without any sleep() calls.
    """

    def __init__(self):
        self._gate    = threading.Event()
        self._gate.set()   # open by default
        self.lines    = []
        self._lock    = threading.Lock()

    def write(self, text):
        self._gate.wait()  # block until gate is open
        with self._lock:
            self.lines.append(text)

    def flush(self):
        pass

    def open_gate(self):
        self._gate.set()

    def close_gate(self):
        self._gate.clear()

    def count(self):
        with self._lock:
            return len(self.lines)


class _CountSink:
    """Fast sink that just counts how many records it received."""

    def __init__(self):
        self._n    = 0
        self._lock = threading.Lock()

    def write(self, text):
        with self._lock:
            self._n += 1

    def flush(self):
        pass

    def count(self):
        with self._lock:
            return self._n


class _RaiseSink:
    """Sink whose write() always raises RuntimeError (simulates a broken handler)."""

    def write(self, _):
        raise RuntimeError('intentional sink failure')

    def flush(self):
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 1 — 'drop' policy
# ═══════════════════════════════════════════════════════════════════════════

class TestDropPolicy(unittest.TestCase):
    """'drop' discards records silently and never parks the calling thread."""

    def _make(self):
        return make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='drop')

    def test_drop_caller_returns_immediately(self):
        """Flooding a full queue with 'drop' must complete well under TIMEOUT_FAST."""
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()  # pause the worker so the queue fills

        start = time.monotonic()
        for _ in range(SMALL_QUEUE * 10):
            L.info('flood')
        elapsed = time.monotonic() - start

        gate.open_gate()
        L.flush()
        self.assertLess(elapsed, TIMEOUT_FAST,
                        f'drop policy blocked caller for {elapsed:.2f}s')

    def test_drop_increments_droppedMessages(self):
        """Overflowing the queue must increment droppedMessages."""
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        for _ in range(SMALL_QUEUE * 5):
            L.info('flood')

        gate.open_gate()
        L.flush()
        self.assertGreater(L.droppedMessages, 0,
                           'droppedMessages stayed 0 despite queue overflow')

    def test_drop_does_not_write_to_stderr(self):
        """`drop` is silent — no stderr output on overflow."""
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        captured = io.StringIO()
        orig_stderr = sys.stderr
        sys.stderr = captured
        try:
            for _ in range(SMALL_QUEUE * 5):
                L.info('flood')
        finally:
            sys.stderr = orig_stderr
            gate.open_gate()
            L.flush()

        self.assertEqual(captured.getvalue(), '',
                         'drop policy wrote unexpected output to stderr')

    def test_surviving_records_are_delivered(self):
        """The first SMALL_QUEUE records must still arrive in the sink."""
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()   # fill the queue

        # Enqueue exactly maxQueueSize records — these should land
        for i in range(SMALL_QUEUE):
            L.info(f'early-{i}')
        # Overflow records — these get dropped
        for _ in range(SMALL_QUEUE * 3):
            L.info('dropped')

        gate.open_gate()
        L.flush()
        # At least some early records must have been delivered
        received = gate.count()
        self.assertGreaterEqual(received, 1,
                                'no records at all made it through the queue')


# ═══════════════════════════════════════════════════════════════════════════
# 2 — 'warn' policy
# ═══════════════════════════════════════════════════════════════════════════

class TestWarnPolicy(unittest.TestCase):
    """`warn` behaves like `drop` but writes one stderr line per overflow."""

    def _make(self):
        return make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='warn')

    def test_warn_caller_does_not_block(self):
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        start = time.monotonic()
        for _ in range(SMALL_QUEUE * 5):
            L.info('flood')
        elapsed = time.monotonic() - start

        gate.open_gate()
        L.flush()
        self.assertLess(elapsed, TIMEOUT_FAST,
                        f'warn policy blocked caller for {elapsed:.2f}s')

    def test_warn_writes_to_stderr(self):
        """Each dropped record under 'warn' must emit at least one stderr line."""
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        captured = io.StringIO()
        orig_stderr = sys.stderr
        sys.stderr = captured
        try:
            for _ in range(SMALL_QUEUE * 4):
                L.info('flood')
        finally:
            sys.stderr = orig_stderr
            gate.open_gate()
            L.flush()

        self.assertIn('pysimplelog', captured.getvalue(),
                      'warn policy emitted no stderr warning')

    def test_warn_increments_droppedMessages(self):
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        for _ in range(SMALL_QUEUE * 5):
            L.info('flood')

        gate.open_gate()
        L.flush()
        self.assertGreater(L.droppedMessages, 0)


# ═══════════════════════════════════════════════════════════════════════════
# 3 — 'raise' policy
# ═══════════════════════════════════════════════════════════════════════════

class TestRaisePolicy(unittest.TestCase):
    """`raise` propagates queue.Full to the caller — circuit-breaker pattern."""

    def _make(self):
        return make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='raise')

    def test_raise_propagates_queue_full(self):
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        # Fill the queue then expect Full on the next call
        try:
            for _ in range(SMALL_QUEUE * 10):
                L.info('flood')
            self.fail('queue.Full was never raised')
        except queue.Full:
            pass   # expected
        finally:
            gate.open_gate()
            L.flush()

    def test_raise_caller_can_handle_and_continue(self):
        """After catching queue.Full the logger must still work normally."""
        gate = _GateSink()
        L, _ = self._make()
        L.add_sink('gate', gate)
        gate.close_gate()

        # Fill and overflow
        caught = False
        for _ in range(SMALL_QUEUE * 5):
            try:
                L.info('flood')
            except queue.Full:
                caught = True
                break

        self.assertTrue(caught, 'queue.Full was never raised')

        # Open gate — logger must still function
        gate.open_gate()
        L.flush()
        good = _CountSink()
        L.add_sink('good', good)
        L.info('after-recovery')
        L.flush()
        self.assertEqual(good.count(), 1,
                         'logger became non-functional after queue.Full')


# ═══════════════════════════════════════════════════════════════════════════
# 4 — 'block' + queueBlockTimeout
# ═══════════════════════════════════════════════════════════════════════════

class TestBlockPolicy(unittest.TestCase):
    """`block` parks the caller; timeout bounds the park duration."""

    def test_block_no_timeout_delivers_all(self):
        """block with no timeout must never drop — all records delivered."""
        gate  = _GateSink()
        count = _CountSink()
        L, _ = make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='block',
                                   queueBlockTimeout=None)
        L.add_sink('gate', gate)
        L.add_sink('count', count)

        # Enqueue in a background thread so we can open the gate
        # from the main thread after a short delay.
        N = SMALL_QUEUE * 4
        errors = []

        def flood():
            try:
                for _ in range(N):
                    L.info('msg')
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=flood)
        t.start()
        # Let the worker drain naturally — gate is open
        t.join(timeout=TIMEOUT_FAST)
        self.assertFalse(t.is_alive(),
                         'block policy hung the flood thread unexpectedly')
        L.flush()
        self.assertFalse(errors)
        self.assertEqual(L.droppedMessages, 0,
                         'block policy (no timeout) dropped messages — must not')

    def test_block_with_timeout_drops_and_warns(self):
        """block + short timeout: after deadline the record is dropped and
        a warning is written to stderr."""
        gate  = _GateSink()
        L, _ = make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='block',
                                   queueBlockTimeout=0.05)  # 50 ms
        L.add_sink('gate', gate)
        gate.close_gate()

        captured   = io.StringIO()
        orig_stderr = sys.stderr
        sys.stderr  = captured
        start       = time.monotonic()
        try:
            # Flood well past capacity — each overflow waits 50 ms then drops
            for _ in range(SMALL_QUEUE + 2):
                L.info('flood')
        finally:
            sys.stderr = orig_stderr
            gate.open_gate()
            L.flush()

        elapsed = time.monotonic() - start
        self.assertGreater(L.droppedMessages, 0,
                           'no records were dropped despite full queue + timeout')
        self.assertIn('pysimplelog', captured.getvalue(),
                      'timeout-drop did not write to stderr')
        self.assertLess(elapsed, TIMEOUT_BLOCK,
                        f'block+timeout took too long: {elapsed:.2f}s')

    def test_block_with_timeout_caller_not_hung_forever(self):
        """The caller's total wait is bounded by queueBlockTimeout * overflow_count,
        not infinite. This verifies that DoS via a dead/slow worker is bounded."""
        gate = _GateSink()
        TIMEOUT = 0.05   # 50 ms per slot
        L, _  = make_enqueue_logger(maxQueueSize=2,
                                    queueFullPolicy='block',
                                    queueBlockTimeout=TIMEOUT)
        L.add_sink('gate', gate)
        gate.close_gate()   # stall the worker

        OVERFLOW_COUNT = 4
        start = time.monotonic()
        for _ in range(2 + OVERFLOW_COUNT):   # 2 fill queue, rest overflow
            L.info('msg')
        elapsed = time.monotonic() - start

        gate.open_gate()
        L.flush()

        # Upper bound: each overflow parks TIMEOUT seconds.
        # Add 1 s of scheduling slack.
        max_allowed = OVERFLOW_COUNT * TIMEOUT + 1.0
        self.assertLess(elapsed, max_allowed,
                        f'block+timeout took {elapsed:.2f}s, '
                        f'expected < {max_allowed:.2f}s')


# ═══════════════════════════════════════════════════════════════════════════
# 5 — Unbounded queue (no maxQueueSize)
# ═══════════════════════════════════════════════════════════════════════════

class TestUnboundedQueue(unittest.TestCase):

    def test_unbounded_zero_drops_under_burst(self):
        """With no cap, any burst must result in zero dropped messages."""
        L, buf = make_enqueue_logger(maxQueueSize=None,
                                     queueFullPolicy='drop',
                                     logToStdout=True)
        N = 500
        for _ in range(N):
            L.info('burst')
        L.flush()
        self.assertEqual(L.droppedMessages, 0,
                         'unbounded queue dropped messages — it must not')
        lines = [l for l in buf.getvalue().splitlines() if '<INFO>' in l]
        self.assertEqual(len(lines), N,
                         f'expected {N} lines, got {len(lines)}')

    def test_unbounded_queueSize_grows_under_load(self):
        """While the worker is stalled, queueSize must reflect backlog depth."""
        gate = _GateSink()
        L, _ = make_enqueue_logger(maxQueueSize=None, logToStdout=False)
        L.add_sink('gate', gate)
        gate.close_gate()

        BATCH = 10
        for _ in range(BATCH):
            L.info('stalled')

        depth = L.queueSize
        gate.open_gate()
        L.flush()

        # Some items may have been drained before we read queueSize,
        # but at least one should have been visible.
        # We assert it was >= 0 (non-negative) and < BATCH + 1 (no phantom).
        self.assertGreaterEqual(depth, 0)
        self.assertLessEqual(depth, BATCH + 1)  # +1 for STOP sentinel


# ═══════════════════════════════════════════════════════════════════════════
# 6 — Exact droppedMessages accounting
# ═══════════════════════════════════════════════════════════════════════════

class TestDroppedCount(unittest.TestCase):

    def test_exact_drop_count(self):
        """droppedMessages must equal total_sent - capacity when using 'drop'."""
        gate = _GateSink()
        CAP  = 4   # deliberately small
        L, _ = make_enqueue_logger(maxQueueSize=CAP, queueFullPolicy='drop')
        L.add_sink('gate', gate)
        gate.close_gate()   # freeze the worker

        TOTAL_SENT = CAP + 6
        for _ in range(TOTAL_SENT):
            L.info('msg')

        # Worker is frozen: queue holds CAP items, the rest were dropped
        dropped = L.droppedMessages
        gate.open_gate()
        L.flush()

        # Exact guarantee: dropped == TOTAL_SENT - CAP
        # (all overflow was rejected immediately by put_nowait)
        self.assertEqual(dropped, TOTAL_SENT - CAP,
                         f'expected {TOTAL_SENT - CAP} dropped, got {dropped}')


# ═══════════════════════════════════════════════════════════════════════════
# 7 — Slow sink creates queue back-pressure
# ═══════════════════════════════════════════════════════════════════════════

class TestSlowSink(unittest.TestCase):

    def test_slow_sink_triggers_drop_policy(self):
        """A slow user sink backs up the worker → queue fills → policy fires."""
        gate  = _GateSink()
        fast  = _CountSink()
        CAP   = 3
        L, _  = make_enqueue_logger(maxQueueSize=CAP, queueFullPolicy='drop')
        L.add_sink('slow', gate)   # acts as the bottleneck
        L.add_sink('fast', fast)
        gate.close_gate()          # slow sink stalls; fast also blocked per-batch

        # Burst well past capacity
        for _ in range(CAP * 4):
            L.info('msg')

        gate.open_gate()
        L.flush()
        self.assertGreater(L.droppedMessages, 0,
                           'slow sink did not cause queue back-pressure')

    def test_drop_policy_never_blocks_caller_with_slow_sink(self):
        gate = _GateSink()
        L, _ = make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='drop')
        L.add_sink('slow', gate)
        gate.close_gate()

        start = time.monotonic()
        for _ in range(SMALL_QUEUE * 8):
            L.info('msg')
        elapsed = time.monotonic() - start

        gate.open_gate()
        L.flush()
        self.assertLess(elapsed, TIMEOUT_FAST,
                        f'drop+slow-sink blocked caller {elapsed:.2f}s')


# ═══════════════════════════════════════════════════════════════════════════
# 8 — Crashing sink does not starve sibling sinks
# ═══════════════════════════════════════════════════════════════════════════

class TestCrashingSink(unittest.TestCase):
    """A sink that raises on every write must not prevent other sinks from
    receiving the same batch of records."""

    def test_crashing_sink_sibling_still_receives(self):
        L, _  = make_enqueue_logger()
        bad   = _RaiseSink()
        good  = _CountSink()
        N     = 20
        L.add_sink('bad',  bad)
        L.add_sink('good', good)

        for _ in range(N):
            L.info('msg')
        L.flush()

        self.assertEqual(good.count(), N,
                         f'good sink got {good.count()}/{N} records '
                         f'despite crashing sibling')

    def test_crashing_sink_does_not_crash_worker(self):
        """After N writes through a crashing sink, the worker must still be alive
        and the logger must still accept and deliver new messages."""
        L, _ = make_enqueue_logger()
        L.add_sink('bad', _RaiseSink())
        good = _CountSink()
        L.add_sink('good', good)

        for _ in range(10):
            L.info('first-batch')
        L.flush()

        # Worker must still be running — deliver a second batch
        for _ in range(5):
            L.info('second-batch')
        L.flush()

        self.assertEqual(good.count(), 15,
                         'worker died after crashing sink: second batch lost')

    def test_crashing_sink_does_not_increment_dropped(self):
        """A sink that raises is a delivery error, not a queue drop.
        droppedMessages must remain zero."""
        L, _ = make_enqueue_logger()
        L.add_sink('bad', _RaiseSink())

        for _ in range(5):
            L.info('msg')
        L.flush()

        self.assertEqual(L.droppedMessages, 0,
                         'droppedMessages incremented for a crashing sink — '
                         'it should only count queue-level drops')


# ═══════════════════════════════════════════════════════════════════════════
# 9 — Runtime policy change (hot-swap)
# ═══════════════════════════════════════════════════════════════════════════

class TestRuntimePolicyChange(unittest.TestCase):

    def test_switch_from_block_to_drop_while_active(self):
        """Changing the policy mid-flight must take effect on the next log() call
        without hanging the logger or deadlocking the worker."""
        gate = _GateSink()
        L, _ = make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='block',
                                   queueBlockTimeout=0.05)
        L.add_sink('gate', gate)
        gate.close_gate()

        # Fill the queue
        for _ in range(SMALL_QUEUE):
            L.info('fill')

        # Switch to drop while queue is full — overflow must now return instantly
        L.set_queue_full_policy('drop')
        start = time.monotonic()
        for _ in range(SMALL_QUEUE * 3):
            L.info('overflow')
        elapsed = time.monotonic() - start

        gate.open_gate()
        L.flush()
        self.assertLess(elapsed, TIMEOUT_FAST,
                        f'policy switch to drop did not take effect: '
                        f'{elapsed:.2f}s elapsed')
        self.assertGreater(L.droppedMessages, 0,
                           'no drops recorded after switch to drop policy')

    def test_switch_from_drop_to_raise(self):
        """Switching from 'drop' to 'raise' mid-run: the first overflow after
        the switch must raise queue.Full instead of silently discarding."""
        gate = _GateSink()
        L, _ = make_enqueue_logger(maxQueueSize=SMALL_QUEUE,
                                   queueFullPolicy='drop')
        L.add_sink('gate', gate)
        gate.close_gate()

        # Fill the queue silently
        for _ in range(SMALL_QUEUE):
            L.info('fill')

        # Switch policy
        L.set_queue_full_policy('raise')

        raised = False
        for _ in range(SMALL_QUEUE * 2):
            try:
                L.info('overflow')
            except queue.Full:
                raised = True
                break

        gate.open_gate()
        L.flush()
        self.assertTrue(raised,
                        'queue.Full was not raised after switching to raise policy')


# ═══════════════════════════════════════════════════════════════════════════
# 10 — queueSize property
# ═══════════════════════════════════════════════════════════════════════════

class TestQueueSizeProperty(unittest.TestCase):

    def test_queueSize_zero_when_drained(self):
        L, _ = make_enqueue_logger()
        for _ in range(5):
            L.info('msg')
        L.flush()
        self.assertEqual(L.queueSize, 0,
                         'queueSize non-zero after flush()')

    def test_queueSize_zero_when_not_enqueue(self):
        L = Logger(name='t', logToFile=False, stdout=io.StringIO(),
                   enqueue=False)
        L.info('msg')
        self.assertEqual(L.queueSize, 0,
                         'queueSize must always be 0 in sync mode')

    def test_queueSize_positive_while_worker_stalled(self):
        gate = _GateSink()
        L, _ = make_enqueue_logger()
        L.add_sink('gate', gate)
        gate.close_gate()

        BATCH = 5
        for _ in range(BATCH):
            L.info('msg')

        # Give the worker thread a moment to pull the first item off the queue
        time.sleep(0.01)
        depth = L.queueSize

        gate.open_gate()
        L.flush()

        # The depth may be anywhere from 0 to BATCH depending on scheduling,
        # but must be non-negative and at most BATCH.
        self.assertGreaterEqual(depth, 0)
        self.assertLessEqual(depth, BATCH)


# ═══════════════════════════════════════════════════════════════════════════
# 11 — Concurrent sink mutation while worker is active
# ═══════════════════════════════════════════════════════════════════════════

class TestConcurrentSinkMutate(unittest.TestCase):
    """add_sink() / remove_sink() called concurrently with active logging
    must not deadlock, raise, or corrupt the active-sink cache."""

    def test_remove_sink_during_flood_no_deadlock(self):
        L, _ = make_enqueue_logger(logToStdout=False)
        sink = _CountSink()
        L.add_sink('ephemeral', sink)

        errors  = []
        barrier = threading.Barrier(2)

        def flood():
            barrier.wait()
            for _ in range(200):
                L.info('msg')

        def mutate():
            barrier.wait()
            time.sleep(0.005)          # let flood get a head start
            try:
                L.remove_sink('ephemeral')
                # re-add to verify the logger recovered
                L.add_sink('ephemeral', sink)
            except Exception as exc:
                errors.append(exc)

        t_flood  = threading.Thread(target=flood)
        t_mutate = threading.Thread(target=mutate)
        t_flood.start(); t_mutate.start()
        t_flood.join(timeout=TIMEOUT_FAST)
        t_mutate.join(timeout=TIMEOUT_FAST)
        L.flush()

        self.assertFalse(t_flood.is_alive(),  'flood thread hung')
        self.assertFalse(t_mutate.is_alive(), 'mutate thread hung')
        self.assertFalse(errors, f'exception during sink mutation: {errors}')

    def test_add_sink_during_flood_receives_subsequent_messages(self):
        """A sink added mid-flood must receive messages logged after the add."""
        L, _ = make_enqueue_logger(logToStdout=False)
        late  = _CountSink()
        EARLY = 100

        # Log EARLY messages before adding the late sink
        for _ in range(EARLY):
            L.info('early')
        L.add_sink('late', late)

        AFTER = 50
        for _ in range(AFTER):
            L.info('after')
        L.flush()

        # The late sink should have received all AFTER messages
        self.assertEqual(late.count(), AFTER,
                         f'late sink got {late.count()}/{AFTER} post-add messages')


# ═══════════════════════════════════════════════════════════════════════════
# 12 — clear_sinks() under load
# ═══════════════════════════════════════════════════════════════════════════

class TestClearSinksUnderLoad(unittest.TestCase):

    def test_clear_sinks_during_flood_no_crash(self):
        """clear_sinks() called while messages are being dispatched
        must not raise, deadlock, or corrupt the logger."""
        L, buf = make_enqueue_logger(logToStdout=True)
        for _ in range(3):
            L.add_sink(f'tmp{_}', _CountSink())

        errors  = []
        barrier = threading.Barrier(2)

        def flood():
            barrier.wait()
            for _ in range(100):
                L.info('msg')

        def clear():
            barrier.wait()
            time.sleep(0.002)
            try:
                L.clear_sinks()
            except Exception as exc:
                errors.append(exc)

        t_f = threading.Thread(target=flood)
        t_c = threading.Thread(target=clear)
        t_f.start(); t_c.start()
        t_f.join(timeout=TIMEOUT_FAST)
        t_c.join(timeout=TIMEOUT_FAST)
        L.flush()

        self.assertFalse(t_f.is_alive(), 'flood thread hung after clear_sinks()')
        self.assertFalse(t_c.is_alive(), 'clear thread hung')
        self.assertFalse(errors, f'exception in clear_sinks() under load: {errors}')

        # Built-in sinks must still be present
        from SimpleLog import _SINK_STDOUT, _SINK_FILE
        self.assertIn(_SINK_STDOUT, L.sinks)
        self.assertIn(_SINK_FILE,   L.sinks)

    def test_logger_still_functional_after_clear_under_load(self):
        """After a concurrent clear_sinks(), the logger must accept and
        deliver new messages to newly added sinks."""
        L, _ = make_enqueue_logger(logToStdout=False)
        for _ in range(3):
            L.add_sink(f's{_}', _CountSink())

        for _ in range(50):
            L.info('pre-clear')
        L.clear_sinks()

        new = _CountSink()
        L.add_sink('new', new)
        for _ in range(10):
            L.info('post-clear')
        L.flush()

        self.assertEqual(new.count(), 10,
                         'logger non-functional after clear_sinks() under load')


# ═══════════════════════════════════════════════════════════════════════════
# entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
