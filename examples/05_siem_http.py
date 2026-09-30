"""
SIEM (Security Information and Event Management) forwarding over HTTP(S).

Spins up a tiny fake HTTP collector on localhost using only the standard
library's ``http.server`` -- fully self-contained; in a real deployment
you'd point *url* at your actual collector (e.g. Splunk's HTTP Event
Collector, an Elastic ingest endpoint, or a custom webhook).

Run directly::

    python3 examples/05_siem_http.py
"""
import http.server
import json
import threading

from pysimplelog import Logger
from pysimplelog.contrib import siem_sink


class _FakeSiemHttpHandler(http.server.BaseHTTPRequestHandler):
    """Reads the JSON body ``HTTPTransport`` POSTs and prints it."""

    received = []   # class-level: shared across requests, read by the example after the run

    def do_POST(self):
        """Accept one POST, print its JSON body, reply 200 OK."""
        contentLength = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(contentLength)
        event = json.loads(body.decode('utf-8'))
        self.received.append(event)
        print('[fake SIEM server] received:', event)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        """Silence http.server's default per-request console noise."""


class FakeHttpSiemServer:
    """Thin wrapper around ``http.server.HTTPServer`` for this example."""

    def __init__(self):
        _FakeSiemHttpHandler.received = []
        self.server = http.server.HTTPServer(('127.0.0.1', 0), _FakeSiemHttpHandler)
        self.host, self.port = self.server.server_address
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        """Full collector URL to hand to quick_attach()."""
        return f'http://{self.host}:{self.port}/collect'

    @property
    def received(self):
        """Every event the fake server has received so far."""
        return _FakeSiemHttpHandler.received

    def start(self):
        """Start serving requests in a background thread."""
        self._thread.start()

    def stop(self):
        """Stop serving and release the listening socket."""
        self.server.shutdown()
        self._thread.join(timeout=2.0)
        self.server.server_close()


def main():
    """Start the fake server, forward some logs to it, then shut down."""
    server = FakeHttpSiemServer()
    server.start()
    print('fake HTTP SIEM server listening at %s\n' % server.url)

    logger = Logger(name='http-siem-example', logToFile=False, logToStdout=False)
    sink = siem_sink.quick_attach(logger, protocol='http', url=server.url)

    logger.info('user bob logged in')
    logger.error('failed login attempt for user mallory')
    logger.critical('firewall rule tampering detected')

    logger.flush(timeout=2.0)
    siem_sink.detach(logger, sink)
    server.stop()

    print('\nserver received %d message(s) total' % len(server.received))


if __name__ == '__main__':
    main()
