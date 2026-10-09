"""
Compares the cost of a log call in pysimplelog, the standard ``logging`` module, Loguru and structlog, for the same work.

Run it from any folder. Choose the libraries and, if you like, the scenarios::

    python3 pysimplelog/benchmarks/bench_compare.py --all
    python3 pysimplelog/benchmarks/bench_compare.py --pysimplelog --loguru
    python3 pysimplelog/benchmarks/bench_compare.py --all --scenario disabled,structured,json
    python3 pysimplelog/benchmarks/bench_compare.py --pysimplelog --components
    python3 pysimplelog/benchmarks/bench_compare.py --list

A library that is not installed is skipped and said so. Nothing is installed by this script. The tables are printed and
also saved in the ``results`` folder next to this file, as a text file and a JSON file, unless ``--no-save`` is given.

What is measured, and what is not
---------------------------------
Every scenario logs the same message the same number of times with each library. For each one it reports:

* ``events/s``: log calls per second of wall time, seen by the threads that log. For an asynchronous case this counts only the
  time to hand records over, so it flatters a library whose background thread cannot keep up.
* ``e2e/s``: events per second from the first call to the moment the last record has been written. Read this one for the
  asynchronous cases. For a synchronous case it is the same as ``events/s``.
* ``mean``, ``p50``, ``p95``, ``p99``: microseconds spent in one log call, from a second pass that times every call on its own,
  started with an empty queue. It is a separate pass because reading the clock around each call costs about 0.1 microsecond.
* ``p50 range``: the lowest and the highest p50 among the repeats. A wide range means the number is not stable.
* ``cpu``: microseconds of processor time per event, for every thread of the process, background threads and the draining of
  their queues included.
* ``bytes``: characters written for one event, from a short separate run. Libraries write different amounts for the same event.
* ``drain``: seconds the background work took to finish after the last call, for the asynchronous cases, and ``backlog`` the
  records still waiting at that moment, where the library can say.
* ``rss``: kilobytes by which the resident memory grew while handing over the records, for the asynchronous cases only.

Read the numbers with these in mind:

* The libraries differ in what they do by default. Loguru does not flush a file after each line, the standard module and
  pysimplelog do. ``file`` is each library as it ships, ``file_flush`` flushes every line in every library, ``file_noflush`` in none.
* The repeats of a scenario take turns between the libraries, the first library changes at each repeat, so that a machine that
  warms up or gets busy does not favour one of them. The load of the machine is printed first. Run it when nothing else is running.
* Differences under about 10 percent, or with overlapping ranges, are noise.
* The structured scenarios give two values with each event. pysimplelog and structlog take them as arguments, Loguru takes them
  from ``bind``, the standard module from ``extra`` with a formatter written in this file to print them.
* A library that has no equivalent of a scenario shows ``n/a``. It is not a failure.
* Console cases write to a file opened on the null device, so the terminal does not count.
* Nothing is tuned for any library beyond what a user would write. The numbers belong to this machine, this Python and its load.

To add a library, write a class like ``StandardLibrary`` with one method ``scenario_<name>(self, folder)`` for each scenario it can
do, and add it to ``LIBRARIES``.
"""
import argparse
import datetime
import gc
import itertools
import json
import logging
import logging.handlers
import os
import platform
import queue
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import timeit
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE_PARENT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PACKAGE_PARENT)

import pysimplelog  # noqa: E402
from pysimplelog import Logger, context  # noqa: E402

try:
    import loguru
except ImportError:
    loguru = None
try:
    import structlog
except ImportError:
    structlog = None
try:
    import psutil
except ImportError:
    psutil = None

RESULTS_FOLDER = os.path.join(HERE, 'results')
MESSAGE = 'order created'
FORMATTED_MESSAGE = 'order {} created for {}'
PERCENT_MESSAGE = 'order %s created for %s'
# Names a standard record has by itself, anything else on it was added with ``extra``
STANDARD_ATTRIBUTES = frozenset(logging.LogRecord('', 0, '', 0, '', (), None).__dict__) | {'message', 'asctime'}
LOGGER_NUMBERS = itertools.count()
LARGE_MESSAGE = 'x' * 10000
PROBE_EVENTS = 100


class NullStream:
    """A file-like object that accepts text and keeps nothing, with the methods a logging library may look for."""

    characters = 0

    def read(self, size=-1):
        # Logger(stdout=...) asks for a read method as well as a write method
        return ''

    def write(self, text):
        # Only the short separate run that measures the size of a record reads this, so a race between threads does not matter
        NullStream.characters += len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


class NoFlushFile:
    """Wraps an open file so that writes are buffered by the file and a flush request does nothing."""

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        self.stream.write(text)

    def flush(self):
        pass

    def isatty(self):
        return False

    def close(self):
        self.stream.close()


def nothing():
    """Returns zero seconds: the finish of a case that has no background work."""
    return 0.0


def expensive():
    """Builds a text that takes a few microseconds, for the disabled calls that show the cost of an argument."""
    return '-'.join(str(number) for number in range(40))


def raise_error(order, user):
    """Raises a TypeError with two local variables in the frame, so an exception has the same shape in every library."""
    return order + user


class Built(NamedTuple):
    """
    What a library gives for a scenario.

    :Parameters:
        #. call (callable): Makes one log call.
        #. finish (callable): Closes everything.
        #. backlog (callable, None): Returns how many records wait in a queue, or None when the library cannot say.
        #. drain (callable, None): Waits until every record has been written, without closing. None for a synchronous case.
    """
    call: object
    finish: object
    backlog: object = None
    drain: object = None


