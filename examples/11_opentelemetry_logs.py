"""
OpenTelemetry logs: send records to an OTLP/HTTP receiver, in groups, with a spool.

This script plays the receiver itself, a few lines of the standard library, so it runs with nothing installed. To use it for real, give
``attach`` the address of your OpenTelemetry Collector instead of ``receiver.url``. It shows three things:

1. records arrive in one request, with their fields, context, exception and the resource that says who sent them;
2. the receiver goes down: the records wait on disk, the sink warns once, and when the receiver is back they arrive in order, each
   with the same ``log.record.uid`` it would have had the first time;
3. what ``sink_stats`` says at the end.

Run directly::

    python3 examples/11_opentelemetry_logs.py
"""
import json
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pysimplelog import Logger
from pysimplelog.contrib.otlp_sink import attach


class Receiver:
    """A minimal OTLP/HTTP receiver: it keeps the log records it is given, and it can be made to answer 503."""

    def __init__(self):
        self.records = []
        self.isDown = False
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                status = 503 if receiver.isDown else 200
                if status == 200:
                    request = json.loads(body)
                    for scope in request['resourceLogs'][0]['scopeLogs']:
                        receiver.records.extend(scope['logRecords'])
                    receiver.resource = {item['key']: next(iter(item['value'].values()))
                                         for item in request['resourceLogs'][0]['resource']['attributes']}
                self.send_response(status)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *arguments):
                pass

        self.resource = {}
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.05), daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def attributes(record):
    """The attributes of an OTLP log record as a dictionary of plain values."""
    return {item['key']: next(iter(item['value'].values())) for item in record['attributes']}


receiver = Receiver()
folder = tempfile.mkdtemp(prefix='otlp-example-')
logger = Logger('orders', logToFile=False, logToStdout=False, callerInfo=True)
attach(logger, receiver.url, resource={'service.name': 'orders', 'deployment.environment': 'example'},
       batchInterval=0.05, maxRetries=1, retryBackoffBase=0.05, retryBackoffMax=0.1,
       spool={'path': folder, 'id': 'orders-otel-example', 'maxBytes': 10 * 1024 ** 2, 'totalMaxBytes': 100 * 1024 ** 2,
              'retryBackoffBase': 0.05, 'retryBackoffMax': 0.2})

print("1. a few records")
with logger.context(request_id='r-77'):
    logger.info("Order created", order_id=123, amount=12.5)
    try:
        raise ValueError("card declined")
    except ValueError:
        logger.error("Payment failed", order_id=123, exc_info=True)
logger.flush()
print(f"   the receiver got {len(receiver.records)} records, from {receiver.resource['service.name']} "
      f"({receiver.resource['deployment.environment']})")
for record in receiver.records:
    values = attributes(record)
    print(f"   severity {record['severityNumber']:>2}  {record['body']['stringValue']!r:18} order_id={values['order_id']} "
          f"request_id={values['request_id']} {values['code.function.name']}")
print(f"   the error carries {attributes(receiver.records[1])['exception.type']}: {attributes(receiver.records[1])['exception.message']}")

print("2. the receiver goes down")
receiver.isDown = True
receiver.records.clear()
for number in range(1, 4):
    logger.info(f"while it was down {number}", n=number)
deadline = time.time() + 10
while time.time() < deadline and logger.sink_stats('otlp')['spool']['retries'] < 2:
    time.sleep(0.01)
print(f"   the receiver has {len(receiver.records)} records, {logger.sink_stats('otlp')['spool']['depth']} wait on disk, "
      f"{logger.sink_stats('otlp')['spool']['retries']} sends failed so far")
receiver.isDown = False
logger.flush(timeout=15)
print(f"   it is back: {[record['body']['stringValue'] for record in receiver.records]}")
print(f"   each has the identifier a receiver can drop a repeat by: {[attributes(record)['log.record.uid'][-2:] for record in receiver.records]}")

print("3. the numbers")
delivery = logger.sink_stats('otlp')['delivery']
print(f"   sent {delivery['sent']} records in {delivery['batches']} requests, {delivery['retries']} retried at once by the sink, "
      f"{logger.sink_stats('otlp')['spool']['retries']} sends repeated by the spool, {logger.sink_stats('otlp')['spool']['depth']} waiting")

logger.remove_sink('otlp')
receiver.stop()
shutil.rmtree(folder, ignore_errors=True)
