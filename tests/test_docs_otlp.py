"""Tests that keep the documentation, the README and the examples of the OpenTelemetry sink true.

The page of the documentation shows a request, and it must be what the encoder writes. The names of the settings must be explained, the
numbers the sink counts must be named, the code blocks must at least parse, and the example that runs on its own must run.

Run from the repo root::

    python3 -m unittest tests.test_docs_otlp -v
"""
import ast
import inspect
import json
import os
import re
import subprocess
import sys
import textwrap
import unittest
from datetime import datetime, timezone

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from __pkginfo__ import __version__  # noqa: E402
from contrib import otlp_encoder, otlp_sink, otlp_transport  # noqa: E402
from contrib.otlp_encoder import OtlpLogEncoder  # noqa: E402
from contrib.otlp_sink import OtlpLogSink, attach  # noqa: E402
from record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo  # noqa: E402

DOCUMENTATION = os.path.join(PACKAGE_DIR, 'docs', 'source', 'getting_started.rst')
API_REFERENCE = os.path.join(PACKAGE_DIR, 'docs', 'source', 'api_reference.rst')
README = os.path.join(PACKAGE_DIR, 'README.md')
EXAMPLES = os.path.join(PACKAGE_DIR, 'examples')
OBSERVED = 1790000000000000000


def read(path):
    with open(path, encoding='utf-8') as stream:
        return stream.read()


def section_of_the_page():
    """The text of the page from its OpenTelemetry heading to the next heading of the same level."""
    text = read(DOCUMENTATION)
    start = text.index('OpenTelemetry logs (OTLP)\n---')
    end = text.index('API stability\n---')
    return text[start:end]


def documented_record():
    """The record whose request the page shows."""
    return LogRecord.create(
        timestamp=datetime(2026, 10, 6, 18, 31, 52, 123456, tzinfo=timezone.utc), severity='ERROR', logType='error', level=30.0,
        logger='orders', message='Payment failed', processId=4321, threadId=140234, threadName='worker-3',
        fields={'order_id': 123, 'amount': 12.5, 'event_id': 'slot-7'}, context={'request_id': 'r-77'},
        exception=ExceptionInfo('PaymentError', 'card declined',
                                'Traceback (most recent call last):\n  File "billing.py", line 42, in charge\nPaymentError: card declined'),
        caller=CallerInfo('billing.py', 42, 'charge', 'orders.billing'),
        trace=TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1))


