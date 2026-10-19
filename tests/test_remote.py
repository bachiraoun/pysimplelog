"""The receiver and the remote sink: many processes log through one logger that writes the files.

Run from the repo root::

    python3 -m unittest tests.test_remote -v

The security cases speak to the receiver with raw sockets, as an attacker or a broken program would. The multi-process case starts real
processes. Outages are real too: the receiver is stopped like a crash and a new one takes its port.
"""
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PACKAGE_DIR)
from simple_log import Logger  # noqa: E402
from sinks import Sink, FileSink  # noqa: E402
from record import LogRecord  # noqa: E402
from spool import Spool, record_to_dict  # noqa: E402
from remote import (Receiver, RemoteSink, ProtocolError, HEADER, ACK, ACK_MAX_FRAME, HANDSHAKE_MAX_FRAME,  # noqa: E402
                    send_frame, recv_frame, recv_exact, compute_mac, client_handshake, server_handshake)

# Seconds a test waits for something that must happen
WAIT_SECONDS = 15.0


def wait_until(condition, timeout=WAIT_SECONDS, what='the condition'):
    """Polls until the condition is true, and fails the test when it never is."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def free_port():
    """A port that nothing listens on."""
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class Central(Sink):
    """The sink of the logger that writes: it keeps the records it is given, and can be made to wait."""

    def __init__(self):
        super().__init__(formatter=lambda record: record.message)
        self.records = []
        self.gate = None
        self.lock = threading.Lock()

    def write(self, text, record):
        if self.gate is not None:
            self.gate.wait(WAIT_SECONDS)
        with self.lock:
            self.records.append(record)

    def messages(self):
        with self.lock:
            return [record.message for record in self.records]

    def count(self):
        with self.lock:
            return len(self.records)


class Capture(Sink):
    """Keeps the severity and the message of what reaches it."""

    def __init__(self):
        super().__init__(formatter=lambda record: f"{record.severity} {record.message}")
        self.lines = []

    def write(self, text, record):
        self.lines.append(text)

    def warnings(self):
        return [line for line in self.lines if line.startswith('WARN')]


def make_dict(index, eventId=None, timestampUs=None, logType='info', message=None):
    """A record as it travels on the wire."""
    fields = {'n': index}
    if eventId is not None:
        fields['event_id'] = eventId
    record = LogRecord.create(timestamp=datetime.now(timezone.utc), severity='INFO', logType='info', level=10.0, logger='raw',
                              message=message or f'raw {index}', processId=7, threadId=8, threadName='raw', fields=fields)
    data = record_to_dict(record)
    data['logType'] = logType
    if timestampUs is not None:
        data['ts'] = timestampUs
    return data


class RemoteTestCase(unittest.TestCase):
    """A central logger with a sink that keeps what it gets, a token, and everything cleaned up afterwards."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='remotetest-')
        self.token = secrets.token_bytes(32)
        self.loggers, self.receivers, self.sockets = [], [], []
        self.central, self.centralSink = self.make_central()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self.centralSink.gate is not None:
            self.centralSink.gate.set()
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass
        for logger in self.loggers:
            try:
                logger.clear_sinks(timeout=0.5)
            except Exception:
                pass
        for receiver in self.receivers:
            try:
                receiver.abort()
            except Exception:
                pass
        shutil.rmtree(self.root, ignore_errors=True)

    def make_central(self, sinkOptions=None, **loggerOptions):
        logger = Logger('central', logToFile=False, logToStdout=False, **loggerOptions)
        sink = Central()
        logger.add_sink('list', sink, **(sinkOptions or {}))
        return logger, sink

    def start_receiver(self, logger=None, **options):
        receiver = Receiver(logger or self.central, options.pop('token', self.token), **options)
        receiver.start()
        self.receivers.append(receiver)
        return receiver

    def make_sender(self, receiver=None, port=None, token=None, name='worker', spool=False, loggerOptions=None, **spoolOptions):
        """A logger with a capture sink and a remote sink named ``remote``; with a spool when asked."""
        logger = Logger(name, logToFile=False, logToStdout=False, **(loggerOptions or {}))
        self.loggers.append(logger)
        capture = Capture()
        logger.add_sink('cap', capture)
        port = port if port is not None else receiver.address[1]
        sink = RemoteSink('127.0.0.1', port, token or self.token, batchInterval=0.02)
        options = dict(threaded=True, threadQueuePolicy='block')
        if spool:
            settings = dict(path=os.path.join(self.root, 'spool'), id=name, maxBytes=10 ** 7, totalMaxBytes=10 ** 8,
                            retryBackoffBase=0.01, retryBackoffMax=0.05)
            settings.update(spoolOptions)
            options['spool'] = settings
        logger.add_sink('remote', sink, **options)
        return logger, capture

    def connect(self, receiver):
        sock = socket.create_connection(receiver.address, timeout=5)
        self.sockets.append(sock)
        return sock

    def authenticated(self, receiver):
        sock = self.connect(receiver)
        client_handshake(sock, self.token)
        sock.settimeout(5)
        return sock

    def send_batch(self, sock, dicts):
        send_frame(sock, json.dumps(dicts).encode('utf-8'))
        return recv_frame(sock, ACK_MAX_FRAME)

    def is_closed_by_peer(self, sock, seconds=3.0):
        """Reads what the peer sends and tells whether it closed the connection in time."""
        sock.settimeout(seconds)
        try:
            while True:
                if sock.recv(4096) == b'':
                    return True
        except socket.timeout:
            return False
        except OSError:
            return True


