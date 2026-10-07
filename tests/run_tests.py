"""Runs every test of the package and prints a short summary, the same way on every machine.

Usage::

    python3 tests/run_tests.py                    ## everything
    python3 tests/run_tests.py --repeat 5         ## five times, to find a test that sometimes fails
    python3 tests/run_tests.py record queues      ## only tests/test_record.py and tests/test_queues.py
    python3 tests/run_tests.py --list             ## the test files

The exit code is 0 when every test passed and 1 otherwise, so a script or a scheduler can use it.
"""
import argparse
import os
import platform
import sys
import time
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


def run_once(names, isVerbose):
    """Runs the tests once and returns the result."""
    runner = unittest.TextTestRunner(verbosity=2 if isVerbose else 1, stream=sys.stderr, buffer=True)
    return runner.run(load_suite(names))


def main():
    """Parses the command line, runs the tests and returns the exit code."""
    parser = argparse.ArgumentParser(description='Run the tests of pysimplelog.')
    parser.add_argument('names', nargs='*', help='test files to run, without test_ and .py, all when none is given')
    parser.add_argument('--repeat', type=int, default=1, help='number of times to run, to find tests that fail sometimes')
    parser.add_argument('--list', action='store_true', help='print the test files and stop')
    parser.add_argument('--verbose', action='store_true', help='print every test')
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
        started = time.monotonic()
        result = run_once(names, arguments.verbose)
        seconds = time.monotonic() - started
        isGood = result.wasSuccessful()
        failedRuns += 0 if isGood else 1
        print(f"run {number}/{arguments.repeat}: {result.testsRun} tests in {seconds:.1f}s, "
              f"{len(result.failures)} failed, {len(result.errors)} errors, {len(result.skipped)} skipped "
              f"-> {'PASS' if isGood else 'FAIL'}")
        for test, reason in result.skipped:
            print(f"  skipped {test.id()}: {reason}")
    print(f"{'ALL RUNS PASSED' if failedRuns == 0 else f'{failedRuns} RUN(S) FAILED'}")
    return 0 if failedRuns == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
