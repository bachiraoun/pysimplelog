"""
Standard logging: libraries log with Python's ``logging`` package. ``redirect_standard_logging`` sends their
records through the same processors, filters and sinks as the records of a pysimplelog Logger.

Run directly::

    python3 examples/08_standard_logging.py
"""
import logging

from pysimplelog import Logger, redact_fields, redirect_standard_logging, restore_standard_logging


def main():
    # One JSON object per line, so every record of the application and of its libraries looks the same.
    logger = Logger('standard-logging-example', logToFile=False, consoleFormatter=None)
    # Secrets are hidden for everything that reaches the logger, also what a library logs.
    logger.add_processor(redact_fields())

    # 1. Nothing is redirected yet: a library record goes where the standard library sends it.
    # 2. From here, the root logger takes INFO and above, and gives every record to the logger.
    handler = redirect_standard_logging(logger, loggerLevel=logging.INFO)

    print('--- a library record: the standard logger name and extra= become fields ---')
    logging.getLogger('urllib3.connectionpool').info('Starting new HTTPS connection (%d): example.com', 1)
    logging.getLogger('my-lib').warning('disk almost full: %s%%', 93, extra={'disk': '/data', 'token': 'abc'})

    print('\n--- logging.exception keeps the type, the message and the traceback ---')
    try:
        1 / 0
    except ZeroDivisionError:
        logging.getLogger('my-lib').exception('calculation failed')

    print('\n--- a record of the logger itself, next to them ---')
    logger.info('application started', version='6.0')

    restore_standard_logging(handler)


if __name__ == '__main__':
    main()
