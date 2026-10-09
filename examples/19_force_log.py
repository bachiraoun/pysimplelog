"""
``force_log``: a message that must appear whatever the levels, the filters and ``disable()`` say.

Run directly::

    python3 examples/19_force_log.py
"""
import io

from pysimplelog import Logger


def run():
    audit = io.StringIO()
    logger = Logger('force-example', logToFile=False, stdoutMinLevel='error', consoleFormatter='text')
    logger.add(audit, name='audit', level='CRITICAL')

    logger.info('not written: below the level of every output')
    logger.force_log('info', 'Shutting down')                           # every output that is switched on
    logger.force_log('error', 'Audit trail broken', sinks=['audit'])    # only the output named audit

    print('the audit output received:')
    print(audit.getvalue(), end='')

    # An output that is switched off stays silent, even for a forced message
    quiet = Logger('quiet', logToFile=False, logToStdout=False)
    quiet.force_log('error', 'nobody sees this')


if __name__ == '__main__':
    run()
