"""Runs the examples that need no network, so that they cannot go stale when the library changes.

Run from the repo root::

    python3 -m unittest tests.test_examples -v

Each example runs in a process of its own, in an empty folder, and must end without an error and print what it is about.
"""
import os
import subprocess
import sys
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EXAMPLES_DIR = os.path.join(PACKAGE_DIR, 'examples')
# The examples import the package by its name, so the folder that holds it must be on the path
PARENT_DIR = os.path.dirname(PACKAGE_DIR)
PACKAGE_IS_NAMED = os.path.basename(PACKAGE_DIR) == 'pysimplelog'

# Each example, with the text it must print and the text it must not
EXPECTED = {
    '01_basic_logging.py': (['basic-example'], []),
    '02_siem_console.py': (['<'], []),
    '08_standard_logging.py': (['standard-logging-example'], []),
    '09_context.py': (['request_id'], []),
    '13_hello_world.py': (['Application started', 'Disk is 91% full', 'User 7 logged in'], []),
    '14_files_and_rotation.py': (['errors.jsonl', 'app_'], []),
    '15_opt_lazy_depth.py': (['calls after the debug call: 0', 'calls after the info call:  1',
                              'in application_code something happened', 'Calculation failed'], []),
    '16_exceptions_and_diagnose.py': (['password = <redacted>', 'amount = 19.9', 'direct cause', 'RuntimeError: payment failed'],
                                      ['hunter2']),
    '17_redaction.py': (['password=[REDACTED]', 'admin:[REDACTED]@', 'hmac:'], ['hunter2', 'pw123', 'sk-live-123']),
    '18_namespaces_and_environment.py': (['visible again', 'written as JSON', 'the argument wins'], ['silenced', 'not written']),
    '19_force_log.py': (['Shutting down', 'Audit trail broken'], ['nobody sees this', 'not written']),
    '20_many_processes.py': (['300 records, every line complete JSON'], ['in order: False']),
}


@unittest.skipUnless(PACKAGE_IS_NAMED, "the examples import the package by its name, so its folder must be called pysimplelog")
class TestExamples(unittest.TestCase):

    def run_example(self, fileName):
        environment = dict(os.environ)
        environment['PYTHONPATH'] = PARENT_DIR + os.pathsep + environment.get('PYTHONPATH', '')
        for name in ('PYSIMPLELOG_LEVEL', 'PYSIMPLELOG_FORMAT', 'PYSIMPLELOG_COLOR', 'PYSIMPLELOG_NAMESPACE_DISABLE'):
            environment.pop(name, None)
        with tempfile.TemporaryDirectory() as folder:
            try:
                return subprocess.run([sys.executable, os.path.join(EXAMPLES_DIR, fileName)], cwd=folder, env=environment,
                                      capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                self.fail(f"{fileName} did not end in 120 seconds")

    def test_every_example_runs_and_prints_what_it_is_about(self):
        for fileName, (expected, forbidden) in sorted(EXPECTED.items()):
            with self.subTest(example=fileName):
                done = self.run_example(fileName)
                self.assertEqual(done.returncode, 0, done.stderr)
                for text in expected:
                    self.assertIn(text, done.stdout + done.stderr)
                for text in forbidden:
                    self.assertNotIn(text, done.stdout + done.stderr)

    def test_every_example_file_is_listed_here(self):
        # A new example must be added to EXPECTED, or to the ones below that are not run here (a network, a local
        # server or a long run), so that none is forgotten
        listed = set(EXPECTED) | {'03_siem_udp.py', '04_siem_tcp.py', '05_siem_http.py', '06_admin_error_catch_siem.py',
                                  '07_processors.py', '10_durable_delivery.py', '11_opentelemetry_logs.py',
                                  '12_real_collector_check.py'}
        found = {name for name in os.listdir(EXAMPLES_DIR) if name.endswith('.py')}
        self.assertEqual(found - listed, set(), "examples that are not in the test")


if __name__ == '__main__':
    unittest.main()