class Scenario:
    """
    One thing to measure.

    :Parameters:
        #. key (str): The name used by ``--scenario`` and in the tables.
        #. title (str): What it is, in one line.
        #. threadCounts (tuple): How many threads log. More than one gives one table row for each.
        #. count (None, int): Calls in the first pass, instead of ``--count``, for a case that is slow.
        #. samples (None, int): Calls timed one by one, instead of ``--samples``.
        #. minRepeats (int): The least number of repeats, for a case that varies a lot.
        #. isAsync (bool): True when a background thread writes, so the drain and the memory are reported.
        #. kind (str): ``'calls'`` for log calls, ``'import'`` for the time to import the library.
    """

    def __init__(self, key, title, threadCounts=(1,), count=None, samples=None, minRepeats=1, isAsync=False, kind='calls'):
        self.key, self.title, self.threadCounts = key, title, threadCounts
        self.count, self.samples, self.minRepeats, self.isAsync, self.kind = count, samples, minRepeats, isAsync, kind


SCENARIOS = (
    Scenario('import_time', 'the time to import the library, in a fresh process', kind='import'),
    Scenario('create_logger', 'making a logger', count=500, samples=300),
    Scenario('disabled', 'a DEBUG call that no sink wants'),
    Scenario('disabled_eager', 'a disabled DEBUG call whose argument is built by the caller'),
    Scenario('disabled_lazy', 'the same, with the argument given as a function to call only if needed'),
    Scenario('enabled', 'an INFO call, plain message, to a stream'),
    Scenario('formatted', 'an INFO call with two positional values in the message'),
    Scenario('structured', 'an INFO call with two structured values'),
    Scenario('large_message', 'an INFO call with a 10000 character message', count=5000, samples=1000),
    Scenario('json', 'an INFO call with two structured values, written as JSON'),
    Scenario('console', 'an INFO call to the console as the library shows it'),
    Scenario('file', 'two structured values to a text file, flushed or not as the library does by default'),
    Scenario('file_flush', 'the same file, flushed after each line in every library'),
    Scenario('file_noflush', 'the same file, with no flush after each line in any library'),
    Scenario('multisink', 'two structured values to a text file, a JSON file and the console'),
    Scenario('async', 'two structured values to a text file written by a background thread', isAsync=True),
    Scenario('contention', 'the asynchronous file written to by 8 threads at once', threadCounts=(8,), minRepeats=15,
             isAsync=True),
    Scenario('context', 'a plain INFO call inside a block that adds request_id'),
    Scenario('bound', 'a plain INFO call on a logger that has request_id bound'),
    Scenario('exception', 'an exception logged with its traceback'),
    Scenario('exception_diagnose', 'an exception logged with the values of its variables', count=5000, samples=1000),
    Scenario('threads', 'two structured values to a text file from 1, 4 and 16 threads', threadCounts=(1, 4, 16)),
)


class Library:
    """
    A logging library under test. A subclass writes one method ``scenario_<key>(self, folder)`` for each scenario it can do.
    The method returns ``(call, finish)``: *call* makes one log call, *finish* waits for any background work, closes
    everything and returns the seconds it took.
    """
    name = ''
    flag = ''
    module = ''

    def available(self):
        """Returns True when the library can be imported."""
        return True

    def version(self):
        """Returns the version text of the library."""
        return ''

    def build(self, scenarioKey, folder):
        """Returns a :class:`Built` for a scenario, or None when the library has no such scenario."""
        method = getattr(self, f"scenario_{scenarioKey}", None)
        if method is None:
            return None
        built = method(folder)
        return built if isinstance(built, Built) else Built(*built)


class PySimpleLog(Library):
    """pysimplelog, used as its documentation shows."""
    name = 'pysimplelog'
    flag = 'pysimplelog'
    module = 'pysimplelog'

    def version(self):
        return pysimplelog.get_version()

    @staticmethod
    def _logger(**options):
        """Makes a logger whose console goes to the null stream and that has no log file of its own."""
        return Logger('bench', logToFile=False, stdout=NullStream(), **options)

    @staticmethod
    def _file_logger(folder, **options):
        """Makes a logger that writes only to a text file."""
        return Logger('bench', logToStdout=False, logFile=os.path.join(folder, 'psl.log'), fileFormatter='text', **options)

    @staticmethod
    def _flush_then_stop(logger):
        """Returns a finish function that flushes the logger and takes no time."""
        def finish():
            logger.flush()
            return 0.0

        return finish

    @staticmethod
    def _async_logger(folder):
        """Makes a logger whose only sink is a text file written by a thread of its own, with a queue that never drops."""
        logger = Logger('bench', logToStdout=False, logToFile=False)
        logger.add(os.path.join(folder, 'psl.log'), threaded=True, threadQueueSize=1000000, threadQueuePolicy='block')

        def drain():
            logger.flush(timeout=600)

        def finish():
            dropped = logger.sink_stats('sink-1')['queue']['dropped']
            logger.clear_sinks()
            if dropped > 0:
                raise RuntimeError(f"the queue dropped {dropped} records, the measurement is not valid")

        def backlog():
            return logger.sink_stats('sink-1')['queue']['depth']

        return Built(lambda: logger.info(MESSAGE, order_id=1, user='a'), finish, backlog, drain)

    def scenario_disabled(self, folder):
        logger = self._logger(consoleFormatter='text', stdoutMinLevel=10)
        return (lambda: logger.debug(MESSAGE)), nothing

    def scenario_create_logger(self, folder):
        return (lambda: Logger('bench', logToFile=False, stdout=NullStream())), nothing

    def scenario_disabled_eager(self, folder):
        logger = self._logger(consoleFormatter='text', stdoutMinLevel=10)
        return (lambda: logger.debug('value={}', expensive())), nothing

    def scenario_disabled_lazy(self, folder):
        logger = self._logger(consoleFormatter='text', stdoutMinLevel=10)
        return (lambda: logger.opt(lazy=True).debug('value={}', expensive)), nothing

    def scenario_large_message(self, folder):
        logger = self._logger(consoleFormatter='text')
        return (lambda: logger.info(LARGE_MESSAGE)), nothing

    def scenario_file_flush(self, folder):
        return self.scenario_file(folder)

    def scenario_enabled(self, folder):
        logger = self._logger(consoleFormatter='text')
        return (lambda: logger.info(MESSAGE)), nothing

    def scenario_formatted(self, folder):
        logger = self._logger(consoleFormatter='text')
        return (lambda: logger.info(FORMATTED_MESSAGE, 1, 'a')), nothing

    def scenario_structured(self, folder):
        logger = self._logger(consoleFormatter='text')
        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), nothing

    def scenario_json(self, folder):
        logger = self._logger(consoleFormatter='json')
        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), nothing

    def scenario_console(self, folder):
        logger = self._logger(consoleFormatter='pretty')
        return (lambda: logger.info(MESSAGE)), nothing

    def scenario_file(self, folder):
        logger = self._file_logger(folder, flush=True)
        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), self._flush_then_stop(logger)

    def scenario_file_noflush(self, folder):
        logger = self._file_logger(folder, flush=False)
        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), self._flush_then_stop(logger)

    def scenario_multisink(self, folder):
        logger = self._logger(consoleFormatter='pretty')
        logger.add(os.path.join(folder, 'text.log'), format='text')
        logger.add(os.path.join(folder, 'json.jsonl'), format='json')

        def finish():
            logger.clear_sinks()
            return 0.0

        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), finish

    def scenario_async(self, folder):
        return self._async_logger(folder)

    def scenario_contention(self, folder):
        return self._async_logger(folder)

    def scenario_context(self, folder):
        logger = self._logger(consoleFormatter='text')

        def call():
            with context(request_id='r1'):
                logger.info(MESSAGE)

        return call, nothing

    def scenario_bound(self, folder):
        bound = self._logger(consoleFormatter='text').bind(request_id='r1')
        return (lambda: bound.info(MESSAGE)), nothing

    def scenario_exception(self, folder):
        logger = self._logger(consoleFormatter='text')

        def call():
            try:
                raise_error(1, 'a')
            except TypeError:
                logger.exception('failed')

        return call, nothing

    def scenario_exception_diagnose(self, folder):
        logger = self._logger(consoleFormatter='text', diagnose='summary')

        def call():
            try:
                raise_error(1, 'a')
            except TypeError:
                logger.exception('failed')

        return call, nothing

    def scenario_threads(self, folder):
        return self.scenario_file(folder)