class TestRoundTrip(RemoteTestCase):

    def test_a_record_arrives_with_its_message_fields_time_and_origin(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver)
        original = []
        local = Sink.__new__(Sink)
        logger.info('hello {}', 'there', order=7, name='bob')
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        record = self.centralSink.records[0]
        self.assertEqual((record.message, record.severity, record.logType), ('hello there', 'INFO', 'info'))
        self.assertEqual((record.fields['order'], record.fields['name']), (7, 'bob'))
        self.assertEqual(record.fields['origin_logger'], 'worker')          # a different logger name is said
        self.assertNotIn('event_id', record.fields)                           # the id served to drop repeats, it is not written
        self.assertEqual(record.processId, os.getpid())
        self.assertEqual(record.threadName, 'MainThread')

    def test_the_time_of_the_record_is_the_time_it_was_logged_and_not_the_time_it_arrived(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver, spool=True)
        before = datetime.now(timezone.utc)
        logger.info('timed')
        after = datetime.now(timezone.utc)
        time.sleep(0.5)                                                       # it arrives later
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        stamp = self.centralSink.records[0].timestamp
        self.assertTrue(before.timestamp() - 0.001 <= stamp.timestamp() <= after.timestamp() + 0.001)

    def test_the_origin_logger_is_not_said_when_the_names_are_the_same(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver, name='central')
        logger.info('same name')
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        self.assertNotIn('origin_logger', self.centralSink.records[0].fields)

    def test_a_log_type_the_central_logger_does_not_know_is_written_as_info_and_keeps_its_own_name(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver)
        logger.add_log_type('billing', name='BILLING', level=25)
        logger.log('billing', 'an invoice')
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        record = self.centralSink.records[0]
        self.assertEqual((record.message, record.logType), ('an invoice', 'info'))
        self.assertEqual(record.fields['origin_log_type'], 'billing')

    def test_a_log_type_both_know_is_kept(self):
        for logger in (self.central,):
            logger.add_log_type('billing', name='BILLING', level=25)
        receiver = self.start_receiver()
        sender, _ = self.make_sender(receiver)
        sender.add_log_type('billing', name='BILLING', level=25)
        sender.log('billing', 'an invoice')
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        record = self.centralSink.records[0]
        self.assertEqual(record.logType, 'billing')
        self.assertNotIn('origin_log_type', record.fields)

    def test_an_exception_arrives_with_its_text(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver)
        try:
            1 / 0
        except ZeroDivisionError:
            logger.error('it failed', exc_info=True)
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        exception = self.centralSink.records[0].exception
        self.assertIsNotNone(exception)
        self.assertIn('ZeroDivisionError', exception.stacktrace)

    def test_text_that_is_not_plain_ascii_and_a_very_long_message_arrive_intact(self):
        central, sink = self.make_central(maxMessageSize=None)          # a logger cuts a message at 10000 characters unless told not to
        receiver = self.start_receiver(central)
        logger, _ = self.make_sender(receiver, spool=True, loggerOptions={'maxMessageSize': None})
        long = 'x' * 300000
        logger.info('héllo wörld ✓ 日本語')
        logger.info(long)
        wait_until(lambda: sink.count() == 2, what='both records')
        self.assertEqual(sink.messages(), ['héllo wörld ✓ 日本語', long])

    def test_a_message_over_the_limit_of_the_sender_arrives_cut_like_it_would_be_locally(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver)
        logger.info('y' * 50000)
        wait_until(lambda: self.centralSink.count() == 1, what='the record')
        self.assertTrue(self.centralSink.messages()[0].endswith('[truncated]'))

    def test_many_records_arrive_in_the_order_they_were_logged(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver)
        for index in range(2000):
            logger.info(f'm{index}')
        wait_until(lambda: self.centralSink.count() == 2000, what='all the records')
        self.assertEqual(self.centralSink.messages(), [f'm{index}' for index in range(2000)])

    def test_a_record_goes_through_the_routing_of_the_central_logger_like_any_other(self):
        central, sink = self.make_central(sinkOptions={'minLevel': 30})        # this sink only wants warnings and above
        receiver = self.start_receiver(central)
        logger, _ = self.make_sender(receiver)
        logger.info('quiet')
        logger.error('loud')
        wait_until(lambda: sink.count() >= 1, what='the loud record')
        time.sleep(0.3)
        self.assertEqual(sink.messages(), ['loud'])

    def test_a_record_goes_through_the_processors_of_the_central_logger(self):
        central, sink = self.make_central()
        central.add_processor(lambda record: record._replace(message=record.message.replace('secret', '<hidden>')))
        receiver = self.start_receiver(central)
        logger, _ = self.make_sender(receiver)
        logger.info('the secret is here')
        wait_until(lambda: sink.count() == 1, what='the record')
        self.assertEqual(sink.messages(), ['the <hidden> is here'])


