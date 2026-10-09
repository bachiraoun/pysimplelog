"""The concurrency models side by side: processes and threads, asyncio, start methods, crashes, full queues and a durable spool.

Run from the repo root::

    python3 -m unittest tests.test_concurrency_matrix -v

What these tests establish, and the limit of each claim:

* Many processes and threads can write one file through a logger each: no line is torn, none is lost, and the records of one
  thread keep their order. Records of different threads or processes have no order between them.
* A process that is killed loses at most what it had not yet written, and leaves the others and the file intact.
* The four queue policies give the same result every time for the same input.
* A program that ends with records waiting waits for them for ``shutdownTimeout`` seconds, then says how many it left.
* A spool recovers the records of every process that died, and may deliver one twice, never none.

Every case that starts processes runs them as a script with a time limit, so a hang is a failure and not a test run that never
ends. A case that needs a start method this system does not have is skipped.
"""
import asyncio
import json
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from simple_log import Logger  # noqa: E402
from sinks import Sink  # noqa: E402
from queues import QueueFull  # noqa: E402
from spool import Spool  # noqa: E402

SCRIPT_SECONDS = 120
WAIT_SECONDS = 15.0

# The header of every script: the package on the path, and the helpers they share
HEADER = '''
import asyncio, json, multiprocessing, os, signal, sys, threading, time
sys.path.insert(0, %r)
from simple_log import Logger
from sinks import Sink
from log_context import context
''' % PACKAGE_DIR

FILE_WORKER = HEADER + '''
def log_from_threads(path, processNumber, threadCount, perThread):
    """Makes the logger of this process, and logs from many threads into the shared file."""
    logger = Logger('matrix', logToFile=False, logToStdout=False)
    logger.add(path, format='json')
    def run(threadNumber):
        for index in range(perThread):
            logger.info('{}-{}-{}', processNumber, threadNumber, index, process=processNumber, thread=threadNumber, index=index)
    threads = [threading.Thread(target=run, args=(number,)) for number in range(threadCount)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    logger.flush()
    logger.clear_sinks()

def main():
    method, path, processCount, threadCount, perThread = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    context_ = multiprocessing.get_context(method)
    processes = [context_.Process(target=log_from_threads, args=(path, number, threadCount, perThread)) for number in range(processCount)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(%d)
        if process.is_alive():
            process.kill()
            print('STUCK', process.pid)
        elif process.exitcode != 0:
            print('EXIT', process.exitcode)

if __name__ == '__main__':
    main()
''' % (SCRIPT_SECONDS // 2)


def run_script(source, *arguments, timeout=SCRIPT_SECONDS):
    """Runs a script in its own process, and returns what it printed. A script that does not end in time fails the test."""
    folder = tempfile.mkdtemp(prefix='matrix-script-')
    try:
        path = os.path.join(folder, 'script.py')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(source)
        try:
            return subprocess.run([sys.executable, path, *map(str, arguments)], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise AssertionError(f"the script did not end in {timeout} seconds (a hang)") from error
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def read_records(path):
    """Returns the lines of a file as dictionaries, and fails if a line is not complete JSON."""
    records = []
    with open(path, encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            try:
                records.append(json.loads(line))
            except ValueError:
                raise AssertionError(f"line {number} is not a complete record: {line[:80]!r}") from None
    return records


def wait_until(condition, what, seconds=WAIT_SECONDS):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


class MatrixCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='matrix-')
        self.addCleanup(shutil.rmtree, self.folder, True)

    def path(self, name):
        return os.path.join(self.folder, name)


class TestProcessesAndThreads(MatrixCase):

    def check_file(self, path, processCount, threadCount, perThread):
        records = read_records(path)
        self.assertEqual(len(records), processCount * threadCount * perThread)
        seen = {}
        for record in records:
            fields = record['fields']
            seen.setdefault((fields['process'], fields['thread']), []).append(fields['index'])
            self.assertEqual(record['message'], f"{fields['process']}-{fields['thread']}-{fields['index']}")
        self.assertEqual(len(seen), processCount * threadCount)
        for indexes in seen.values():
            # The records of one thread keep their order, whatever the others do
            self.assertEqual(indexes, list(range(perThread)))
        return records

    def run_method(self, method, processCount=4, threadCount=4, perThread=150):
        if method not in multiprocessing.get_all_start_methods():
            self.skipTest(f"{method} is not available on this system")
        path = self.path('shared.jsonl')
        done = run_script(FILE_WORKER, method, path, processCount, threadCount, perThread)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), '', done.stdout)
        self.check_file(path, processCount, threadCount, perThread)

    def test_one_process_and_many_threads_into_one_file(self):
        self.run_method('fork' if 'fork' in multiprocessing.get_all_start_methods() else 'spawn', processCount=1, threadCount=8, perThread=300)

    def test_many_processes_started_by_fork_into_one_file(self):
        self.run_method('fork')

    def test_many_processes_started_by_spawn_into_one_file(self):
        self.run_method('spawn')

    def test_many_processes_started_by_forkserver_into_one_file(self):
        self.run_method('forkserver')

    def test_many_processes_with_one_thread_each(self):
        self.run_method('spawn', processCount=6, threadCount=1, perThread=300)


