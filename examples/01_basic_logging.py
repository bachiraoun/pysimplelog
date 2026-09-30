"""
Plain pysimplelog tour -- no SIEM, no contrib, just the core Logger.

Run directly::

    python3 examples/01_basic_logging.py

Shows:
    #. stdout + rotating file logging
    #. the built-in log types (debug/info/warning/error/critical)
    #. a custom log type
    #. a custom in-memory sink
    #. per-sink log-type filtering
"""
import os
import tempfile

from pysimplelog import Logger


class MemorySink:
    """A tiny custom sink that just remembers every line it receives."""

    def __init__(self):
        self.lines = []

    def write(self, record):
        """Store *record* as-is (pysimplelog's own handler contract)."""
        self.lines.append(record)


def main():
    """Run the tour end-to-end and print what happened at each step."""
    logFilePath = os.path.join(tempfile.gettempdir(), 'pysimplelog_example.log')
    logger = Logger(name='basic-example', logFile=logFilePath)

    print('--- built-in log types ---')
    logger.debug('debug details nobody needs in production')
    logger.info('server started')
    logger.warning('disk usage above 80%')
    logger.error('failed to reach payment service')
    logger.critical('database connection pool exhausted')

    print('\n--- a custom log type ---')
    logger.add_log_type('audit', name='AUDIT', level=15, color='magenta')
    logger.log('audit', 'user alice changed billing settings')

    print('\n--- a custom in-memory sink ---')
    memorySink = MemorySink()
    logger.add_sink('memory', memorySink)
    logger.info('this line goes to stdout, the file, AND the memory sink')
    logger.remove_sink('memory')
    print('memory sink captured %d line(s)' % len(memorySink.lines))

    print('\n--- per-sink log-type filtering ---')
    errorsOnlySink = MemorySink()
    logger.add_sink('errors-only', errorsOnlySink,
                     logTypeFlags={'error': True, 'critical': True}, defaultFlag=False)
    logger.info('ignored by the errors-only sink')
    logger.error('captured by the errors-only sink')
    logger.remove_sink('errors-only')
    print('errors-only sink captured %d line(s)' % len(errorsOnlySink.lines))

    logger.flush()
    print('\nlog file written to:', logFilePath)


if __name__ == '__main__':
    main()
