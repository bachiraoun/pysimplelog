"""Sends the records of many processes to one logger over a local network connection, so that a single process writes the files."""

import collections
import hashlib
import heapq
import hmac
import json
import queue
import secrets
import socket
import struct
import threading
import time

try:
    from .sinks import Sink
    from .spool import record_to_dict, record_from_dict
except ImportError:
    from sinks import Sink
    from spool import record_to_dict, record_from_dict

HEADER = struct.Struct('>I')
MAX_FRAME = 8 * 1024 * 1024
HANDSHAKE_MAX_FRAME = 128
ACK_MAX_FRAME = 16
ACK = b'OK'
NONCE_SIZE = 32
MAC_SIZE = 32


class ProtocolError(Exception):
    """Raised when a peer breaks the protocol or fails the handshake."""


def recv_exact(sock, size):
    """
    Reads exactly *size* bytes from a socket.

    :Parameters:
        #. sock (socket.socket): The connected socket.
        #. size (int): Number of bytes to read.

    :Returns:
        #. data (bytes): The bytes read.

    :Raises:
        #. ConnectionError: If the peer closes the connection before *size* bytes arrive.
    """
    buffer = bytearray(size)
    view = memoryview(buffer)
    received = 0
    while received < size:
        count = sock.recv_into(view[received:], size - received)
        if count == 0:
            raise ConnectionError('connection closed')
        received += count
    return bytes(buffer)


def send_frame(sock, payload):
    """
    Sends a payload preceded by its length.

    :Parameters:
        #. sock (socket.socket): The connected socket.
        #. payload (bytes): The data to send.
    """
    sock.sendall(HEADER.pack(len(payload)) + payload)


def recv_frame(sock, maxFrame):
    """
    Reads a payload preceded by its length.

    :Parameters:
        #. sock (socket.socket): The connected socket.
        #. maxFrame (int): Largest accepted payload. A larger declared length is refused before anything is read.

    :Returns:
        #. payload (bytes): The data received.

    :Raises:
        #. ProtocolError: If the declared length is above *maxFrame*.
    """
    size = HEADER.unpack(recv_exact(sock, HEADER.size))[0]
    if size > maxFrame:
        raise ProtocolError(f"frame of {size} bytes is above the limit of {maxFrame}")
    return recv_exact(sock, size)


def compute_mac(token, label, serverNonce, clientNonce):
    """
    Computes the answer to a challenge. The label keeps an answer made for one side from being accepted by the other.

    :Parameters:
        #. token (bytes): The shared secret.
        #. label (bytes): ``b'client'`` or ``b'server'``.
        #. serverNonce (bytes): The random value the server chose for this connection.
        #. clientNonce (bytes): The random value the client chose for this connection.

    :Returns:
        #. mac (bytes): The HMAC-SHA256 digest.
    """
    return hmac.new(token, label + serverNonce + clientNonce, hashlib.sha256).digest()


def server_handshake(sock, token):
    """
    Challenges a client, then proves to it that the server knows the token too. The token never travels on the connection.

    :Parameters:
        #. sock (socket.socket): The accepted socket.
        #. token (bytes): The shared secret.

    :Raises:
        #. ProtocolError: If the client's answer is malformed or wrong.
    """
    serverNonce = secrets.token_bytes(NONCE_SIZE)
    send_frame(sock, serverNonce)
    answer = recv_frame(sock, HANDSHAKE_MAX_FRAME)
    if len(answer) != NONCE_SIZE + MAC_SIZE:
        raise ProtocolError('malformed handshake answer')
    clientNonce, clientMac = answer[:NONCE_SIZE], answer[NONCE_SIZE:]
    if not hmac.compare_digest(clientMac, compute_mac(token, b'client', serverNonce, clientNonce)):
        raise ProtocolError('wrong token')
    send_frame(sock, compute_mac(token, b'server', serverNonce, clientNonce))