ASYNC_WORKER = HEADER + '''
def run_process(path, processNumber, taskCount, perTask, threadCount, perThread):
    """In one process: asyncio tasks, each with its own context, and plain threads, all logging into the same file."""
    logger = Logger('matrix', logToFile=False, logToStdout=False)
    logger.add(path, format='json')

    async def task(number):
        with logger.context(task=number, process=processNumber):
            for index in range(perTask):
                logger.info('task {} {}', number, index, kind='task', index=index)
                if index % 10 == 0:
                    await asyncio.sleep(0)

    def thread_run(number):
        for index in range(perThread):
            logger.info('thread {} {}', number, index, kind='thread', thread=number, index=index, process=processNumber)

    async def main():
        threads = [threading.Thread(target=thread_run, args=(number,)) for number in range(threadCount)]
        for thread in threads:
            thread.start()
        await asyncio.gather(*(task(number) for number in range(taskCount)))
        # A blocking call made from a coroutine on a worker thread of the loop
        await asyncio.get_running_loop().run_in_executor(None, logger.info, 'from the executor', )
        for thread in threads:
            thread.join()

    asyncio.run(main())
    logger.flush()
    logger.clear_sinks()

if __name__ == '__main__':
    method, path, processCount = sys.argv[1], sys.argv[2], int(sys.argv[3])
    args = [int(value) for value in sys.argv[4:8]]
    if processCount == 0:
        run_process(path, 0, *args)
    else:
        context_ = multiprocessing.get_context(method)
        processes = [context_.Process(target=run_process, args=(path, number, *args)) for number in range(processCount)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(60)
            if process.is_alive():
                process.kill()
                print('STUCK')
            elif process.exitcode != 0:
                print('EXIT', process.exitcode)
'''


class TestAsyncio(MatrixCase):

    TASKS, PER_TASK, THREADS, PER_THREAD = 6, 80, 3, 120

    def check(self, path, processCount):
        records = read_records(path)
        processes = max(processCount, 1)
        expected = processes * (self.TASKS * self.PER_TASK + self.THREADS * self.PER_THREAD + 1)
        self.assertEqual(len(records), expected)
        taskOrder = {}
        for record in records:
            fields = record.get('fields', {})
            if fields.get('kind') == 'task':
                context = record['context']
                # A task sees its own context and never the one of another task
                self.assertEqual(record['message'], f"task {context['task']} {fields['index']}")
                taskOrder.setdefault((context['process'], context['task']), []).append(fields['index'])
            elif fields.get('kind') == 'thread':
                # A plain thread does not inherit the context of any task
                self.assertNotIn('task', record.get('context', {}))
        for indexes in taskOrder.values():
            self.assertEqual(indexes, list(range(self.PER_TASK)))
        self.assertEqual(len(taskOrder), processes * self.TASKS)

    def run_case(self, method, processCount):
        if method not in multiprocessing.get_all_start_methods():
            self.skipTest(f"{method} is not available on this system")
        path = self.path('async.jsonl')
        done = run_script(ASYNC_WORKER, method, path, processCount, self.TASKS, self.PER_TASK, self.THREADS, self.PER_THREAD)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), '', done.stdout + done.stderr)
        self.check(path, processCount)

    def test_asyncio_tasks_and_threads_in_one_process(self):
        self.run_case('fork', 0)

    def test_asyncio_tasks_and_threads_in_many_processes_started_by_fork(self):
        self.run_case('fork', 3)

    def test_asyncio_tasks_and_threads_in_many_processes_started_by_spawn(self):
        self.run_case('spawn', 3)

    def test_asyncio_tasks_and_threads_in_many_processes_started_by_forkserver(self):
        self.run_case('forkserver', 3)

    def test_asyncio_with_a_threaded_sink_and_the_logger_queue(self):
        records = []
        lock = threading.Lock()

        class Keep(Sink):
            def write(self, text, record):
                with lock:
                    records.append(record)

        logger = Logger('matrix', logToFile=False, logToStdout=False, enqueue=True)
        logger.add(Keep(formatter='json'), threaded=True)

        async def task(number):
            with logger.context(task=number):
                for index in range(100):
                    logger.info('task {} {}', number, index)
                    if index % 7 == 0:
                        await asyncio.sleep(0)

        async def main():
            await asyncio.gather(*(task(number) for number in range(8)))

        try:
            asyncio.run(main())
            self.assertTrue(logger.flush(timeout=30))
        finally:
            logger.clear_sinks()
        self.assertEqual(len(records), 800)
        for record in records:
            self.assertEqual(record.message, f"task {record.context['task']} {record.message.split()[-1]}")


