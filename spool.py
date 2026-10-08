"""A disk spool: records are written to files before they are delivered, so a crash or an outage does not lose them."""

import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from json.encoder import encode_basestring_ascii

try:
    from .record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo, validate_record
    from .formatters import _dumps, _json_value, _mapping_to_json
    from .queues import QueueFull, validate_queue_policy
    from .sinks import validate_flush_mode, sync_descriptor
    from .forking import register_for_fork_reset
except ImportError:
    from record import LogRecord, ExceptionInfo, CallerInfo, TraceInfo, validate_record
    from formatters import _dumps, _json_value, _mapping_to_json
    from queues import QueueFull, validate_queue_policy
    from sinks import validate_flush_mode, sync_descriptor
    from forking import register_for_fork_reset

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

FORMAT_VERSION = 1
MEGABYTE = 1024 ** 2
DEFAULT_SEGMENT_BYTES = MEGABYTE
DEFAULT_DEAD_MAX_BYTES = 10 * MEGABYTE
DEFAULT_ACK_EVERY = 100
DEFAULT_ACK_INTERVAL = 1.0
# Longest the text around a record can be: the key, a sequence number of 20 digits, the other key and the end of line
SEQUENCE_OVERHEAD_BYTES = 40

# A segment is named after the sequence number of its first record, so the folder listing alone says which
# records each file holds
SEGMENT_NAME = re.compile(r'^(\d{12})\.spool$')
SLOT_NAME = re.compile(r'^\d{8}T\d{6}-\d+-[0-9a-f]{6}$')
LOCK_FILE = 'lock'
ACK_FILE = 'ack'
META_FILE = 'meta.json'
DEAD_FILE = 'dead'

# A time is kept as whole microseconds since this moment and the offset of its time zone in seconds: exact, and cheaper to
# write than the text of the time
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)

# Windows opens files as text unless told otherwise, which would change the bytes of the lock and the segments
_BINARY = getattr(os, 'O_BINARY', 0)

# Folders locked by this process. A POSIX lock belongs to the process, so a second lock by the same process
# always succeeds, and closing any descriptor of the file drops it. Both are why this process keeps its own list
_HELD_PATHS = set()
_HELD_LOCK = threading.Lock()


class SpoolError(Exception):
    """Base class of the errors a spool raises."""


class SpoolBusyError(SpoolError):
    """Raised when the folder of a slot is in use by another spool, in this process or in another one."""


class SpoolMismatchError(SpoolError):
    """Raised when a slot was made for another spool id, sink class or delivery target."""


class SpoolOwnerError(SpoolError):
    """Raised when a spool is used by a process that does not own it, as a forked child does."""


class SpoolUnsupportedError(SpoolError):
    """Raised when the operating system gives no file lock, so a spool cannot be protected."""


def _reset_after_fork():
    """Forgets the folders the parent locked, because a forked child holds none of them."""
    global _HELD_LOCK
    _HELD_PATHS.clear()
    _HELD_LOCK = threading.Lock()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_after_fork)


class FileLock:
    """
    An exclusive lock on a file that is given back by the operating system when the process ends, however it ends.

    The lock is a record lock on the first byte: ``fcntl.lockf`` on Linux, macOS and the BSD systems, and
    ``msvcrt.locking`` on Windows. Neither is inherited by a forked or spawned child, so a crashed owner leaves the
    lock free even while its children live. The process id of the holder is written after the first byte, for
    error messages only.

    :Parameters:
        #. path (str): The lock file. It is created when missing.
    """

    def __init__(self, path):
        self.__path = os.path.realpath(path)
        self.__fd = None
        self.__pid = None

    @property
    def isHeld(self):
        """True while this object holds the lock."""
        return self.__fd is not None

    def try_acquire(self):
        """
        Takes the lock without waiting.

        :Returns:
            #. isAcquired (bool): True when the lock is held now, False when another spool or process holds it.

        :Raises:
            #. SpoolUnsupportedError: If the operating system gives no file lock.
        """
        if fcntl is None and msvcrt is None:
            raise SpoolUnsupportedError("this operating system gives no file lock, a spool cannot be protected here")
        if self.__fd is not None:
            return True
        with _HELD_LOCK:
            if self.__path in _HELD_PATHS:
                return False
            descriptor = os.open(self.__path, os.O_RDWR | os.O_CREAT | _BINARY, 0o600)
            try:
                if fcntl is not None:
                    fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)
                else:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError:
                os.close(descriptor)
                return False
            text = f"{os.getpid()}\n".encode('ascii')
            os.lseek(descriptor, 1, os.SEEK_SET)
            os.write(descriptor, text)
            os.ftruncate(descriptor, 1 + len(text))
            _HELD_PATHS.add(self.__path)
            self.__fd = descriptor
            self.__pid = os.getpid()
            return True

    def release(self):
        """Gives the lock back. Calling it when the lock is not held does nothing."""
        if self.__fd is None:
            return
        descriptor, self.__fd = self.__fd, None
        with _HELD_LOCK:
            _HELD_PATHS.discard(self.__path)
        # A forked child has a copy of the descriptor but not the lock, so it only closes its copy
        if self.__pid == os.getpid():
            try:
                if fcntl is not None:
                    fcntl.lockf(descriptor, fcntl.LOCK_UN, 1, 0)
                else:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            except OSError:
                # Closing the descriptor drops the lock anyway
                pass
        os.close(descriptor)

    @staticmethod
    def holder(path):
        """
        Returns the process id written by the process that holds a lock, for an error message.

        :Parameters:
            #. path (str): The lock file.

        :Returns:
            #. pid (int, None): The process id, or None when it cannot be read.
        """
        real = os.path.realpath(path)
        # Closing a descriptor of a file this process has locked would drop that lock, so it is not opened
        if real in _HELD_PATHS:
            return os.getpid()
        try:
            with open(real, 'rb') as stream:
                stream.seek(1)
                return int(stream.read(32).strip())
        except (OSError, ValueError):
            return None


