"""
SIEM (Security Information and Event Management) forwarding over TCP syslog.

Spins up a tiny fake TCP syslog collector on localhost that understands
RFC 6587 octet-counting framing (``"<byte-length> <message>"``) -- the
same framing ``TCPSyslogTransport`` sends. Fully self-contained; in a
real deployment you'd point *host*/*port* at your actual collector.

Run directly::

    python3 examples/04_siem_tcp.py
"""
import socket
import threading

from pysimplelog import Logger
from pysimplelog.contrib import siem_sink


class FakeTcpSiemServer:
    """A minimal RFC 6587 octet-counting TCP syslog receiver.

    Reads the ASCII length prefix before each message, then reads
    exactly that many bytes -- the only TCP syslog framing that stays
    unambiguous even when a message contains embedded newlines.
    """

    def __init__(self):
        self.listenSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listenSocket.bind(('127.0.0.1', 0))
        self.listenSocket.listen(1)
        self.host, self.port = self.listenSocket.getsockname()
        self.received = []
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)

    def _accept_loop(self):
        self.listenSocket.settimeout(0.2)
        while not self._stopped.is_set():
            try:
                connection, _ = self.listenSocket.accept()
            except socket.timeout:
                continue
            with connection:
                self._read_frames(connection)

    def _read_frames(self, connection):
        buffer = b''
        connection.settimeout(0.2)
        while not self._stopped.is_set():
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                return
            buffer += chunk
            buffer = self._drain_complete_frames(buffer)

    def _drain_complete_frames(self, buffer):
        while b' ' in buffer:
            lengthPrefix, _, rest = buffer.partition(b' ')
            if not lengthPrefix.isdigit():
                return buffer   # not a full length prefix yet
            frameLength = int(lengthPrefix)
            if len(rest) < frameLength:
                return buffer   # message body not fully arrived yet
            message = rest[:frameLength].decode('utf-8', 'replace')
            self.received.append(message)
            print('[fake SIEM server] received:', message)
            buffer = rest[frameLength:]
        return buffer

    def start(self):
        """Start accepting connections in a background thread."""
        self._thread.start()

    def stop(self):
        """Stop accepting connections and release the listening socket."""
        self._stopped.set()
        self._thread.join(timeout=2.0)
        self.listenSocket.close()


def main():
    """Start the fake server, forward some logs to it, then shut down."""
    server = FakeTcpSiemServer()
    server.start()
    print('fake TCP SIEM server listening on %s:%d\n' % (server.host, server.port))

    logger = Logger(name='tcp-siem-example', logToFile=False, logToStdout=False)
    sink = siem_sink.quick_attach(logger, protocol='tcp', host=server.host, port=server.port)

    logger.info('user bob logged in')
    logger.error('failed login attempt for user mallory')
    logger.critical('firewall rule tampering detected')

    logger.flush(timeout=2.0)
    siem_sink.detach(logger, sink)
    server.stop()

    print('\nserver received %d message(s) total' % len(server.received))


if __name__ == '__main__':
    main()
