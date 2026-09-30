"""
SIEM (Security Information and Event Management) forwarding, console mode.

The simplest possible SIEM example: no server to stand up, because
``ConsoleTransport`` just prints instead of sending anywhere. Good first
step before pointing at a real collector -- see the tcp/udp/http examples
in this same folder for that.

Run directly::

    python3 examples/02_siem_console.py
"""
from pysimplelog import Logger
from pysimplelog.contrib import siem_sink


def main():
    """Attach a console SIEM sink, log a few things, detach cleanly."""
    logger = Logger(name='console-siem-example', logToFile=False, logToStdout=False)

    # protocol='console' prints every forwarded record instead of sending
    # it anywhere -- swap this one string for 'tcp'/'udp'/'https' later
    # and nothing else in this file needs to change.
    sink = siem_sink.quick_attach(logger, protocol='console')

    print('--- forwarding a few log lines to the console SIEM sink ---')
    logger.info('user bob logged in')
    logger.error('failed login attempt for user mallory')
    logger.critical('firewall rule tampering detected')

    logger.flush(timeout=2.0)
    siem_sink.detach(logger, sink)
    print('\ndone -- detached cleanly, no thread left running')


if __name__ == '__main__':
    main()
