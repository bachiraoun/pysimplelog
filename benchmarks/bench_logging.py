"""
Cost of one log call, for pysimplelog next to the standard ``logging`` module, Loguru and structlog.

Run it from the folder that holds the ``pysimplelog`` package::

    python3 pysimplelog/benchmarks/bench_logging.py
    python3 pysimplelog/benchmarks/bench_logging.py --count 50000 --repeats 7
    python3 pysimplelog/benchmarks/bench_logging.py --only spool

Loguru and structlog are used when they are installed and skipped when they are not. Nothing is installed by this script.

What is measured, and what is not
---------------------------------
Each case logs the same message with two fields, ``count`` times, ``repeats`` times, and reports the time the calling thread
spends in the log call, in microseconds: the median of the repeats and the best one. Files are written in a temporary folder
that is deleted afterwards.

* Flushing counts. The standard module and pysimplelog hand each record to the operating system as it is written, which
  is the safe way and costs about 11 microseconds. structlog writes to a buffered file and does not. The cases marked
  ``no flush`` turn it off, to compare like with like. Check what a library does before comparing it with another.
* The cases differ in what they do. A JSON line, a text line, a record written to a spool and a record sent to a thread are
  different amounts of work, so compare a case with the one that does the same, not the fastest with the slowest.
* Only the calling thread is timed. The work that a background thread does afterwards is not in the number, and the time
  to finish it is printed for the cases that have one.
* The numbers belong to the machine, the Python version and the load they were measured under. Run it on yours.
"""
import argparse
import logging
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import pysimplelog  # noqa: E402
from pysimplelog import Logger, Sink, FileSink  # noqa: E402

try:
    import loguru
except ImportError:
    loguru = None
try:
    import structlog
except ImportError:
    structlog = None


class Destination(Sink):
    """A sink that goes nowhere, to measure the cost of a thread and of a spool without the cost of a receiver."""
    SPOOL_DESTINATION = ('host',)
    host = 'benchmark'

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)

    def write(self, text, record):
        pass


class Case:
    """
    One thing to measure.

    :Parameters:
        #. name (str): What it is called in the table.
        #. group (str): The family it belongs to, for ``--only``.
        #. prepare (callable): ``f(folder) -> (call, finish)`` where *call* logs one record and *finish* waits for any
           background work, closes everything, and returns the seconds it took.
    """

    def __init__(self, name, group, prepare):
        self.name, self.group, self.prepare = name, group, prepare


