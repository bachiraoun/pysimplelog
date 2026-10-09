"""
Libraries and environment: silence a noisy library by name, and set the console from the environment, without changing code.

Run directly::

    python3 examples/18_namespaces_and_environment.py
"""
import os

import pysimplelog
from pysimplelog import Logger


def run():
    # A library names its loggers with dots. The application silences the whole branch.
    library = Logger('payments.stripe', logToFile=False, consoleFormatter='text')
    library.error('visible')
    pysimplelog.disable('payments')
    library.error('silenced')
    pysimplelog.enable('payments')
    library.error('visible again')

    # The environment sets the console of a logger made with env=True. An argument you pass always wins.
    os.environ['PYSIMPLELOG_LEVEL'] = 'WARNING'
    os.environ['PYSIMPLELOG_FORMAT'] = 'json'
    os.environ['PYSIMPLELOG_COLOR'] = 'never'
    fromEnvironment = Logger('env-example', logToFile=False, env=True)
    fromEnvironment.info('below WARNING, not written')
    fromEnvironment.warning('written as JSON')

    explicit = Logger('env-example', logToFile=False, env=True, stdoutMinLevel='debug', consoleFormatter='text')
    explicit.debug('the argument wins over PYSIMPLELOG_LEVEL and PYSIMPLELOG_FORMAT')


if __name__ == '__main__':
    run()