def client_handshake(sock, token):
    """
    Answers the server's challenge, then checks the server's proof. No record is sent to a server that cannot prove it knows the token.

    :Parameters:
        #. sock (socket.socket): The connected socket.
        #. token (bytes): The shared secret.

    :Raises:
        #. ProtocolError: If the server's challenge or proof is malformed or wrong.
    """
    serverNonce = recv_frame(sock, HANDSHAKE_MAX_FRAME)
    if len(serverNonce) != NONCE_SIZE:
        raise ProtocolError('malformed server challenge')
    clientNonce = secrets.token_bytes(NONCE_SIZE)
    send_frame(sock, clientNonce + compute_mac(token, b'client', serverNonce, clientNonce))
    serverMac = recv_frame(sock, HANDSHAKE_MAX_FRAME)
    if not hmac.compare_digest(serverMac, compute_mac(token, b'server', serverNonce, clientNonce)):
        raise ProtocolError('the server did not prove it knows the token')


class PendingBatch:
    """A batch waiting for the writer thread, and the outcome the reader thread waits for."""

    def __init__(self, records):
        self.records = records
        self.done = threading.Event()
        self.isFailed = False


class Receiver:
    """
    Receives the records of other processes and writes them through one logger, from a single writer thread.

    One thread accepts connections and one thread per connection reads batches, so a slow disk never stops a sender from
    being served. A single writer thread takes the batches, drops the records it already has, and gives the rest to
    :meth:`pysimplelog.simple_log.Logger.log_external`, which runs the routing, the processors, the filters and the sinks of the
    logger. Only that thread reaches the sinks, so file rolling is correct and the lines are never mixed.

    A batch is confirmed to its sender after it has been written and the logger flushed, so a sender with a spool can send it again
    if the receiver stops first. A record can then arrive twice, and it is dropped when its ``event_id`` was seen recently. With a
    *reorderWindow* the batch is confirmed when it is accepted instead, because its records wait in memory to be sorted.

    :Parameters:
        #. logger (Logger): The logger that writes the records. Its file sink should use ``flush='none'``, the receiver flushes once per batch.
        #. token (bytes): The shared secret of the senders, at least 16 bytes.
        #. host (str): Address to listen on. Only the local machine by default.
        #. port (int): Port to listen on. 0 picks a free one, see :attr:`address`.
        #. queueSize (int): Number of batches held between the readers and the writer. A full queue makes the readers wait.
        #. reorderWindow (float): Seconds a record waits to be sorted by its time. 0 writes in arrival order.
        #. handshakeTimeout (float): Seconds a new connection has to complete the handshake.
        #. dedupeSize (int): Number of recent event ids remembered.
        #. eventIdField (str): Name of the field that carries the id of a record, the one of the ``eventIdField`` setting of the spool. The id is used to drop
           a record that arrives twice, and is not written to the log.
        #. maxFrame (int): Largest batch accepted, in bytes.

    .. code-block:: python

        token = secrets.token_bytes(32)
        receiver = Receiver(logger, token)
        receiver.start()
        ## give receiver.address and the token to the other processes: RemoteSink(host, port, token)
    """

    def __init__(self, logger, token, host='127.0.0.1', port=0, queueSize=64, reorderWindow=0.0, handshakeTimeout=2.0,
                 dedupeSize=200000, maxFrame=MAX_FRAME, eventIdField='event_id'):
        if not isinstance(token, bytes) or len(token) < 16:
            raise ValueError("token must be bytes of at least 16 bytes")
        self._logger = logger
        self._token = token
        self._reorderWindow = reorderWindow
        self._handshakeTimeout = handshakeTimeout
        self._dedupeSize = dedupeSize
        self._maxFrame = maxFrame
        self._eventIdField = eventIdField
        self._batches = queue.Queue(maxsize=queueSize)
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._listener.bind((host, port))
            self._listener.listen(128)
        except OSError:
            # A port in use must not leave a half-made socket behind
            self._listener.close()
            raise
        self._listener.settimeout(0.2)
        self._lock = threading.Lock()
        self._connections = set()
        self._readers = []
        self._stats = collections.Counter()
        self._isRunning = True
        self._isAborted = False
        self._acceptThread = threading.Thread(target=self._accept_loop, name='pysimplelog-receiver-accept', daemon=True)
        self._writerThread = threading.Thread(target=self._writer_loop, name='pysimplelog-receiver-writer', daemon=True)

    @property
    def address(self):
        """The ``(host, port)`` the receiver listens on."""
        return self._listener.getsockname()

    @property
    def stats(self):
        """A copy of the counters: accepted, rejected, batches, written, repeats, bad_records, write_errors."""
        with self._lock:
            return dict(self._stats)

    def start(self):
        """Starts accepting connections and writing records."""
        self._acceptThread.start()
        self._writerThread.start()

    def stop(self, timeout=60.0):
        """
        Stops cleanly: no new connection is accepted, the connected senders are served until they leave, everything received is written.

        :Parameters:
            #. timeout (float): Seconds to wait for the senders to leave. The remaining connections are then closed.
        """
        self._isRunning = False
        self._listener.close()
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                isBusy = any(reader.is_alive() for reader in self._readers)
            if not isBusy:
                break
            time.sleep(0.02)
        self._close_connections()
        self._batches.put(None)
        self._writerThread.join(timeout=timeout)
        self._logger.flush()

    def abort(self):
        """Stops at once, as a crash would: connections are closed and batches not yet written are dropped, unconfirmed."""
        self._isAborted = True
        self._isRunning = False
        self._listener.close()
        self._close_connections()
        self._batches.put(None)
        self._writerThread.join(timeout=30)

    def _close_connections(self):
        """Closes every connection, which also ends their reader threads."""
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

    def _accept_loop(self):
        """Gives every new connection a reader thread."""
        while self._isRunning:
            try:
                connection, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._connections.add(connection)
                reader = threading.Thread(target=self._serve, args=(connection,), name='pysimplelog-receiver-reader', daemon=True)
                self._readers = [thread for thread in self._readers if thread.is_alive()]
                self._readers.append(reader)
            reader.start()

    def _serve(self, connection):
        """Runs the handshake, then reads batches and confirms each one after it is written. Never touches the disk itself."""
        try:
            connection.settimeout(self._handshakeTimeout)
            server_handshake(connection, self._token)
            connection.settimeout(None)
            with self._lock:
                self._stats['accepted'] += 1
            while True:
                pending = PendingBatch(json.loads(recv_frame(connection, self._maxFrame)))
                self._batches.put(pending)
                # The wait is cut into short turns so that an abort never leaves a reader waiting for a writer that has stopped
                while not pending.done.wait(0.2):
                    if self._isAborted:
                        break
                if pending.done.is_set() and not pending.isFailed and not self._isAborted:
                    send_frame(connection, ACK)
                else:
                    break
        except ConnectionError:
            pass
        except (ProtocolError, socket.timeout, ValueError, OSError):
            with self._lock:
                self._stats['rejected'] += 1
        finally:
            with self._lock:
                self._connections.discard(connection)
            try:
                connection.close()
            except OSError:
                pass

    def _writer_loop(self):
        """The only thread that reaches the logger: skips repeats, sorts when asked, writes, flushes once per batch."""
        seen = collections.OrderedDict()
        waiting = []
        counter = 0
        windowUs = int(self._reorderWindow * 1e6)
        while True:
            try:
                item = self._batches.get(timeout=0.05)
            except queue.Empty:
                item = False
            if item is None or self._isAborted:
                break
            if item is not False:
                try:
                    for data in item.records:
                        eventId = data['fields'].get(self._eventIdField)
                        if eventId is not None and eventId in seen:
                            self._count('repeats')
                            continue
                        if windowUs == 0:
                            self._write_record(data)
                        else:
                            counter += 1
                            heapq.heappush(waiting, (data['ts'], counter, data))
                        if eventId is not None:
                            seen[eventId] = None
                            if len(seen) > self._dedupeSize:
                                seen.popitem(last=False)
                    if windowUs == 0:
                        self._logger.flush()
                except Exception:
                    self._count('write_errors')
                    item.isFailed = True
                item.done.set()
            if windowUs > 0:
                limit = int(time.time() * 1e6) - windowUs
                while waiting and waiting[0][0] <= limit:
                    self._write_record(heapq.heappop(waiting)[2])
                self._logger.flush()
        while waiting and not self._isAborted:
            self._write_record(heapq.heappop(waiting)[2])
        self._logger.flush()

    def _count(self, name):
        """Adds one to a counter."""
        with self._lock:
            self._stats[name] += 1

    def _write_record(self, data):
        """Rebuilds one record and gives it to the logger with its original time, process, thread and caller."""
        try:
            record = record_from_dict(data)
        except (TypeError, ValueError, KeyError):
            self._count('bad_records')
            return
        # A type the logger does not define would be refused, so the record is written as info and keeps its own type in a field
        logType = record.logType if self._logger.is_log_type(record.logType) else 'info'
        fields = dict(record.fields)
        fields.pop(self._eventIdField, None)
        # Said only when it tells something: a record from a logger of the same name and a known type reads like a local one
        if record.logger != getattr(self._logger, 'name', None):
            fields['origin_logger'] = record.logger
        if logType != record.logType:
            fields['origin_log_type'] = record.logType
        self._logger.log_external(logType, record.message, created=data['ts'] / 1e6, processId=record.processId,
                                  threadId=record.threadId, threadName=record.threadName, caller=record.caller,
                                  exc_info=None if record.exception is None else record.exception.stacktrace, fields=fields)
        self._count('written')