KILL_WORKER = HEADER + '''
path, role = sys.argv[1], sys.argv[2]
logger = Logger('matrix', logToFile=False, logToStdout=False)
logger.add(path, format='json')
if role == 'victim':
    print('ready', flush=True)
    index = 0
    while True:
        logger.info('victim {}', index, index=index)
        index += 1
else:
    for index in range(2000):
        logger.info('survivor {}', index, index=index)
    logger.clear_sinks()
    print('done', flush=True)
'''


class TestTerminationWhileLogging(MatrixCase):

    def test_a_killed_process_leaves_a_clean_file_and_the_others_are_not_harmed(self):
        path = self.path('shared.jsonl')
        script = os.path.join(self.folder, 'kill_worker.py')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(KILL_WORKER)
        victims = [subprocess.Popen([sys.executable, script, path, 'victim'], stdout=subprocess.PIPE, text=True) for _ in range(3)]
        survivor = None
        try:
            for victim in victims:
                self.assertEqual(victim.stdout.readline().strip(), 'ready')
            survivor = subprocess.Popen([sys.executable, script, path, 'survivor'], stdout=subprocess.PIPE, text=True)
            wait_until(lambda: os.path.getsize(path) > 20000, 'the victims to write')
            for victim in victims:
                victim.send_signal(signal.SIGKILL)
            for victim in victims:
                victim.wait(timeout=WAIT_SECONDS)
            self.assertEqual(survivor.stdout.readline().strip(), 'done')
            survivor.wait(timeout=WAIT_SECONDS)
            self.assertEqual(survivor.returncode, 0)
        finally:
            for process in victims + ([survivor] if survivor is not None else []):
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=WAIT_SECONDS)
                process.stdout.close()
        records = read_records(path)
        survivors = sorted(record['fields']['index'] for record in records if record['message'].startswith('survivor'))
        self.assertEqual(survivors, list(range(2000)))
        self.assertGreater(len([record for record in records if record['message'].startswith('victim')]), 0)

    def test_the_parent_goes_on_when_a_forked_child_is_killed_while_logging(self):
        if 'fork' not in multiprocessing.get_all_start_methods():
            self.skipTest("fork is not available on this system")
        path = self.path('parent.jsonl')
        logger = Logger('matrix', logToFile=False, logToStdout=False)
        logger.add(path, format='json')
        childPid = os.fork()
        if childPid == 0:
            try:
                while True:
                    logger.info('child')
            finally:
                os._exit(0)
        try:
            for index in range(300):
                logger.info('parent {}', index)
            os.kill(childPid, signal.SIGKILL)
            os.waitpid(childPid, 0)
            for index in range(300, 600):
                logger.info('parent {}', index)
            logger.flush(timeout=WAIT_SECONDS)
        finally:
            logger.clear_sinks()
        records = read_records(path)
        parent = sorted(int(record['message'].split()[1]) for record in records if record['message'].startswith('parent'))
        self.assertEqual(parent, list(range(600)))


class Gate(Sink):
    """A receiver that holds every write until it is opened, and keeps what it was given in order."""

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)
        self.opened = threading.Event()
        self.started = threading.Event()
        self.got = []

    def write(self, text, record):
        self.started.set()
        self.opened.wait(WAIT_SECONDS)
        self.got.append(text.rstrip('\n'))


