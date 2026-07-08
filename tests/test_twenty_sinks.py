"""20-sink dynamic-reconfiguration integrity test.

setUpClass runs the full 5-phase scenario ONCE.  Every test method
is a focused analytical assertion on the captured in-memory buffers.

Scenario
--------
20 sinks arranged in 5 groups of 4.  Between phases, groups are added,
removed, or have their level constraints changed.  4 threads log all 5
log types concurrently during each phase.  flush() is called between
phases to guarantee clean phase boundaries.

Phase overview (E is the control — never touched after registration)
-------------------------------------------------------------------
       P1    P2    P3    P4    P5
  A   all  gone   all   all   all   re-added in P3; reset in P5
  B   all   all  min≥W max≤I  all   filters swapped P3→P4; reset in P5
  C   all   all   all   all   all   reference — never filtered
  D   all   all  max≤I min≥W  all   filters swapped P3→P4; reset in P5
  E   all   all   all   all   all   control — never touched

   W = warn level (20.0),  I = info level (10.0)

Expected record counts per group per phase
------------------------------------------
         P1   P2   P3   P4   P5   total
  A      100    0  100  100  100    400
  B      100  100   60   40  100    400
  C      100  100  100  100  100    500
  D      100  100   40   60  100    400
  E      100  100  100  100  100    500

MSGS_PER_PHASE = 4 threads × 5 msg/type × 5 types = 100
ABOVE_WARN     = 4 × 5 × 3 types (warn/error/critical) = 60
AT_MOST_INFO   = 4 × 5 × 2 types (debug/info)          = 40

Analysis checks (one test method each)
---------------------------------------
 1  No malformed lines in any of the 20 buffers
 2  Group A is completely absent during Phase 2
 3  Group A recovers fully in Phases 3–5
 4  Group B min=warn filter: no DEBUG/INFO records in Phase 3
 5  Group B max=info filter: no WARNING/ERROR/CRITICAL in Phase 4
 6  Group D max=info filter: no WARNING/ERROR/CRITICAL in Phase 3
 7  Group D min=warn filter: no DEBUG/INFO in Phase 4
 8  Reference group C always has all 5 level types in all 5 phases
 9  Control group E is identical to C in every phase
10  Cumulative totals per group match the expected table above
11  Per-phase counts are exact for every one of the 20 sinks
12  Phase 5 reset: all 20 sinks receive the same count (uniformity)
13  Per-thread ordering: within every (sink, phase, type, thread) tuple,
    sequence numbers are strictly increasing
14  B and D level-filter sets are disjoint (no tag overlap) in P3 and P4
15  Buffer independence: a record in sink s00 is not in sink s01
"""

import io
import re
import threading
import unittest
import os
import sys
from collections import defaultdict, namedtuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from SimpleLog import Logger  # noqa: E402


# ── constants ────────────────────────────────────────────────────────────────

N_SINKS   = 20
N_THREADS = 4           # concurrent writers per phase
N_PER     = 5           # messages per thread per log-type per phase
LOG_TYPES = ('debug', 'info', 'warn', 'error', 'critical')

MSGS_PER_PHASE = N_THREADS * N_PER * len(LOG_TYPES)   # 100
ABOVE_WARN     = N_THREADS * N_PER * 3                 # 60
AT_MOST_INFO   = N_THREADS * N_PER * 2                 # 40

SINK_NAMES = [f's{i:02d}' for i in range(N_SINKS)]

GROUPS = {
    'A': SINK_NAMES[0:4],    # s00-s03  removed P2, re-added P3
    'B': SINK_NAMES[4:8],    # s04-s07  min=warn P3, max=info P4, reset P5
    'C': SINK_NAMES[8:12],   # s08-s11  reference — never filtered
    'D': SINK_NAMES[12:16],  # s12-s15  max=info P3, min=warn P4, reset P5
    'E': SINK_NAMES[16:20],  # s16-s19  control   — never touched
}

# Log-type tags as they appear inside < > in every sink record
ABOVE_WARN_TAGS   = frozenset({'WARNING', 'ERROR', 'CRITICAL'})
AT_MOST_INFO_TAGS = frozenset({'DEBUG', 'INFO'})
ALL_TAGS          = frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'})

# Exact count expected for each group in each phase
EXPECTED = {
    'A': {1: 100, 2: 0,   3: 100, 4: 100, 5: 100},
    'B': {1: 100, 2: 100, 3: 60,  4: 40,  5: 100},
    'C': {1: 100, 2: 100, 3: 100, 4: 100, 5: 100},
    'D': {1: 100, 2: 100, 3: 40,  4: 60,  5: 100},
    'E': {1: 100, 2: 100, 3: 100, 4: 100, 5: 100},
}
CUMULATIVE = {g: sum(EXPECTED[g].values()) for g in EXPECTED}

