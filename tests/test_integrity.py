"""Log-record integrity tests for pysimplelog under concurrent load.

Run from the repo root:
    python3 -m pytest tests/test_integrity.py -v
    python3 tests/test_integrity.py

The three questions answered here
----------------------------------
(1) ATOMICITY — Is every write() call to a sink a single, complete record?
    A record must never be split across two write() calls, and two records
    must never be merged into one write() call.

(2) PER-THREAD ORDERING — Within a single thread's message stream, do that
    thread's records arrive in the order they were logged?
    (Cross-thread ordering is intentionally non-deterministic.)

(3) COMPLETENESS — Does total delivered count == N_threads × N_messages?
    Zero loss, zero duplication.

Why the GIL alone is not enough
---------------------------------
In CPython's sync mode, each log() call assembles the complete formatted
string then calls sink.handler.write(complete_string).  Because write() is
a single Python operation it is atomic under the GIL — character-level
interleaving is impossible.  HOWEVER:

  • Records from different threads can still arrive in any order (fine).
  • If the write path were ever split into two steps (format, then write
    header, then write body) the GIL would not protect against interleaving.
  • In enqueue mode the single worker thread guarantees serialisation, but
    that is a property of the architecture, not the GIL, and must be tested.
  • For real file I/O (buffered + flush), the write may release the GIL on
    large payloads — tested in TestFileSinkIntegrity.

Test structure
--------------
TestAtomicity              -- each write() carries exactly one record
TestPerThreadOrdering      -- each thread's records are in sequence
TestCompleteness           -- no loss, no duplication
TestFileSinkIntegrity      -- same three checks against a real OS file
TestEnqueueIntegrity       -- all three checks in enqueue mode
TestLargeRecordIntegrity   -- records near or over typical OS buffer sizes
"""

import glob
import io
import os
import re
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from SimpleLog import Logger  # noqa: E402


# ── tuning ──────────────────────────────────────────────────────────────────

N_THREADS       = 8    # concurrent writers
N_PER_THREAD    = 200  # messages each thread sends
TOTAL           = N_THREADS * N_PER_THREAD
JOIN_TIMEOUT    = 10.0 # seconds to wait for all threads

# Sentinel embedded in every message so records are parseable after the fact.
# Format: "T{thread_index:02d}:S{sequence:06d}"
MSG_PATTERN = re.compile(r'T(\d{2}):S(\d{6})')

# Expected record format produced by the logger's plain-text path:
# "YYYY-MM-DD HH:MM:SS - name <TYPE> T07:S000042"
RECORD_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - \S+ <\w+> .+$'
)


# ── helpers ─────────────────────────────────────────────────────────────────

def make_sync_logger(**kwargs):
    """Sync-mode Logger (enqueue=False) with stdout sent to /dev/null."""
    buf = io.StringIO()
    defaults = dict(name='integrity', logToFile=False,
                    logToStdout=True, enqueue=False, stdout=buf)
    defaults.update(kwargs)
    return Logger(**defaults), buf


def make_enqueue_logger(**kwargs):
    buf = io.StringIO()
    defaults = dict(name='integrity', logToFile=False,
                    logToStdout=True, enqueue=True, stdout=buf)
    defaults.update(kwargs)
    return Logger(**defaults), buf


def msg(thread_idx, seq):
    """Build a uniquely-parseable message string."""
    return f'T{thread_idx:02d}:S{seq:06d}'