class TestQueuePoliciesAreDeterministic(MatrixCase):
    """With a receiver that is stuck on its first record and a queue of 5, each policy keeps a known set."""

    SIZE = 5
    TOTAL = 20

    def make(self, policy, **options):
        gate = Gate()
        logger = Logger('matrix', logToFile=False, logToStdout=False)
        logger.add_sink('gate', gate, threaded=True, threadQueueSize=self.SIZE, threadQueuePolicy=policy, **options)
        self.addCleanup(logger.clear_sinks, 1.0)
        logger.info('0')
        self.assertTrue(gate.started.wait(WAIT_SECONDS), 'the first write did not start')
        return logger, gate

    def finish(self, logger, gate):
        gate.opened.set()
        self.assertTrue(logger.flush(timeout=WAIT_SECONDS))

    def test_drop_newest_keeps_the_first_ones(self):
        logger, gate = self.make('drop_newest')
        for number in range(1, self.TOTAL):
            logger.info(str(number))
        self.finish(logger, gate)
        self.assertEqual(gate.got, [str(number) for number in range(0, 1 + self.SIZE)])
        self.assertEqual(logger.sink_stats('gate')['queue']['dropped'], self.TOTAL - 1 - self.SIZE)

    def test_drop_oldest_keeps_the_last_ones(self):
        logger, gate = self.make('drop_oldest')
        for number in range(1, self.TOTAL):
            logger.info(str(number))
        self.finish(logger, gate)
        expected = ['0'] + [str(number) for number in range(self.TOTAL - self.SIZE, self.TOTAL)]
        self.assertEqual(gate.got, expected)
        self.assertEqual(logger.sink_stats('gate')['queue']['dropped'], self.TOTAL - 1 - self.SIZE)

    def test_reject_raises_for_the_ones_that_do_not_fit_and_keeps_the_first(self):
        logger, gate = self.make('reject')
        raised = 0
        for number in range(1, self.TOTAL):
            try:
                logger.info(str(number))
            except QueueFull:
                raised += 1
        self.finish(logger, gate)
        self.assertEqual(raised, self.TOTAL - 1 - self.SIZE)
        self.assertEqual(gate.got, [str(number) for number in range(0, 1 + self.SIZE)])

    def test_block_waits_and_loses_nothing(self):
        logger, gate = self.make('block')
        opener = threading.Timer(0.3, gate.opened.set)
        opener.start()
        started = time.time()
        for number in range(1, self.TOTAL):
            logger.info(str(number))
        self.assertGreaterEqual(time.time() - started, 0.2, 'the calls did not wait')
        self.finish(logger, gate)
        opener.join()
        self.assertEqual(gate.got, [str(number) for number in range(self.TOTAL)])

    def test_block_with_a_timeout_gives_up_the_same_way_every_time(self):
        results = []
        for _ in range(2):
            logger, gate = self.make('block', threadBlockTimeout=0.05)
            for number in range(1, 10):
                logger.info(str(number))
            self.finish(logger, gate)
            results.append(list(gate.got))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], [str(number) for number in range(0, 1 + self.SIZE)])

    def test_the_stats_say_what_happened(self):
        logger, gate = self.make('drop_newest')
        for number in range(1, self.TOTAL):
            logger.info(str(number))
        self.finish(logger, gate)
        queue = logger.sink_stats('gate')['queue']
        self.assertEqual(queue['policy'], 'drop_newest')
        self.assertEqual(queue['queued'] + queue['dropped'], self.TOTAL)
        self.assertEqual(queue['capacity'], self.SIZE)


SHUTDOWN_SCRIPT = HEADER + '''
class Stuck(Sink):
    def write(self, text, record):
        time.sleep(60)
policy, timeout = sys.argv[1], float(sys.argv[2])
logger = Logger('matrix', logToFile=False, logToStdout=False, shutdownTimeout=timeout)
logger.add_sink('stuck', Stuck(formatter='{message}'), threaded=True, threadQueueSize=100, threadQueuePolicy=policy)
for index in range(50):
    logger.info('record {}', index)
print('logged', flush=True)
'''

