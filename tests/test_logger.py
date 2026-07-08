"""Developer test suite for pysimplelog.

Run from the repo root with any of:
    python3 -m pytest tests/test_logger.py -v
    python3 tests/test_logger.py

Each TestCase class covers one feature area.  Tests use io.StringIO for
output capture so no real files are created unless a test explicitly
needs file-sink or rotation behaviour (those tests clean up after
themselves).

Coverage map
------------
TestLoggerInit          -- constructor parameters and initial property values
TestBuiltinLogTypes     -- info / warn / warning / error / critical / debug
TestCountConstraint     -- countConstraint parameter on log()
TestLastLogged          -- lastLogged / lastLoggedMessage / lastLogged* properties
TestStdoutSink          -- enable/disable, per-type flags, level window
TestFileSink            -- file creation, enable/disable, rotation
TestUserSinkBasic       -- add_sink / remove_sink / clear_sinks, routing, ANSI-free
TestUserSinkEnabled     -- enabled flag at add time and via set_log_to_stdout_flag
TestUserSinkLogTypeFlags -- per-type flags on a user sink
TestUserSinkLevelFilter -- minLevel / maxLevel via add_sink and set_minimum/maximum_level
TestRebuildActiveSinks  -- white-box: __activeSinks cache structure after every change
TestUserSinkIndependence -- user sink receives a type suppressed globally for stdout
TestSinkApiValidation   -- bad inputs to add/remove/clear sinks
TestLevelMethods        -- set_minimum/maximum_level for built-ins and sinks=
TestIsEnabled           -- is_enabled / is_enabled_for_stdout / is_enabled_for_file
TestEnqueue             -- non-blocking mode, flush(), thread safety
TestBind                -- context-tag binding, isolation from parent logger
TestCatch               -- @catch decorator, context manager, reraise
TestForceLog            -- force_log bypasses user sinks
TestSanitize            -- ANSI stripping, maxMessageSize, maxDataSize
TestParametersStr       -- parameters property, userSinks snapshot, __str__
TestFlushAtexit         -- _flush_atexit_logfile lifecycle contract
"""

import glob
import io
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from SimpleLog import Logger, _SINK_STDOUT, _SINK_FILE  # noqa: E402


# ─────────────────────────── helpers ────────────────────────────────────────

def make_logger(**kwargs):
    """Return a Logger whose stdout is captured in a StringIO buffer.

    Any keyword argument is forwarded to Logger(). logToFile defaults to
    False so tests do not create disk files unless they need to.
    """
    defaults = dict(name='test', logToFile=False, logToStdout=True)
    defaults.update(kwargs)
    buf = io.StringIO()
    defaults.setdefault('stdout', buf)
    logger = Logger(**defaults)
    return logger, buf


class _CaptureSink:
    """Minimal write-only handler that collects every record as a list entry."""

    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)

    def flush(self):
        pass

    def contains(self, substring):
        return any(substring in line for line in self.lines)

    def count(self, substring):
        return sum(1 for line in self.lines if substring in line)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — Initialisation
# ═══════════════════════════════════════════════════════════════════════════