def target_id(sinkClass, **destination):
    """
    Returns the identity of a delivery target, the place a spool sends its records to.

    Only what decides where the records go belongs in *destination*: the protocol, the host, the port, the path.
    Credentials, timeouts, retry settings and formatters do not, because changing them does not change the receiver and
    must not leave a spool behind. Only the hash is stored on disk.

    :Parameters:
        #. sinkClass (str): Qualified name of the sink class.
        #. destination: The destination values, each a str, an int, a bool or None.

    :Returns:
        #. targetId (str): A hexadecimal hash of the class and the destination.

    :Raises:
        #. TypeError: If a value is not a str, an int, a bool or None, because anything else has no stable text.
    """
    for key, value in destination.items():
        if not (value is None or isinstance(value, (str, int))):
            raise TypeError(f"destination value {key!r} must be a str, an int, a bool or None, got {type(value).__name__}")
    canonical = json.dumps({'class': sinkClass, 'destination': destination}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def record_to_dict(record):
    """
    Returns a record as a dictionary that JSON can write.

    :Parameters:
        #. record (LogRecord): The record.

    :Returns:
        #. data (dict): The record as plain values. A value that JSON cannot represent is written as its text
           when the dictionary is encoded.
    """
    exception, caller, trace = record.exception, record.caller, record.trace
    timestamp = record.timestamp
    return {'ts': (timestamp - _EPOCH) // _MICROSECOND, 'off': int(timestamp.utcoffset().total_seconds()),
            'severity': record.severity, 'logType': record.logType,
            'level': record.level, 'logger': record.logger, 'message': record.message,
            'processId': record.processId, 'threadId': record.threadId, 'threadName': record.threadName,
            'fields': dict(record.fields), 'context': dict(record.context),
            'exception': None if exception is None else
            {'typeName': exception.typeName, 'message': exception.message, 'stacktrace': exception.stacktrace},
            'caller': None if caller is None else
            {'fileName': caller.fileName, 'line': caller.line, 'function': caller.function,
             'moduleName': caller.moduleName},
            'trace': None if trace is None else
            {'traceId': trace.traceId, 'spanId': trace.spanId, 'flags': trace.flags}}


def record_from_dict(data):
    """
    Builds a record from the dictionary that :func:`record_to_dict` wrote, and checks it.

    The timestamp keeps its microseconds and its offset, but its time zone object becomes a fixed offset. A field value
    that JSON cannot represent comes back as the text it was written as.

    :Parameters:
        #. data (dict): The dictionary read from a spool file.

    :Returns:
        #. record (LogRecord): The checked record.

    :Raises:
        #. TypeError, ValueError, KeyError: If the dictionary is not a valid record.
    """
    exception, caller, trace = data['exception'], data['caller'], data['trace']
    microseconds, offset = data['ts'], data['off']
    level = data['level']
    if isinstance(level, str) and level in ('NaN', 'Infinity', '-Infinity'):
        # JSON has no such numbers, they are written as text, and a level is a number
        level = float(level)
    if not isinstance(microseconds, int) or not isinstance(offset, int):
        raise TypeError("the time of a record must be made of integers")
    timestamp = (_EPOCH + timedelta(microseconds=microseconds)).astimezone(timezone(timedelta(seconds=offset)))
    record = LogRecord.create(
        timestamp=timestamp, severity=data['severity'], logType=data['logType'],
        level=level, logger=data['logger'], message=data['message'], processId=data['processId'],
        threadId=data['threadId'], threadName=data['threadName'], fields=dict(data['fields']),
        context=dict(data['context']),
        exception=None if exception is None else
        ExceptionInfo(exception['typeName'], exception['message'], exception['stacktrace']),
        caller=None if caller is None else
        CallerInfo(caller['fileName'], caller['line'], caller['function'], caller['moduleName']),
        trace=None if trace is None else TraceInfo(trace['traceId'], trace['spanId'], trace['flags']))
    validate_record(record)
    return record


def record_line(seq, record):
    """
    Returns the line that holds a record in a spool file: one JSON object and an end of line, as ASCII bytes.

    It writes the same text as ``_dumps({'seq': seq, 'record': record_to_dict(record)}) + '\\n'``, built by hand, because it
    runs in the thread that logs and that is about three times faster.

    :Parameters:
        #. seq (int): The sequence number of the record.
        #. record (LogRecord): The record.

    :Returns:
        #. line (bytes): The line.
    """
    timestamp, exception, caller, trace = record.timestamp, record.exception, record.caller, record.trace
    text = (f'{{"seq":{seq},"record":{{"ts":{(timestamp - _EPOCH) // _MICROSECOND},'
            f'"off":{int(timestamp.utcoffset().total_seconds())},'
            f'"severity":{encode_basestring_ascii(record.severity)},"logType":{encode_basestring_ascii(record.logType)},'
            f'"level":{_json_value(record.level)},"logger":{encode_basestring_ascii(record.logger)},'
            f'"message":{encode_basestring_ascii(record.message)},"processId":{record.processId},'
            f'"threadId":{record.threadId},"threadName":{encode_basestring_ascii(record.threadName)},'
            f'"fields":{_mapping_to_json(record.fields)},"context":{_mapping_to_json(record.context)},'
            f'"exception":{"null" if exception is None else _json_value({"typeName": exception.typeName, "message": exception.message, "stacktrace": exception.stacktrace})},'
            f'"caller":{"null" if caller is None else _json_value({"fileName": caller.fileName, "line": caller.line, "function": caller.function, "moduleName": caller.moduleName})},'
            f'"trace":{"null" if trace is None else _json_value({"traceId": trace.traceId, "spanId": trace.spanId, "flags": trace.flags})}'
            '}}\n')
    return text.encode('ascii')


def _check_size(name, value, allowNone=False):
    """Returns a size after checking that it is a positive integer, or None when None is allowed."""
    if value is None and allowNone:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be a positive integer" + (" or None" if allowNone else ""))
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _check_seconds(name, value, allowNone=False):
    """Returns a duration after checking that it is a positive number, or None when None is allowed."""
    if value is None and allowNone:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a positive number" + (" or None" if allowNone else ""))
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _atomic_write(path, text, isSynced):
    """Replaces a file by writing a temporary file and renaming it, so a crash leaves the old text or the new one."""
    temporary = f"{path}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _BINARY, 0o600)
    try:
        os.write(descriptor, text.encode('utf-8'))
        if isSynced:
            sync_descriptor(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


@dataclass(frozen=True)
class SpoolConfig:
    """
    The settings that keep the records of a sink on disk until they are delivered.

    The settings are checked when the object is made, so a wrong one is found when the sink is set up and never while
    logging. An object cannot be changed afterwards. Wherever a SpoolConfig is expected, a dictionary with the same
    names is accepted, see :meth:`coerce`.

    :Parameters:
        #. path (str, os.PathLike): The base folder that holds the slots of this spool. Fixed in the application and the same
           in every run, so that a later run finds what an earlier one left.
        #. id (str): The label of this spool, fixed in the application. A slot is only taken over by a sink with the same
           label.
        #. maxBytes (int): Largest size of the slot of this process, in bytes. Required.
        #. totalMaxBytes (int): Largest size of all the slots in the base folder, in bytes. Required.
        #. target (str, None): Where the records go, as text of your choice, for a sink that cannot say it itself, see
           :meth:`pysimplelog.sinks.Sink.spool_destination`. None for a sink that can.
        #. segmentBytes (int): Size at which a file is closed and the next one started.
        #. policy (str): What a full spool does: ``block``, ``drop_newest``, ``drop_oldest`` or ``reject``.
        #. blockTimeout (None, int, float): Seconds the ``block`` policy waits. None waits as long as it takes.
        #. maxAge (None, int, float): Seconds after which a closed file is thrown away, delivered or not. None keeps it.
        #. deadMaxBytes (int): Size at which the file of given-up records is moved aside.
        #. flush (str, None): ``none``, ``flush``, ``fsync`` or ``fullsync``, see
           :func:`pysimplelog.sinks.validate_flush_mode`.
        #. ackEvery (int): Number of delivered records after which the position is saved.
        #. ackInterval (int, float): Seconds after which the position is saved.
        #. retryBackoffBase (int, float): Seconds to wait after the first failed send. The wait doubles after each one.
        #. retryBackoffMax (int, float): Longest wait between two tries, in seconds.
        #. maxAttempts (None, int): Number of failed sends after which a record is given up on. None never gives up,
           and the size limits are what bounds the spool.
        #. adoptOrphans (bool): True to send what slots of other, dead, processes hold. False leaves them alone.
        #. adoptInterval (int, float): Seconds between two looks at the other slots.
        #. adoptBatch (int): Number of records of another slot sent each time the sink is idle.
        #. eventIdField (str, None): Name of the field that carries the unique, stable id of each record, so a receiver can
           recognize a record that arrives twice. None adds no id. A field of the record with the same name is kept.

    :Raises:
        #. TypeError: If a setting has the wrong type.
        #. ValueError: If a setting has a value that is not allowed.

    .. code-block:: python

        config = SpoolConfig(path='/var/spool/app/siem', id='siem', maxBytes=100 * 1024 ** 2,
                             totalMaxBytes=500 * 1024 ** 2, adoptOrphans=True)
        ## The same, as a dictionary
        config = SpoolConfig.coerce({'path': '/var/spool/app/siem', 'id': 'siem', 'maxBytes': 100 * 1024 ** 2,
                                     'totalMaxBytes': 500 * 1024 ** 2, 'adoptOrphans': True})
    """
    path: str
    id: str
    maxBytes: int
    totalMaxBytes: int
    target: str | None = None
    segmentBytes: int = DEFAULT_SEGMENT_BYTES
    policy: str = 'drop_oldest'
    blockTimeout: float | None = None
    maxAge: float | None = None
    deadMaxBytes: int = DEFAULT_DEAD_MAX_BYTES
    flush: str | None = 'flush'
    ackEvery: int = DEFAULT_ACK_EVERY
    ackInterval: float = DEFAULT_ACK_INTERVAL
    retryBackoffBase: float = 1.0
    retryBackoffMax: float = 60.0
    maxAttempts: int | None = None
    adoptOrphans: bool = False
    adoptInterval: float = 30.0
    adoptBatch: int = 100
    eventIdField: str | None = 'event_id'

    def __post_init__(self):
        path = os.fspath(self.path) if isinstance(self.path, os.PathLike) else self.path
        if not isinstance(path, str) or len(path) == 0:
            raise TypeError("path must be a non-empty string or a path")
        object.__setattr__(self, 'path', path)
        if not isinstance(self.id, str) or len(self.id) == 0:
            raise TypeError("id must be a non-empty string")
        for name in ('target', 'eventIdField'):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or len(value) == 0):
                raise TypeError(f"{name} must be a non-empty string or None")
        for name in ('maxBytes', 'totalMaxBytes', 'segmentBytes', 'deadMaxBytes', 'ackEvery', 'adoptBatch'):
            _check_size(name, getattr(self, name))
        _check_size('maxAttempts', self.maxAttempts, allowNone=True)
        for name in ('blockTimeout', 'maxAge'):
            _check_seconds(name, getattr(self, name), allowNone=True)
        for name in ('ackInterval', 'retryBackoffBase', 'retryBackoffMax', 'adoptInterval'):
            _check_seconds(name, getattr(self, name))
        if self.retryBackoffBase > self.retryBackoffMax:
            raise ValueError("retryBackoffBase cannot be larger than retryBackoffMax")
        if not isinstance(self.adoptOrphans, bool):
            raise TypeError("adoptOrphans must be a boolean")
        validate_queue_policy(self.policy)
        object.__setattr__(self, 'flush', validate_flush_mode(self.flush))

    @classmethod
    def coerce(cls, value):
        """
        Returns settings from what a caller gave: a SpoolConfig, a dictionary of the same names, or None.

        :Parameters:
            #. value (SpoolConfig, dict, None): The settings. None means no spool.

        :Returns:
            #. config (SpoolConfig, None): The settings, or None when *value* is None.

        :Raises:
            #. TypeError: If *value* is none of the three, or the dictionary has a key that is not a setting, or a setting
               has the wrong type.
            #. ValueError: If a setting has a value that is not allowed.
        """
        if value is None or isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError(f"spool must be a SpoolConfig, a dictionary or None, got {type(value).__name__}")
        known = [field.name for field in fields(cls)]
        unknown = sorted(str(key) for key in value if key not in known)
        if len(unknown) > 0:
            raise TypeError(f"unknown spool setting {', '.join(unknown)}, the settings are: {', '.join(known)}")
        return cls(**value)


class Spool:
    """
    The records of one sink, kept in files until the sink has delivered them.

    A spool is a folder, a *slot*, owned by one spool object in one process at a time. It holds segment files named
    after the sequence number of their first record, an ``ack`` file with the last sequence number that was
    delivered, a ``dead`` file for records given up on, a ``meta.json`` that says which sink the slot was made for, and
    a ``lock`` file. Every record gets the next sequence number when it is appended. A record is delivered when
    its number is at or below the acknowledged number, so no per-record flag is kept. A segment is deleted when
    every record in it is acknowledged, and the whole slot is deleted by a clean :meth:`close` when nothing is left.

    The spool uses no thread of its own: rotation and the size checks run in :meth:`append`, deleting runs in
    :meth:`ack`. The ``ack`` file is written every *ackEvery* records or *ackInterval* seconds, so after a crash up to
    that many records are delivered a second time, which is the at-least-once guarantee.

    Make one with :meth:`create` for a new slot, or :meth:`open` for an existing one.

    :Parameters:
        #. slotPath (str): The folder of the slot.
        #. spoolId (str): The identifier of the spool, chosen by the application and the same in every run.
        #. sinkClass (str): Qualified name of the sink class the records are for.
        #. targetId (str): The identity of the delivery target, see :func:`target_id`.
        #. maxBytes (int): Largest size of the slot, in bytes. There is no default, a spool without a limit can fill a disk.
        #. totalMaxBytes (int): Largest size of all the slots in the folder that holds this one, checked when a segment is
           started. There is no default.
        #. segmentBytes (int): Size at which a segment is closed and a new one started.
        #. policy (str): What a full spool does with a new record: ``block``, ``drop_newest``, ``drop_oldest`` or
           ``reject``, see :func:`pysimplelog.queues.validate_queue_policy`.
        #. blockTimeout (None, int, float): Seconds the ``block`` policy waits. None waits as long as it takes.
        #. maxAge (None, int, float): Seconds after which a closed segment is thrown away, delivered or not. None keeps it.
        #. deadMaxBytes (int): Size of the ``dead`` file at which it is moved to ``dead.old``, replacing the older one.
        #. flush (str, None): ``none``, ``flush``, ``fsync`` or ``fullsync``, see
           :func:`pysimplelog.sinks.validate_flush_mode`.
        #. ackEvery (int): Number of acknowledged records that make the ``ack`` file be written.
        #. ackInterval (int, float): Seconds that make the ``ack`` file be written.

    :Raises:
        #. SpoolBusyError: If the slot is in use.
        #. SpoolMismatchError: If the slot was made for another spool id, sink class or target.
        #. SpoolUnsupportedError: If the operating system gives no file lock.

    .. code-block:: python

        targetId = target_id('SiemForwardSink', protocol='tcp', host='siem.example.org', port=514)
        spool = Spool.create('/var/spool/app/siem', 'siem', 'SiemForwardSink', targetId,
                             maxBytes=50 * 1024 ** 2, totalMaxBytes=200 * 1024 ** 2)
        seq = spool.append(record)
        for seq, record in spool.pending():
            deliver(record)
            spool.ack(seq)
        spool.close()
    """

    def __init__(self, slotPath, spoolId, sinkClass, targetId, maxBytes, totalMaxBytes,
                 segmentBytes=DEFAULT_SEGMENT_BYTES, policy='drop_oldest', blockTimeout=None, maxAge=None,
                 deadMaxBytes=DEFAULT_DEAD_MAX_BYTES, flush='flush', ackEvery=DEFAULT_ACK_EVERY,
                 ackInterval=DEFAULT_ACK_INTERVAL):
        if not isinstance(spoolId, str) or len(spoolId) == 0:
            raise TypeError("spoolId must be a non-empty string")
        self.__maxBytes = _check_size('maxBytes', maxBytes)
        self.__totalMaxBytes = _check_size('totalMaxBytes', totalMaxBytes)
        self.__segmentBytes = _check_size('segmentBytes', segmentBytes)
        self.__deadMaxBytes = _check_size('deadMaxBytes', deadMaxBytes)
        self.__ackEvery = _check_size('ackEvery', ackEvery)
        self.__ackInterval = _check_seconds('ackInterval', ackInterval)
        self.__maxAge = _check_seconds('maxAge', maxAge, allowNone=True)
        self.__blockTimeout = _check_seconds('blockTimeout', blockTimeout, allowNone=True)
        self.__policy = validate_queue_policy(policy)
        self.__flush = validate_flush_mode(flush)
        self.__path = os.path.abspath(slotPath)
        self.__meta = {'format': FORMAT_VERSION, 'spoolId': spoolId, 'sinkClass': sinkClass, 'targetId': targetId}
        self.__pid = os.getpid()
        self.__condition = threading.Condition()
        self.__lock = FileLock(os.path.join(self.__path, LOCK_FILE))
        self.__segments = []
        self.__active = None
        self.__bytes = 0
        self.__othersBytes = 0
        self.__nextSeq = 1
        self.__ackedSeq = 0
        self.__ackWritten = 0
        self.__unwrittenAcks = 0
        self.__lastAckTime = time.monotonic()
        self.__lastExpireTime = 0.0
        self.__isClosed = False
        self.__isDropping = False
        # Where the last read stopped: (first sequence number of the segment, byte offset, next sequence number)
        self.__cursor = None
        self.__reported = set()
        # Segment files that could not be deleted when they should have been, tried again at the next acknowledgement
        self.__undeleted = set()
        register_for_fork_reset(self)
        self.__counters = {'spooled': 0, 'dropped': 0, 'rejected': 0, 'torn': 0, 'lost': 0, 'corrupt': 0, 'dead': 0}
        self._load()

    def _reset_after_fork(self):
        """Gives a forked process a lock of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        self.__condition = threading.Condition()

    # ------------------------------------------------------------------ construction

    @classmethod
    def create(cls, basePath, spoolId, sinkClass, targetId, maxBytes, totalMaxBytes, **options):
        """
        Makes a new slot with a unique name in a base folder, and opens it.

        The name is made of the time, the process id and a random part, so no two slots collide. The id is only a
        label for a person. The slot is found again by scanning the base folder, never by its name.

        :Parameters:
            #. basePath (str): The folder that holds the slots. It is created, with owner-only permissions, when missing.
            #. spoolId (str): The identifier of the spool.
            #. sinkClass (str): Qualified name of the sink class.
            #. targetId (str): The identity of the delivery target.
            #. maxBytes (int): Largest size of the slot.
            #. totalMaxBytes (int): Largest size of all the slots in the base folder.
            #. options: The other arguments of the class.

        :Returns:
            #. spool (Spool): The new spool.
        """
        os.makedirs(basePath, mode=0o700, exist_ok=True)
        name = f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{os.getpid()}-{secrets.token_hex(3)}"
        slotPath = os.path.join(basePath, name)
        os.mkdir(slotPath, 0o700)
        try:
            return cls(slotPath, spoolId, sinkClass, targetId, maxBytes, totalMaxBytes, **options)
        except BaseException:
            try:
                os.rmdir(slotPath)
            except OSError:
                pass
            raise

    @classmethod
    def open(cls, slotPath, spoolId, sinkClass, targetId, maxBytes, totalMaxBytes, **options):
        """
        Opens an existing slot, to send what an earlier run left unsent.

        :Parameters:
            #. slotPath (str): The folder of the slot.
            #. spoolId (str): The identifier the slot must have.
            #. sinkClass (str): The sink class the slot must have.
            #. targetId (str): The delivery target the slot must have.
            #. maxBytes (int): Largest size of the slot.
            #. totalMaxBytes (int): Largest size of all the slots in the base folder.
            #. options: The other arguments of the class.

        :Returns:
            #. spool (Spool): The spool.

        :Raises:
            #. SpoolBusyError: If the slot is in use.
            #. SpoolMismatchError: If the slot was made for something else, it is left untouched.
        """
        return cls(slotPath, spoolId, sinkClass, targetId, maxBytes, totalMaxBytes, **options)

    @staticmethod
    def slots(basePath):
        """
        Lists the slots of a base folder, the oldest first.

        :Parameters:
            #. basePath (str): The folder that holds the slots.

        :Returns:
            #. paths (list): The folder of every slot. Empty when the base folder does not exist.
        """
        try:
            names = sorted(name for name in os.listdir(basePath) if SLOT_NAME.match(name))
        except FileNotFoundError:
            return []
        return [os.path.join(basePath, name) for name in names if os.path.isdir(os.path.join(basePath, name))]

    def _load(self):
        """Takes the lock, checks the meta file, and rebuilds the state from the folder, scanning one segment at most."""
        if not self.__lock.try_acquire():
            holder = FileLock.holder(os.path.join(self.__path, LOCK_FILE))
            raise SpoolBusyError(f"the spool slot {self.__path} is in use" + ("" if holder is None else f" by process {holder}"))
        try:
            self._check_meta()
            self.__ackedSeq = self._read_ack()
            self.__ackWritten = self.__ackedSeq
            for name in sorted(name for name in os.listdir(self.__path) if SEGMENT_NAME.match(name)):
                size = os.path.getsize(os.path.join(self.__path, name))
                self.__segments.append([int(name[:12]), size])
            self.__bytes = sum(size for _, size in self.__segments)
            self.__nextSeq = self._scan_last_segment()
            self.__nextSeq = max(self.__nextSeq, self.__ackedSeq + 1)
            self.__ackedSeq = min(self.__ackedSeq, self.__nextSeq - 1)
            with self.__condition:
                self._delete_finished()
            self.__othersBytes = self._measure_others()
        except BaseException:
            self.__lock.release()
            raise

    def _check_meta(self):
        """Compares the meta file with what this spool was asked for, and writes it for a new slot."""
        path = os.path.join(self.__path, META_FILE)
        try:
            with open(path, 'r', encoding='utf-8') as stream:
                stored = json.load(stream)
        except FileNotFoundError:
            _atomic_write(path, json.dumps(self.__meta), False)
            return
        except ValueError:
            stored = {}
        different = [key for key in ('format', 'spoolId', 'sinkClass', 'targetId') if stored.get(key) != self.__meta[key]]
        if len(different) > 0:
            # Only the names are given, a hash or an identifier could say too much about the receiver
            raise SpoolMismatchError(f"the spool slot {self.__path} was made for another {', '.join(different)}")

    def _read_ack(self):
        """Returns the acknowledged sequence number written on disk, 0 when there is none."""
        try:
            with open(os.path.join(self.__path, ACK_FILE), 'r', encoding='ascii') as stream:
                return max(0, int(stream.read().strip()))
        except (OSError, ValueError):
            return 0

    def _scan_last_segment(self):
        """
        Reads the newest segment once, cuts a half-written last line off, and returns the next sequence number.

        A crash can leave the last line without its end of line. Appending after it would glue the new record to the
        broken text, so the broken part is cut off and counted.
        """
        if len(self.__segments) == 0:
            return 1
        first, size = self.__segments[-1]
        path = self._segment_path(first)
        lastSeq = first - 1
        validEnd = 0
        position = 0
        with open(path, 'rb') as stream:
            for line in stream:
                position += len(line)
                if not line.endswith(b'\n'):
                    break
                try:
                    lastSeq = int(json.loads(line)['seq'])
                except (ValueError, KeyError, TypeError):
                    # A complete but broken line is kept, the readers skip it and count it
                    pass
                validEnd = position
        if validEnd < size:
            with open(path, 'r+b') as stream:
                stream.truncate(validEnd)
            self.__bytes -= size - validEnd
            self.__segments[-1][1] = validEnd
            self.__counters['torn'] += 1
        return lastSeq + 1

    # ------------------------------------------------------------------ paths and sizes

    def _segment_path(self, firstSeq):
        """Returns the path of the segment whose first record has this sequence number."""
        return os.path.join(self.__path, f"{firstSeq:012d}.spool")

    def _closed_count(self):
        """Returns how many segments are closed: all of them, except the one being written to."""
        return len(self.__segments) - (1 if self.__active is not None else 0)

    def _last_seq_of(self, index):
        """Returns the sequence number of the last record of a segment, which is one below the start of the next."""
        if index + 1 < len(self.__segments):
            return self.__segments[index + 1][0] - 1
        return self.__nextSeq - 1

    def _measure_others(self):
        """Returns the size of every other slot in the base folder, found by listing it."""
        total = 0
        base = os.path.dirname(self.__path)
        for slot in Spool.slots(base):
            if slot == self.__path:
                continue
            try:
                total += sum(entry.stat().st_size for entry in os.scandir(slot) if entry.is_file())
            except OSError:
                # A slot deleted while it is being measured is simply not counted
                pass
        return total

    # ------------------------------------------------------------------ writing

    def append(self, record):
        """
        Writes a record to the spool and gives it the next sequence number.

        When the spool is full, the policy decides, see the arguments of the class.

        :Parameters:
            #. record (LogRecord): The record to keep.

        :Returns:
            #. seq (int, None): The sequence number of the record, or None when it was thrown away, which is counted.

        :Raises:
            #. QueueFull: If the spool is full and the policy is ``reject``.
            #. SpoolOwnerError: If the spool is used from a process that does not own it.
        """
        # The line is built with a placeholder number, then the real one is put in once there is room: the block policy can
        # wait, and the numbers must not be taken in a different order than they are written
        template = record_line(0, record)
        needed = len(template) + SEQUENCE_OVERHEAD_BYTES
        with self.__condition:
            self._check_usable()
            droppedBefore = self.__counters['dropped']
            self._expire_old()
            if not self._make_room(needed):
                return None
            if self.__active is None or self.__segments[-1][1] + needed > self.__segmentBytes:
                self._start_segment(needed)
                if not self._make_room(needed):
                    return None
                if self.__active is None or self.__segments[-1][1] + needed > self.__segmentBytes:
                    # The wait of the block policy let another thread fill the new segment
                    self._start_segment(needed)
            seq = self.__nextSeq
            # The placeholder is the one digit right after the key, so the real number replaces only that
            line = b'{"seq":' + str(seq).encode('ascii') + template[8:]
            self.__active.write(line)
            if self.__flush in ('flush', 'fsync', 'fullsync'):
                self.__active.flush()
                if self.__flush in ('fsync', 'fullsync'):
                    sync_descriptor(self.__active.fileno(), self.__flush == 'fullsync')
            self.__segments[-1][1] += len(line)
            self.__bytes += len(line)
            self.__nextSeq += 1
            self.__counters['spooled'] += 1
            # Under drop_oldest an append succeeds while it drops, so only an append that dropped nothing ends the run
            if self.__counters['dropped'] == droppedBefore:
                self.__isDropping = False
            return seq

    def _start_segment(self, needed):
        """Closes the segment being written to when it is full, and opens the next, or the newest one when it has room."""
        if self.__active is not None:
            self.__active.close()
            self.__active = None
        if len(self.__segments) > 0 and self.__segments[-1][1] + needed <= self.__segmentBytes:
            first = self.__segments[-1][0]
        else:
            first = self.__nextSeq
            self.__segments.append([first, 0])
            # A new segment is the moment to look at the other slots, listing them for every record would cost too much
            self.__othersBytes = self._measure_others()
        descriptor = os.open(self._segment_path(first), os.O_WRONLY | os.O_CREAT | os.O_APPEND | _BINARY, 0o600)
        self.__active = os.fdopen(descriptor, 'ab')

    def _is_over(self, needed):
        """Returns True when a record of this size does not fit, in this slot or in the whole base folder."""
        return (self.__bytes + needed > self.__maxBytes
                or self.__othersBytes + self.__bytes + needed > self.__totalMaxBytes)

    def _make_room(self, needed):
        """
        Applies the policy until a record of this size fits.

        :Returns:
            #. isRoom (bool): True when the record fits, False when it is thrown away and counted.
        """
        if not self._is_over(needed):
            return True
        policy = self.__policy
        if policy == 'reject':
            self.__counters['rejected'] += 1
            raise QueueFull("the spool is full")
        if policy == 'block':
            deadline = None if self.__blockTimeout is None else time.monotonic() + self.__blockTimeout
            while self._is_over(needed):
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return self._drop_new_record()
                self.__condition.wait(remaining)
                self._check_usable()
            return True
        if policy == 'drop_oldest':
            while self._is_over(needed):
                if not self._drop_oldest_segment():
                    return self._drop_new_record()
            return True
        return self._drop_new_record()

    def _drop_new_record(self):
        """Counts a record that is thrown away and warns once for each run of them. Always returns False."""
        self._count_dropped(1, f"policy {self.__policy}")
        return False

    def _count_dropped(self, count, reason):
        """Counts records that were thrown away, and warns once for each run of them."""
        self.__counters['dropped'] += count
        if not self.__isDropping:
            self.__isDropping = True
            try:
                sys.stderr.write(f"pysimplelog WARNING: the spool {self.__path} is full, records are being dropped "
                                 f"({reason}, {self.__counters['dropped']} dropped so far)\n")
            except (OSError, ValueError):
                # The error stream is closed or broken, the count is still there
                pass

    def _drop_oldest_segment(self):
        """
        Deletes the oldest segment, delivered or not, and counts the undelivered records in it as dropped.

        :Returns:
            #. isDropped (bool): False when there is nothing to delete.
        """
        if len(self.__segments) == 0:
            return False
        if self._closed_count() == 0:
            if self.__segments[0][1] == 0:
                return False
            # The segment being written to is the only one, closing it makes it a segment that can go
            self.__active.close()
            self.__active = None
        self._drop_segment(0, 'oldest segment dropped')
        return True

    def _drop_segment(self, index, reason):
        """Deletes a closed segment, counts its undelivered records as dropped, and moves the acknowledged number past it."""
        first, size = self.__segments[index]
        last = self._last_seq_of(index)
        unsent = max(0, last - max(self.__ackedSeq, first - 1))
        if unsent > 0:
            self._count_dropped(unsent, reason)
            self.__unwrittenAcks += unsent
        self.__ackedSeq = max(self.__ackedSeq, last)
        self._remove_segment_file(first)
        self.__bytes -= size
        del self.__segments[index]
        self.__condition.notify_all()

    def _remove_segment_file(self, firstSeq):
        """
        Deletes a segment file. A file that is already gone is not an error, and a file that is in use is tried again later.

        Windows refuses to delete a file that another handle has open, which happens when a segment is dropped by a log call
        while the worker reads it, and when a virus scanner looks at it. The segment is already out of the books of the spool,
        so nothing reads it again, and the file is deleted at one of the next acknowledgements.
        """
        path = self._segment_path(firstSeq)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except PermissionError:
            self.__undeleted.add(path)
        else:
            self.__undeleted.discard(path)

    def _retry_undeleted(self):
        """Tries again to delete the segment files that were in use."""
        for path in list(self.__undeleted):
            try:
                os.remove(path)
            except PermissionError:
                continue
            except FileNotFoundError:
                pass
            self.__undeleted.discard(path)

    def _expire_old(self, isForced=False):
        """Deletes closed segments older than maxAge, checked at most once a second unless *isForced*."""
        if self.__maxAge is None:
            return
        now = time.monotonic()
        if not isForced and now - self.__lastExpireTime < 1.0:
            return
        self.__lastExpireTime = now
        while self._closed_count() > 0:
            try:
                age = time.time() - os.path.getmtime(self._segment_path(self.__segments[0][0]))
            except OSError:
                return
            if age <= self.__maxAge:
                return
            self._drop_segment(0, 'segment older than maxAge')

    # ------------------------------------------------------------------ acknowledging and reading

    def ack(self, seq):
        """
        Says that every record up to this sequence number has been delivered.

        Segments that are now fully delivered are deleted. The ``ack`` file is written when *ackEvery* records or
        *ackInterval* seconds have passed, and by :meth:`sync` and :meth:`close`.

        :Parameters:
            #. seq (int): The sequence number of the last delivered record. A smaller number than the one already
               acknowledged does nothing.

        :Raises:
            #. ValueError: If seq is beyond the last record that was appended.
            #. SpoolOwnerError: If the spool is used from a process that does not own it.
        """
        with self.__condition:
            self._check_usable()
            if seq > self.__nextSeq - 1:
                raise ValueError(f"cannot acknowledge {seq}, the last record is {self.__nextSeq - 1}")
            if seq <= self.__ackedSeq:
                return
            self.__unwrittenAcks += seq - self.__ackedSeq
            self.__ackedSeq = seq
            self._delete_finished()
            self._expire_old()
            if (self.__unwrittenAcks >= self.__ackEvery
                    or time.monotonic() - self.__lastAckTime >= self.__ackInterval):
                self._write_ack()
            self.__condition.notify_all()

    def _delete_finished(self):
        """Deletes the closed segments whose last record is acknowledged, the oldest first."""
        isDeleted = False
        if len(self.__undeleted) > 0:
            self._retry_undeleted()
        while self._closed_count() > 0 and self._last_seq_of(0) <= self.__ackedSeq:
            first, size = self.__segments[0]
            self._remove_segment_file(first)
            self.__bytes -= size
            del self.__segments[0]
            isDeleted = True
        if isDeleted:
            self.__condition.notify_all()

    def _write_ack(self):
        """Writes the acknowledged number to the ``ack`` file, atomically, when it changed."""
        self.__lastAckTime = time.monotonic()
        self.__unwrittenAcks = 0
        if self.__ackedSeq != self.__ackWritten:
            _atomic_write(os.path.join(self.__path, ACK_FILE), str(self.__ackedSeq),
                          self.__flush in ('fsync', 'fullsync'))
            self.__ackWritten = self.__ackedSeq

    def pending(self, limit=None):
        """
        Reads the records that are not delivered yet, in order, from the files.

        It reads forward from the first record above the acknowledged number, so a spool reopened after a crash is read
        from where it stopped. A line that cannot be read is skipped and counted as ``corrupt``, and records missing
        between two files are counted as ``lost``, each once. Reading a long backlog in batches does not read the
        same lines again: the spool remembers where the last batch ended.

        :Parameters:
            #. limit (None, int): The largest number of records to give. None gives all of them.

        :Returns:
            #. records (list): Tuples ``(seq, record)``, the record being a LogRecord.
        """
        return self.read_batch(limit)[0]

    def read_batch(self, limit=None):
        """
        Reads like :meth:`pending`, and also says how far the reading got.

        The second answer is what lets a caller tell records that are not there yet from records that cannot be read: when
        no record comes back but the number is above the acknowledged one, everything up to that number is unreadable
        or lost, and can be acknowledged without losing a record that was appended in the meantime.

        :Parameters:
            #. limit (None, int): The largest number of records to give. None gives all of them.

        :Returns:
            #. records (list): Tuples ``(seq, record)``.
            #. upTo (int): The highest sequence number that was looked at: the last record given, or, when the reading
               reached the end, the last record that existed when it started.
        """
        with self.__condition:
            self._check_usable()
            if self.__active is not None:
                self.__active.flush()
            snapshot = [(first, size) for first, size in self.__segments]
            acked, nextSeq, cursor = self.__ackedSeq, self.__nextSeq, self.__cursor
        found = []
        lastSegment, endOffset = None, 0
        for index, (first, size) in enumerate(snapshot):
            last = snapshot[index + 1][0] - 1 if index + 1 < len(snapshot) else nextSeq - 1
            if last <= acked:
                continue
            lastSeen = first - 1
            position = 0
            try:
                stream = open(self._segment_path(first), 'rb')
            except FileNotFoundError:
                continue
            with stream:
                if cursor is not None and cursor[0] == first and cursor[2] == acked + 1 and 0 < cursor[1] <= size:
                    # The last batch ended here and everything before is delivered, so nothing is read twice
                    stream.seek(cursor[1])
                    position, lastSeen = cursor[1], acked
                for line in stream:
                    if position >= size:
                        break
                    position += len(line)
                    try:
                        entry = json.loads(line)
                        seq = int(entry['seq'])
                    except (ValueError, KeyError, TypeError):
                        self._report('corrupt', first, position)
                        continue
                    # A record that cannot be read still has its place, it is corrupt and not lost
                    lastSeen = max(lastSeen, seq)
                    if seq <= acked:
                        continue
                    try:
                        record = record_from_dict(entry['record'])
                    except (ValueError, KeyError, TypeError):
                        self._report('corrupt', first, position)
                        continue
                    found.append((seq, record))
                    lastSegment, endOffset = first, position
                    if limit is not None and len(found) >= limit:
                        self._remember(lastSegment, endOffset, seq + 1)
                        return found, seq
            if lastSeen < last:
                self._report('lost', first, last - lastSeen)
        if len(found) > 0:
            self._remember(lastSegment, endOffset, found[-1][0] + 1)
        return found, found[-1][0] if len(found) > 0 else nextSeq - 1

    def _remember(self, firstSeq, offset, nextSeq):
        """Keeps where a read ended, so that the next one starts there."""
        with self.__condition:
            self.__cursor = (firstSeq, offset, nextSeq)

    def maintain(self):
        """
        Does the housekeeping now: deletes the closed segments older than *maxAge*, and tries again to delete the files that
        were in use. No record is sent and none is kept back: expired records are counted as dropped, like when the spool is full.

        :Returns:
            #. result (dict): ``dropped`` (records thrown away by this call because their segment expired) and ``undeleted``
               (files that could not be deleted yet).
        """
        with self.__condition:
            self._check_usable()
            droppedBefore = self.__counters['dropped']
            self._expire_old(isForced=True)
            self._retry_undeleted()
            return {'dropped': self.__counters['dropped'] - droppedBefore, 'undeleted': len(self.__undeleted)}

    @property
    def depth(self):
        """The number of records that were appended and are not acknowledged yet."""
        with self.__condition:
            return self.__nextSeq - 1 - self.__ackedSeq

    @property
    def acked(self):
        """The sequence number of the last record that was acknowledged as delivered."""
        with self.__condition:
            return self.__ackedSeq

    def wait_empty(self, timeout=None):
        """
        Waits until every record that was appended is acknowledged.

        :Parameters:
            #. timeout (None, int, float): Seconds to wait. None waits as long as it takes.

        :Returns:
            #. isEmpty (bool): True when nothing is waiting, False when the time ran out first.
        """
        with self.__condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.__nextSeq - 1 > self.__ackedSeq and not self.__isClosed:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self.__condition.wait(remaining)
            return self.__nextSeq - 1 <= self.__ackedSeq

    def _report(self, kind, first, detail):
        """Counts a damaged line or a gap, once for each place, however many times the files are read."""
        key = (kind, first, detail if kind == 'corrupt' else 0)
        with self.__condition:
            if key in self.__reported:
                return
            self.__reported.add(key)
            self.__counters[kind] += detail if kind == 'lost' else 1

    def give_up(self, seq, record, reason):
        """
        Parks a record that could not be delivered in the ``dead`` file, and acknowledges it so the others can go on.

        :Parameters:
            #. seq (int): The sequence number of the record.
            #. record (LogRecord): The record.
            #. reason (str): Why it was given up, for example the class of the last error. It is written to disk, so it
               must not hold secrets.
        """
        text = _dumps({'seq': seq, 'reason': reason, 'record': record_to_dict(record)}) + '\n'
        with self.__condition:
            self._check_usable()
            path = os.path.join(self.__path, DEAD_FILE)
            try:
                if os.path.getsize(path) + len(text) > self.__deadMaxBytes:
                    os.replace(path, f"{path}.old")
            except FileNotFoundError:
                pass
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | _BINARY, 0o600)
            with os.fdopen(descriptor, 'ab') as stream:
                stream.write(text.encode('ascii'))
            self.__counters['dead'] += 1
        self.ack(seq)

    # ------------------------------------------------------------------ state

    def sync(self):
        """Writes the ``ack`` file now, and forces the segment being written to onto the disk."""
        with self.__condition:
            self._check_usable()
            self._write_ack()
            if self.__active is not None:
                self.__active.flush()
                sync_descriptor(self.__active.fileno(), self.__flush == 'fullsync')

    def stats(self):
        """
        Returns what the spool holds and what it lost.

        :Returns:
            #. stats (dict): ``spooled`` (records appended), ``depth`` (records not delivered), ``bytes``, ``segments``,
               ``acked`` and ``next`` (sequence numbers), ``dropped`` (thrown away), ``rejected`` (refused),
               ``dead`` (given up on), ``torn`` (half-written last lines cut off), ``corrupt`` (lines that could not
               be read) and ``lost`` (records missing between files).
        """
        with self.__condition:
            return {**self.__counters, 'depth': self.__nextSeq - 1 - self.__ackedSeq, 'bytes': self.__bytes,
                    'segments': len(self.__segments), 'acked': self.__ackedSeq, 'next': self.__nextSeq}

    @property
    def path(self):
        """The folder of the slot."""
        return self.__path

    def close(self):
        """
        Closes the spool and gives the folder back.

        When every record was delivered, the files and the folder are deleted, so a clean shutdown leaves nothing behind.
        When records are left, or the ``dead`` file holds some, everything stays for the next run. Calling it again
        does nothing.
        """
        with self.__condition:
            if self.__isClosed:
                return
            self.__isClosed = True
            if self.__pid != os.getpid():
                # A forked child shares the files with its parent, it must not write to them or delete them
                self.__lock.release()
                return
            isEmpty = self.__ackedSeq >= self.__nextSeq - 1
            if self.__active is not None:
                self.__active.close()
                self.__active = None
            # Written also when the slot is empty, because a slot kept for its dead file must go on numbering from here
            self._write_ack()
            if isEmpty:
                for first, _ in self.__segments:
                    self._remove_segment_file(first)
                self._retry_undeleted()
                self.__segments = []
                self.__bytes = 0
            self.__condition.notify_all()
            hasDead = any(os.path.exists(os.path.join(self.__path, name)) for name in (DEAD_FILE, f"{DEAD_FILE}.old"))
            self.__lock.release()
            # A file that could not be deleted keeps the folder, its ack file and its meta file: they are what tells the next run
            # that the records in that file were delivered
            if isEmpty and not hasDead and len(self.__undeleted) == 0:
                for name in (ACK_FILE, META_FILE, LOCK_FILE, f"{ACK_FILE}.tmp", f"{META_FILE}.tmp"):
                    try:
                        os.remove(os.path.join(self.__path, name))
                    except FileNotFoundError:
                        pass
                try:
                    os.rmdir(self.__path)
                except OSError:
                    # Something else is in the folder, it is not ours to delete
                    pass

    def _check_usable(self):
        """Raises when the spool is closed, or when it is used from a process that does not own it."""
        if self.__pid != os.getpid():
            raise SpoolOwnerError("this spool belongs to another process, a forked child must open its own slot")
        if self.__isClosed:
            raise SpoolError("the spool is closed")