class StructuredTextFormatter(logging.Formatter):
    """A standard formatter that adds the values given with ``extra`` to the line as ``key=value``."""

    def format(self, record):
        text = super().format(record)
        pairs = ' '.join(f"{key}={value}" for key, value in record.__dict__.items() if key not in STANDARD_ATTRIBUTES)
        return f"{text} {pairs}" if pairs != '' else text


class JsonFormatter(logging.Formatter):
    """A standard formatter that writes the record and its ``extra`` values as one line of JSON."""

    def format(self, record):
        document = {'timestamp': self.formatTime(record), 'level': record.levelname, 'logger': record.name,
                    'message': record.getMessage()}
        document.update({key: value for key, value in record.__dict__.items() if key not in STANDARD_ATTRIBUTES})
        return json.dumps(document)


class StandardLibrary(Library):
    """The ``logging`` module of Python, with handlers and formatters written the way its documentation shows."""
    name = 'stdlib'
    flag = 'stdlib'
    module = 'logging'

    def version(self):
        return f"python {platform.python_version()}"

    @staticmethod
    def _logger(handlers, level=logging.INFO):
        """Makes a logger with its own name and these handlers, and a function that closes them."""
        logger = logging.getLogger(f"bench-{next(LOGGER_NUMBERS)}")
        logger.setLevel(level)
        logger.propagate = False
        for handler in handlers:
            logger.addHandler(handler)

        def finish():
            for handler in handlers:
                logger.removeHandler(handler)
                handler.close()
            return 0.0

        return logger, finish

    @staticmethod
    def _handler(stream, formatter):
        """Makes a stream handler with a formatter."""
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        return handler

    @staticmethod
    def _text(structured=False):
        """Returns a formatter with the same layout as the others."""
        layout = '%(asctime)s - %(name)s <%(levelname)s> %(message)s'
        return StructuredTextFormatter(layout) if structured else logging.Formatter(layout)

    def scenario_disabled(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text())])
        return (lambda: logger.debug(MESSAGE)), finish

    def scenario_create_logger(self, folder):
        return (lambda: self._logger([self._handler(NullStream(), self._text())])), nothing

    def scenario_disabled_eager(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text())])
        return (lambda: logger.debug('value=%s', expensive())), finish

    def scenario_large_message(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text())])
        return (lambda: logger.info(LARGE_MESSAGE)), finish

    def scenario_file_flush(self, folder):
        return self._file(folder, 'std.log', True)

    def scenario_enabled(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text())])
        return (lambda: logger.info(MESSAGE)), finish

    def scenario_formatted(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text())])
        return (lambda: logger.info(PERCENT_MESSAGE, 1, 'a')), finish

    def scenario_structured(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text(True))])
        return (lambda: logger.info(MESSAGE, extra={'order_id': 1, 'user': 'a'})), finish

    def scenario_json(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), JsonFormatter())])
        return (lambda: logger.info(MESSAGE, extra={'order_id': 1, 'user': 'a'})), finish

    def scenario_console(self, folder):
        return self.scenario_enabled(folder)

    def _file(self, folder, name, flushes):
        """Makes a logger that writes the structured text to a file, with or without a flush after each line."""
        handler = logging.FileHandler(os.path.join(folder, name))
        handler.setFormatter(self._text(True))
        if not flushes:
            handler.flush = lambda: None
        logger, finish = self._logger([handler])
        return (lambda: logger.info(MESSAGE, extra={'order_id': 1, 'user': 'a'})), finish

    def scenario_file(self, folder):
        return self._file(folder, 'std.log', True)

    def scenario_file_noflush(self, folder):
        return self._file(folder, 'std.log', False)

    def scenario_threads(self, folder):
        return self._file(folder, 'std.log', True)

    def scenario_multisink(self, folder):
        text = logging.FileHandler(os.path.join(folder, 'text.log'))
        text.setFormatter(self._text(True))
        asJson = logging.FileHandler(os.path.join(folder, 'json.jsonl'))
        asJson.setFormatter(JsonFormatter())
        logger, finish = self._logger([self._handler(NullStream(), self._text(True)), text, asJson])
        return (lambda: logger.info(MESSAGE, extra={'order_id': 1, 'user': 'a'})), finish

    def _async(self, folder):
        """Makes a logger that puts records on a queue that a listener thread writes to a file."""
        fileHandler = logging.FileHandler(os.path.join(folder, 'std.log'))
        fileHandler.setFormatter(self._text(True))
        records = queue.SimpleQueue()
        listener = logging.handlers.QueueListener(records, fileHandler)
        logger, closeHandlers = self._logger([logging.handlers.QueueHandler(records)])
        listener.start()

        def drain():
            # A record that the listener has taken but not written yet is not counted, the file is flushed by the handler
            while records.qsize() > 0:
                time.sleep(0.001)
            fileHandler.flush()

        def finish():
            listener.stop()
            fileHandler.close()
            closeHandlers()

        return Built(lambda: logger.info(MESSAGE, extra={'order_id': 1, 'user': 'a'}), finish, records.qsize, drain)

    def scenario_async(self, folder):
        return self._async(folder)

    def scenario_contention(self, folder):
        return self._async(folder)

    def scenario_bound(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text(True))])
        adapter = logging.LoggerAdapter(logger, {'request_id': 'r1'})
        return (lambda: adapter.info(MESSAGE)), finish

    def scenario_exception(self, folder):
        logger, finish = self._logger([self._handler(NullStream(), self._text())])

        def call():
            try:
                raise_error(1, 'a')
            except TypeError:
                logger.exception('failed')

        return call, finish