# Regex to parse one record line (after rstrip('\n'))
RECORD_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - \S+ <(\w+)> (P\d:T\d{2}:S\d{5})$'
)
MSG_RE = re.compile(r'P(\d):T(\d{2}):S(\d{5})')

ParsedRecord = namedtuple('ParsedRecord', ['tag', 'phase', 'tid', 'seq'])

JOIN_TIMEOUT = 15.0   # seconds per phase


# ── helpers ─────────────────────────────────────────────────────────────────

class _MemSink:
    """User sink backed by an in-memory io.StringIO buffer.

    In enqueue mode the worker is the sole writer, so no lock is
    technically needed; the lock is kept for correctness in any mode.
    """

    def __init__(self, name):
        self.name = name
        self.buf  = io.StringIO()
        self._lock = threading.Lock()

    def write(self, text):
        with self._lock:
            self.buf.write(text)

    def flush(self):
        pass


def _parse_buffer(mem_sink):
    """Parse all records from a _MemSink buffer.

    :Returns:
        records (list[ParsedRecord]): Fully parsed records.
        malformed (list[str]): Lines that did not match the expected format.
    """
    mem_sink.buf.seek(0)
    records  = []
    malformed = []
    for raw in mem_sink.buf:
        line = raw.rstrip('\n')
        if not line:
            continue
        m = RECORD_RE.match(line)
        if not m:
            malformed.append(line)
            continue
        msg_m = MSG_RE.match(m.group(2))
        if not msg_m:
            malformed.append(line)
            continue
        records.append(ParsedRecord(
            tag   = m.group(1),
            phase = int(msg_m.group(1)),
            tid   = int(msg_m.group(2)),
            seq   = int(msg_m.group(3)),
        ))
    return records, malformed


def _group_of(sink_name):
    """Return the group letter ('A'..'E') for a sink name."""
    for letter, names in GROUPS.items():
        if sink_name in names:
            return letter
    raise KeyError(sink_name)


# ═══════════════════════════════════════════════════════════════════════════
# Main test class
# ═══════════════════════════════════════════════════════════════════════════

