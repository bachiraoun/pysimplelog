"""
Checks the OTLP encoder and transport against a REAL OpenTelemetry Collector, in a throwaway Docker container.

It starts the official image with an OTLP/HTTP receiver and a ``debug`` exporter that prints everything it receives, sends records
through the encoder and the transport, reads what the container printed, and removes the container. It needs Docker running, a free
port 4318 on this machine, and one download of the image the first time (about 130 MB). Nothing in it is part of the test suite.

Run directly::

    python3 examples/12_real_collector_check.py
"""
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from pysimplelog.contrib.otlp_encoder import OtlpLogEncoder
from pysimplelog.contrib.otlp_transport import OtlpHttpTransport
from pysimplelog.record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo

NAME = 'pysimplelog-otel-check'
IMAGE = 'otel/opentelemetry-collector:latest'
PORT = 4318
CONFIG = """receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    logs:
      receivers: [otlp]
      exporters: [debug]
"""
# What must appear in what the collector printed
EXPECTED = ('checked by a real collector 0', 'orders-check', 'order_id', 'exception.type', 'code.function.name', 'log.record.uid',
            '0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 'SeverityNumber: Error(17)', 'telemetry.sdk.language')


def docker(*arguments, timeout=300):
    """Runs a docker command and returns the finished process."""
    return subprocess.run(['docker', *arguments], capture_output=True, text=True, timeout=timeout)


def docker_is_running():
    """True when the docker command exists and its engine answers."""
    try:
        return docker('info', '--format', '{{.ServerVersion}}', timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def make_records():
    """Three records with everything a record can carry."""
    return [LogRecord.create(
        datetime(2026, 10, 6, 18, 31, 52, 123456, tzinfo=timezone.utc), 'ERROR', 'error', 30.0, 'orders',
        f'checked by a real collector {number}', 4321, 7, 'worker-3',
        fields={'order_id': number, 'ratio': 2.5, 'tags': ['a', 'b'], 'event_id': f'slot-{number}'}, context={'service': 'checkout'},
        exception=ExceptionInfo('ConnectionError', 'timed out', 'Traceback...'), caller=CallerInfo('db.py', 9, 'connect', 'orders.db'),
        trace=TraceInfo('0af7651916cd43dd8448eb211c80319c', 'b7ad6b7169203331', 1)) for number in range(3)]


def main():
    """Runs the check and returns the exit code: 0 when everything was found, 1 when something is missing, 2 when it cannot run."""
    if not docker_is_running():
        print("Docker is not running. Start Docker Desktop (or the docker service) and run this again.")
        return 2
    folder = tempfile.mkdtemp(prefix='otelcheck-')
    configPath = os.path.join(folder, 'config.yaml')
    with open(configPath, 'w') as stream:
        stream.write(CONFIG)
    docker('rm', '-f', NAME)
    print(f"starting {IMAGE} (the first time it is downloaded)...")
    started = docker('run', '-d', '--rm', '--name', NAME, '-p', f'127.0.0.1:{PORT}:4318', '-v', f'{configPath}:/etc/otelcol/config.yaml:ro',
                     IMAGE, '--config', '/etc/otelcol/config.yaml', timeout=900)
    if started.returncode != 0:
        print("the container did not start:", (started.stderr or started.stdout).strip()[:300])
        return 2
    try:
        time.sleep(4)
        encoder = OtlpLogEncoder(resource={'service.name': 'orders-check', 'deployment.environment': 'test'})
        body = encoder.encode(make_records(), time.time_ns())
        for compress in (False, True):
            transport = OtlpHttpTransport(f'http://127.0.0.1:{PORT}', compress=compress)
            print(f"compress={compress!s:5} ->", transport.send(body))
            transport.close()
        print("a body the collector cannot read ->", OtlpHttpTransport(f'http://127.0.0.1:{PORT}').send(b'{"resourceLogs": 5}'))
        print("a wrong path ->", OtlpHttpTransport(f'http://127.0.0.1:{PORT}/nowhere').send(b'{}'))
        time.sleep(2)
        output = docker('logs', NAME)
        printed = output.stderr + output.stdout
        missing = [text for text in EXPECTED if text not in printed]
        for text in EXPECTED:
            print(f"  {'found  ' if text not in missing else 'MISSING'} {text}")
        start = printed.find('LogRecord #0')
        print("\nthe first record, as the collector printed it:\n" + printed[start:start + 1400])
        return 1 if missing else 0
    finally:
        docker('rm', '-f', NAME)


if __name__ == '__main__':
    sys.exit(main())