SENDER_SCRIPT = '''
import os, sys, time
sys.path.insert(0, sys.argv[1])
from simple_log import Logger
from remote import RemoteSink

host, port, token, name, count = sys.argv[2], int(sys.argv[3]), bytes.fromhex(sys.argv[4]), sys.argv[5], int(sys.argv[6])
logger = Logger(name, logToFile=False, logToStdout=False)
logger.add_sink('remote', RemoteSink(host, port, token, batchInterval=0.02), threaded=True, threadQueuePolicy='block')
for index in range(count):
    logger.info(f'{name} record {index}', sender=name, seq=index)
logger.remove_sink('remote', timeout=30)
print(os.getpid(), flush=True)
'''


class TestManyProcesses(RemoteTestCase):

    def test_several_processes_write_through_one_logger_into_correctly_rolled_files(self):
        folder = os.path.join(self.root, 'central')
        central = Logger('central', logToFile=False, logToStdout=False)
        limitMb = 0.05
        central.add_sink('file', FileSink(os.path.join(folder, 'out'), extension='log', formatter=None, flush='none', maxSize=limitMb))
        receiver = self.start_receiver(central)
        host, port = receiver.address
        names = [f's{number}' for number in range(6)]
        processes = [subprocess.Popen([sys.executable, '-c', SENDER_SCRIPT, PACKAGE_DIR, host, str(port), self.token.hex(), name, '600'],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for name in names]
        pids = set()
        for process in processes:
            output, error = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, error)
            pids.add(int(output.strip()))
        receiver.stop(timeout=10)
        central.remove_sink('file')
        files = sorted(os.listdir(folder), key=lambda name: int(name.rsplit('_', 1)[1].split('.')[0]))
        self.assertGreater(len(files), 3)                                    # the limit was crossed many times
        perSender, writers = {name: [] for name in names}, set()
        for name in files:
            self.assertLess(os.path.getsize(os.path.join(folder, name)), limitMb * 1024 * 1024 + 2048)    # one record over, at most
            with open(os.path.join(folder, name), encoding='utf-8') as stream:
                for line in stream:
                    data = json.loads(line)
                    perSender[data['fields']['sender']].append(data['fields']['seq'])
                    writers.add(data['process']['id'])
        for name in names:
            self.assertEqual(perSender[name], list(range(600)))              # complete, once, in order
        self.assertEqual(writers, pids)                                      # each line keeps the process that logged it
        self.assertEqual(receiver.stats['written'], 3600)


