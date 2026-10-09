"""
Many processes: each process makes its own logger after it starts, and all of them append to one JSON Lines file.

Records of one thread keep their order. Records of different processes have no order between them.

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


def work(path, number):
    # The logger is made inside the process: with spawn nothing is inherited, and with fork it is cleaner
    logger = Logger(f'worker-{number}', logToFile=False, logToStdout=False)
    logger.add(path, format='json')
    for index in range(RECORDS_PER_PROCESS):
        logger.info('step {}', index, worker=number)
    logger.flush()
    logger.clear_sinks()


def run():
    folder = tempfile.mkdtemp(prefix='pysimplelog-example-')
    path = os.path.join(folder, 'all.jsonl')
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=work, args=(path, number)) for number in range(PROCESSES)]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    with open(path, encoding='utf-8') as handle:
        records = [json.loads(line) for line in handle]
    print(f'{len(records)} records, every line complete JSON')
    for number in range(PROCESSES):
        steps = [int(record['message'].split()[1]) for record in records if record['fields']['worker'] == number]
        print(f'worker {number}: {len(steps)} records, in order: {steps == list(range(RECORDS_PER_PROCESS))}')


if __name__ == '__main__':
    run()