class RemoteSink(Sink):
    """
    Sends records in batches to a :class:`Receiver`. A batch that is not confirmed is given back, for the spool of the sink to send again.

    Add it with ``threaded=True`` so that the caller never waits for the network, and with ``spool=`` so that a receiver that is down,
    or restarting, loses nothing.

    :Parameters:
        #. host (str): Address of the receiver.
        #. port (int): Port of the receiver.
        #. token (bytes): The shared secret of the receiver.
        #. batchSize (int): Most records sent together.
        #. batchInterval (float): Most seconds a record waits for its batch to fill.
        #. ackTimeout (float): Seconds to wait for the receiver to confirm a batch.

    .. code-block:: python

        sink = RemoteSink(host, port, token)
        logger.add_sink('remote', sink, threaded=True, threadQueuePolicy='block', spool={'path': spoolFolder, 'id': 'worker3'})
    """

    SPOOL_DESTINATION = ('host', 'port')

    def __init__(self, host, port, token, batchSize=500, batchInterval=0.2, ackTimeout=10.0):
        super().__init__(formatter=lambda record: json.dumps(record_to_dict(record), default=str), batchSize=batchSize,
                         batchInterval=batchInterval)
        self.host = host
        self.port = port
        self._token = token
        self._ackTimeout = ackTimeout
        self._connection = None

    def _connect(self):
        """Opens the connection and runs the handshake."""
        connection = socket.create_connection((self.host, self.port), timeout=self._ackTimeout)
        try:
            client_handshake(connection, self._token)
        except Exception:
            connection.close()
            raise
        self._connection = connection

    def _drop_connection(self):
        """Closes the connection, the next batch opens a new one."""
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass

    def write_batch(self, items):
        """
        Sends a group of records and waits for the receiver to confirm it.

        :Parameters:
            #. items (list): Tuples ``(text, record)``, the text being the record as JSON.

        :Returns:
            #. outcome (bool, None): ``False`` when the batch was not confirmed, so that it is sent again later.
        """
        payload = ('[' + ','.join(text for text, _ in items) + ']').encode('utf-8')
        try:
            if self._connection is None:
                self._connect()
            send_frame(self._connection, payload)
            if recv_frame(self._connection, ACK_MAX_FRAME) != ACK:
                raise ProtocolError('the receiver did not confirm the batch')
        except (OSError, ProtocolError):
            self._drop_connection()
            return False
        return None

    def close(self):
        """Closes the connection and the sink."""
        super().close()
        self._drop_connection()
