"""Runs every test of the package and prints a short summary, the same way on every machine.

Usage::

    python3 tests/run_tests.py                    ## everything, one line for each test
    python3 tests/run_tests.py --quiet            ## only the summary
    python3 tests/run_tests.py --repeat 5         ## five times, to find a test that sometimes fails
    python3 tests/run_tests.py record queues      ## only tests/test_record.py and tests/test_queues.py
    python3 tests/run_tests.py --list             ## the test files

Every test prints one line, ``PASS``, ``FAIL``, ``ERROR`` or ``SKIP`` with the seconds it took and its name, then a summary by
test file, the details of what failed, and the totals. The exit code is 0 when every test passed and 1 otherwise, so a script or
a scheduler can use it.
"""
import argparse
import os
import platform
import sys
import time
import traceback
import unittest

TESTS_FOLDER = os.path.dirname(os.path.abspath(__file__))


def find_test_files():
    """Returns the names of the test modules, without the ``test_`` prefix, in alphabetical order."""
    return sorted(name[5:-3] for name in os.listdir(TESTS_FOLDER) if name.startswith('test_') and name.endswith('.py'))


def load_suite(names):
    """Returns one suite with the tests of the named modules."""
    loader = unittest.TestLoader()
    sys.path.insert(0, TESTS_FOLDER)
    suite = unittest.TestSuite()
    for name in names:
        suite.addTests(loader.loadTestsFromName(f'test_{name}'))
    return suite


class LineResult(unittest.TestResult):
    """
    A test result that prints one line for each test, and keeps what every test did for the summary.

    The output of a test is held back while it runs, and shown with the details of a test that failed.

    :Parameters:
        #. isQuiet (bool): True to print no line for the tests, only the summary at the end.
    """

    def __init__(self, isQuiet):
        super().__init__()
        self.buffer = True
        self.isQuiet = isQuiet
        self.outcomes = []
        self.__started = 0.0

    def startTest(self, test):
        """Remembers when a test started."""
        super().startTest(test)
        self.__started = time.monotonic()

    @staticmethod
    def _last_line(err):
        """Returns the last line of an exception, such as ``AssertionError: 1 != 2``, cut to one line."""
        return traceback.format_exception_only(err[0], err[1])[-1].strip()[:160]

    def _record(self, name, outcome, detail=''):
        """Keeps the outcome of a test and prints its line, straight to the terminal because the test holds back its own output."""
        seconds = time.monotonic() - self.__started
        self.outcomes.append((name, outcome, seconds))
        if not self.isQuiet:
            sys.__stdout__.write(f"{outcome:5s} {seconds:7.3f}s  {name}{'  (' + detail + ')' if detail else ''}\n")
            sys.__stdout__.flush()

    def addSuccess(self, test):
        """Prints PASS for a test."""
        super().addSuccess(test)
        self._record(test.id(), 'PASS')

    def addFailure(self, test, err):
        """Prints FAIL and the last line of the traceback for a test."""
        super().addFailure(test, err)
        self._record(test.id(), 'FAIL', self._last_line(err))

    def addError(self, test, err):
        """Prints ERROR and the last line of the traceback for a test."""
        super().addError(test, err)
        self._record(test.id(), 'ERROR', self._last_line(err))

    def addSkip(self, test, reason):
        """Prints SKIP and the reason for a test."""
        super().addSkip(test, reason)
        self._record(test.id(), 'SKIP', reason)

    def addExpectedFailure(self, test, err):
        """Prints PASS for a test that is expected to fail and does."""
        super().addExpectedFailure(test, err)
        self._record(test.id(), 'PASS', 'expected failure')

    def addUnexpectedSuccess(self, test):
        """Prints FAIL for a test that is expected to fail and passes."""
        super().addUnexpectedSuccess(test)
        self._record(test.id(), 'FAIL', 'unexpected success')

    def addSubTest(self, test, subtest, err):
        """Prints a line for each failing part of a test that uses subTest, a part that passes has no line of its own."""
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._record(subtest.id(), 'FAIL' if issubclass(err[0], test.failureException) else 'ERROR', self._last_line(err))


def print_summary(result):
    """Prints the results by test file, the names of what failed, their details, and the skipped tests."""
    byFile = {}
    for name, outcome, taken in result.outcomes:
        counts = byFile.setdefault(name.split('.')[0], {'PASS': 0, 'FAIL': 0, 'ERROR': 0, 'SKIP': 0, 'seconds': 0.0})
        counts[outcome] += 1
        counts['seconds'] += taken
    print(f"\n{'test file':32s} {'passed':>7s} {'failed':>7s} {'errors':>7s} {'skipped':>8s} {'seconds':>8s}")
    for fileName in sorted(byFile):
        counts = byFile[fileName]
        print(f"{fileName:32s} {counts['PASS']:7d} {counts['FAIL']:7d} {counts['ERROR']:7d} {counts['SKIP']:8d} {counts['seconds']:8.1f}")
    failed = [(name, outcome) for name, outcome, _ in result.outcomes if outcome in ('FAIL', 'ERROR')]
    if len(failed) > 0:
        print('\nfailed tests:')
        for name, outcome in failed:
            print(f"  {outcome:5s} {name}")
    for kind, entries in (('FAILURES', result.failures), ('ERRORS', result.errors)):
        for test, details in entries:
            print(f"\n{'=' * 70}\n{kind[:-1]}: {test}\n{'-' * 70}\n{details.rstrip()}")
    for test, reason in result.skipped:
        print(f"skipped {test.id()}: {reason}")


def run_once(names, isQuiet):
    """Runs the tests once, prints a line for each and the summary, and returns the result and the seconds it took."""
    started = time.monotonic()
    result = LineResult(isQuiet)
    load_suite(names).run(result)
    seconds = time.monotonic() - started
    print_summary(result)
    return result, seconds


def main():
    """Parses the command line, runs the tests and returns the exit code."""
    parser = argparse.ArgumentParser(description='Run the tests of pysimplelog.')
    parser.add_argument('names', nargs='*', help='test files to run, without test_ and .py, all when none is given')
    parser.add_argument('--repeat', type=int, default=1, help='number of times to run, to find tests that fail sometimes')
    parser.add_argument('--list', action='store_true', help='print the test files and stop')
    parser.add_argument('--quiet', action='store_true', help='print only the summary, not a line for each test')
    arguments = parser.parse_args()
    available = find_test_files()
    if arguments.list:
        print('\n'.join(available))
        return 0
    unknown = [name for name in arguments.names if name not in available]
    if len(unknown) > 0:
        print(f"unknown test files: {', '.join(unknown)}. Available: {', '.join(available)}")
        return 2
    if arguments.repeat < 1:
        print('--repeat must be at least 1')
        return 2
    names = arguments.names if len(arguments.names) > 0 else available
    print(f"Python {platform.python_version()} on {platform.system()} {platform.release()} ({platform.machine()})")
    failedRuns = 0
    for number in range(1, arguments.repeat + 1):
        result, seconds = run_once(names, arguments.quiet)
        isGood = result.wasSuccessful()
        failedRuns += 0 if isGood else 1
        print(f"run {number}/{arguments.repeat}: {result.testsRun} tests in {seconds:.1f}s, "
              f"{len(result.failures)} failed, {len(result.errors)} errors, {len(result.skipped)} skipped "
              f"-> {'PASS' if isGood else 'FAIL'}")
    print(f"{'ALL RUNS PASSED' if failedRuns == 0 else f'{failedRuns} RUN(S) FAILED'}")
    return 0 if failedRuns == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
