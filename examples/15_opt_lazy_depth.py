"""
``opt()``: advanced options behind one call, so the normal calls stay simple. Lazy values, the exception, and the caller depth.

Run directly::

    python3 examples/15_opt_lazy_depth.py
"""
from pysimplelog import Logger

calls = []


def expensive():
    calls.append(1)
    return 42


def log_for_the_framework(logger, message):
    # depth=1 reports the caller of this helper, not this helper
    logger.opt(depth=1).info(message)


def application_code(logger):
    log_for_the_framework(logger, 'something happened')


def run():
    logger = Logger('opt-example', logToFile=False, stdoutMinLevel='info', callerInfo=True,
                    consoleFormatter='{caller} {message}')

    # Lazy: the function is called only if the record is really written
    logger.opt(lazy=True).debug('Result: {}', expensive)
    print('calls after the debug call:', len(calls))
    logger.opt(lazy=True).info('Result: {}', expensive)
    print('calls after the info call: ', len(calls))

    # The caller is the line in application_code, not the helper
    application_code(logger)

    # The exception being handled, without the logger.exception() shortcut
    try:
        1 / 0
    except ZeroDivisionError:
        logger.opt(exception=True).error('Calculation failed')


if __name__ == '__main__':
    run()