FAILING_SINK_SCRIPT = HEADER + '''
class Flaky(Sink):
    def __init__(self):
        super().__init__(formatter='{message}')
        self.count = 0
    def write(self, text, record):
        self.count += 1
        if self.count % 3 == 0:
            raise RuntimeError('refused')
        return True
good = []
logger = Logger('matrix', logToFile=False, logToStdout=False)
logger.add(lambda text, record: good.append(record.message), name='good')
logger.add_sink('flaky', Flaky(), threaded=True, threadQueueSize=1000)
for index in range(300):
    logger.info('record {}', index)
print(logger.flush(timeout=20))
stats = logger.sink_stats('flaky')['delivery']
print(len(good), stats['processed'], stats['failed'])
'''


class TestShutdownAndFailures(MatrixCase):

    def test_a_program_that_ends_with_a_stuck_receiver_ends_after_the_shutdown_timeout(self):
        for policy in ('block', 'drop_newest', 'drop_oldest', 'reject'):
            started = time.time()
            done = run_script(SHUTDOWN_SCRIPT, policy, 1.0, timeout=60)
            elapsed = time.time() - started
            self.assertEqual(done.returncode, 0, f"{policy}: {done.stderr}")
            self.assertIn('logged', done.stdout)
            self.assertLess(elapsed, 30, f"{policy}: the program waited too long")
            # The program says that it left records behind, once
            self.assertIn('pysimplelog', done.stderr, f"{policy}: {done.stderr!r}")

    def test_a_sink_that_fails_for_some_records_does_not_harm_the_others(self):
        done = run_script(FAILING_SINK_SCRIPT)
        self.assertEqual(done.returncode, 0, done.stderr)
        flushed, counts = done.stdout.strip().splitlines()[-2:]
        self.assertEqual(flushed, 'True')
        good, processed, failed = [int(value) for value in counts.split()]
        self.assertEqual(good, 300)
        self.assertEqual(failed, 100)
        self.assertEqual(processed + failed, 300)

    def test_a_threaded_sink_whose_thread_ends_does_not_make_logging_hang(self):
        class Dies(Sink):
            def __init__(self):
                super().__init__(formatter=lambda record: record.message)
                self.seen = []

            def write(self, text, record):
                self.seen.append(text)
                if text == 'die':
                    raise SystemExit("the worker is told to end")

        sink = Dies()
        logger = Logger('matrix', logToFile=False, logToStdout=False)
        other = []
        logger.add(lambda text, record: other.append(record.message), name='other')
        logger.add_sink('dies', sink, threaded=True, threadQueueSize=10, threadQueuePolicy='drop_newest')
        self.addCleanup(logger.clear_sinks, 1.0)
        logger.info('die')
        finished = []

        def keep_logging():
            for index in range(50):
                logger.info('after {}', index)
            logger.flush(timeout=2.0)
            finished.append(True)

        worker = threading.Thread(target=keep_logging, daemon=True)
        worker.start()
        worker.join(WAIT_SECONDS)
        self.assertFalse(worker.is_alive(), 'logging hung after the sink thread ended')
        self.assertEqual(finished, [True])
        self.assertEqual(len(other), 51)

    def test_a_blocked_producer_is_freed_when_its_sink_is_removed(self):
        gate = Gate()
        logger = Logger('matrix', logToFile=False, logToStdout=False)
        logger.add_sink('gate', gate, threaded=True, threadQueueSize=2, threadQueuePolicy='block')
        logger.info('0')
        self.assertTrue(gate.started.wait(WAIT_SECONDS))
        finished = []

        def produce():
            for index in range(1, 10):
                logger.info(str(index))
            finished.append(True)

        producer = threading.Thread(target=produce, daemon=True)
        producer.start()
        time.sleep(0.2)
        self.assertTrue(producer.is_alive(), 'the producer should be waiting on a full queue')
        gate.opened.set()
        logger.remove_sink('gate', timeout=WAIT_SECONDS)
        producer.join(WAIT_SECONDS)
        self.assertFalse(producer.is_alive(), 'the producer was not freed')