class TestLoggerInit(unittest.TestCase):
    """Constructor parameters and initial property values."""

    def test_default_properties(self):
        L, _ = make_logger(name='init-test')
        self.assertEqual(L.logToStdout, True)
        self.assertEqual(L.logToFile, False)
        self.assertFalse(L.enqueue)
        self.assertIsNotNone(L.logFileName)

    def test_name_reflected_in_output(self):
        L, buf = make_logger(name='myapp')
        L.info('hello')
        self.assertIn('myapp', buf.getvalue())

    def test_logToStdout_false_at_init(self):
        L, buf = make_logger(logToStdout=False)
        L.info('silent')
        self.assertNotIn('silent', buf.getvalue())

    def test_logToFile_false_no_file_written(self):
        """logToFile=False is reflected by the property and no file
        opens are attempted by the sink (file sink is disabled)."""
        L, _ = make_logger(logToFile=False)
        self.assertFalse(L.logToFile)
        # file sink must be marked disabled in the sinks dict
        self.assertFalse(L.sinks[_SINK_FILE].enabled)

    def test_enqueue_mode_enabled(self):
        L, _ = make_logger(enqueue=True)
        self.assertTrue(L.enqueue)
        L.flush()

    def test_callerInfo_false_by_default(self):
        L, buf = make_logger()
        L.info('msg')
        # callerInfo adds a bracketed file:line token; absent by default
        self.assertNotIn('.py:', buf.getvalue())

    def test_callerInfo_true_adds_annotation(self):
        L, buf = make_logger(callerInfo=True)
        L.info('msg')
        self.assertIn('[', buf.getvalue())

    def test_custom_stdout_stream(self):
        custom = io.StringIO()
        L = Logger(name='t', logToFile=False, stdout=custom)
        L.info('custom-stream')
        self.assertIn('custom-stream', custom.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
# 2 — Built-in log types
# ═══════════════════════════════════════════════════════════════════════════

class TestBuiltinLogTypes(unittest.TestCase):
    """Every built-in type produces the correct tag in output."""

    def setUp(self):
        self.L, self.buf = make_logger()

    def _out(self):
        return self.buf.getvalue()

    def test_info(self):
        self.L.info('msg')
        self.assertIn('<INFO>', self._out())
        self.assertIn('msg', self._out())

    def test_warn(self):
        self.L.warn('msg')
        self.assertIn('<WARNING>', self._out())

    def test_warning_alias(self):
        """warning() must be an alias for warn() — produces same tag."""
        self.L.warning('msg')
        self.assertIn('<WARNING>', self._out())

    def test_error(self):
        self.L.error('msg')
        self.assertIn('<ERROR>', self._out())

    def test_critical(self):
        self.L.critical('msg')
        self.assertIn('<CRITICAL>', self._out())

    def test_debug(self):
        self.L.debug('msg')
        self.assertIn('<DEBUG>', self._out())

    def test_generic_log_method(self):
        self.L.log('info', 'via-log')
        self.assertIn('via-log', self._out())

    def test_tback_appended(self):
        """Passing tback= causes the traceback string to appear in output."""
        self.L.info('err', tback='Traceback (most recent call last):\n  File "x.py"')
        self.assertIn('Traceback', self._out())

    def test_data_appended(self):
        self.L.info('d', data='extra-data-payload')
        self.assertIn('extra-data-payload', self._out())


# ═══════════════════════════════════════════════════════════════════════════
# 3 — countConstraint
# ═══════════════════════════════════════════════════════════════════════════

class TestCountConstraint(unittest.TestCase):
    """log() should skip duplicate messages once the constraint is hit."""

    def setUp(self):
        self.L, self.buf = make_logger()

    def test_constraint_of_2_logs_exactly_twice(self):
        for _ in range(5):
            self.L.log('info', 'repeat', countConstraint=2)
        logged = self.buf.getvalue().count('repeat')
        self.assertEqual(logged, 2)

    def test_no_constraint_logs_all(self):
        for _ in range(3):
            self.L.log('info', 'unlimited')
        self.assertEqual(self.buf.getvalue().count('unlimited'), 3)

    def test_constraint_is_per_message(self):
        for _ in range(5):
            self.L.log('info', 'msgA', countConstraint=1)
            self.L.log('info', 'msgB', countConstraint=1)
        self.assertEqual(self.buf.getvalue().count('msgA'), 1)
        self.assertEqual(self.buf.getvalue().count('msgB'), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 4 — lastLogged properties
# ═══════════════════════════════════════════════════════════════════════════

class TestLastLogged(unittest.TestCase):

    def setUp(self):
        self.L, _ = make_logger()

    def test_lastLoggedMessage_after_info(self):
        self.L.info('hello')
        self.assertIn('hello', self.L.lastLoggedMessage)

    def test_lastLoggedInfo(self):
        self.L.info('i-msg')
        self.assertIn('i-msg', self.L.lastLoggedInfo)

    def test_lastLoggedWarning(self):
        self.L.warn('w-msg')
        self.assertIn('w-msg', self.L.lastLoggedWarning)

    def test_lastLoggedError(self):
        self.L.error('e-msg')
        self.assertIn('e-msg', self.L.lastLoggedError)

    def test_lastLoggedCritical(self):
        self.L.critical('c-msg')
        self.assertIn('c-msg', self.L.lastLoggedCritical)

    def test_lastLogged_dict_contains_all_types(self):
        self.L.debug('d'); self.L.info('i')
        d = self.L.lastLogged
        self.assertIn('debug', d)
        self.assertIn('info', d)
        # integer key -1 (lastLoggedMessage sentinel) must be absent
        self.assertNotIn(-1, d)


# ═══════════════════════════════════════════════════════════════════════════
# 5 — Stdout sink
# ═══════════════════════════════════════════════════════════════════════════

class TestStdoutSink(unittest.TestCase):

    def test_disable_stdout_globally(self):
        L, buf = make_logger()
        L.set_log_to_stdout_flag(False)
        L.info('hidden')
        self.assertNotIn('hidden', buf.getvalue())

    def test_re_enable_stdout(self):
        L, buf = make_logger()
        L.set_log_to_stdout_flag(False)
        L.set_log_to_stdout_flag(True)
        L.info('visible')
        self.assertIn('visible', buf.getvalue())

    def test_per_type_flag_suppresses_type(self):
        L, buf = make_logger()
        L.set_log_type_flags('debug', stdoutFlag=False, fileFlag=False)
        L.debug('no-debug')
        self.assertNotIn('no-debug', buf.getvalue())

    def test_stdout_minimum_level_filters_below(self):
        L, buf = make_logger()
        warnLevel = L.logTypeLevels['warn']
        L.set_minimum_level(warnLevel, stdoutFlag=True)
        L.info('below-min')
        L.warn('at-min')
        self.assertNotIn('below-min', buf.getvalue())
        self.assertIn('at-min', buf.getvalue())

    def test_stdout_maximum_level_filters_above(self):
        L, buf = make_logger()
        infoLevel = L.logTypeLevels['info']
        L.set_maximum_level(infoLevel, stdoutFlag=True)
        L.warn('above-max')
        L.info('at-max')
        self.assertNotIn('above-max', buf.getvalue())
        self.assertIn('at-max', buf.getvalue())

    def test_set_stdout_redirects_midrun(self):
        L, bufA = make_logger()
        L.info('first')
        bufB = io.StringIO()
        L.set_stdout(bufB)
        L.info('second')
        self.assertIn('first', bufA.getvalue())
        self.assertNotIn('second', bufA.getvalue())
        self.assertIn('second', bufB.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
# 6 — File sink
# ═══════════════════════════════════════════════════════════════════════════

class TestFileSink(unittest.TestCase):

    def setUp(self):
        self.tmpBase = tempfile.mktemp(suffix='.log')

    def tearDown(self):
        base = self.tmpBase.replace('.log', '')
        for f in glob.glob(base + '*.log'):
            try:
                os.unlink(f)
            except OSError:
                pass

    def _make_file_logger(self, **kwargs):
        defaults = dict(name='ftest', logToFile=True, logFile=self.tmpBase,
                        logToStdout=False, stdout=io.StringIO())
        defaults.update(kwargs)
        return Logger(**defaults)

    def test_message_written_to_file(self):
        L = self._make_file_logger()
        L.info('to-file'); L.flush()
        with open(L.logFileName) as fh:
            self.assertIn('to-file', fh.read())

    def test_disable_file_stops_writes(self):
        L = self._make_file_logger()
        L.set_log_to_file_flag(False)
        L.info('no-file'); L.flush()
        content = open(L.logFileName).read() if os.path.exists(L.logFileName) else ''
        self.assertNotIn('no-file', content)

    def test_file_rotation_occurs(self):
        L = self._make_file_logger(logFileMaxSize=0.001)  # 1 KB cap
        for _ in range(40):
            L.info('x' * 100)
        L.flush()
        base = self.tmpBase.replace('.log', '')
        rotated = glob.glob(base + '*.log')
        self.assertGreater(len(rotated), 1, 'expected at least one rotation')

    def test_logFileName_property(self):
        L = self._make_file_logger()
        self.assertTrue(L.logFileName.endswith('.log'))


# ═══════════════════════════════════════════════════════════════════════════
# 7 — User sink basics
# ═══════════════════════════════════════════════════════════════════════════

class TestUserSinkBasic(unittest.TestCase):

    def setUp(self):
        self.L, self.bufStdout = make_logger()

    def test_add_sink_receives_messages(self):
        sink = _CaptureSink()
        self.L.add_sink('s', sink)
        self.L.info('hello-sink')
        self.assertTrue(sink.contains('hello-sink'))

    def test_user_sink_receives_no_ansi(self):
        """The plain-text record sent to user sinks must be ANSI-free."""
        sink = _CaptureSink()
        self.L.add_sink('s', sink)
        self.L.info('check-ansi')
        combined = ''.join(sink.lines)
        self.assertNotIn('\x1b', combined)

    def test_remove_sink_stops_delivery(self):
        sink = _CaptureSink()
        self.L.add_sink('s', sink)
        self.L.info('before')
        self.L.remove_sink('s')
        self.L.info('after')
        self.assertTrue(sink.contains('before'))
        self.assertFalse(sink.contains('after'))

    def test_clear_sinks_removes_all_user_sinks(self):
        self.L.add_sink('a', _CaptureSink())
        self.L.add_sink('b', _CaptureSink())
        self.L.clear_sinks()
        # only integer built-in keys remain
        self.assertTrue(all(isinstance(k, int) for k in self.L.sinks))

    def test_clear_sinks_preserves_builtins(self):
        self.L.add_sink('tmp', _CaptureSink())
        self.L.clear_sinks()
        self.assertIn(_SINK_STDOUT, self.L.sinks)
        self.assertIn(_SINK_FILE, self.L.sinks)

    def test_duplicate_name_raises(self):
        self.L.add_sink('dup', _CaptureSink())
        with self.assertRaises(ValueError):
            self.L.add_sink('dup', _CaptureSink())

    def test_remove_unknown_raises(self):
        with self.assertRaises(ValueError):
            self.L.remove_sink('ghost')

    def test_multiple_sinks_all_receive(self):
        sinkA = _CaptureSink(); sinkB = _CaptureSink()
        self.L.add_sink('a', sinkA); self.L.add_sink('b', sinkB)
        self.L.info('broadcast')
        self.assertTrue(sinkA.contains('broadcast'))
        self.assertTrue(sinkB.contains('broadcast'))


# ═══════════════════════════════════════════════════════════════════════════
# 8 — User sink enabled flag
# ═══════════════════════════════════════════════════════════════════════════

class TestUserSinkEnabled(unittest.TestCase):

    def test_add_sink_disabled_receives_nothing(self):
        L, _ = make_logger()
        sink = _CaptureSink()
        L.add_sink('s', sink, enabled=False)
        L.info('silent')
        self.assertFalse(sink.contains('silent'))

    def test_stdout_disable_does_not_affect_user_sink(self):
        """Turning off stdout must not suppress a user sink."""
        L, buf = make_logger()
        sink = _CaptureSink()
        L.add_sink('s', sink)
        L.set_log_to_stdout_flag(False)
        L.info('only-sink')
        self.assertNotIn('only-sink', buf.getvalue())
        self.assertTrue(sink.contains('only-sink'))


# ═══════════════════════════════════════════════════════════════════════════
# 9 — User sink per-type logTypeFlags
# ═══════════════════════════════════════════════════════════════════════════

class TestUserSinkLogTypeFlags(unittest.TestCase):

    def test_logTypeFlag_false_suppresses_that_type(self):
        L, _ = make_logger()
        sink = _CaptureSink()
        L.add_sink('s', sink, logTypeFlags={'debug': False})
        L.debug('no-debug')
        L.info('yes-info')
        self.assertFalse(sink.contains('no-debug'))
        self.assertTrue(sink.contains('yes-info'))

    def test_missing_key_defaults_to_true(self):
        L, _ = make_logger()
        sink = _CaptureSink()
        # logTypeFlags has no 'info' entry → info defaults to enabled
        L.add_sink('s', sink, logTypeFlags={'debug': False})
        L.info('should-arrive')
        self.assertTrue(sink.contains('should-arrive'))

    def test_all_types_suppressed_via_flags(self):
        L, _ = make_logger()
        sink = _CaptureSink()
        L.add_sink('s', sink, logTypeFlags={t: False for t in L.logTypeLevels})
        L.info('x'); L.warn('x'); L.error('x')
        self.assertEqual(sink.lines, [])


# ═══════════════════════════════════════════════════════════════════════════
# 10 — User sink level filtering (the user's core concern)
# ═══════════════════════════════════════════════════════════════════════════

class TestUserSinkLevelFilter(unittest.TestCase):
    """
    Verifies that __rebuild_active_sinks correctly applies minLevel /
    maxLevel constraints for user sinks.

    Each test uses two sinks side-by-side: an unrestricted reference sink
    (receives everything) and a constrained sink under test.  Comparing
    their output proves the filtering is correct without touching internals.
    """

    def _setup(self, **sink_kwargs):
        L, _ = make_logger(logToStdout=False)
        ref  = _CaptureSink()
        test = _CaptureSink()
        L.add_sink('ref',  ref)
        L.add_sink('test', test, **sink_kwargs)
        return L, ref, test

    def test_minLevel_blocks_below(self):
        L, ref, test = self._setup(minLevel=L.logTypeLevels['warn']
                                   if False else None)  # placeholder
        # redo with real level
        L, _ = make_logger(logToStdout=False)
        ref  = _CaptureSink(); test = _CaptureSink()
        L.add_sink('ref', ref)
        warnLevel = L.logTypeLevels['warn']
        L.add_sink('test', test, minLevel=warnLevel)
        L.debug('no'); L.info('no'); L.warn('yes'); L.error('yes')
        self.assertTrue(ref.contains('no'))       # ref gets debug
        self.assertFalse(test.contains('debug'))  # test does not
        self.assertTrue(test.contains('yes'))

    def test_maxLevel_blocks_above(self):
        L, _ = make_logger(logToStdout=False)
        test = _CaptureSink()
        infoLevel = L.logTypeLevels['info']
        L.add_sink('test', test, maxLevel=infoLevel)
        L.debug('dbg-pass'); L.info('inf-pass')
        L.warn('wrn-block'); L.error('err-block')
        self.assertTrue(test.contains('dbg-pass'))
        self.assertTrue(test.contains('inf-pass'))
        self.assertFalse(test.contains('wrn-block'))
        self.assertFalse(test.contains('err-block'))

    def test_level_window_only_passes_middle_range(self):
        L, _ = make_logger(logToStdout=False)
        test = _CaptureSink()
        infoLevel = L.logTypeLevels['info']
        warnLevel = L.logTypeLevels['warn']
        L.add_sink('test', test, minLevel=infoLevel, maxLevel=warnLevel)
        L.debug('dbg-block'); L.info('inf-pass')
        L.warn('wrn-pass'); L.error('err-block')
        self.assertFalse(test.contains('dbg-block'))
        self.assertTrue(test.contains('inf-pass'))
        self.assertTrue(test.contains('wrn-pass'))
        self.assertFalse(test.contains('err-block'))

    def test_set_minimum_level_sinks_param(self):
        """set_minimum_level(sinks=['name']) updates the active-sink cache."""
        L, _ = make_logger(logToStdout=False)
        test = _CaptureSink()
        L.add_sink('test', test)
        warnLevel = L.logTypeLevels['warn']
        L.set_minimum_level(warnLevel, stdoutFlag=False, fileFlag=False, sinks=['test'])
        L.info('inf-block'); L.warn('wrn-pass')
        self.assertFalse(test.contains('inf-block'))
        self.assertTrue(test.contains('wrn-pass'))

    def test_set_maximum_level_sinks_param(self):
        L, _ = make_logger(logToStdout=False)
        test = _CaptureSink()
        L.add_sink('test', test)
        infoLevel = L.logTypeLevels['info']
        L.set_maximum_level(infoLevel, stdoutFlag=False, fileFlag=False, sinks=['test'])
        L.warn('wrn-block'); L.info('inf-pass')
        self.assertFalse(test.contains('wrn-block'))
        self.assertTrue(test.contains('inf-pass'))

    def test_combined_stdoutFlag_and_sinks_both_updated(self):
        """When stdoutFlag=True AND sinks=['x'], both sinks must see the new floor."""
        L, bufOut = make_logger()
        test = _CaptureSink()
        L.add_sink('test', test)
        warnLevel = L.logTypeLevels['warn']
        L.set_minimum_level(warnLevel, stdoutFlag=True, fileFlag=False, sinks=['test'])
        L.info('inf-block'); L.warn('wrn-pass')
        self.assertNotIn('inf-block', bufOut.getvalue())
        self.assertFalse(test.contains('inf-block'))
        self.assertIn('wrn-pass',    bufOut.getvalue())
        self.assertTrue(test.contains('wrn-pass'))

    def test_level_constraint_violation_raises(self):
        L, _ = make_logger(logToStdout=False)
        L.add_sink('s', _CaptureSink(), maxLevel=10.0)
        with self.assertRaises(ValueError):
            L.set_minimum_level(20, stdoutFlag=False, fileFlag=False, sinks=['s'])


# ═══════════════════════════════════════════════════════════════════════════
# 11 — __rebuild_active_sinks white-box verification
# ═══════════════════════════════════════════════════════════════════════════

class TestRebuildActiveSinks(unittest.TestCase):
    """
    Accesses _Logger__activeSinks directly (name-mangled) to verify the
    cache structure is correct after configuration changes.

    These tests prove that __rebuild_active_sinks uses the enabled flag,
    logTypeFlags, and minLevel/maxLevel — not just one of the three.
    """

    def _active(self, logger, log_type):
        """Return the list of active _Sink objects for a given log type."""
        return logger._Logger__activeSinks.get(log_type, [])

    def test_disabled_user_sink_absent_from_cache(self):
        L, _ = make_logger(logToStdout=False)
        sink = _CaptureSink()
        L.add_sink('s', sink, enabled=False)
        for lt in L.logTypeLevels:
            self.assertFalse(
                any(s.sinkType == 'user' for s in self._active(L, lt)),
                f'disabled sink appeared in activeSinks for {lt}'
            )

    def test_enabled_user_sink_present_in_cache(self):
        L, _ = make_logger(logToStdout=False)
        L.add_sink('s', _CaptureSink(), enabled=True)
        for lt in L.logTypeLevels:
            types = [s.sinkType for s in self._active(L, lt)]
            self.assertIn('user', types)

    def test_logTypeFlag_false_removes_type_from_cache(self):
        L, _ = make_logger(logToStdout=False)
        L.add_sink('s', _CaptureSink(), logTypeFlags={'debug': False})
        debug_sinks = self._active(L, 'debug')
        self.assertFalse(any(s.sinkType == 'user' for s in debug_sinks))
        info_sinks = self._active(L, 'info')
        self.assertTrue(any(s.sinkType == 'user' for s in info_sinks))

    def test_minLevel_removes_low_types_from_cache(self):
        L, _ = make_logger(logToStdout=False)
        warnLevel = L.logTypeLevels['warn']
        L.add_sink('s', _CaptureSink(), minLevel=warnLevel)
        # debug and info are below warnLevel — must be absent
        for lt in ('debug', 'info'):
            self.assertFalse(
                any(s.sinkType == 'user' for s in self._active(L, lt)),
                f'{lt} (below minLevel) found in activeSinks'
            )
        # warn, error, critical are at-or-above — must be present
        for lt in ('warn', 'error', 'critical'):
            self.assertTrue(
                any(s.sinkType == 'user' for s in self._active(L, lt)),
                f'{lt} (at/above minLevel) missing from activeSinks'
            )

    def test_maxLevel_removes_high_types_from_cache(self):
        L, _ = make_logger(logToStdout=False)
        infoLevel = L.logTypeLevels['info']
        L.add_sink('s', _CaptureSink(), maxLevel=infoLevel)
        for lt in ('warn', 'error', 'critical'):
            self.assertFalse(
                any(s.sinkType == 'user' for s in self._active(L, lt)),
                f'{lt} (above maxLevel) found in activeSinks'
            )
        for lt in ('debug', 'info'):
            self.assertTrue(
                any(s.sinkType == 'user' for s in self._active(L, lt)),
                f'{lt} (at/below maxLevel) missing from activeSinks'
            )

    def test_stdout_sink_enabled_flag_respected(self):
        L, _ = make_logger()
        L.set_log_to_stdout_flag(False)
        for lt in L.logTypeLevels:
            self.assertFalse(
                any(s.sinkType == 'stdout' for s in self._active(L, lt)),
                f'disabled stdout sink appeared in activeSinks for {lt}'
            )

    def test_rebuild_triggered_by_add_and_remove(self):
        L, _ = make_logger(logToStdout=False)
        sink = _CaptureSink()
        L.add_sink('s', sink)
        # after add — user sink must appear
        self.assertTrue(any(s.sinkType == 'user'
                            for s in self._active(L, 'info')))
        L.remove_sink('s')
        # after remove — user sink must be gone
        self.assertFalse(any(s.sinkType == 'user'
                             for s in self._active(L, 'info')))


# ═══════════════════════════════════════════════════════════════════════════
# 12 — User sink independence from global stdout/file flags
# ═══════════════════════════════════════════════════════════════════════════

class TestUserSinkIndependence(unittest.TestCase):

    def test_user_sink_receives_type_suppressed_for_stdout(self):
        L, buf = make_logger()
        L.set_log_type_flags('debug', stdoutFlag=False, fileFlag=False)
        sink = _CaptureSink()
        L.add_sink('s', sink)
        L.debug('stealth')
        self.assertNotIn('stealth', buf.getvalue())
        self.assertTrue(sink.contains('stealth'))

    def test_user_sink_unaffected_by_stdout_minLevel(self):
        L, buf = make_logger()
        warnLevel = L.logTypeLevels['warn']
        L.set_minimum_level(warnLevel, stdoutFlag=True, fileFlag=False)
        sink = _CaptureSink()
        L.add_sink('s', sink)   # no level restriction on this sink
        L.info('info-msg')
        self.assertNotIn('info-msg', buf.getvalue())
        self.assertTrue(sink.contains('info-msg'))


# ═══════════════════════════════════════════════════════════════════════════
# 13 — Sink API validation
# ═══════════════════════════════════════════════════════════════════════════

class TestSinkApiValidation(unittest.TestCase):

    def setUp(self):
        self.L, _ = make_logger()

    def test_non_string_name_raises_TypeError(self):
        with self.assertRaises(TypeError):
            self.L.add_sink(123, _CaptureSink())

    def test_empty_name_raises_ValueError(self):
        with self.assertRaises(ValueError):
            self.L.add_sink('', _CaptureSink())

    def test_handler_without_write_raises_TypeError(self):
        with self.assertRaises(TypeError):
            self.L.add_sink('bad', object())

    def test_non_bool_enabled_raises_TypeError(self):
        with self.assertRaises(TypeError):
            self.L.add_sink('bad', _CaptureSink(), enabled=1)

    def test_non_number_minLevel_raises_TypeError(self):
        with self.assertRaises(TypeError):
            self.L.add_sink('bad', _CaptureSink(), minLevel='low')

    def test_non_dict_logTypeFlags_raises_TypeError(self):
        with self.assertRaises(TypeError):
            self.L.add_sink('bad', _CaptureSink(), logTypeFlags=['debug'])

    def test_remove_builtin_key_raises_ValueError(self):
        with self.assertRaises((ValueError, TypeError)):
            self.L.remove_sink(_SINK_STDOUT)

    def test_set_minimum_level_unknown_sink_raises_ValueError(self):
        with self.assertRaises(ValueError):
            self.L.set_minimum_level(10, stdoutFlag=False,
                                     fileFlag=False, sinks=['ghost'])

    def test_set_minimum_level_integer_in_sinks_raises_TypeError(self):
        with self.assertRaises(TypeError):
            self.L.set_minimum_level(10, stdoutFlag=False,
                                     fileFlag=False, sinks=[42])


# ═══════════════════════════════════════════════════════════════════════════
# 14 — is_enabled
# ═══════════════════════════════════════════════════════════════════════════

class TestIsEnabled(unittest.TestCase):

    def test_true_when_stdout_active(self):
        L, _ = make_logger(logToStdout=True)
        self.assertTrue(L.is_enabled('info'))

    def test_false_when_both_builtins_off(self):
        L, _ = make_logger(logToStdout=False, logToFile=False)
        self.assertFalse(L.is_enabled('info'))

    def test_true_when_only_user_sink_active(self):
        L, _ = make_logger(logToStdout=False, logToFile=False)
        L.add_sink('s', _CaptureSink())
        self.assertTrue(L.is_enabled('info'))

    def test_false_after_user_sink_removed(self):
        L, _ = make_logger(logToStdout=False, logToFile=False)
        L.add_sink('s', _CaptureSink())
        L.remove_sink('s')
        self.assertFalse(L.is_enabled('info'))

    def test_is_enabled_for_stdout_reflects_flag(self):
        L, _ = make_logger(logToStdout=True)
        self.assertTrue(L.is_enabled_for_stdout('info'))
        L.set_log_to_stdout_flag(False)
        self.assertFalse(L.is_enabled_for_stdout('info'))

    def test_is_enabled_for_file_reflects_flag(self):
        tmpBase = tempfile.mktemp(suffix='.log')
        try:
            L = Logger(name='t', logToFile=True, logFile=tmpBase,
                       logToStdout=False, stdout=io.StringIO())
            self.assertTrue(L.is_enabled_for_file('info'))
            L.set_log_to_file_flag(False)
            self.assertFalse(L.is_enabled_for_file('info'))
        finally:
            for f in glob.glob(tmpBase.replace('.log', '') + '*.log'):
                try:
                    os.unlink(f)
                except OSError:
                    pass


# ═══════════════════════════════════════════════════════════════════════════
# 15 — Enqueue mode
# ═══════════════════════════════════════════════════════════════════════════

class TestEnqueue(unittest.TestCase):

    def test_messages_delivered_after_flush(self):
        L, buf = make_logger(enqueue=True)
        L.info('queued')
        L.flush()
        self.assertIn('queued', buf.getvalue())

    def test_user_sink_receives_via_queue(self):
        L, _ = make_logger(logToStdout=False, enqueue=True)
        sink = _CaptureSink()
        L.add_sink('s', sink)
        L.info('enqueued')
        L.flush()
        self.assertTrue(sink.contains('enqueued'))

    def test_concurrent_writes_all_delivered(self):
        """3 threads × 50 messages each must all arrive in every sink."""
        sink = _CaptureSink()
        L, buf = make_logger(enqueue=True)
        L.add_sink('s', sink)
        N_THREADS, N_MSGS = 3, 50
        barrier = threading.Barrier(N_THREADS)

        def worker(tid):
            barrier.wait()
            for i in range(N_MSGS):
                L.info(f'T{tid}-M{i}')

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        L.flush()
        total = N_THREADS * N_MSGS
        stdout_lines = [l for l in buf.getvalue().splitlines() if '<INFO>' in l]
        self.assertEqual(len(stdout_lines), total)
        self.assertEqual(len(sink.lines), total)

    def test_flush_is_callable(self):
        """Logger.flush() drains the queue (or is a no-op for sync loggers).
        It must not raise, and must return None.
        (Note: the @property 'flush' is shadowed by the method definition;
        the callable form is the externally visible API.)
        """
        L, _ = make_logger()
        result = L.flush()
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════════
# 16 — bind()
# ═══════════════════════════════════════════════════════════════════════════

class TestBind(unittest.TestCase):

    def test_bind_adds_context_tag_to_stdout(self):
        L, buf = make_logger()
        L.bind(reqId='abc').info('msg')
        self.assertIn('[reqId=abc]', buf.getvalue())

    def test_bind_adds_context_tag_to_user_sink(self):
        L, _ = make_logger(logToStdout=False)
        sink = _CaptureSink()
        L.add_sink('s', sink)
        L.bind(traceId='xyz').info('msg')
        self.assertTrue(sink.contains('[traceId=xyz]'))

    def test_bind_multiple_keys(self):
        L, buf = make_logger()
        L.bind(a='1', b='2').info('msg')
        out = buf.getvalue()
        self.assertIn('a=1', out)
        self.assertIn('b=2', out)

    def test_bind_does_not_affect_parent(self):
        L, buf = make_logger()
        BL = L.bind(x='val')
        BL.info('ONLY-BOUND-MSG')
        L.info('PARENT-ONLY-MSG')
        out = buf.getvalue()
        # bound call must carry the tag
        bound_line   = next(l for l in out.splitlines() if 'ONLY-BOUND-MSG' in l)
        parent_line  = next(l for l in out.splitlines() if 'PARENT-ONLY-MSG' in l)
        self.assertIn('[x=val]', bound_line)
        self.assertNotIn('[x=val]', parent_line)


# ═══════════════════════════════════════════════════════════════════════════
# 17 — catch()
# ═══════════════════════════════════════════════════════════════════════════

class TestCatch(unittest.TestCase):

    def test_decorator_logs_exception_no_reraise(self):
        L, buf = make_logger()

        @L.catch(logType='error', reraise=False)
        def boom():
            raise RuntimeError('kaboom')

        boom()   # must not propagate
        self.assertIn('kaboom', buf.getvalue())

    def test_decorator_logs_to_user_sink(self):
        L, _ = make_logger(logToStdout=False)
        sink = _CaptureSink()
        L.add_sink('s', sink)

        @L.catch(logType='error', reraise=False)
        def boom():
            raise ValueError('oops')

        boom()
        self.assertTrue(sink.contains('oops'))

    def test_decorator_reraises_when_requested(self):
        L, _ = make_logger()

        @L.catch(logType='error', reraise=True)
        def boom():
            raise KeyError('re-raised')

        with self.assertRaises(KeyError):
            boom()

    def test_context_manager_catches_exception(self):
        L, buf = make_logger()
        with L.catch(logType='error', reraise=False):
            raise TypeError('ctx-exc')
        self.assertIn('ctx-exc', buf.getvalue())

    def test_no_exception_context_manager_clean(self):
        L, buf = make_logger()
        with L.catch(logType='error', reraise=False):
            pass   # no exception — nothing logged
        self.assertNotIn('<ERROR>', buf.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
# 18 — force_log
# ═══════════════════════════════════════════════════════════════════════════

class TestForceLog(unittest.TestCase):

    def test_force_log_ignores_type_suppression(self):
        """force_log routes to stdout even when the type flag is False."""
        L, buf = make_logger()
        L.set_log_type_flags('debug', stdoutFlag=False, fileFlag=False)
        L.force_log('debug', 'forced-debug', stdout=True, file=False)
        self.assertIn('forced-debug', buf.getvalue())

    def test_force_log_does_not_reach_user_sinks(self):
        """By design, force_log bypasses user-added sinks."""
        L, _ = make_logger()
        sink = _CaptureSink()
        L.add_sink('s', sink)
        L.force_log('info', 'force-only', stdout=True, file=False)
        self.assertFalse(sink.contains('force-only'))

    def test_force_log_stdout_false_suppresses_stdout(self):
        L, buf = make_logger()
        L.force_log('info', 'no-show', stdout=False, file=False)
        self.assertNotIn('no-show', buf.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
# 19 — Sanitisation (ANSI stripping, size limits)
# ═══════════════════════════════════════════════════════════════════════════

class TestSanitize(unittest.TestCase):

    def test_ansi_codes_stripped_from_message(self):
        L, buf = make_logger()
        L.info('\x1b[31mred text\x1b[0m')
        out = buf.getvalue()
        # message content should survive; escape sequences should not
        self.assertIn('red text', out)
        # ANSI in output is only from the logger's own colouriser, not the msg
        # verify the raw escape from the message is gone
        self.assertNotIn('\x1b[31m', out)

    def test_maxMessageSize_truncates(self):
        L, buf = make_logger(maxMessageSize=10)
        L.info('A' * 50)
        self.assertIn('[truncated]', buf.getvalue())

    def test_maxMessageSize_does_not_truncate_short(self):
        L, buf = make_logger(maxMessageSize=100)
        L.info('short')
        self.assertNotIn('[truncated]', buf.getvalue())

    def test_maxMessageSize_truncation_in_user_sink(self):
        L, _ = make_logger(logToStdout=False, maxMessageSize=10)
        sink = _CaptureSink()
        L.add_sink('s', sink)
        L.info('B' * 50)
        self.assertTrue(sink.contains('[truncated]'))

    def test_maxDataSize_truncates_data_field(self):
        L, buf = make_logger(maxDataSize=5)
        L.info('msg', data='X' * 50)
        self.assertIn('[truncated]', buf.getvalue())


# ═══════════════════════════════════════════════════════════════════════════
# 20 — parameters property and __str__
# ═══════════════════════════════════════════════════════════════════════════

class TestParametersStr(unittest.TestCase):

    def test_parameters_contains_userSinks_key(self):
        L, _ = make_logger()
        self.assertIn('userSinks', L.parameters)

    def test_parameters_userSinks_empty_with_no_sinks(self):
        L, _ = make_logger()
        self.assertEqual(L.parameters['userSinks'], {})

    def test_parameters_userSinks_reflects_added_sink(self):
        L, _ = make_logger()
        L.add_sink('audit', _CaptureSink(), minLevel=5.0, maxLevel=30.0)
        us = L.parameters['userSinks']
        self.assertIn('audit', us)
        self.assertEqual(us['audit']['minLevel'], 5.0)
        self.assertEqual(us['audit']['maxLevel'], 30.0)
        self.assertEqual(us['audit']['enabled'], True)

    def test_parameters_userSinks_is_snapshot(self):
        """Mutating the returned dict must not affect the live sink."""
        L, _ = make_logger()
        L.add_sink('s', _CaptureSink())
        snap = L.parameters['userSinks']
        snap['s']['enabled'] = False
        self.assertTrue(L._Logger__sinks['s'].enabled)

    def test_str_contains_standard_headers(self):
        """str(L) must include the standard structural headers."""
        L, _ = make_logger()
        out = str(L)
        self.assertIn('Logger', out)
        self.assertIn('Log To Stdout', out)
        self.assertIn('Log To File', out)

    def test_str_contains_log_type_names(self):
        L, _ = make_logger()
        s = str(L)
        for lt in ('info', 'warn', 'error', 'debug', 'critical'):
            self.assertIn(lt, s.lower())

    def test_str_shows_user_sinks_block(self):
        L, _ = make_logger()
        L.add_sink('monitor', _CaptureSink(), minLevel=10.0)
        self.assertIn('User sinks', str(L))
        self.assertIn('monitor', str(L))

    def test_str_omits_user_sinks_block_when_none(self):
        L, _ = make_logger()
        self.assertNotIn('User sinks', str(L))


# ═══════════════════════════════════════════════════════════════════════════
# 21 — flush / _flush_atexit_logfile lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestFlushAtexit(unittest.TestCase):

    def test_atexit_flushes_user_sink(self):
        L, _ = make_logger(logToStdout=False)
        sink = _CaptureSink()
        flushed = []
        original_flush = sink.flush
        sink.flush = lambda: flushed.append(True) or original_flush()
        L.add_sink('s', sink)
        L.info('before-exit')
        L._flush_atexit_logfile()
        self.assertTrue(sink.contains('before-exit'))
        self.assertTrue(flushed, 'flush() was never called on the user sink')

    def test_atexit_does_not_close_user_sink(self):
        """The logger must never close a user-supplied handler."""
        L, _ = make_logger(logToStdout=False)
        sink = _CaptureSink()
        closed = []
        sink.close = lambda: closed.append(True)
        L.add_sink('s', sink)
        L._flush_atexit_logfile()
        self.assertFalse(closed, 'logger closed the user sink — it must not')

    def test_custom_handler_without_fileno_does_not_crash(self):
        """A handler that lacks fileno() must not crash the flush path."""
        L, _ = make_logger(enqueue=True)
        sink = _CaptureSink()  # _CaptureSink has no fileno()
        L.add_sink('s', sink)
        for _ in range(3):
            L.info('msg')
        L.flush()  # must not hang or raise
        self.assertEqual(len(sink.lines), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 22 — Custom log types
# ═══════════════════════════════════════════════════════════════════════════

class TestCustomLogTypes(unittest.TestCase):

    def setUp(self):
        self.L, self.buf = make_logger()

    def test_add_log_type_and_use(self):
        self.L.add_log_type('trace', name='TRACE', level=5,
                            stdoutFlag=True, fileFlag=False)
        self.L.log('trace', 'trace-msg')
        self.assertIn('trace-msg', self.buf.getvalue())

    def test_new_type_routed_to_user_sink(self):
        sink = _CaptureSink()
        self.L.add_sink('s', sink)
        self.L.add_log_type('verbose', name='VERBOSE', level=2,
                            stdoutFlag=True, fileFlag=False)
        self.L.log('verbose', 'verbose-msg')
        self.assertTrue(sink.contains('verbose-msg'))

    def test_remove_log_type_stops_routing(self):
        self.L.add_log_type('tmp', name='TMP', level=7,
                            stdoutFlag=True, fileFlag=False)
        self.L.log('tmp', 'before')
        self.L.remove_log_type('tmp')
        with self.assertRaises(Exception):
            self.L.log('tmp', 'after')
        self.assertNotIn('after', self.buf.getvalue())

    def test_logTypeLevels_ordering(self):
        lvls = self.L.logTypeLevels
        self.assertLess(lvls['debug'], lvls['info'])
        self.assertLess(lvls['info'],  lvls['warn'])
        self.assertLess(lvls['warn'],  lvls['error'])
        self.assertLess(lvls['error'], lvls['critical'])


# ═══════════════════════════════════════════════════════════════════════════
# entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