class _RecordCaptureSink:
    """User sink that records each write() call as one entry.

    This is the primary probe: if a record were split across two write()
    calls, or two records merged into one, the post-run analysis would
    detect it.
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._records = []          # one entry per write() call

    def write(self, text):
        # Strip the trailing newline; keep everything else as-is.
        with self._lock:
            self._records.append(text.rstrip('\n'))

    def flush(self):
        pass

    @property
    def records(self):
        with self._lock:
            return list(self._records)


def run_flood(logger, n_threads=N_THREADS, n_per_thread=N_PER_THREAD):
    """Spawn n_threads threads, each logging n_per_thread messages.

    Returns when every thread has finished.  Each message embeds the
    thread index and a per-thread sequence counter so records are
    traceable back to their source after the run.
    """
    barrier = threading.Barrier(n_threads)
    errors  = []

    def worker(tid):
        barrier.wait()           # all threads start at the same moment
        for seq in range(n_per_thread):
            logger.info(msg(tid, seq))

    threads = [threading.Thread(target=worker, args=(i,))
               for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=JOIN_TIMEOUT)
        if t.is_alive():
            errors.append('Thread did not finish within timeout')

    if errors:
        raise AssertionError('\n'.join(errors))


def parse_records(records):
    """Return a dict mapping thread_idx → sorted list of sequence numbers
    extracted from a list of raw record strings.

    Also returns a list of records that contained no T:S sentinel, which
    signals corruption or a source we did not inject.
    """
    by_thread  = {i: [] for i in range(N_THREADS)}
    unparsed   = []
    for record in records:
        m = MSG_PATTERN.search(record)
        if m:
            tid, seq = int(m.group(1)), int(m.group(2))
            by_thread[tid].append(seq)
        else:
            unparsed.append(record)
    return by_thread, unparsed


# ═══════════════════════════════════════════════════════════════════════════
# 1 — Atomicity: each write() call is one complete record
# ═══════════════════════════════════════════════════════════════════════════

class TestAtomicity(unittest.TestCase):
    """Each write() call must deliver exactly one complete, well-formed record.

    'Complete' means:
      - exactly one T:S sentinel (never zero, never two)
      - matches the expected timestamp+name+type+message format
      - no embedded newlines (which would signal merged records)
    """

    def _run(self, logger, sink):
        run_flood(logger)
        return sink.records

    def test_sync_each_write_contains_one_sentinel(self):
        """Sync mode: every write() call carries exactly one T:S sentinel."""
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        records = self._run(L, sink)

        for i, rec in enumerate(records):
            sentinels = MSG_PATTERN.findall(rec)
            self.assertEqual(
                len(sentinels), 1,
                f'Record #{i} contains {len(sentinels)} sentinels '
                f'(expected exactly 1):\n  {rec!r}'
            )

    def test_sync_each_write_matches_record_format(self):
        """Sync mode: every write() call is a well-formed log record."""
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        records = self._run(L, sink)

        for i, rec in enumerate(records):
            self.assertRegex(
                rec, RECORD_RE,
                f'Record #{i} does not match expected format:\n  {rec!r}'
            )

    def test_sync_no_embedded_newlines(self):
        """Sync mode: no record string contains an embedded newline.

        An embedded newline would mean two records were merged into one
        write() call — a definitive sign of corruption.
        """
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        records = self._run(L, sink)

        for i, rec in enumerate(records):
            self.assertNotIn(
                '\n', rec,
                f'Record #{i} contains an embedded newline — '
                f'two records were merged:\n  {rec!r}'
            )

    def test_sync_no_empty_writes(self):
        """Sync mode: no write() call delivers an empty string."""
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        records = self._run(L, sink)

        for i, rec in enumerate(records):
            self.assertTrue(
                rec.strip(),
                f'Record #{i} is empty — a partial or null write occurred'
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2 — Per-thread ordering
# ═══════════════════════════════════════════════════════════════════════════

class TestPerThreadOrdering(unittest.TestCase):
    """Within a single thread's stream, messages must appear in sequence order.

    Cross-thread ordering is intentionally unspecified — thread A's records
    may appear before, after, or interleaved with thread B's records at the
    record level.  What must hold is that thread A's own records, read from
    the sink in arrival order, are monotonically increasing in sequence number.

    Rationale: each thread calls log() sequentially (seq 0, 1, 2, …).
    The logger must not reorder messages from the same thread.
    In sync mode this is trivially guaranteed by the call order.
    In enqueue mode the queue is FIFO so the worker sees them in order too.
    """

    def _check_ordering(self, records):
        by_thread, unparsed = parse_records(records)
        for tid, seqs in by_thread.items():
            for pos in range(1, len(seqs)):
                self.assertGreater(
                    seqs[pos], seqs[pos - 1],
                    f'Thread {tid}: sequence out of order at position {pos}: '
                    f'{seqs[pos - 1]} → {seqs[pos]}'
                )

    def test_sync_per_thread_ordering(self):
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        self._check_ordering(sink.records)

    def test_enqueue_per_thread_ordering(self):
        L, _  = make_enqueue_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        L.flush()
        self._check_ordering(sink.records)


# ═══════════════════════════════════════════════════════════════════════════
# 3 — Completeness: zero loss, zero duplication
# ═══════════════════════════════════════════════════════════════════════════

class TestCompleteness(unittest.TestCase):
    """Total delivered count must equal N_THREADS × N_PER_THREAD.

    Also checked per-thread: every sequence number 0..N_PER_THREAD-1 must
    appear exactly once for each thread.
    """

    def _check_completeness(self, records, label):
        by_thread, unparsed = parse_records(records)

        self.assertEqual(
            len(unparsed), 0,
            f'{label}: {len(unparsed)} records had no T:S sentinel '
            f'(first few: {unparsed[:3]})'
        )

        for tid in range(N_THREADS):
            seqs = sorted(by_thread[tid])
            expected = list(range(N_PER_THREAD))
            missing  = sorted(set(expected) - set(seqs))
            duped    = [s for s in seqs if seqs.count(s) > 1]
            self.assertEqual(
                seqs, expected,
                f'{label} thread {tid}: '
                f'missing={missing[:5]}, duplicated={list(set(duped))[:5]}'
            )

    def test_sync_all_records_delivered(self):
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        self._check_completeness(sink.records, 'sync')

    def test_enqueue_all_records_delivered(self):
        L, _  = make_enqueue_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        L.flush()
        self._check_completeness(sink.records, 'enqueue')

    def test_sync_total_count_exact(self):
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        self.assertEqual(
            len(sink.records), TOTAL,
            f'sync: expected {TOTAL} records, got {len(sink.records)}'
        )

    def test_enqueue_total_count_exact(self):
        L, _  = make_enqueue_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        L.flush()
        self.assertEqual(
            len(sink.records), TOTAL,
            f'enqueue: expected {TOTAL} records, got {len(sink.records)}'
        )

    def test_no_cross_contamination_between_threads(self):
        """No single record must contain sentinels from two different threads.

        A merged record ('T00:S000001 … T03:S000001') would appear here as
        a record with two sentinels — caught by the atomicity suite too, but
        repeated here as an explicit cross-contamination probe.
        """
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L)
        for i, rec in enumerate(sink.records):
            sentinels = MSG_PATTERN.findall(rec)
            if len(sentinels) > 1:
                tids = {int(s[0]) for s in sentinels}
                self.assertEqual(
                    len(tids), 1,
                    f'Record #{i} mixes content from threads {tids}:\n  {rec!r}'
                )


# ═══════════════════════════════════════════════════════════════════════════
# 4 — File sink integrity
# ═══════════════════════════════════════════════════════════════════════════

class TestFileSinkIntegrity(unittest.TestCase):
    """Same three checks against a real OS file written in sync mode.

    File I/O is the highest-risk path because:
      - Python's buffered writer may release the GIL on large writes
      - The flush step is a separate system call from the write
      - Concurrent writers share the same file descriptor

    In enqueue mode the worker is the sole writer so interleaving is
    impossible by design.  The sync-mode file test is the interesting case.
    """

    def setUp(self):
        self._tmpBase = tempfile.mktemp(suffix='.log')

    def tearDown(self):
        base = self._tmpBase.replace('.log', '')
        for f in glob.glob(base + '*.log'):
            try:
                os.unlink(f)
            except OSError:
                pass

    def _make_file_logger(self, enqueue=False):
        return Logger(
            name        = 'integrity',
            logToFile   = True,
            logFile     = self._tmpBase,
            logToStdout = False,
            stdout      = io.StringIO(),
            enqueue     = enqueue,
        )

    def _read_file_lines(self, logger):
        """Read the log file and return stripped, non-empty lines."""
        with open(logger.logFileName) as fh:
            return [l.rstrip('\n') for l in fh if l.strip()]

    def test_file_sync_each_line_is_one_complete_record(self):
        """Sync mode: every line in the file is a well-formed log record."""
        L = self._make_file_logger(enqueue=False)
        run_flood(L)
        lines = self._read_file_lines(L)

        for i, line in enumerate(lines):
            self.assertRegex(
                line, RECORD_RE,
                f'File line #{i} does not match record format:\n  {line!r}'
            )

    def test_file_sync_total_line_count(self):
        """Sync mode: the file contains exactly TOTAL lines."""
        L = self._make_file_logger(enqueue=False)
        run_flood(L)
        lines = self._read_file_lines(L)
        self.assertEqual(
            len(lines), TOTAL,
            f'File sync: expected {TOTAL} lines, got {len(lines)}'
        )

    def test_file_sync_per_thread_ordering(self):
        """Sync mode: within each thread, file lines are in sequence order."""
        L = self._make_file_logger(enqueue=False)
        run_flood(L)
        lines = self._read_file_lines(L)
        by_thread, _ = parse_records(lines)
        for tid, seqs in by_thread.items():
            for pos in range(1, len(seqs)):
                self.assertGreater(
                    seqs[pos], seqs[pos - 1],
                    f'File thread {tid}: out of order at position {pos}: '
                    f'{seqs[pos - 1]} → {seqs[pos]}'
                )

    def test_file_sync_no_partial_lines(self):
        """Sync mode: no file line fails to parse — no truncated records."""
        L = self._make_file_logger(enqueue=False)
        run_flood(L)
        lines = self._read_file_lines(L)
        _, unparsed = parse_records(lines)
        self.assertEqual(
            len(unparsed), 0,
            f'{len(unparsed)} lines could not be parsed '
            f'(first: {unparsed[:2]})'
        )

    def test_file_enqueue_all_records_delivered(self):
        """Enqueue mode: the single writer serialises all records — zero loss."""
        L = self._make_file_logger(enqueue=True)
        run_flood(L)
        L.flush()
        lines = self._read_file_lines(L)
        self.assertEqual(
            len(lines), TOTAL,
            f'File enqueue: expected {TOTAL} lines, got {len(lines)}'
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5 — Enqueue mode: full three-property check in one test
# ═══════════════════════════════════════════════════════════════════════════

class TestEnqueueIntegrity(unittest.TestCase):
    """Dedicated enqueue-mode variants of atomicity, ordering, completeness.

    In enqueue mode the calling thread only puts a (record, sinks) tuple on
    the queue.  The single worker thread processes items in FIFO order.
    This guarantees:
      - No concurrent writes to the same sink (worker is the sole writer)
      - FIFO ordering: records from the same thread stay in order
      - No record splitting or merging (each queue item is one record)
    These tests verify those guarantees at the observable (sink) level.
    """

    def _run_and_capture(self, n_threads=N_THREADS, n_per=N_PER_THREAD):
        L, _  = make_enqueue_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)
        run_flood(L, n_threads=n_threads, n_per_thread=n_per)
        L.flush()
        return sink.records

    def test_enqueue_each_write_has_one_sentinel(self):
        records = self._run_and_capture()
        for i, rec in enumerate(records):
            sentinels = MSG_PATTERN.findall(rec)
            self.assertEqual(
                len(sentinels), 1,
                f'Enqueue record #{i} has {len(sentinels)} sentinels:\n  {rec!r}'
            )

    def test_enqueue_no_embedded_newlines(self):
        records = self._run_and_capture()
        for i, rec in enumerate(records):
            self.assertNotIn(
                '\n', rec,
                f'Enqueue record #{i} has an embedded newline:\n  {rec!r}'
            )

    def test_enqueue_per_thread_seqs_are_complete_and_ordered(self):
        records = self._run_and_capture()
        by_thread, unparsed = parse_records(records)
        self.assertEqual(len(unparsed), 0)
        for tid in range(N_THREADS):
            seqs = by_thread[tid]      # already in arrival order
            self.assertEqual(
                seqs, list(range(N_PER_THREAD)),
                f'Enqueue thread {tid}: sequence not contiguous and ordered '
                f'(first 5 missing: '
                f'{sorted(set(range(N_PER_THREAD)) - set(seqs))[:5]})'
            )

    def test_enqueue_worker_is_sole_writer_to_sink(self):
        """Every write() call to the user sink must come from the single
        worker thread — never from the calling threads."""
        L, _          = make_enqueue_logger()
        writer_tids   = set()
        lock          = threading.Lock()

        class _TidSink:
            def write(self, _):
                with lock:
                    writer_tids.add(threading.get_ident())
            def flush(self):
                pass

        L.add_sink('probe', _TidSink())
        run_flood(L)
        L.flush()

        self.assertEqual(
            len(writer_tids), 1,
            f'Expected exactly 1 writer thread (worker), '
            f'got {len(writer_tids)}: {writer_tids}'
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6 — Large records (near OS buffer boundaries)
# ═══════════════════════════════════════════════════════════════════════════

class TestLargeRecordIntegrity(unittest.TestCase):
    """Records near or above PIPE_BUF (4096 bytes on Linux, 512 on macOS).

    For larger records the OS write may not be atomic.  This test does NOT
    assert atomicity at the OS level for file writes (that would be a kernel
    guarantee, not a logger guarantee), but it DOES assert:
      - Each write() call to a user sink still carries exactly one record
      - The total record count is exact
      - Per-thread ordering is preserved
    These hold because the GIL protects StringIO.write() and because
    the user-sink path writes each record with a single write() call.
    """

    # Pad each message to this length so records exceed PIPE_BUF on both
    # Linux (4096) and macOS (512).
    PADDING = 5000

    def _run_large(self, n_threads=4, n_per=50):
        L, _  = make_sync_logger()
        sink  = _RecordCaptureSink()
        L.add_sink('probe', sink)

        barrier = threading.Barrier(n_threads)
        errors  = []

        def worker(tid):
            barrier.wait()
            for seq in range(n_per):
                # Build a large payload that still embeds our sentinel
                payload = msg(tid, seq) + ('X' * self.PADDING)
                L.info(payload)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(n_threads)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=JOIN_TIMEOUT)

        return sink.records, n_threads * n_per

    def test_large_record_total_count(self):
        records, expected = self._run_large()
        self.assertEqual(
            len(records), expected,
            f'Large-record test: expected {expected}, got {len(records)}'
        )

    def test_large_record_each_write_one_sentinel(self):
        records, _ = self._run_large()
        for i, rec in enumerate(records):
            sentinels = MSG_PATTERN.findall(rec)
            self.assertEqual(
                len(sentinels), 1,
                f'Large record #{i} has {len(sentinels)} sentinels:\n'
                f'  {rec[:120]!r}…'
            )

    def test_large_record_no_truncation(self):
        """Each record must be at least as long as the padding we injected."""
        records, _ = self._run_large()
        for i, rec in enumerate(records):
            # Allow for the logger header (timestamp + name + type).
            # The record body alone must be at least PADDING chars.
            self.assertGreater(
                len(rec), self.PADDING,
                f'Large record #{i} appears truncated: len={len(rec)}'
            )

    def test_large_record_per_thread_ordering(self):
        records, _ = self._run_large()
        by_thread, _ = parse_records(records)
        for tid, seqs in by_thread.items():
            for pos in range(1, len(seqs)):
                self.assertGreater(
                    seqs[pos], seqs[pos - 1],
                    f'Large-record thread {tid}: out of order at pos {pos}'
                )


# ═══════════════════════════════════════════════════════════════════════════
# entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