SPOOL_CHILD = HEADER + '''
from sinks import Sink
class Receiver(Sink):
    SPOOL_DESTINATION = ('host',)
    def __init__(self):
        super().__init__(formatter=lambda record: record.message)
        self.host = 'collector.example.org'
    def write(self, text, record):
        return False
base, number, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
logger = Logger('child', logToFile=False, logToStdout=False)
logger.add_sink('c', Receiver(), threaded=True, spool={'path': base, 'id': 'matrix', 'maxBytes': 10**7, 'totalMaxBytes': 10**8,
                'retryBackoffBase': 0.05, 'retryBackoffMax': 0.1, 'ackEvery': 10**6})
for index in range(count):
    logger.info('p{}-{}', number, index)
deadline = time.time() + 20
while logger.sink_stats('c')['spool']['spooled'] < count and time.time() < deadline:
    time.sleep(0.005)
print(os.path.basename(logger.sink_stats('c')['spool']['slot']), flush=True)
# The process ends with no cleanup, as a crash does
os._exit(0)
'''


class Receiver(Sink):
    """The receiver that comes up: it keeps every record it accepts. A spool belongs to the class of its sink, so the child that
    crashed used a class of the same name that was down."""

    SPOOL_DESTINATION = ('host',)

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)
        self.host = 'collector.example.org'
        self.got = []
        self.lock = threading.Lock()

    def write(self, text, record):
        with self.lock:
            self.got.append(text.rstrip('\n'))
        return True


class TestDurableSpoolWithManyProcesses(MatrixCase):

    PROCESSES = 4
    PER_PROCESS = 40

    def crash_children(self, base):
        script = os.path.join(self.folder, 'spool_child.py')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(SPOOL_CHILD)
        children = [subprocess.Popen([sys.executable, script, base, str(number), str(self.PER_PROCESS)], stdout=subprocess.PIPE, text=True)
                    for number in range(self.PROCESSES)]
        slots = []
        for child in children:
            try:
                slots.append(child.stdout.readline().strip())
                child.wait(timeout=WAIT_SECONDS)
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=WAIT_SECONDS)
                child.stdout.close()
            self.assertEqual(child.returncode, 0)
        return slots

    def test_every_process_that_died_leaves_its_own_slot_and_none_is_lost(self):
        base = os.path.join(self.folder, 'spools')
        slots = self.crash_children(base)
        self.assertEqual(len(set(slots)), self.PROCESSES, 'two processes used the same slot')
        self.assertEqual(len(Spool.slots(base)), self.PROCESSES)
        collector = Receiver()
        logger = Logger('parent', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks, 1.0)
        logger.add_sink('c', collector, threaded=True, spool={'path': base, 'id': 'matrix', 'maxBytes': 10**7, 'totalMaxBytes': 10**8,
                                                              'retryBackoffBase': 0.05, 'retryBackoffMax': 0.1})
        result = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        self.assertEqual(result['orphans_adopted'], self.PROCESSES)
        expected = {f"p{number}-{index}" for number in range(self.PROCESSES) for index in range(self.PER_PROCESS)}
        wait_until(lambda: expected.issubset(set(collector.got)), 'the records of every process to arrive')
        # At least once: a record may arrive twice, and none may be missing
        self.assertEqual(set(collector.got), expected)
        # Within one process the order is kept
        for number in range(self.PROCESSES):
            own = [text for text in collector.got if text.startswith(f"p{number}-")]
            firsts = []
            for text in own:
                if text not in firsts:
                    firsts.append(text)
            self.assertEqual(firsts, [f"p{number}-{index}" for index in range(self.PER_PROCESS)])

    def test_a_second_adoption_finds_nothing_left_to_send(self):
        base = os.path.join(self.folder, 'spools')
        self.crash_children(base)
        collector = Receiver()
        logger = Logger('parent', logToFile=False, logToStdout=False)
        self.addCleanup(logger.clear_sinks, 1.0)
        logger.add_sink('c', collector, threaded=True, spool={'path': base, 'id': 'matrix', 'maxBytes': 10**7, 'totalMaxBytes': 10**8,
                                                              'retryBackoffBase': 0.05, 'retryBackoffMax': 0.1})
        first = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        second = logger.adopt_orphans('c', timeout=WAIT_SECONDS)
        total = self.PROCESSES * self.PER_PROCESS
        wait_until(lambda: len(collector.got) >= total, 'the records to arrive')
        # The counters of the result add up over the life of the sink, so the second call changes nothing
        self.assertEqual(first['replayed'], total)
        self.assertEqual(second['replayed'], total)
        time.sleep(0.3)
        self.assertEqual(len(collector.got), total, 'the second adoption sent records again')


if __name__ == '__main__':
    unittest.main()
