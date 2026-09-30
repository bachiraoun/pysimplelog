"""
SIEM (Security Information and Event Management) forwarding over UDP syslog.

Spins up a tiny fake UDP syslog collector on localhost so this example is
fully self-contained -- no real SIEM infrastructure needed to see it work.
In a real deployment you'd point *host*/*port* at your actual collector
instead.

Run directly::

    python3 examples/03_siem_udp.py
"""
import socket
import threading
import time

from pysimplelog import Logger
from pysimplelog.contrib import siem_sink


class FakeUdpSiemServer:
    """A minimal UDP syslog receiver: reads datagrams, prints them.

    Real SIEM/syslog collectors (rsyslog, syslog-ng, Splunk's UDP input,
    etc.) all speak this same fire-and-forget UDP protocol -- this class
    exists only so the example has something to send to.
    """

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1', 0))   # let the OS pick a free port
        self.host, self.port = self.socket.getsockname()
        self.received = []
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        self.socket.settimeout(0.2)
        while not self._stopped.is_set():
            try:
                data, _ = self.socket.recvfrom(65535)
            except socket.timeout:
                continue
            line = data.decode('utf-8', 'replace')
            self.received.append(line)
            print('[fake SIEM server] received:', line)

    def start(self):
        """Start listening in a background thread."""
        self._thread.start()

    def stop(self):
        """Stop listening and release the socket."""
        self._stopped.set()
        self._thread.join(timeout=2.0)
        self.socket.close()


def main():
    """Start the fake server, forward some logs to it, then shut down."""
    server = FakeUdpSiemServer()
    server.start()
    print('fake UDP SIEM server listening on %s:%d\n' % (server.host, server.port))

    logger = Logger(name='udp-siem-example', logToFile=False, logToStdout=False)
    sink = siem_sink.quick_attach(logger, protocol='udp', host=server.host, port=server.port)

    logger.info('user bob logged in')
    logger.error('failed login attempt for user mallory')
    logger.critical('firewall rule tampering detected')

    logger.flush(timeout=2.0)
    time.sleep(0.2)   # UDP has no delivery guarantee -- give the datagrams a moment to land
    siem_sink.detach(logger, sink)
    server.stop()

    print('\nserver received %d message(s) total' % len(server.received))


if __name__ == '__main__':
    main()