@unittest.skipUnless(os.path.isfile(DOCUMENTATION), 'the documentation is not installed')
class TestThePage(unittest.TestCase):

    def test_the_request_on_the_page_is_what_the_encoder_writes(self):
        section = section_of_the_page()
        block = section.split('.. otlp-example-start')[1].split('.. otlp-example-end')[0]
        code = block.split('.. code-block:: json')[1]
        shown = json.loads(textwrap.dedent(code))
        encoder = OtlpLogEncoder(resource={'service.name': 'orders', 'deployment.environment': 'production'})
        expected = encoder.encode_request([documented_record()], OBSERVED)
        # The page was written for one version, and the version is the only thing that changes with the release
        text = json.dumps(shown).replace('"6.0.0"', f'"{__version__}"')
        self.assertEqual(json.loads(text), expected)

    def test_every_python_block_of_the_section_parses(self):
        section = section_of_the_page()
        blocks = re.findall(r'\.\. code-block:: python\n\n((?:    .*\n|\n)+)', section)
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            ast.parse(textwrap.dedent(block))

    def test_the_names_the_page_imports_exist(self):
        import importlib
        import simple_log
        section = section_of_the_page()
        found = re.findall(r'from (pysimplelog[\w.]*) import (\w+)', section)
        self.assertGreaterEqual(len(found), 2)
        for module, name in found:
            # The package is imported by its flat names here, because the tests run from the folder of the package
            flat = module[len('pysimplelog'):].lstrip('.')
            target = importlib.import_module(flat) if flat else simple_log
            self.assertTrue(hasattr(target, name), f"{module}.{name}")

    def test_every_number_the_sink_counts_is_named_on_the_page(self):
        section = section_of_the_page()
        stats = OtlpLogSink('http://127.0.0.1:1', captureTrace=False).stats
        for name in stats:
            if name in ('last_error', 'latency_mean', 'latency_max'):
                continue
            self.assertIn(f'``{name}``', section, name)

    def test_the_settings_the_page_names_exist(self):
        section = section_of_the_page()
        parameters = set(inspect.signature(OtlpLogSink.__init__).parameters)
        for name in re.findall(r'``(\w+)=', section) + re.findall(r'``(batchSize|batchInterval|maxRetries|captureTrace|eventIdField|maxAttempts)``', section):
            self.assertTrue(name in parameters or name in ('maxAttempts', 'spool', 'threaded', 'callerInfo'), name)

    def test_the_defaults_the_page_states_are_the_real_ones(self):
        section = section_of_the_page()
        sink = OtlpLogSink('http://127.0.0.1:1', captureTrace=False)
        self.assertEqual((sink.batchSize, sink.batchInterval), (512, 1.0))
        self.assertIn('``batchSize`` (512)', section)
        self.assertIn('``batchInterval`` (1 second)', section)
        self.assertIn('``maxRetries`` times (2)', section)
        self.assertEqual(inspect.signature(OtlpLogSink.__init__).parameters['maxRetries'].default, 2)

    def test_the_status_codes_the_page_states_are_the_ones_the_transport_uses(self):
        section = section_of_the_page()
        for status in sorted(otlp_transport.RETRYABLE_STATUS | otlp_transport.REFUSED_STATUS):
            self.assertIn(str(status), section, status)

    def test_the_page_says_what_is_not_supported(self):
        section = section_of_the_page()
        for word in ('metrics', 'traces', 'gRPC', 'protobuf'):
            self.assertIn(word, section)

    def test_the_section_is_in_the_page_once(self):
        self.assertEqual(read(DOCUMENTATION).count('OpenTelemetry logs (OTLP)\n---'), 1)


@unittest.skipUnless(os.path.isfile(API_REFERENCE), 'the documentation is not installed')
class TestTheReference(unittest.TestCase):

    def test_the_new_modules_are_in_the_reference(self):
        text = read(API_REFERENCE)
        for module in ('pysimplelog.contrib.otlp_sink', 'pysimplelog.contrib.otlp_encoder', 'pysimplelog.contrib.otlp_transport',
                       'pysimplelog.tracing'):
            self.assertIn(f'.. automodule:: {module}', text, module)


class TestDocstrings(unittest.TestCase):
    """The reference is made from the docstrings, so every parameter of what a user calls must be explained there."""

    def _check(self, target, docstring):
        for name in inspect.signature(target).parameters:
            if name in ('self', 'kwargs', 'sinkKwargs'):
                continue
            self.assertRegex(docstring, rf'#\. {name} \(', f"{target.__qualname__}: {name}")

    def test_the_sink(self):
        self._check(OtlpLogSink.__init__, inspect.getdoc(OtlpLogSink))

    def test_the_encoder(self):
        self._check(OtlpLogEncoder.__init__, inspect.getdoc(OtlpLogEncoder))

    def test_the_transport(self):
        self._check(otlp_transport.OtlpHttpTransport.__init__, inspect.getdoc(otlp_transport.OtlpHttpTransport))

    def test_attach(self):
        self._check(attach, inspect.getdoc(attach))

    def test_the_functions_and_methods_have_a_docstring(self):
        for module in (otlp_sink, otlp_encoder, otlp_transport):
            self.assertTrue(inspect.getdoc(module), module.__name__)
            for name, member in vars(module).items():
                if name.startswith('_') or getattr(member, '__module__', None) != module.__name__:
                    continue
                if inspect.isclass(member):
                    self.assertTrue(inspect.getdoc(member), f"{module.__name__}.{name}")
                    for method, function in vars(member).items():
                        if not method.startswith('_') and (inspect.isfunction(function) or isinstance(function, (property, staticmethod))):
                            self.assertTrue(inspect.getdoc(function), f"{module.__name__}.{name}.{method}")
                elif inspect.isfunction(member):
                    self.assertTrue(inspect.getdoc(member), f"{module.__name__}.{name}")