class LoguruLibrary(Library):
    """Loguru, with its one global logger set up the way its documentation shows."""
    name = 'loguru'
    flag = 'loguru'
    module = 'loguru'
    TEXT = '{time:YYYY-MM-DD HH:mm:ss} - {name} <{level}> {message} {extra}'

    def available(self):
        return loguru is not None

    def version(self):
        return loguru.__version__

    @staticmethod
    def _setup(sink, **options):
        """Removes every sink of the global logger, adds one, and returns the logger and a function that removes it."""
        from loguru import logger
        logger.remove()
        identifier = logger.add(sink, **options)

        def finish():
            started = time.perf_counter()
            logger.remove(identifier)
            return time.perf_counter() - started

        return logger, finish

    def scenario_disabled(self, folder):
        logger, finish = self._setup(NullStream(), level='INFO', format=self.TEXT, colorize=False)
        return (lambda: logger.debug(MESSAGE)), finish

    def scenario_create_logger(self, folder):
        from loguru import logger
        logger.remove()

        def call():
            identifier = logger.add(NullStream(), format=self.TEXT, colorize=False)
            logger.remove(identifier)

        return call, nothing

    def scenario_disabled_eager(self, folder):
        logger, finish = self._setup(NullStream(), level='INFO', format=self.TEXT, colorize=False)
        return (lambda: logger.debug('value={}', expensive())), finish

    def scenario_disabled_lazy(self, folder):
        logger, finish = self._setup(NullStream(), level='INFO', format=self.TEXT, colorize=False)
        return (lambda: logger.opt(lazy=True).debug('value={}', expensive)), finish

    def scenario_large_message(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)
        return (lambda: logger.info(LARGE_MESSAGE)), finish

    def scenario_file_flush(self, folder):
        stream = open(os.path.join(folder, 'loguru.log'), 'w')

        def flushing_sink(message):
            stream.write(message)
            stream.flush()

        logger, removeSink = self._setup(flushing_sink, format=self.TEXT, colorize=False)

        def finish():
            removeSink()
            stream.close()

        return (lambda: logger.bind(order_id=1, user='a').info(MESSAGE)), finish

    def scenario_enabled(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)
        return (lambda: logger.info(MESSAGE)), finish

    def scenario_formatted(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)
        return (lambda: logger.info(FORMATTED_MESSAGE, 1, 'a')), finish

    def scenario_structured(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)
        return (lambda: logger.bind(order_id=1, user='a').info(MESSAGE)), finish

    def scenario_json(self, folder):
        logger, finish = self._setup(NullStream(), serialize=True)
        return (lambda: logger.bind(order_id=1, user='a').info(MESSAGE)), finish

    def scenario_console(self, folder):
        logger, finish = self._setup(NullStream(), colorize=False)
        return (lambda: logger.info(MESSAGE)), finish

    def scenario_file(self, folder):
        # Loguru writes a file through a buffer and does not flush after each line, so this is its default
        logger, finish = self._setup(os.path.join(folder, 'loguru.log'), format=self.TEXT, colorize=False)
        return (lambda: logger.bind(order_id=1, user='a').info(MESSAGE)), finish

    def scenario_file_noflush(self, folder):
        return self.scenario_file(folder)

    def scenario_threads(self, folder):
        return self.scenario_file(folder)

    def scenario_multisink(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)
        logger.add(os.path.join(folder, 'text.log'), format=self.TEXT, colorize=False)
        logger.add(os.path.join(folder, 'json.jsonl'), serialize=True)
        return (lambda: logger.bind(order_id=1, user='a').info(MESSAGE)), finish

    def _async(self, folder):
        logger, finish = self._setup(os.path.join(folder, 'loguru.log'), format=self.TEXT, colorize=False, enqueue=True)
        return Built(lambda: logger.bind(order_id=1, user='a').info(MESSAGE), finish, None, logger.complete)

    def scenario_async(self, folder):
        return self._async(folder)

    def scenario_contention(self, folder):
        return self._async(folder)

    def scenario_context(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)

        def call():
            with logger.contextualize(request_id='r1'):
                logger.info(MESSAGE)

        return call, finish

    def scenario_bound(self, folder):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False)
        bound = logger.bind(request_id='r1')
        return (lambda: bound.info(MESSAGE)), finish

    def _exception(self, **options):
        logger, finish = self._setup(NullStream(), format=self.TEXT, colorize=False, **options)

        def call():
            try:
                raise_error(1, 'a')
            except TypeError:
                logger.exception('failed')

        return call, finish

    def scenario_exception(self, folder):
        return self._exception(backtrace=False, diagnose=False)

    def scenario_exception_diagnose(self, folder):
        # backtrace and diagnose are on by default in Loguru
        return self._exception()