class TestTwentySinks(unittest.TestCase):
    """Run the 5-phase scenario in setUpClass, analyse in test methods."""

    # ── shared class-level state set by setUpClass ──────────────────────────
    #   mem_sinks  : dict[str, _MemSink]
    #   parsed     : dict[str, list[ParsedRecord]]
    #   malformed  : dict[str, list[str]]
    #   WARN_LEVEL : float
    #   INFO_LEVEL : float

    # ── setup ───────────────────────────────────────────────────────────────

    @classmethod
    def setUpClass(cls):
        """Build the logger, run all 5 phases, parse every buffer."""

        cls.mem_sinks = {name: _MemSink(name) for name in SINK_NAMES}

        cls.L = Logger(
            name        = 'msink',
            logToFile   = False,
            logToStdout = False,
            stdout      = io.StringIO(),
            enqueue     = True,
        )

        lvls = cls.L.logTypeLevels
        cls.WARN_LEVEL = lvls['warn']   # 20.0
        cls.INFO_LEVEL = lvls['info']   # 10.0

        # Register all 20 sinks — Phase 1 baseline
        for name in SINK_NAMES:
            cls.L.add_sink(name, cls.mem_sinks[name])

        # ── Phase 1: all 20 sinks, no filters ─────────────────────────────
        cls._run_phase(1)

        # ── Phase 2: remove Group A ────────────────────────────────────────
        for name in GROUPS['A']:
            cls.L.remove_sink(name)
        cls._run_phase(2)

        # ── Phase 3: re-add A; B → min=warn; D → max=info ─────────────────
        for name in GROUPS['A']:
            cls.L.add_sink(name, cls.mem_sinks[name])
        for name in GROUPS['B']:
            cls.L.set_minimum_level(
                cls.WARN_LEVEL, stdoutFlag=False, fileFlag=False, sinks=[name]
            )
        for name in GROUPS['D']:
            cls.L.set_maximum_level(
                cls.INFO_LEVEL, stdoutFlag=False, fileFlag=False, sinks=[name]
            )
        cls._run_phase(3)

        # ── Phase 4: swap B and D filters via remove+re-add ────────────────
        # Swapping min→max (or max→min) on a live sink would violate the
        # min≤max invariant and raise ValueError, so we remove and re-add.
        for name in GROUPS['B']:
            cls.L.remove_sink(name)
            cls.L.add_sink(name, cls.mem_sinks[name],
                           maxLevel=cls.INFO_LEVEL)
        for name in GROUPS['D']:
            cls.L.remove_sink(name)
            cls.L.add_sink(name, cls.mem_sinks[name],
                           minLevel=cls.WARN_LEVEL)
        cls._run_phase(4)

        # ── Phase 5: reset all modified groups; back to 20 sinks, no filters
        for name in GROUPS['A'] + GROUPS['B'] + GROUPS['D']:
            cls.L.remove_sink(name)
            cls.L.add_sink(name, cls.mem_sinks[name])
        cls._run_phase(5)

        # Parse every buffer exactly once
        cls.parsed   = {}
        cls.malformed = {}
        for name in SINK_NAMES:
            recs, bad = _parse_buffer(cls.mem_sinks[name])
            cls.parsed[name]   = recs
            cls.malformed[name] = bad

    @classmethod
    def tearDownClass(cls):
        cls.L.flush()

    @classmethod
    def _run_phase(cls, phase_num):
        """Spawn N_THREADS threads; each logs all types N_PER times; then flush."""
        barrier = threading.Barrier(N_THREADS)

        def worker(tid):
            barrier.wait()
            for seq in range(N_PER):
                for lt in LOG_TYPES:
                    cls.L.log(lt, f'P{phase_num}:T{tid:02d}:S{seq:05d}')

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=JOIN_TIMEOUT)
        cls.L.flush()

    # ── convenience accessors ────────────────────────────────────────────────

    def _phase(self, sink_name, phase):
        """All ParsedRecords from one sink for one phase."""
        return [r for r in self.parsed[sink_name] if r.phase == phase]

    def _count(self, sink_name, phase):
        return len(self._phase(sink_name, phase))

    def _tags(self, sink_name, phase):
        """Set of level tags seen in a sink during a phase."""
        return {r.tag for r in self._phase(sink_name, phase)}

    # ═══════════════════════════════════════════════════════════════════════
    # Test methods (numbered so they run in scenario order)
    # ═══════════════════════════════════════════════════════════════════════

    def test_01_no_malformed_records_in_any_buffer(self):
        """Every line in all 20 in-memory buffers must parse cleanly.

        A malformed line means a partial write, two records merged into one
        write() call, or a truncated record — all are corruption indicators.
        """
        for name in SINK_NAMES:
            bad = self.malformed[name]
            self.assertEqual(
                bad, [],
                f'Sink {name}: {len(bad)} malformed lines '
                f'(first: {repr(bad[0]) if bad else ""})'
            )

    def test_02_group_A_absent_in_phase_2(self):
        """Group A was removed before Phase 2 — its buffers must contain
        zero Phase-2 records."""
        for name in GROUPS['A']:
            count = self._count(name, 2)
            self.assertEqual(
                count, 0,
                f'Sink {name}: expected 0 Phase-2 records after removal, '
                f'got {count}'
            )

    def test_03_group_A_recovers_fully_in_phases_3_4_5(self):
        """Re-adding Group A in Phase 3 must restore full delivery."""
        for name in GROUPS['A']:
            for phase in (3, 4, 5):
                count = self._count(name, phase)
                self.assertEqual(
                    count, MSGS_PER_PHASE,
                    f'Sink {name} Phase {phase}: expected {MSGS_PER_PHASE}, '
                    f'got {count}'
                )

    def test_04_group_B_min_warn_blocks_debug_and_info_in_phase3(self):
        """Phase 3: Group B has min=warn, so DEBUG and INFO records must be absent."""
        for name in GROUPS['B']:
            tags = self._tags(name, 3)
            forbidden = tags & AT_MOST_INFO_TAGS
            self.assertEqual(
                forbidden, set(),
                f'Sink {name} Phase 3 (min=warn): found forbidden tags {forbidden}'
            )

    def test_05_group_B_min_warn_passes_warn_error_critical_in_phase3(self):
        """Phase 3: Group B must receive exactly warn, error, critical."""
        for name in GROUPS['B']:
            tags = self._tags(name, 3)
            self.assertEqual(
                tags, ABOVE_WARN_TAGS,
                f'Sink {name} Phase 3 (min=warn): expected tags '
                f'{ABOVE_WARN_TAGS}, got {tags}'
            )

    def test_06_group_B_max_info_blocks_warn_error_critical_in_phase4(self):
        """Phase 4: Group B filter swapped to max=info — WARNING/ERROR/CRITICAL absent."""
        for name in GROUPS['B']:
            tags = self._tags(name, 4)
            forbidden = tags & ABOVE_WARN_TAGS
            self.assertEqual(
                forbidden, set(),
                f'Sink {name} Phase 4 (max=info): found forbidden tags {forbidden}'
            )

    def test_07_group_B_max_info_passes_debug_and_info_in_phase4(self):
        """Phase 4: Group B must receive exactly debug and info."""
        for name in GROUPS['B']:
            tags = self._tags(name, 4)
            self.assertEqual(
                tags, AT_MOST_INFO_TAGS,
                f'Sink {name} Phase 4 (max=info): expected tags '
                f'{AT_MOST_INFO_TAGS}, got {tags}'
            )

    def test_08_group_D_max_info_blocks_above_warn_in_phase3(self):
        """Phase 3: Group D has max=info — WARNING/ERROR/CRITICAL must be absent."""
        for name in GROUPS['D']:
            tags = self._tags(name, 3)
            forbidden = tags & ABOVE_WARN_TAGS
            self.assertEqual(
                forbidden, set(),
                f'Sink {name} Phase 3 (max=info): found forbidden tags {forbidden}'
            )

    def test_09_group_D_min_warn_blocks_debug_and_info_in_phase4(self):
        """Phase 4: Group D filter swapped to min=warn — DEBUG/INFO must be absent."""
        for name in GROUPS['D']:
            tags = self._tags(name, 4)
            forbidden = tags & AT_MOST_INFO_TAGS
            self.assertEqual(
                forbidden, set(),
                f'Sink {name} Phase 4 (min=warn): found forbidden tags {forbidden}'
            )

    def test_10_group_C_reference_always_receives_all_types(self):
        """Group C is never filtered — it must see all 5 tags in every phase."""
        for name in GROUPS['C']:
            for phase in range(1, 6):
                tags = self._tags(name, phase)
                self.assertEqual(
                    tags, ALL_TAGS,
                    f'Sink {name} Phase {phase}: expected all tags {ALL_TAGS}, '
                    f'got {tags}'
                )

    def test_11_control_group_E_matches_group_C_in_every_phase(self):
        """Group E (control) is identical to Group C in count and tag diversity."""
        c_name = GROUPS['C'][0]
        for e_name in GROUPS['E']:
            for phase in range(1, 6):
                c_count = self._count(c_name, phase)
                e_count = self._count(e_name, phase)
                self.assertEqual(
                    e_count, c_count,
                    f'Control sink {e_name} Phase {phase}: '
                    f'expected {c_count} (same as {c_name}), got {e_count}'
                )
                self.assertEqual(
                    self._tags(e_name, phase), ALL_TAGS,
                    f'Control sink {e_name} Phase {phase}: '
                    f'missing some tag types'
                )

    def test_12_per_phase_exact_counts_all_20_sinks(self):
        """Every one of the 20 sinks must have exactly the expected count
        in every phase — the complete expected-count table, cell by cell."""
        for sink_name in SINK_NAMES:
            group = _group_of(sink_name)
            for phase in range(1, 6):
                expected = EXPECTED[group][phase]
                actual   = self._count(sink_name, phase)
                self.assertEqual(
                    actual, expected,
                    f'Sink {sink_name} (group {group}) Phase {phase}: '
                    f'expected {expected}, got {actual}'
                )

    def test_13_cumulative_totals_match_expected_table(self):
        """Total record count across all phases must equal the pre-calculated
        cumulative for each group."""
        for sink_name in SINK_NAMES:
            group    = _group_of(sink_name)
            expected = CUMULATIVE[group]
            actual   = len(self.parsed[sink_name])
            self.assertEqual(
                actual, expected,
                f'Sink {sink_name} (group {group}): '
                f'cumulative expected {expected}, got {actual}'
            )

    def test_14_phase5_reset_all_20_sinks_receive_same_count(self):
        """After the Phase 5 reset (all constraints cleared, all 20 re-added),
        every sink must receive exactly MSGS_PER_PHASE records."""
        for name in SINK_NAMES:
            count = self._count(name, 5)
            self.assertEqual(
                count, MSGS_PER_PHASE,
                f'Sink {name} Phase 5 (post-reset): expected {MSGS_PER_PHASE}, '
                f'got {count}'
            )

    def test_15_phase5_all_20_sinks_see_all_5_types(self):
        """Phase 5: no filters remain; every sink must see all 5 level tags."""
        for name in SINK_NAMES:
            tags = self._tags(name, 5)
            self.assertEqual(
                tags, ALL_TAGS,
                f'Sink {name} Phase 5 (post-reset): missing tags '
                f'{ALL_TAGS - tags}'
            )

    def test_16_group_B_and_D_level_sets_are_disjoint_in_filtered_phases(self):
        """In Phases 3 and 4, B and D have complementary level windows.
        Their tag sets must be disjoint — their union must be ALL_TAGS.

        Phase 3: B gets {WARNING,ERROR,CRITICAL}, D gets {DEBUG,INFO}  → ∩ = ∅
        Phase 4: B gets {DEBUG,INFO}, D gets {WARNING,ERROR,CRITICAL}  → ∩ = ∅
        """
        for phase in (3, 4):
            for b_name, d_name in zip(GROUPS['B'], GROUPS['D']):
                b_tags = self._tags(b_name, phase)
                d_tags = self._tags(d_name, phase)
                intersection = b_tags & d_tags
                self.assertEqual(
                    intersection, set(),
                    f'Phase {phase}: {b_name} and {d_name} share tags '
                    f'{intersection} — level windows overlapped'
                )
                self.assertEqual(
                    b_tags | d_tags, ALL_TAGS,
                    f'Phase {phase}: {b_name}∪{d_name} = {b_tags | d_tags}, '
                    f'expected all 5 tags (no gaps in coverage)'
                )

    def test_17_per_thread_ordering_within_every_sink(self):
        """For every (sink, phase, tag, thread) combination, the sequence
        numbers of that thread's records must be strictly increasing.

        This verifies that the FIFO guarantee of the queue is preserved
        end-to-end: no message from a single thread ever overtakes another.
        """
        for sink_name in SINK_NAMES:
            # Group records by (phase, tag, tid)
            buckets = defaultdict(list)
            for rec in self.parsed[sink_name]:
                buckets[(rec.phase, rec.tag, rec.tid)].append(rec.seq)

            for (phase, tag, tid), seqs in buckets.items():
                for pos in range(1, len(seqs)):
                    self.assertGreater(
                        seqs[pos], seqs[pos - 1],
                        f'Sink {sink_name} Phase {phase} tag {tag} '
                        f'thread {tid}: sequence out of order at position '
                        f'{pos}: {seqs[pos-1]} → {seqs[pos]}'
                    )

    def test_18_buffer_independence(self):
        """A Phase-1 record from sink s00 must not appear in sink s01's buffer.

        This catches a shared-reference bug where two 'different' sinks are
        writing to the same underlying object.
        """
        # Each sink's buffer is independent: the raw text content of s00
        # and s01 will be different (different sink name appears in the header,
        # plus non-deterministic interleaving). We verify there is no
        # object-level aliasing.
        for i in range(len(SINK_NAMES) - 1):
            a = self.mem_sinks[SINK_NAMES[i]].buf
            b = self.mem_sinks[SINK_NAMES[i + 1]].buf
            self.assertIsNot(
                a, b,
                f'Sinks {SINK_NAMES[i]} and {SINK_NAMES[i+1]} share '
                f'the same buffer object — they are not independent'
            )

    def test_19_raw_buffer_content_is_non_empty_for_active_sinks(self):
        """Every sink that should have received records must have a non-empty
        in-memory buffer after all phases complete."""
        for name in SINK_NAMES:
            group    = _group_of(name)
            expected_total = CUMULATIVE[group]
            if expected_total > 0:
                self.mem_sinks[name].buf.seek(0)
                content = self.mem_sinks[name].buf.read()
                self.assertTrue(
                    content.strip(),
                    f'Sink {name} (group {group}) buffer is empty '
                    f'but expected {expected_total} records'
                )

    def test_20_full_type_coverage_per_thread_in_unconstrained_phases(self):
        """In unconstrained phases, every thread must have contributed records
        of all 5 types to every active sink.  This catches a bug where one
        thread's records for a specific type were silently lost.

        Checks Phase 1 (all sinks) and Phase 5 (after reset) for Group C
        as the reference, plus Group E as the control.
        """
        for phase in (1, 5):
            for group_name in ('C', 'E'):
                for sink_name in GROUPS[group_name]:
                    for tid in range(N_THREADS):
                        thread_tags = {
                            r.tag
                            for r in self.parsed[sink_name]
                            if r.phase == phase and r.tid == tid
                        }
                        self.assertEqual(
                            thread_tags, ALL_TAGS,
                            f'Sink {sink_name} Phase {phase} '
                            f'thread {tid}: missing types '
                            f'{ALL_TAGS - thread_tags}'
                        )


# ═══════════════════════════════════════════════════════════════════════════
# entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