@unittest.skipUnless(os.path.isfile(README), 'the README is not installed')
class TestTheReadme(unittest.TestCase):

    def test_it_presents_the_sink_and_the_examples_it_names_exist(self):
        text = read(README)
        self.assertIn('OpenTelemetry logs', text)
        self.assertIn('otlp_sink.attach', text)
        for name in re.findall(r'examples/(\d\d_\w+\.py)', text):
            self.assertTrue(os.path.isfile(os.path.join(EXAMPLES, name)), name)

    def test_the_documentation_names_the_examples_that_exist(self):
        for text in (read(DOCUMENTATION), read(API_REFERENCE)):
            for name in re.findall(r'examples/(\d\d_\w+\.py)', text):
                self.assertTrue(os.path.isfile(os.path.join(EXAMPLES, name)), name)


@unittest.skipUnless(os.path.isdir(EXAMPLES), 'the examples are not installed')
class TestTheExamples(unittest.TestCase):

    def _run(self, name, timeout=120):
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.dirname(PACKAGE_DIR), os.environ.get('PYTHONPATH', '')]))
        return subprocess.run([sys.executable, os.path.join(EXAMPLES, name)], capture_output=True, text=True, timeout=timeout, env=environment)

    @unittest.skipUnless(os.path.basename(PACKAGE_DIR) == 'pysimplelog', 'the examples import the installed package name')
    def test_the_example_that_runs_on_its_own_runs(self):
        completed = self._run('11_opentelemetry_logs.py')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = completed.stdout
        self.assertIn('the receiver got 2 records, from orders (example)', output)
        self.assertIn("'Order created'", output)
        self.assertIn('request_id=r-77', output)
        self.assertIn('the error carries ValueError: card declined', output)
        self.assertRegex(output, r"it is back: \['while it was down 1', 'while it was down 2', 'while it was down 3'\]")
        self.assertRegex(output, r'sent 5 records in 2 requests')
        self.assertRegex(output, r'0 waiting')
        # The outage was real: the sends failed and the sink said so once
        self.assertRegex(output, r'[1-9]\d* sends failed so far')
        self.assertEqual(completed.stderr.count('WARNING'), 1, completed.stderr)

    def test_the_example_that_needs_docker_says_so_when_there_is_no_engine(self):
        # It must end with code 2 and a message and not with a traceback. The engine is replaced here, docker is never called
        import importlib.util
        import io
        import contextlib
        from unittest import mock
        specification = importlib.util.spec_from_file_location('real_collector_check', os.path.join(EXAMPLES, '12_real_collector_check.py'))
        module = importlib.util.module_from_spec(specification)
        environment = {'PYTHONPATH': os.pathsep.join([os.path.dirname(PACKAGE_DIR), os.environ.get('PYTHONPATH', '')])}
        with mock.patch.dict(os.environ, environment), mock.patch.dict(sys.modules, {}):
            try:
                specification.loader.exec_module(module)
            except ImportError:
                self.skipTest('the package is not importable under the name pysimplelog')
        output = io.StringIO()
        with mock.patch.object(module, 'docker_is_running', return_value=False), mock.patch.object(module, 'docker') as docker:
            with contextlib.redirect_stdout(output):
                code = module.main()
        self.assertEqual(code, 2)
        self.assertIn('Docker is not running', output.getvalue())
        docker.assert_not_called()

    def test_the_two_new_examples_and_the_benchmark_parse(self):
        for path in (os.path.join(EXAMPLES, '11_opentelemetry_logs.py'), os.path.join(EXAMPLES, '12_real_collector_check.py'),
                     os.path.join(PACKAGE_DIR, 'benchmarks', 'bench_otlp.py')):
            ast.parse(read(path))


if __name__ == '__main__':
    unittest.main()