class StructlogLibrary(Library):
    """structlog, configured with the processors its documentation shows."""
    name = 'structlog'
    flag = 'structlog'
    module = 'structlog'

    def available(self):
        return structlog is not None

    def version(self):
        return structlog.__version__

    @staticmethod
    def _logger(stream, renderer='text', level=logging.INFO, extraProcessors=()):
        """Configures structlog to write to *stream*, and returns a logger."""
        processors = [structlog.contextvars.merge_contextvars, structlog.processors.add_log_level,
                      structlog.processors.TimeStamper(fmt='%Y-%m-%d %H:%M:%S'), *extraProcessors]
        processors.append(structlog.processors.JSONRenderer() if renderer == 'json'
                          else structlog.dev.ConsoleRenderer(colors=False))
        structlog.reset_defaults()
        structlog.configure(processors=processors, logger_factory=structlog.WriteLoggerFactory(file=stream),
                            wrapper_class=structlog.make_filtering_bound_logger(level), cache_logger_on_first_use=True)
        return structlog.get_logger()

    def scenario_disabled(self, folder):
        logger = self._logger(NullStream())
        return (lambda: logger.debug(MESSAGE)), nothing

    def scenario_create_logger(self, folder):
        return (lambda: self._logger(NullStream())), nothing

    def scenario_disabled_eager(self, folder):
        logger = self._logger(NullStream())
        return (lambda: logger.debug('value=' + expensive())), nothing

    def scenario_large_message(self, folder):
        logger = self._logger(NullStream())
        return (lambda: logger.info(LARGE_MESSAGE)), nothing

    def scenario_file_flush(self, folder):
        return self._file(folder, True)

    def scenario_enabled(self, folder):
        logger = self._logger(NullStream())
        return (lambda: logger.info(MESSAGE)), nothing

    def scenario_formatted(self, folder):
        logger = self._logger(NullStream())
        # structlog does not format positional values, a message is built by the caller
        return (lambda: logger.info(f"order {1} created for {'a'}")), nothing

    def scenario_structured(self, folder):
        logger = self._logger(NullStream())
        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), nothing

    def scenario_json(self, folder):
        logger = self._logger(NullStream(), renderer='json')
        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), nothing

    def scenario_console(self, folder):
        return self.scenario_enabled(folder)

    def _file(self, folder, flushes):
        stream = open(os.path.join(folder, 'structlog.log'), 'w')
        logger = self._logger(stream if flushes else NoFlushFile(stream))

        def finish():
            stream.close()
            return 0.0

        return (lambda: logger.info(MESSAGE, order_id=1, user='a')), finish

    def scenario_file(self, folder):
        return self._file(folder, True)

    def scenario_file_noflush(self, folder):
        return self._file(folder, False)

    def scenario_threads(self, folder):
        return self._file(folder, True)

    def scenario_context(self, folder):
        logger = self._logger(NullStream())

        def call():
            with structlog.contextvars.bound_contextvars(request_id='r1'):
                logger.info(MESSAGE)

        return call, nothing

    def scenario_bound(self, folder):
        bound = self._logger(NullStream()).bind(request_id='r1')
        return (lambda: bound.info(MESSAGE)), nothing

    def scenario_exception(self, folder):
        logger = self._logger(NullStream(), extraProcessors=(structlog.processors.format_exc_info,))

        def call():
            try:
                raise_error(1, 'a')
            except TypeError:
                logger.exception('failed')

        return call, nothing


LIBRARIES = (PySimpleLog(), StandardLibrary(), LoguruLibrary(), StructlogLibrary())


def percentile(sortedValues, fraction):
    """Returns the value below which *fraction* of the sorted values lie."""
    return sortedValues[min(len(sortedValues) - 1, int(len(sortedValues) * fraction))]


def run_threads(call, count, threadCount):
    """
    Makes *count* calls in all, split between *threadCount* threads that start together.

    :Returns:
        #. result (tuple): ``(seconds, total calls made)``.
    """
    if threadCount == 1:
        started = time.perf_counter()
        for _ in range(count):
            call()
        return time.perf_counter() - started, count
    perThread = count // threadCount
    barrier = threading.Barrier(threadCount + 1)

    def work():
        barrier.wait()
        for _ in range(perThread):
            call()

    threads = [threading.Thread(target=work) for _ in range(threadCount)]
    for thread in threads:
        thread.start()
    barrier.wait()
    started = time.perf_counter()
    for thread in threads:
        thread.join()
    return time.perf_counter() - started, perThread * threadCount