class TestSecurity(RemoteTestCase):

    def test_a_token_that_is_not_bytes_or_is_too_short_is_refused(self):
        for token in ('a text token that is long enough', b'short', None, 12345):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    Receiver(self.central, token)

    def test_a_client_with_the_wrong_token_is_dropped_and_nothing_it_sends_is_written(self):
        receiver = self.start_receiver()
        sock = self.connect(receiver)
        with self.assertRaises((ProtocolError, ConnectionError, OSError)):
            client_handshake(sock, secrets.token_bytes(32))
        wait_until(lambda: receiver.stats.get('rejected', 0) == 1, what='the rejection')
        self.assertEqual(self.centralSink.count(), 0)

    def test_a_sender_with_the_wrong_token_keeps_its_records_and_the_receiver_writes_none(self):
        receiver = self.start_receiver()
        logger, capture = self.make_sender(receiver, token=secrets.token_bytes(32), spool=True)
        logger.info('secret')
        wait_until(lambda: receiver.stats.get('rejected', 0) >= 2, what='repeated rejections')
        self.assertEqual(self.centralSink.count(), 0)
        self.assertEqual(logger.sink_stats('remote')['spool']['depth'], 1)

    def test_a_silent_connection_is_dropped_after_the_handshake_time_and_does_not_hold_up_a_good_one(self):
        receiver = self.start_receiver(handshakeTimeout=0.5)
        silent = self.connect(receiver)
        logger, _ = self.make_sender(receiver)
        logger.info('through')
        wait_until(lambda: self.centralSink.count() == 1, timeout=3, what='the good record')
        self.assertTrue(self.is_closed_by_peer(silent, seconds=3))

    def test_random_bytes_are_dropped(self):
        receiver = self.start_receiver()
        sock = self.connect(receiver)
        sock.sendall(secrets.token_bytes(200))
        self.assertTrue(self.is_closed_by_peer(sock))

    def test_a_handshake_cut_short_is_dropped(self):
        receiver = self.start_receiver()
        sock = self.connect(receiver)
        recv_frame(sock, HANDSHAKE_MAX_FRAME)
        sock.sendall(HEADER.pack(64) + b'only a few bytes')
        sock.close()
        wait_until(lambda: receiver.stats.get('accepted', 0) == 0 and len(receiver._connections) == 0, what='the connection to end')

    def test_a_handshake_answer_of_the_wrong_size_is_dropped(self):
        receiver = self.start_receiver()
        sock = self.connect(receiver)
        recv_frame(sock, HANDSHAKE_MAX_FRAME)
        send_frame(sock, b'x' * 10)
        self.assertTrue(self.is_closed_by_peer(sock))

    def test_a_handshake_frame_declared_larger_than_allowed_is_dropped_without_being_read(self):
        receiver = self.start_receiver()
        sock = self.connect(receiver)
        recv_frame(sock, HANDSHAKE_MAX_FRAME)
        sock.sendall(HEADER.pack(10 ** 9))
        self.assertTrue(self.is_closed_by_peer(sock))

    def test_a_batch_declared_larger_than_the_limit_is_dropped_before_it_is_read(self):
        receiver = self.start_receiver(maxFrame=1000)
        sock = self.authenticated(receiver)
        sock.sendall(HEADER.pack(5000))
        self.assertTrue(self.is_closed_by_peer(sock))
        self.assertEqual(self.centralSink.count(), 0)

    def test_a_recorded_answer_cannot_be_used_again(self):
        receiver = self.start_receiver()
        first = self.connect(receiver)
        serverNonce = recv_frame(first, HANDSHAKE_MAX_FRAME)
        clientNonce = secrets.token_bytes(32)
        answer = clientNonce + compute_mac(self.token, b'client', serverNonce, clientNonce)
        send_frame(first, answer)
        recv_frame(first, HANDSHAKE_MAX_FRAME)                       # the first use is accepted
        second = self.connect(receiver)
        recv_frame(second, HANDSHAKE_MAX_FRAME)                      # a new challenge
        send_frame(second, answer)                                    # the recorded answer
        self.assertTrue(self.is_closed_by_peer(second))

    def test_an_answer_made_for_the_other_side_is_not_accepted(self):
        receiver = self.start_receiver()
        sock = self.connect(receiver)
        serverNonce = recv_frame(sock, HANDSHAKE_MAX_FRAME)
        clientNonce = secrets.token_bytes(32)
        send_frame(sock, clientNonce + compute_mac(self.token, b'server', serverNonce, clientNonce))      # the label of the server
        self.assertTrue(self.is_closed_by_peer(sock))

    def test_a_client_sends_nothing_to_a_server_that_does_not_know_the_token(self):
        rogue = socket.socket()
        rogue.bind(('127.0.0.1', 0))
        rogue.listen(1)
        self.sockets.append(rogue)
        received = {'bytes': 0}

        def serve():
            connection, _ = rogue.accept()
            self.sockets.append(connection)
            send_frame(connection, secrets.token_bytes(32))
            recv_frame(connection, HANDSHAKE_MAX_FRAME)
            send_frame(connection, secrets.token_bytes(32))              # a made-up proof
            connection.settimeout(1.5)
            try:
                received['bytes'] = len(connection.recv(65536))
            except (socket.timeout, OSError):
                pass

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        logger, _ = self.make_sender(port=rogue.getsockname()[1], spool=True)
        logger.info('private')
        thread.join(timeout=10)
        self.assertEqual(received['bytes'], 0)
        self.assertEqual(logger.sink_stats('remote')['spool']['depth'], 1)

    def test_a_batch_that_is_not_json_is_refused_and_the_connection_ends(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        send_frame(sock, b'this is not json')
        self.assertTrue(self.is_closed_by_peer(sock))
        self.assertEqual(self.centralSink.count(), 0)

    def test_a_batch_that_is_not_a_list_of_records_is_not_confirmed(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        send_frame(sock, b'{"a": 1}')
        self.assertTrue(self.is_closed_by_peer(sock))
        wait_until(lambda: receiver.stats.get('write_errors', 0) == 1, what='the error to be counted')
        self.assertEqual(self.centralSink.count(), 0)

    def test_a_bad_record_among_good_ones_is_counted_and_the_good_ones_are_written_and_confirmed(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        bad = make_dict(1)
        del bad['ts']
        self.assertEqual(self.send_batch(sock, [make_dict(0), bad, make_dict(2)]), ACK)
        self.assertEqual(self.centralSink.messages(), ['raw 0', 'raw 2'])
        self.assertEqual(receiver.stats['bad_records'], 1)

    def test_a_hundred_bad_connections_do_not_stop_a_good_one(self):
        receiver = self.start_receiver(handshakeTimeout=0.5)
        for _ in range(100):
            sock = self.connect(receiver)
            sock.sendall(secrets.token_bytes(10))
        logger, _ = self.make_sender(receiver)
        logger.info('still served')
        wait_until(lambda: self.centralSink.count() == 1, what='the good record')

    def test_a_hundred_good_connections_at_once(self):
        receiver = self.start_receiver()
        socks = [self.authenticated(receiver) for _ in range(100)]
        for number, sock in enumerate(socks):
            self.assertEqual(self.send_batch(sock, [make_dict(number)]), ACK)
        self.assertEqual(self.centralSink.count(), 100)
        self.assertEqual(receiver.stats['accepted'], 100)


class TestDelivery(RemoteTestCase):

    def test_a_batch_is_confirmed_only_after_it_is_written(self):
        self.centralSink.gate = threading.Event()                      # the central logger cannot write
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver, spool=True)
        for index in range(10):
            logger.info(f'm{index}')
        time.sleep(0.6)
        self.assertEqual(logger.sink_stats('remote')['spool']['depth'], 10)       # nothing was confirmed
        self.centralSink.gate.set()
        wait_until(lambda: logger.sink_stats('remote')['spool']['depth'] == 0, what='the batch to be confirmed')
        self.assertEqual(self.centralSink.messages(), [f'm{index}' for index in range(10)])

    def test_a_record_that_arrives_twice_is_written_once(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        batch = [make_dict(index, eventId=f'e{index}') for index in range(5)]
        self.assertEqual(self.send_batch(sock, batch), ACK)
        self.assertEqual(self.send_batch(sock, batch), ACK)                # the same batch again, as a retry would
        self.assertEqual(self.centralSink.messages(), [f'raw {index}' for index in range(5)])
        self.assertEqual(receiver.stats['repeats'], 5)

    def test_the_memory_of_repeats_is_bounded(self):
        receiver = self.start_receiver(dedupeSize=5)
        sock = self.authenticated(receiver)
        self.send_batch(sock, [make_dict(index, eventId=f'e{index}') for index in range(10)])
        self.send_batch(sock, [make_dict(0, eventId='e0')])                # forgotten, so written again
        self.send_batch(sock, [make_dict(9, eventId='e9')])                # remembered
        self.assertEqual(self.centralSink.count(), 11)

    def test_records_without_an_id_are_never_taken_for_repeats(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        batch = [make_dict(0), make_dict(0)]
        self.send_batch(sock, batch)
        self.assertEqual(self.centralSink.count(), 2)

    def test_the_name_of_the_id_field_can_be_changed(self):
        receiver = self.start_receiver(eventIdField='uid')
        sock = self.authenticated(receiver)
        one, two = make_dict(0), make_dict(0)
        one['fields']['uid'] = two['fields']['uid'] = 'same'
        self.send_batch(sock, [one, two])
        self.assertEqual(self.centralSink.count(), 1)
        self.assertNotIn('uid', self.centralSink.records[0].fields)

    def test_records_are_sorted_by_their_time_when_a_window_is_asked_for(self):
        receiver = self.start_receiver(reorderWindow=0.3)
        sock = self.authenticated(receiver)
        base = int((time.time() - 60) * 1e6)
        self.assertEqual(self.send_batch(sock, [make_dict(index, timestampUs=base + offset)
                                                for index, offset in ((0, 300), (1, 100), (2, 200))]), ACK)
        wait_until(lambda: self.centralSink.count() == 3, what='the records')
        self.assertEqual(self.centralSink.messages(), ['raw 1', 'raw 2', 'raw 0'])

    def test_records_keep_their_arrival_order_without_a_window(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        base = int((time.time() - 60) * 1e6)
        self.send_batch(sock, [make_dict(index, timestampUs=base + offset) for index, offset in ((0, 300), (1, 100), (2, 200))])
        self.assertEqual(self.centralSink.messages(), ['raw 0', 'raw 1', 'raw 2'])

    def test_a_receiver_that_starts_after_the_sender_receives_everything_the_spool_kept(self):
        port = free_port()
        logger, _ = self.make_sender(port=port, spool=True)
        for index in range(40):
            logger.info(f'm{index}')
        time.sleep(0.3)
        self.assertEqual(logger.sink_stats('remote')['spool']['depth'], 40)
        receiver = Receiver(self.central, self.token, port=port)
        receiver.start()
        self.receivers.append(receiver)
        wait_until(lambda: self.centralSink.count() == 40, what='the spool to be sent')
        self.assertEqual(self.centralSink.messages(), [f'm{index}' for index in range(40)])

    def test_a_receiver_that_stops_like_a_crash_and_comes_back_loses_nothing(self):
        first = self.start_receiver()
        port = first.address[1]
        logger, _ = self.make_sender(first, spool=True)
        for index in range(150):
            logger.info(f'm{index}')
            if index == 60:
                first.abort()
            time.sleep(0.002)
        second = Receiver(self.central, self.token, port=port)
        second.start()
        self.receivers.append(second)
        wanted = {f'm{index}' for index in range(150)}
        wait_until(lambda: wanted <= set(self.centralSink.messages()), what='every record to arrive')
        messages = self.centralSink.messages()
        self.assertLessEqual(len(messages) - len(set(messages)), 100)         # a batch can be sent again, nothing more
        wait_until(lambda: logger.sink_stats('remote')['spool']['depth'] == 0, what='the spool to be empty')

    def test_the_sender_goes_on_through_a_restart_of_the_receiver(self):
        first = self.start_receiver()
        port = first.address[1]
        logger, _ = self.make_sender(first, spool=True)
        logger.info('before')
        wait_until(lambda: self.centralSink.count() == 1, what='the first record')
        first.stop(timeout=5)
        second = Receiver(self.central, self.token, port=port)
        second.start()
        self.receivers.append(second)
        logger.info('after')
        wait_until(lambda: 'after' in self.centralSink.messages(), what='the record after the restart')

    def test_the_sender_does_not_wait_for_a_receiver_that_is_down(self):
        logger, _ = self.make_sender(port=free_port(), spool=True)
        started = time.monotonic()
        for index in range(500):
            logger.info(f'm{index}')
        self.assertLess(time.monotonic() - started, 5.0)


class TestStopping(RemoteTestCase):

    def test_an_idle_receiver_writes_nothing_and_stops_at_once(self):
        threadsBefore = threading.active_count()
        receiver = Receiver(self.central, self.token)
        receiver.start()
        time.sleep(0.3)
        started = time.monotonic()
        receiver.stop(timeout=5)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual((receiver.stats, self.centralSink.count()), ({}, 0))
        wait_until(lambda: threading.active_count() <= threadsBefore, what='the threads to end')

    def test_stop_writes_everything_that_was_received(self):
        receiver = self.start_receiver()
        logger, _ = self.make_sender(receiver)
        for index in range(1000):
            logger.info(f'm{index}')
        logger.remove_sink('remote', timeout=10)
        receiver.stop(timeout=10)
        self.assertEqual(self.centralSink.messages(), [f'm{index}' for index in range(1000)])

    def test_stop_waits_for_a_connected_sender_up_to_its_time_and_then_closes_the_connection(self):
        receiver = self.start_receiver()
        sock = self.authenticated(receiver)
        started = time.monotonic()
        receiver.stop(timeout=0.5)
        elapsed = time.monotonic() - started
        self.assertTrue(0.4 <= elapsed < 4.0, elapsed)
        self.assertTrue(self.is_closed_by_peer(sock, seconds=2))

    def test_abort_is_immediate_and_closes_every_connection(self):
        receiver = self.start_receiver()
        socks = [self.authenticated(receiver) for _ in range(5)]
        started = time.monotonic()
        receiver.abort()
        self.assertLess(time.monotonic() - started, 3.0)
        for sock in socks:
            self.assertTrue(self.is_closed_by_peer(sock, seconds=2))

    def test_a_port_that_is_in_use_is_refused(self):
        receiver = self.start_receiver()
        with self.assertRaises(OSError):
            Receiver(self.central, self.token, port=receiver.address[1])

    def test_the_address_is_the_local_machine_unless_told_otherwise(self):
        receiver = self.start_receiver()
        self.assertEqual(receiver.address[0], '127.0.0.1')


class TestRemovingARemoteSink(RemoteTestCase):

    def test_removing_it_while_the_receiver_is_up_delivers_everything_and_says_nothing(self):
        receiver = self.start_receiver()
        logger, capture = self.make_sender(receiver, spool=True)
        for index in range(300):
            logger.info(f'm{index}')
        logger.remove_sink('remote')
        self.assertEqual(self.centralSink.messages(), [f'm{index}' for index in range(300)])
        self.assertEqual(capture.warnings(), [])

    def test_removing_it_while_the_receiver_is_down_makes_dead_letters_and_says_how_many(self):
        logger, capture = self.make_sender(port=free_port(), spool=True)
        for index in range(5):
            logger.info(f'm{index}')
        logger.remove_sink('remote', timeout=0.4)
        self.assertEqual(len(capture.warnings()), 1)
        self.assertIn('5 undelivered records', capture.warnings()[0])
        slot = os.listdir(os.path.join(self.root, 'spool'))[0]
        with open(os.path.join(self.root, 'spool', slot, 'dead'), encoding='ascii') as stream:
            self.assertEqual([json.loads(line)['record']['message'] for line in stream], [f'm{index}' for index in range(5)])

    def test_removing_it_with_purge_leaves_nothing_on_disk(self):
        logger, capture = self.make_sender(port=free_port(), spool=True, onRemove='purge')
        for index in range(5):
            logger.info(f'm{index}')
        logger.remove_sink('remote', timeout=0.4)
        self.assertIn('Action: purge', capture.warnings()[0])
        self.assertFalse(os.path.exists(os.path.join(self.root, 'spool')) and any(os.scandir(os.path.join(self.root, 'spool'))))

    def test_a_batch_the_receiver_refuses_for_its_size_is_kept_and_then_dead_lettered(self):
        receiver = self.start_receiver(maxFrame=1000)
        logger, capture = self.make_sender(receiver, spool=True)
        logger.info('x' * 5000)
        wait_until(lambda: receiver.stats.get('rejected', 0) >= 1, what='the refusal')
        self.assertEqual(self.centralSink.count(), 0)
        logger.remove_sink('remote', timeout=0.4)
        self.assertIn('1 undelivered records', capture.warnings()[0])

    def test_adding_and_removing_it_many_times_against_one_receiver(self):
        receiver = self.start_receiver()
        logger = Logger('cycles', logToFile=False, logToStdout=False)
        self.loggers.append(logger)
        threadsBefore = threading.active_count()
        for cycle in range(15):
            logger.add_sink('remote', RemoteSink('127.0.0.1', receiver.address[1], self.token, batchInterval=0.01), threaded=True,
                            spool=dict(path=os.path.join(self.root, 'spool'), id=f'cycle{cycle % 3}', maxBytes=10 ** 7,
                                       totalMaxBytes=10 ** 8, retryBackoffBase=0.01, retryBackoffMax=0.05))
            for index in range(20):
                logger.info(f'{cycle}-{index}')
            logger.remove_sink('remote')
        self.assertEqual(self.centralSink.count(), 300)
        self.assertEqual(receiver.stats['accepted'], 15)
        self.assertLessEqual(threading.active_count(), threadsBefore + 2)
        self.assertEqual(os.listdir(os.path.join(self.root, 'spool')), [])

    def test_the_remote_sink_cannot_be_given_a_wrong_batch_size(self):
        with self.assertRaises(ValueError):
            RemoteSink('127.0.0.1', 1, self.token, batchSize=0)
        with self.assertRaises(TypeError):
            RemoteSink('127.0.0.1', 1, self.token, batchSize='many')


if __name__ == '__main__':
    unittest.main()
