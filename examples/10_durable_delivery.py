"""
Durable delivery: a sink keeps its records on disk until the receiver has them.

A collector that is down, or a program that crashes, loses nothing that was written. This script plays three parts:

1. the collector is down, so the records wait on disk;
2. the sink is removed while the collector is still down: the records are moved to the ``dead`` file, a warning says how many and
   where, and nothing stays in the spool that a later sink could send by accident;
3. a new sink on the same spool does not send them: dead letters are only sent on purpose.

Run directly::

    python3 examples/10_durable_delivery.py
"""
import os
import sys
import tempfile
import time

from pysimplelog import Logger, Sink


class Collector(Sink):
    """A stand-in for the receiver: it can be down, and it prints what it gets."""

    # Where this sink sends: a spool is only taken over by a sink with the same destination
    SPOOL_DESTINATION = ('host',)

    def __init__(self, isUp):
        super().__init__(formatter=lambda record: record.message)
        self.host = 'collector.example.org'
        self.isUp = isUp

    def write(self, text, record):
        if not self.isUp:
            return False         # "I could not deliver this, keep it"
        print(f"  received {record.fields['event_id']}  {text.strip()}")


def make_logger(spoolFolder, isUp, **options):
    logger = Logger('durable-example', logToFile=False, logToStdout=False)
    logger.add_sink('screen', sys.stdout, minLevel=15)      # shows the warning of a sink removed with records left
    settings = {'path': spoolFolder, 'id': 'example', 'maxBytes': 10 * 1024 ** 2, 'totalMaxBytes': 50 * 1024 ** 2,
                'retryBackoffBase': 0.05, 'retryBackoffMax': 0.2}
    settings.update(options)
    logger.add_sink('collector', Collector(isUp), threaded=True, spool=settings)
    return logger


def main():
    spoolFolder = os.path.join(tempfile.mkdtemp(prefix='durable-example-'), 'spool')

    print('1. The collector is down: three records are written to disk, and nothing is received')
    logger = make_logger(spoolFolder, isUp=False)
    for number in range(3):
        logger.info(f'order {number} created', order_id=number)
    time.sleep(0.3)
    stats = logger.sink_stats('collector')['spool']
    print(f"  on disk: {stats['depth']} records, {stats['retries']} tries so far")

    print('2. The sink is removed while the collector is still down: the warning says what happened to the records')
    logger.remove_sink('collector', timeout=0.2)
    deadFiles = [os.path.join(root, 'dead') for root, _, names in os.walk(spoolFolder) if 'dead' in names]
    with open(deadFiles[0], encoding='ascii') as stream:
        print(f"  dead letters on disk: {len(stream.readlines())}")

    print('3. A new sink on the same spool, with the collector up, does not send them')
    logger = make_logger(spoolFolder, isUp=True, adoptOrphans=True, adoptInterval=0.05)
    logger.info('a record of the new run')
    logger.flush()
    logger.remove_sink('collector')


if __name__ == '__main__':
    main()