def sample_latencies(call, samples, threadCount):
    """Times *samples* calls one by one, split between the threads, and returns the sorted nanoseconds."""
    perThread = max(1, samples // threadCount)
    results = [[] for _ in range(threadCount)]

    def work(index):
        local, clock = results[index], time.perf_counter_ns
        for _ in range(perThread):
            started = clock()
            call()
            local.append(clock() - started)

    if threadCount == 1:
        work(0)
    else:
        threads = [threading.Thread(target=work, args=(index,)) for index in range(threadCount)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    return sorted(value for local in results for value in local)


def folder_size(folder):
    """Returns the characters in every file under a folder."""
    return sum(os.path.getsize(os.path.join(path, name)) for path, _, names in os.walk(folder) for name in names)


def measure_once(build, count, samples, threadCount):
    """
    Measures one library on one scenario, once.

    The first pass makes *count* calls and then waits for any background work, so that the second pass, which times *samples*
    calls one by one, starts with an empty queue.

    :Parameters:
        #. build (callable): ``f(folder) -> Built``.
        #. count (int): Calls in the first pass.
        #. samples (int): Calls timed one by one in the second pass.
        #. threadCount (int): Threads that make the calls.

    :Returns:
        #. metrics (dict): ``events_per_second``, ``e2e_per_second``, ``mean``, ``p50``, ``p95``, ``p99`` (microseconds),
           ``cpu`` (microseconds per event), ``rss`` (kilobytes), ``drain`` (seconds) and ``backlog`` (records, or None).
    """
    process = psutil.Process() if psutil is not None else None
    folder = tempfile.mkdtemp(prefix='bench-compare-')
    try:
        built = build(folder)
        for _ in range(min(200, count)):
            built.call()
        if built.drain is not None:
            built.drain()
        gc.collect()
        rssBefore = process.memory_info().rss if process is not None else 0
        cpuBefore = time.process_time()
        seconds, total = run_threads(built.call, count, threadCount)
        backlog = None if built.backlog is None else built.backlog()
        rssAfter = process.memory_info().rss if process is not None else 0
        drainSeconds = 0.0
        if built.drain is not None:
            started = time.perf_counter()
            built.drain()
            drainSeconds = time.perf_counter() - started
        latencies = sample_latencies(built.call, samples, threadCount)
        if built.drain is not None:
            # The processor time of writing the sampled records belongs to the events
            built.drain()
        built.finish()
        cpu = time.process_time() - cpuBefore
        return {'events_per_second': total / seconds,
                'e2e_per_second': total / (seconds + drainSeconds),
                'mean': statistics.fmean(latencies) / 1000,
                'p50': percentile(latencies, 0.50) / 1000,
                'p95': percentile(latencies, 0.95) / 1000,
                'p99': percentile(latencies, 0.99) / 1000,
                'cpu': cpu / (total + len(latencies)) * 1e6,
                'rss': (rssAfter - rssBefore) / 1024,
                'drain': drainSeconds,
                'backlog': backlog}
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def aggregate(runs):
    """
    Combines the repeats of one case: the median of each number, the lowest and highest p50, and every repeat.

    :Returns:
        #. metrics (dict): The medians under the names of :func:`measure_once`, ``p50_min``, ``p50_max`` and ``runs``.
    """
    metrics = {}
    for name in runs[0]:
        values = [run[name] for run in runs if run[name] is not None]
        metrics[name] = statistics.median(values) if len(values) > 0 else None
    metrics['p50_min'] = min(run['p50'] for run in runs)
    metrics['p50_max'] = max(run['p50'] for run in runs)
    metrics['runs'] = runs
    return metrics


def measure_baseline():
    """Returns the microseconds an empty call takes with the same one-by-one timing as the cases, to take away from a disabled call."""
    return percentile(sample_latencies(lambda: None, 50000, 1), 0.5) / 1000


def measure_components(count):
    """
    Times, in nanoseconds, the parts of pysimplelog that every log call goes through.

    :Returns:
        #. components (dict): ``{description: nanoseconds per call}``.
    """
    from pysimplelog.namespaces import is_disabled
    from pysimplelog.formatters import escape_control_characters
    from pysimplelog.message_format import render_message
    logger = Logger('bench', logToFile=False, stdout=NullStream(), stdoutMinLevel=100)

    def per_call(function):
        return min(timeit.repeat(function, number=count, repeat=7)) / count * 1e9

    return {
        'an empty function call': per_call(lambda: None),
        'is_disabled(name), nothing disabled': per_call(lambda: is_disabled('bench')),
        'escape_control_characters, clean text': per_call(lambda: escape_control_characters('order created')),
        'escape_control_characters, text with a line break': per_call(lambda: escape_control_characters('a\nb')),
        'render_message, no values': per_call(lambda: render_message('order created', (), {})),
        'render_message, two positional values': per_call(lambda: render_message('order {} for {}', (1, 'a'), {})),
        'Logger.log, a call no sink wants': per_call(lambda: logger.log('info', 'x')),
        'Logger._log_call, the same without the wrapper': per_call(
            lambda: logger._log_call('info', 'x', (), {}, None, None, False, 0)),
    }


def machine_load():
    """
    Looks at how busy the machine is before the measurement.

    :Returns:
        #. load (tuple): ``(processor percent over one second, load averages)``, each None when the machine cannot say.
    """
    percent = psutil.cpu_percent(interval=1.0) if psutil is not None else None
    averages = os.getloadavg() if hasattr(os, 'getloadavg') else None
    return percent, averages


def format_table(title, rows, isAsync):
    """Returns the lines of a table: *rows* is a list of ``(label, metrics or text, characters per event)``."""
    header = (f"  {'library':22s} {'events/s':>9s} {'e2e/s':>9s} {'mean':>7s} {'p50':>7s} {'p50 range':>13s} {'p95':>7s} "
              f"{'p99':>7s} {'cpu':>7s} {'bytes':>6s} {'drain':>6s} {'backlog':>8s} {'rss':>6s}")
    lines = [title, header]
    for label, metrics, size in rows:
        if isinstance(metrics, str):
            lines.append(f"  {label:22s} {metrics}")
            continue
        span = f"{metrics['p50_min']:.1f}-{metrics['p50_max']:.1f}"
        written = f"{size:6.0f}" if size else f"{'-':>6s}"
        drain = f"{metrics['drain']:6.2f}" if isAsync else f"{'-':>6s}"
        backlog = f"{metrics['backlog']:8.0f}" if isAsync and metrics['backlog'] is not None else f"{'-':>8s}"
        rss = f"{metrics['rss']:6.0f}" if isAsync else f"{'-':>6s}"
        lines.append(f"  {label:22s} {metrics['events_per_second']:9.0f} {metrics['e2e_per_second']:9.0f} {metrics['mean']:7.2f} "
                     f"{metrics['p50']:7.2f} {span:>13s} {metrics['p95']:7.2f} {metrics['p99']:7.2f} {metrics['cpu']:7.2f} "
                     f"{written} {drain} {backlog} {rss}")
    return lines


def parse_arguments():
    """Reads the command line and returns the parser and the arguments."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--all', action='store_true', help='every library that is installed')
    for library in LIBRARIES:
        parser.add_argument(f"--{library.flag}", action='store_true', help=f"measure {library.name}")
    parser.add_argument('--scenario', default=None, help='comma separated scenarios, all of them by default, see --list')
    parser.add_argument('--components', action='store_true', help='also time the parts of pysimplelog that every call goes through')
    parser.add_argument('--list', action='store_true', help='show the libraries and the scenarios, then stop')
    parser.add_argument('--count', type=int, default=20000, help='log calls in the first pass of a run')
    parser.add_argument('--repeats', type=int, default=5, help='runs of each case, the median is kept')
    parser.add_argument('--samples', type=int, default=5000, help='calls timed one by one for the percentiles')
    parser.add_argument('--output', default=RESULTS_FOLDER, help='folder where the results are saved')
    parser.add_argument('--no-save', action='store_true', help='print the results and save nothing')
    return parser, parser.parse_args()


def show_list():
    """Prints the libraries, whether they are installed, and the scenarios."""
    print('libraries:')
    for library in LIBRARIES:
        state = f"version {library.version()}" if library.available() else 'not installed'
        print(f"  --{library.flag:12s} {library.name}: {state}")
    print('scenarios:')
    for scenario in SCENARIOS:
        print(f"  {scenario.key:20s} {scenario.title}")


def choose_libraries(parser, arguments):
    """Returns the libraries asked for that are installed, and says which are skipped."""
    chosen = [library for library in LIBRARIES if arguments.all or getattr(arguments, library.flag)]
    if len(chosen) == 0 and not arguments.components:
        parser.error('choose libraries with --all or one flag for each library, see --list')
    for library in chosen:
        if not library.available():
            print(f"{library.name} is not installed, it is skipped")
    return [library for library in chosen if library.available()]


def choose_scenarios(parser, arguments):
    """Returns the scenarios asked for with ``--scenario``, all of them when it is not given."""
    if arguments.scenario is None:
        return list(SCENARIOS)
    wanted = [key.strip() for key in arguments.scenario.split(',')]
    unknown = set(wanted) - {scenario.key for scenario in SCENARIOS}
    if len(unknown) > 0:
        parser.error(f"unknown scenario {sorted(unknown)}, see --list")
    return [scenario for scenario in SCENARIOS if scenario.key in wanted]


def probe(library, scenarioKey):
    """
    Builds a scenario once, makes a few calls, and measures how much it wrote.

    :Returns:
        #. answer (str, None): ``'n/a'`` when the library has no such scenario, a text with the error when it failed, None
           when it can be measured.
        #. size (float, None): Characters written for one event, None when the case could not run or writes nothing.
    """
    folder = tempfile.mkdtemp(prefix='bench-probe-')
    NullStream.characters = 0
    try:
        built = library.build(scenarioKey, folder)
        if built is None:
            return 'n/a', None
        for _ in range(PROBE_EVENTS):
            built.call()
        if built.drain is not None:
            built.drain()
        built.finish()
        return None, (NullStream.characters + folder_size(folder)) / PROBE_EVENTS
    except Exception as error:
        return f"error while building: {type(error).__name__}: {error}", None
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def measure_import_time(library, repeats=9):
    """Returns the milliseconds that importing a library takes in a fresh process: the median, the lowest and the highest."""
    code = f"import time; started = time.perf_counter(); import {library.module}; print(time.perf_counter() - started)"
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join([PACKAGE_PARENT, os.environ.get('PYTHONPATH', '')]))
    values = []
    for number in range(repeats + 1):
        answer = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True, env=environment)
        # The first start only fills the cache of the disk
        if number > 0:
            values.append(float(answer.stdout) * 1000)
    return {'median': statistics.median(values), 'min': min(values), 'max': max(values)}


def run_import(chosen, scenario, results):
    """Measures the import time of each library and returns the lines of its table."""
    lines = [f"{scenario.key}: {scenario.title}", f"  {'library':22s} {'median ms':>10s} {'min':>8s} {'max':>8s}"]
    results[scenario.key] = {}
    for library in chosen:
        try:
            values = measure_import_time(library)
            results[scenario.key][library.name] = values
            lines.append(f"  {library.name:22s} {values['median']:10.1f} {values['min']:8.1f} {values['max']:8.1f}")
        except Exception as error:
            results[scenario.key][library.name] = None
            lines.append(f"  {library.name:22s} error: {type(error).__name__}")
    return lines + ['']


def run_calls(chosen, scenario, threadCount, arguments, results):
    """
    Measures every library on a scenario, taking turns between the libraries at each repeat, and returns the lines of its table.
    """
    key = scenario.key if len(scenario.threadCounts) == 1 else f"{scenario.key} x{threadCount}"
    answers, sizes, runnable = {}, {}, []
    for library in chosen:
        answer, sizes[library.name] = probe(library, scenario.key)
        if answer is None:
            runnable.append(library)
        else:
            answers[library.name] = answer
    count = scenario.count or arguments.count
    samples = scenario.samples or arguments.samples
    repeats = max(arguments.repeats, scenario.minRepeats)
    runs = {library.name: [] for library in runnable}
    failures = {}
    for repeat in range(repeats):
        # The first library changes at each repeat, so that no library always runs on a cold or on a tired machine
        shift = repeat % max(1, len(runnable))
        for library in runnable[shift:] + runnable[:shift]:
            if library.name in failures:
                continue
            try:
                runs[library.name].append(measure_once(lambda path, lib=library: lib.build(scenario.key, path), count,
                                                       samples, threadCount))
            except Exception as error:
                failures[library.name] = f"error: {type(error).__name__}: {error}"
    rows = []
    results[key] = {}
    for library in chosen:
        name = library.name
        if name in answers or name in failures:
            rows.append((name, answers.get(name) or failures[name], None))
            results[key][name] = None
        else:
            metrics = aggregate(runs[name])
            rows.append((name, metrics, sizes[name]))
            results[key][name] = metrics
    return format_table(f"{key}: {scenario.title}", rows, scenario.isAsync) + ['']


def run_scenarios(chosen, scenarios, arguments, report):
    """
    Measures every chosen library on every scenario, prints each table, and adds its lines to *report*.

    :Returns:
        #. results (dict): ``{table name: {library name: metrics or None}}``.
    """
    results = {}
    for scenario in scenarios:
        if scenario.kind == 'import':
            blocks = [run_import(chosen, scenario, results)]
        else:
            blocks = [run_calls(chosen, scenario, threadCount, arguments, results) for threadCount in scenario.threadCounts]
        for block in blocks:
            report.extend(block)
            print('\n'.join(block))
    return results


def compute_derived(chosen, results, baseline):
    """Returns, for each library, the overhead of a disabled call, of two structured values, and what a lazy argument saves."""
    derived = {}
    for library in chosen:
        mine = {key: values.get(library.name) for key, values in results.items() if isinstance(values, dict)}
        disabled, structured, enabled = mine.get('disabled'), mine.get('structured'), mine.get('enabled')
        eager, lazy = mine.get('disabled_eager'), mine.get('disabled_lazy')
        if disabled is not None and 'p50' in disabled:
            derived.setdefault(library.name, {})['disabled call, p50 above an empty call timed the same way (us)'] = (
                disabled['p50'] - baseline)
        if structured is not None and enabled is not None:
            derived.setdefault(library.name, {})['two structured values, p50 above a plain call (us)'] = (
                structured['p50'] - enabled['p50'])
        if eager is not None and lazy is not None:
            derived.setdefault(library.name, {})['lazy argument, p50 saved on a disabled call (us)'] = eager['p50'] - lazy['p50']
    return derived


def save_results(arguments, report, environment, results, derived, components):
    """Writes the report as text and the numbers as JSON in the results folder, and says where."""
    os.makedirs(arguments.output, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    base = os.path.join(arguments.output, f"bench_compare-{stamp}")
    with open(f"{base}.txt", 'w') as stream:
        stream.write('\n'.join(report))
    with open(f"{base}.json", 'w') as stream:
        json.dump({'environment': environment, 'results': results, 'derived': derived, 'components': components},
                  stream, indent=2)
    print(f"saved {base}.txt and {base}.json")


def main():
    """Runs the benchmark described by the command line and returns the exit status."""
    parser, arguments = parse_arguments()
    if arguments.list:
        show_list()
        return 0
    chosen = choose_libraries(parser, arguments)
    scenarios = choose_scenarios(parser, arguments)
    percent, averages = machine_load() if len(chosen) > 0 else (None, None)
    environment = {'python': platform.python_version(), 'system': f"{platform.system()} {platform.release()}",
                   'machine': platform.machine(), 'processors': os.cpu_count(),
                   'libraries': {library.name: library.version() for library in LIBRARIES if library.available()},
                   'count': arguments.count, 'repeats': arguments.repeats, 'samples': arguments.samples,
                   'load_percent': percent, 'load_averages': averages,
                   'date': datetime.datetime.now().isoformat(timespec='seconds')}
    report = [f"python {environment['python']} on {environment['system']} {environment['machine']}, "
              f"{environment['processors']} processors",
              'libraries: ' + ', '.join(f"{name} {version}" for name, version in environment['libraries'].items()),
              f"{arguments.count} calls in the first pass, {arguments.samples} timed one by one, "
              f"median of {arguments.repeats} runs (at least {max(s.minRepeats for s in SCENARIOS)} for the unstable cases)",
              'times in microseconds per call, cpu in microseconds per event, bytes in characters per event, rss in kilobytes, '
              'drain in seconds']
    if percent is not None:
        report.append(f"machine load before the start: {percent:.0f} percent of the processors"
                      + ('' if averages is None else f", load averages {averages[0]:.2f} {averages[1]:.2f} {averages[2]:.2f}"))
        if percent > 15:
            report.append('WARNING: the machine is busy, the numbers will be noisy. Close other programs and run it again')
    report.append('')
    print('\n'.join(report))
    results = run_scenarios(chosen, scenarios, arguments, report)
    derived = compute_derived(chosen, results, measure_baseline())
    if len(derived) > 0:
        lines = ['derived']
        for name, values in derived.items():
            lines.extend(f"  {name:22s} {description}: {value:.2f}" for description, value in values.items())
        report.extend(lines + [''])
        print('\n'.join(lines) + '\n')
    components = None
    if arguments.components:
        components = measure_components(200000)
        lines = ['components of pysimplelog (nanoseconds per call)']
        lines.extend(f"  {description:52s} {value:9.1f}" for description, value in components.items())
        report.extend(lines + [''])
        print('\n'.join(lines) + '\n')
    if not arguments.no_save:
        save_results(arguments, report, environment, results, derived, components)
    return 0


if __name__ == '__main__':
    sys.exit(main())