def standard_file(folder):
    logger = logging.getLogger(f"bench-{id(folder)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(os.path.join(folder, 'standard.log'))
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s <%(levelname)s> %(message)s'))
    logger.addHandler(handler)

    def finish():
        handler.close()
        logger.removeHandler(handler)
        return 0.0

    return (lambda: logger.info('order created id=%s user=%s', 1, 'a')), finish


def standard_unflushed(folder):
    logger = logging.getLogger(f"bench-unflushed-{id(folder)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(os.path.join(folder, 'standard.log'))
    handler.flush = lambda: None          # the buffer of the file is written when it fills up and when it is closed
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s <%(levelname)s> %(message)s'))
    logger.addHandler(handler)

    def finish():
        handler.close()
        logger.removeHandler(handler)
        return 0.0

    return (lambda: logger.info('order created id=%s user=%s', 1, 'a')), finish


def standard_disabled(folder):
    logger = logging.getLogger(f"bench-off-{id(folder)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return (lambda: logger.debug('order created id=%s user=%s', 1, 'a')), (lambda: 0.0)


def make_pysimplelog(folder, fileFormatter='text', flush=True, level=None):
    logger = Logger('bench', logToStdout=False, logFile=os.path.join(folder, 'psl.log'), fileFormatter=fileFormatter,
                    flush=flush)
    if level is not None:
        logger.set_minimum_level(level)
    return logger


def psl_text(folder):
    logger = make_pysimplelog(folder)

    def finish():
        logger.flush()
        return 0.0

    return (lambda: logger.info('order created', order_id=1, user='a')), finish


def psl_json(folder):
    logger = make_pysimplelog(folder, fileFormatter=None)

    def finish():
        logger.flush()
        return 0.0

    return (lambda: logger.info('order created', order_id=1, user='a')), finish


def psl_unflushed(fileFormatter):
    def prepare(folder):
        logger = make_pysimplelog(folder, fileFormatter=fileFormatter, flush=False)

        def finish():
            logger.flush()
            return 0.0

        return (lambda: logger.info('order created', order_id=1, user='a')), finish

    return prepare


def psl_disabled(folder):
    logger = make_pysimplelog(folder, level=20)
    return (lambda: logger.debug('order created', order_id=1, user='a')), (lambda: 0.0)


def psl_filesink(**options):
    def prepare(folder):
        logger = Logger('bench', logToStdout=False, logToFile=False)
        logger.add_sink('f', FileSink(os.path.join(folder, 'f'), 'log', formatter='text', **options))

        def finish():
            started = time.perf_counter()
            logger.clear_sinks()
            return time.perf_counter() - started

        return (lambda: logger.info('order created', order_id=1, user='a')), finish

    return prepare


def psl_threaded(folder):
    logger = Logger('bench', logToStdout=False, logToFile=False)
    logger.add_sink('s', Destination(), threaded=True, threadQueueSize=1000000)

    def finish():
        started = time.perf_counter()
        logger.flush(timeout=120)
        logger.clear_sinks()
        return time.perf_counter() - started

    return (lambda: logger.info('order created', order_id=1, user='a')), finish


def psl_spool(flush):
    def prepare(folder):
        logger = Logger('bench', logToStdout=False, logToFile=False)
        logger.add_sink('s', Destination(), threaded=True, threadQueueSize=1000000,
                        spool={'path': os.path.join(folder, 'spool'), 'id': 'bench', 'maxBytes': 10 ** 10,
                               'totalMaxBytes': 10 ** 11, 'flush': flush})

        def finish():
            started = time.perf_counter()
            logger.flush(timeout=300)
            logger.clear_sinks()
            return time.perf_counter() - started

        return (lambda: logger.info('order created', order_id=1, user='a')), finish

    return prepare


def loguru_file(serialize, enqueue=False):
    def prepare(folder):
        from loguru import logger
        logger.remove()
        identifier = logger.add(os.path.join(folder, 'loguru.log'), serialize=serialize, enqueue=enqueue, level='INFO')

        def finish():
            started = time.perf_counter()
            logger.remove(identifier)
            return time.perf_counter() - started

        return (lambda: logger.info('order created id={} user={}', 1, 'a')), finish

    return prepare


def structlog_json(folder):
    stream = open(os.path.join(folder, 'structlog.log'), 'w')
    structlog.configure(processors=[structlog.processors.add_log_level, structlog.processors.TimeStamper(fmt='iso'),
                                    structlog.processors.JSONRenderer()],
                        logger_factory=structlog.WriteLoggerFactory(file=stream),
                        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO), cache_logger_on_first_use=True)
    logger = structlog.get_logger()

    def finish():
        stream.close()
        return 0.0

    return (lambda: logger.info('order created', order_id=1, user='a')), finish


def build_cases():
    cases = [
        Case('standard logging, file', 'standard', standard_file),
        Case('standard logging, file, no flush', 'standard noflush', standard_unflushed),
        Case('standard logging, level off', 'standard', standard_disabled),
        Case('pysimplelog, file text', 'pysimplelog', psl_text),
        Case('pysimplelog, file JSON', 'pysimplelog', psl_json),
        Case('pysimplelog, FileSink, no limits', 'filesink', psl_filesink()),
        Case('pysimplelog, FileSink, maxAge set', 'filesink', psl_filesink(maxAge=3600)),
        Case('pysimplelog, FileSink, rotating', 'filesink', psl_filesink(maxSize=0.05, roll=5)),
        Case('pysimplelog, FileSink, rotating + gz', 'filesink', psl_filesink(maxSize=0.05, roll=5, compress='gz')),
        Case('pysimplelog, file text, no flush', 'pysimplelog noflush', psl_unflushed('text')),
        Case('pysimplelog, file JSON, no flush', 'pysimplelog noflush', psl_unflushed(None)),
        Case('pysimplelog, level off', 'pysimplelog', psl_disabled),
        Case('pysimplelog, threaded sink', 'thread', psl_threaded),
        Case('pysimplelog, spool flush=none', 'spool', psl_spool('none')),
        Case('pysimplelog, spool flush=flush', 'spool', psl_spool('flush')),
        Case('pysimplelog, spool flush=fsync', 'spool', psl_spool('fsync')),
    ]
    if loguru is not None:
        cases += [Case('loguru, file text', 'loguru', loguru_file(False)),
                  Case('loguru, file JSON', 'loguru', loguru_file(True)),
                  Case('loguru, file text enqueue', 'loguru', loguru_file(False, enqueue=True))]
    if structlog is not None:
        cases.append(Case('structlog, file JSON', 'structlog', structlog_json))
    return cases


def measure(case, count, repeats):
    """Returns (median, best, finish seconds) in microseconds for the calls, over *repeats* runs of *count* calls."""
    timings, finishing = [], []
    for _ in range(repeats):
        folder = tempfile.mkdtemp(prefix='bench-logging-')
        try:
            call, finish = case.prepare(folder)
            for _ in range(min(200, count)):
                call()
            started = time.perf_counter()
            for _ in range(count):
                call()
            timings.append((time.perf_counter() - started) / count * 1e6)
            finishing.append(finish())
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    return statistics.median(timings), min(timings), statistics.median(finishing)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--count', type=int, default=20000, help='log calls in one run')
    parser.add_argument('--repeats', type=int, default=5, help='runs of each case')
    parser.add_argument('--only', default=None, help='run the cases whose name or group contains this text')
    arguments = parser.parse_args()
    print(f"python {platform.python_version()} on {platform.system()} {platform.machine()}, pysimplelog {pysimplelog.get_version()}, "
          f"loguru {'not installed' if loguru is None else loguru.__version__}, "
          f"structlog {'not installed' if structlog is None else structlog.__version__}")
    print(f"{arguments.count} calls in a run, {arguments.repeats} runs, microseconds in the calling thread\n")
    print(f"{'case':36s} {'median':>9s} {'best':>9s} {'calls/s':>10s}   {'finish':>9s}")
    for case in build_cases():
        if arguments.only is not None and arguments.only not in case.name and arguments.only not in case.group:
            continue
        count = max(500, arguments.count // 20) if 'fsync' in case.name else arguments.count
        median, best, finish = measure(case, count, arguments.repeats)
        tail = f"{finish * 1000:7.0f} ms" if finish > 0 else ''
        print(f"{case.name:36s} {median:7.1f}us {best:7.1f}us {1e6 / median:10.0f}   {tail:>9s}")


if __name__ == '__main__':
    main()
