"""
Measures the OTLP sink: what a log call costs the thread that makes it, and how many records a second reach a receiver.

The receiver is a small program in a process of its own that reads and counts the requests and keeps nothing, so that it does not share
the interpreter of the program it measures. It runs on this machine, so there is no network delay: the numbers show what the library
costs and not what a distant collector will give. They belong to the machine they are measured on.

Run directly::

    python3 pysimplelog/benchmarks/bench_otlp.py
    python3 pysimplelog/benchmarks/bench_otlp.py --count 50000 --mode rate
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import timeit

from pysimplelog import Logger, Sink
from pysimplelog.contrib.otlp_sink import attach

RECEIVER = r'''
import gzip, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
count = {'requests': 0, 'records': 0, 'bytes': 0}
lock = threading.Lock()
class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        body = gzip.decompress(raw) if self.headers.get('Content-Encoding') == 'gzip' else raw
        with lock:
            count['requests'] += 1
            count['records'] += body.count(b'"timeUnixNano"')
            count['bytes'] += len(raw)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'{}')
    def log_message(self, *arguments):
        pass
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
server.daemon_threads = True
threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True).start()
print(server.server_address[1], flush=True)
for line in sys.stdin:
    if line.strip() == 'count':
        with lock:
            print(count['requests'], count['records'], count['bytes'], flush=True)
'''


class Receiver:
    """A receiver in a process of its own, and the counts it keeps."""

    def __init__(self):
        self.process = subprocess.Popen([sys.executable, '-c', RECEIVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.port = int(self.process.stdout.readline())

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def counts(self):
        """Returns the number of requests, of records and of bytes the receiver got."""
        self.process.stdin.write('count\n')
        self.process.stdin.flush()
        return tuple(int(number) for number in self.process.stdout.readline().split())

    def stop(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)


class Nothing(Sink):
    """A sink that does nothing, to measure the cost of a threaded sink alone."""

    def __init__(self):
        super().__init__(formatter=lambda record: '')

    def write(self, text, record):
        pass


def spool_settings(folder):
    """The settings of a spool that does not flush, so that the disk is not what is measured."""
    return dict(path=folder, id='bench', maxBytes=2 * 10 ** 9, totalMaxBytes=4 * 10 ** 9, flush='none')


def call_cost(make):
    """Returns the microseconds a log call takes in the calling thread, for a logger made by *make*."""
    logger, cleanup = make()
    try:
        return min(timeit.repeat(lambda: logger.info('hello', order_id=5, ratio=1.5), number=3000, repeat=5)) / 3000 * 1e6
    finally:
        logger.clear_sinks(timeout=60)
        cleanup()


def plain_threaded():
    logger = Logger('bench', logToFile=False, logToStdout=False)
    logger.add_sink('nothing', Nothing(), threaded=True, threadQueuePolicy='drop_oldest', threadQueueSize=10 ** 6)
    return logger, lambda: None


def otlp(isSpooled):
    def make():
        receiver, folder = Receiver(), tempfile.mkdtemp(prefix='otlpbench-')
        logger = Logger('bench', logToFile=False, logToStdout=False)
        attach(logger, receiver.url, captureTrace=False, threadQueueSize=10 ** 6, threadQueuePolicy='drop_oldest',
               spool=spool_settings(folder) if isSpooled else None)

        def cleanup():
            receiver.stop()
            shutil.rmtree(folder, ignore_errors=True)
        return logger, cleanup
    return make


def rate(count, compress, isSpooled):
    """Logs *count* records and waits for the receiver to have them. Returns the seconds to log, the seconds in all, and the counts."""
    receiver, folder = Receiver(), tempfile.mkdtemp(prefix='otlpbench-')
    logger = Logger('bench', logToFile=False, logToStdout=False)
    attach(logger, receiver.url, captureTrace=False, compress=compress, resource={'service.name': 'bench'},
           spool=spool_settings(folder) if isSpooled else None, threadQueueSize=count + 10, threadQueuePolicy='block')
    started = time.perf_counter()
    for number in range(count):
        logger.info('order created', order_id=number, ratio=1.5)
    logged = time.perf_counter() - started
    logger.flush(timeout=600)
    total = time.perf_counter() - started
    counts = receiver.counts()
    logger.clear_sinks(timeout=30)
    receiver.stop()
    shutil.rmtree(folder, ignore_errors=True)
    return logged, total, counts


def main():
    """Parses the command line and prints the numbers."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--count', type=int, default=20000, help='records sent in the rate measurement')
    parser.add_argument('--mode', choices=('all', 'cost', 'rate'), default='all')
    arguments = parser.parse_args()
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    if arguments.mode in ('all', 'cost'):
        print(f"logging call, a threaded sink that does nothing: {call_cost(plain_threaded):6.1f} us")
        print(f"logging call, OTLP sink                        : {call_cost(otlp(False)):6.1f} us")
        print(f"logging call, OTLP sink with a spool           : {call_cost(otlp(True)):6.1f} us")
    if arguments.mode in ('all', 'rate'):
        for compress in (False, True):
            for isSpooled in (False, True):
                logged, total, (requests, records, size) = rate(arguments.count, compress, isSpooled)
                print(f"compress={compress!s:5} spool={isSpooled!s:5}: {arguments.count} records logged in {logged:5.2f} s, all received after "
                      f"{total:5.2f} s ({arguments.count / total:7.0f} records/s), {requests} requests, {records} records, "
                      f"{size / 1024:.0f} KiB on the wire")


if __name__ == '__main__':
    main()
