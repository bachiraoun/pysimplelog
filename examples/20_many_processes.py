"""
Many processes: each process makes its own logger after it starts, and writes a JSON Lines file of its own.

A file of its own is the pattern that is safe on every system. Several processes appending to one file is safe on Linux and
macOS, where the operating system makes an append atomic, but not on Windows, where two processes can overwrite each other.
Records of one process keep their order. Records of different processes have no order between them.

Run directly::

    python3 examples/20_many_processes.py
"""
import json
import multiprocessing
import os
import tempfile

from pysimplelog import Logger

PROCESSES = 3
RECORDS_PER_PROCESS = 100


def work(folder, number):
    # The logger is made inside the process: with spawn nothing is inherited, and with fork it is cleaner
    logger = Logger(f'worker-{number}', logToFile=False, logToStdout=False)
    logger.add(os.path.join(folder, f'worker-{number}.jsonl'), format='json')
    for index in range(RECORDS_PER_PROCESS):
        logger.info('step {}', index, worker=number)
    logger.flush()
    logger.clear_sinks()


def run():
    folder = tempfile.mkdtemp(prefix='pysimplelog-example-')
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=work, args=(folder, number)) for number in range(PROCESSES)]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    records = []
    for number in range(PROCESSES):
        with open(os.path.join(folder, f'worker-{number}.jsonl'), encoding='utf-8') as handle:
            records.extend(json.loads(line) for line in handle)
    print(f'{len(records)} records, every line complete JSON')
    for number in range(PROCESSES):
        steps = [int(record['message'].split()[1]) for record in records if record['fields']['worker'] == number]
        print(f'worker {number}: {len(steps)} records, in order: {steps == list(range(RECORDS_PER_PROCESS))}')


if __name__ == '__main__':
    run()
