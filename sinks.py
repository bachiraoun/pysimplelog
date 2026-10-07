"""Sinks deliver one rendered LogRecord to one destination and never raise into the application."""

import os
import re
import sys
import threading
import time

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    from .formatters import resolve_formatter
    from .forking import register_for_fork_reset
except ImportError:
    from formatters import resolve_formatter
    from forking import register_for_fork_reset

FLUSH_MODES = (None, 'none', 'flush', 'fsync', 'fullsync')
MEGABYTE = 1024 ** 2

# What deliver() answers: the record went through, it can be tried again later, or it can never be delivered
DELIVERED = 'delivered'
RETRY = 'retry'
REJECTED = 'rejected'

# macOS only: the call that makes the drive empty its own cache, which fsync does not do there
_FULLSYNC = getattr(fcntl, 'F_FULLFSYNC', None)


def validate_flush_mode(flush):
    """
    Checks a flush mode and returns it.

    ``none`` leaves the data in the buffer of the stream, and None means the same. ``flush``
    pushes it to the operating system after every record, which survives a crash of the
    application and lets other programs read the lines at once. ``fsync`` also forces it to
    the disk, which survives a crash of the operating system and costs several times more per record.
    On macOS ``fsync`` leaves the data in the cache of the drive, so a power loss can still lose it.
    ``fullsync`` also empties that cache, which survives a power loss, and costs thousands of times
    more per record than ``flush`` on a Mac, about 19 milliseconds on the one it was measured on. Anywhere but
    macOS ``fullsync`` is the same as ``fsync``.

    :Parameters:
        #. flush (str, None): One of ``none``, ``flush``, ``fsync``, ``fullsync``, or None for ``none``.

    :Returns:
        #. flush (str): The checked mode, always a string: None becomes ``none``.

    :Raises:
        #. TypeError: If flush is neither a string nor None. A boolean is rejected on purpose,
           because True cannot say which of the modes is meant.
        #. ValueError: If flush is a string but not one of the modes.
    """
    if flush is None:
        return 'none'
    if not isinstance(flush, str):
        raise TypeError(f"flush must be one of {FLUSH_MODES}, not {type(flush).__name__}")
    if flush not in FLUSH_MODES:
        raise ValueError(f"flush must be one of {FLUSH_MODES}, got {flush!r}")
    return flush


def _is_number(value):
    """Returns True for an int or float, False for anything else including a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value):
    """Returns True for an int, False for anything else including a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def sync_descriptor(descriptor, isFull=False):
    """
    Forces what was written to a file onto the drive.

    :Parameters:
        #. descriptor (int): The file descriptor.
        #. isFull (bool): When True, on macOS the drive is also asked to empty its own cache, see
           :func:`validate_flush_mode`. Elsewhere, and when a file system does not support it, plain ``fsync`` is used.
    """
    if isFull and _FULLSYNC is not None:
        try:
            fcntl.fcntl(descriptor, _FULLSYNC)
            return
        except OSError:
            # Some file systems, network ones for example, do not support it, and fsync is the best they give
            pass
    os.fsync(descriptor)


def _apply_flush(stream, flushMode):
    """Flushes the stream as the flush mode says, ``flushMode`` is already checked."""
    if flushMode != 'none':
        stream.flush()
    if flushMode in ('fsync', 'fullsync'):
        sync_descriptor(stream.fileno(), flushMode == 'fullsync')


def _check_basename(basename):
    """Returns the base name of a log file, after checking it."""
    if not isinstance(basename, str):
        raise TypeError("basename must be a string")
    if len(basename) == 0:
        raise ValueError("basename must not be empty")
    return basename


def _check_extension(extension):
    """Returns the extension of a log file without leading and trailing dots, after checking it."""
    if not isinstance(extension, str):
        raise TypeError("extension must be a string")
    extension = extension.strip('.')
    if len(extension) == 0:
        raise ValueError("extension must not be empty")
    return extension


def _check_max_size(maxSize):
    """Returns the largest size of a log file in bytes, or None for no limit, after checking maxSize in megabytes."""
    if maxSize is None:
        return None
    if not _is_number(maxSize):
        raise TypeError("maxSize must be None or a number")
    if maxSize <= 0:
        raise ValueError("maxSize must be greater than zero")
    return maxSize * MEGABYTE


def _check_roll(roll):
    """Returns the number of log files to keep, or None for all of them, after checking it."""
    if roll is not None:
        if not _is_int(roll):
            raise TypeError("roll must be None or an integer")
        if roll < 1:
            raise ValueError("roll must be at least 1")
    return roll


def _check_first_number(firstNumber):
    """Returns the number of the first log file, or None for a first file without a number, after checking it."""
    if firstNumber is not None:
        if not _is_int(firstNumber):
            raise TypeError("firstNumber must be None or an integer")
        if firstNumber < 0:
            raise ValueError("firstNumber must be at least 0")
    return firstNumber


def ensure_spoolable(sink):
    """
    Checks that a sink writes to something outside this process, so that its records can be kept for later.

    :Parameters:
        #. sink (Sink): The sink.

    :Raises:
        #. TypeError: If the sink writes to something that exists only inside this process, such as a stream.
    """
    if not sink.SPOOLABLE:
        raise TypeError(f"{type(sink).__name__} writes to something that exists only inside this process, "
                        "so its records cannot be kept for later")


class Sink:
    """
    Base class of every sink: renders a record with its own formatter and delivers it.

    :meth:`emit` is what the logger calls. It never raises: when the formatter or
    :meth:`write` fails, the record is dropped, the failure is counted in :attr:`stats`,
    and one warning is written to the standard error stream for each run of failures.
    To make a sink, subclass this class and implement :meth:`write`. A :meth:`write` that returns ``False``
    says the record could not be delivered, for example after the sink gave up on a send and already
    reported it. Returning nothing, or anything else, means it was delivered.

    A sink can have its record kept on disk until it is delivered, see :meth:`spool_destination` for what a
    sink must say about where its records go.

    :Parameters:
        #. formatter (None, str, callable): How a record becomes text. None gives JSON, see
           :func:`pysimplelog.formatters.resolve_formatter` for the other values.
        #. terminator (str): Text appended to every rendered record. The default is a newline.

    .. code-block:: python

        ## A sink that collects the rendered lines in a list
        class ListSink(Sink):
            def __init__(self):
                super().__init__(formatter='text')
                self.lines = []

            def write(self, text, record):
                self.lines.append(text)
    """

    # False for a sink that writes to something that exists only inside this process, such as a stream
    SPOOLABLE = True
    # Names of the attributes that say where the records go, for example ('host', 'port'). Not credentials
    SPOOL_DESTINATION = ()

    def __init__(self, formatter=None, terminator='\n'):
        if not isinstance(terminator, str):
            raise TypeError("terminator must be a string")
        self.__renderer = resolve_formatter(formatter)
        self.__terminator = terminator
        self.__statsLock = threading.Lock()
        self.__processed = 0
        self.__failed = 0
        self.__lastError = None
        self.__isFailing = False
        self.__latencyTotal = 0.0
        self.__latencyMax = 0.0
        register_for_fork_reset(self)

    def _reset_after_fork(self):
        """Gives a forked process locks of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        self.__statsLock = threading.Lock()

    def set_formatter(self, formatter):
        """
        Changes how the sink turns a record into text. The next record is rendered with it.

        :Parameters:
            #. formatter (None, str, callable): None gives JSON, see
               :func:`pysimplelog.formatters.resolve_formatter` for the other values.

        :Raises:
            #. TypeError: If formatter is none of the accepted types.
            #. ValueError: If formatter is a string that is neither a registered keyword nor a template.
        """
        self.__renderer = resolve_formatter(formatter)

    @property
    def stats(self):
        """
        Dictionary with what the sink did: the counts ``processed`` and ``failed``, ``last_error`` (the last exception,
        or None), and ``latency_mean`` and ``latency_max``, the seconds it took to render and write a record that
        went through (None for the mean while nothing has).
        """
        with self.__statsLock:
            mean = self.__latencyTotal / self.__processed if self.__processed > 0 else None
            return {'processed': self.__processed, 'failed': self.__failed, 'last_error': self.__lastError,
                    'latency_mean': mean, 'latency_max': self.__latencyMax}

    def emit(self, record):
        """
        Renders a record and delivers it, without ever raising an exception.

        :Parameters:
            #. record (LogRecord): The record to deliver.
        """
        self.deliver(record)

    def deliver(self, record):
        """
        Renders a record and delivers it like :meth:`emit`, and says how it went. It never raises an exception.

        :Parameters:
            #. record (LogRecord): The record to deliver.

        :Returns:
            #. result (str): ``delivered``, when :meth:`write` returned normally. ``retry``, when it raised an exception
               or returned ``False``: the record was not delivered and trying again can work. ``rejected``, when the
               formatter raised an exception: this record can never be delivered, whatever the destination does.
               The constants are ``DELIVERED``, ``RETRY`` and ``REJECTED`` of :mod:`pysimplelog.sinks`.
        """
        started = time.perf_counter()
        try:
            text = self.__renderer(record) + self.__terminator
        except Exception as error:
            self._record_failure(error)
            return REJECTED
        try:
            written = self.write(text, record)
        except Exception as error:
            self._record_failure(error)
            return RETRY
        if written is False:
            # The sink gave up on this record and has already reported it in its own way, so no warning is added
            self._record_failure(None)
            return RETRY
        elapsed = time.perf_counter() - started
        with self.__statsLock:
            self.__processed += 1
            self.__isFailing = False
            self.__latencyTotal += elapsed
            if elapsed > self.__latencyMax:
                self.__latencyMax = elapsed
        return DELIVERED

    def write(self, text, record):
        """
        Delivers the rendered text to the destination. Subclasses implement this.

        :Parameters:
            #. text (str): The rendered record, with the terminator.
            #. record (LogRecord): The record that was rendered, for sinks that also need its fields.

        :Returns:
            #. isDelivered (bool, None): ``False`` when the record could not be delivered and is to be kept for another
               try. None, or anything else, when it was delivered.

        :Raises:
            #. NotImplementedError: Always, in this base class.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement write")

    def spool_destination(self):
        """
        Says where this sink sends its records, as the values that identify the receiver.

        A spool keeps the records of a sink on disk, and hands them only to a sink with the same destination: a
        record meant for one receiver must never go to another. The values are the protocol, the host, the port, the
        path, whatever makes the receiver what it is. Credentials, timeouts, retry settings and formatters are not
        part of it, because changing them does not change the receiver.

        A sink says it with the names of the attributes in ``SPOOL_DESTINATION``, or by overriding this method.

        :Returns:
            #. destination (dict): The names and values, each value a str, an int, a bool or None.

        :Raises:
            #. TypeError: If the sink cannot be spooled, or does not say where it sends its records. In the second
               case the destination can be given as text when the spool is set up.
        """
        ensure_spoolable(self)
        if len(self.SPOOL_DESTINATION) == 0:
            raise TypeError(f"{type(self).__name__} does not say where it sends its records: set SPOOL_DESTINATION, "
                            "override spool_destination(), or give the destination as text when the spool is set up")
        try:
            return {name: getattr(self, name) for name in self.SPOOL_DESTINATION}
        except AttributeError as error:
            raise TypeError(f"{type(self).__name__}.SPOOL_DESTINATION names an attribute the sink does not have: "
                            f"{error}") from None

    def flush(self):
        """Pushes buffered data to the destination. Does nothing here, sinks that buffer override it."""

    def close(self):
        """Releases what the sink owns. Does nothing here, sinks that open resources override it."""

    def _record_failure(self, error):
        """
        Counts a failure and writes one warning for each run of failures.

        An *error* of None is a record the sink reported itself: it is counted, with no warning and no new last error.
        """
        with self.__statsLock:
            self.__failed += 1
            if error is not None:
                self.__lastError = error
            isFirstOfRun = not self.__isFailing
            self.__isFailing = True
        if isFirstOfRun and error is not None:
            try:
                sys.stderr.write(f"pysimplelog WARNING: sink {type(self).__name__} failed, record dropped. "
                                 f"Error: {type(error).__name__}: {error}\n")
            except (OSError, ValueError):
                # The error stream itself is closed or broken, nothing more can be reported
                pass


class StreamSink(Sink):
    """
    Writes records to a file-like object. The sink never closes the stream, its owner does.

    :Parameters:
        #. stream (file-like): Any object with a ``write(str)`` method. It needs a ``flush()`` method
           when *flush* is not ``none``, and a file descriptor (``fileno()``) when *flush* is ``fsync``.
        #. formatter (None, str, callable): How a record becomes text. None gives JSON.
        #. flush (str, None): ``none`` (or None), ``flush``, ``fsync`` or ``fullsync``, see :func:`validate_flush_mode`.
        #. terminator (str): Text appended to every rendered record.

    :Raises:
        #. TypeError: If stream has no write method, or flush is not a string.
        #. ValueError: If flush is not a valid mode, or is ``fsync`` and stream has no file descriptor.

    .. code-block:: python

        ## Write the text layout to an open file, forcing every line to disk
        sink = StreamSink(open('app.log', 'a'), formatter='text', flush='fsync')
    """

    SPOOLABLE = False

    def __init__(self, stream, formatter=None, flush='flush', terminator='\n'):
        super().__init__(formatter, terminator)
        if not hasattr(stream, 'write'):
            raise TypeError("stream must have a write method")
        self.__flushMode = validate_flush_mode(flush)
        if self.__flushMode in ('fsync', 'fullsync'):
            try:
                stream.fileno()
            except (AttributeError, OSError, ValueError):
                raise ValueError(f"flush={self.__flushMode!r} needs a stream with a file descriptor") from None
        self.__stream = stream
        self.__writeLock = threading.Lock()

    def _reset_after_fork(self):
        """Gives a forked process locks of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        super()._reset_after_fork()
        self.__writeLock = threading.Lock()

    @property
    def flushMode(self):
        """The flush mode: ``none``, ``flush``, ``fsync`` or ``fullsync``."""
        return self.__flushMode

    @property
    def stream(self):
        """The file-like object the sink writes to."""
        return self._get_stream()

    def set_flush_mode(self, flush):
        """
        Changes the flush mode. The next record is written with it.

        :Parameters:
            #. flush (str, None): ``none`` (or None), ``flush``, ``fsync`` or ``fullsync``, see :func:`validate_flush_mode`.

        :Raises:
            #. TypeError: If flush is not a string or None.
            #. ValueError: If flush is not a valid mode, if the stream has no ``flush()`` method and the mode is
               not ``none``, or if the mode is ``fsync`` and the stream has no file descriptor.
        """
        flush = validate_flush_mode(flush)
        stream = self._get_stream()
        if flush != 'none' and not hasattr(stream, 'flush'):
            raise ValueError(f"flush={flush!r} needs a stream with a flush method")
        if flush in ('fsync', 'fullsync'):
            try:
                stream.fileno()
            except (AttributeError, OSError, ValueError):
                raise ValueError(f"flush={flush!r} needs a stream with a file descriptor") from None
        with self.__writeLock:
            self.__flushMode = flush

    def close(self):
        """Flushes the stream. The stream itself is never closed, its owner does that."""
        self.flush()

    def write(self, text, record):
        """
        Writes the text to the stream, then flushes as the flush mode says.

        :Parameters:
            #. text (str): The rendered record, with the terminator.
            #. record (LogRecord): The record that was rendered.
        """
        stream = self._get_stream()
        # One lock around write and flush keeps lines from different threads whole and in order
        with self.__writeLock:
            stream.write(text)
            _apply_flush(stream, self.__flushMode)

    def flush(self):
        """Flushes the stream, whatever the flush mode is."""
        stream = self._get_stream()
        with self.__writeLock:
            if hasattr(stream, 'flush'):
                stream.flush()

    def _get_stream(self):
        """Returns the stream to write to, subclasses may choose it per record."""
        return self.__stream


class ConsoleSink(StreamSink):
    """
    Writes records to the console.

    :Parameters:
        #. stream (file-like, None): The stream to write to. None means the current ``sys.stdout``,
           looked up for every record, so a program that replaces ``sys.stdout`` is followed.
        #. formatter (None, str, callable): How a record becomes text. The default ``'text'`` gives a
           readable line. None gives JSON.
        #. flush (str, None): ``none`` (or None) or ``flush``. ``fsync`` makes no sense on a console and
           is rejected.
        #. terminator (str): Text appended to every rendered record.
        #. decorate (callable, None): ``f(text, record) -> text``, called on the rendered text before the
           terminator is added, for example to wrap it in colour codes. None leaves the text as it is.

    :Raises:
        #. ValueError: If flush is ``fsync``.
        #. TypeError: If decorate is neither callable nor None.

    .. code-block:: python

        ## Readable lines, the default
        sink = ConsoleSink()
        ## One JSON object per line, for a log collector that reads the console
        sink = ConsoleSink(formatter=None)
        ## Every line in red
        sink = ConsoleSink(decorate=lambda text, record: f"\033[31m{text}\033[0m")
    """

    def __init__(self, stream=None, formatter='text', flush='flush', terminator='\n', decorate=None):
        if flush in ('fsync', 'fullsync'):
            raise ValueError(f"flush={flush!r} is not supported on a console")
        if decorate is not None and not callable(decorate):
            raise TypeError("decorate must be callable or None")
        self.__decorate = decorate
        super().__init__(sys.stdout if stream is None else stream, None, flush, terminator)
        self.__followsStdout = stream is None
        self.set_formatter(formatter)

    def set_formatter(self, formatter):
        """
        Changes how the console turns a record into text, the colours are still applied to it.

        :Parameters:
            #. formatter (None, str, callable): None gives JSON, see
               :func:`pysimplelog.formatters.resolve_formatter` for the other values.

        :Raises:
            #. TypeError: If formatter is none of the accepted types.
            #. ValueError: If formatter is a string that is neither a registered keyword nor a template.
        """
        render = resolve_formatter(formatter)
        decorate = self.__decorate
        if decorate is not None:
            super().set_formatter(lambda record: decorate(render(record), record))
        else:
            super().set_formatter(render)

    def _get_stream(self):
        """Returns the current ``sys.stdout``, or the stream given at creation."""
        if self.__followsStdout:
            return sys.stdout
        return super()._get_stream()


class CallbackSink(Sink):
    """
    Hands every rendered record to a function.

    :Parameters:
        #. callback (callable): ``f(text, record)``, called once for every record.
        #. formatter (None, str, callable): How a record becomes text. None gives JSON.
        #. terminator (str): Text appended to every rendered record. The default is empty,
           because a function usually wants the text alone.

    :Raises:
        #. TypeError: If callback is not callable.

    .. code-block:: python

        ## Keep the last readable lines in memory
        lines = []
        sink = CallbackSink(lambda text, record: lines.append(text), formatter='text')
    """

    def __init__(self, callback, formatter=None, terminator=''):
        super().__init__(formatter, terminator)
        if not callable(callback):
            raise TypeError("callback must be callable")
        self.__callback = callback

    def write(self, text, record):
        """
        Calls the callback with the text and the record.

        :Parameters:
            #. text (str): The rendered record.
            #. record (LogRecord): The record that was rendered.
        """
        self.__callback(text, record)


class FileSink(Sink):
    """
    Writes records to a log file, starting a new file when the current one is full.

    Files are named ``<basename>_<N>.<extension>``, and ``<basename>.<extension>`` when
    *firstNumber* is None. The sink continues in the newest file that already exists, and starts the
    next number when that file has reached *maxSize*. With *roll*, the oldest files are deleted so that
    no more than that many remain: this is the only place where old files are deleted, see
    :meth:`_enforce_retention`. The file is created on the first record, and the sink owns it:
    :meth:`close` closes it.

    The sink writes UTF-8 bytes and keeps its own size count, so *maxSize* is exact for any text. A file
    can exceed *maxSize* by the size of one record, because the check happens before a write.

    :Parameters:
        #. basename (str): Directory and file name without extension, for example ``logs/app``. The
           directory is created when it does not exist.
        #. extension (str): File extension. A leading or trailing dot is ignored.
        #. formatter (None, str, callable): How a record becomes text. The default ``'text'`` gives a
           readable line. None gives JSON.
        #. flush (str, None): ``none`` (or None), ``flush``, ``fsync`` or ``fullsync``, see :func:`validate_flush_mode`.
        #. terminator (str): Text appended to every rendered record.
        #. maxSize (None, int, float): Largest size of a file in megabytes. None means a file grows without limit.
        #. roll (None, int): Largest number of files to keep, at least 1. Older files are deleted for good.
           None means files are never deleted.
        #. firstNumber (None, int): Number of the first file, at least 0. None means the first file has no
           number and the second one is numbered 0.

    :Raises:
        #. TypeError: If an argument has the wrong type. A boolean is not accepted where a number is expected.
        #. ValueError: If basename or extension is empty, or maxSize, roll or firstNumber is out of range.

    .. code-block:: python

        ## logs/app_0.log, logs/app_1.log, ... of at most 10 megabytes, keeping the newest 5
        sink = FileSink('logs/app', maxSize=10, roll=5)
        ## One JSON object per line, forced to disk
        sink = FileSink('logs/audit', formatter=None, flush='fsync')
    """

    SPOOLABLE = False

    def __init__(self, basename, extension='log', formatter='text', flush='flush', terminator='\n',
                 maxSize=None, roll=None, firstNumber=0):
        super().__init__(formatter, terminator)
        self.__basename = _check_basename(basename)
        self.__extension = _check_extension(extension)
        self.__flushMode = validate_flush_mode(flush)
        self.__maxBytes = _check_max_size(maxSize)
        self.__roll = _check_roll(roll)
        self.__firstNumber = _check_first_number(firstNumber)
        self.__lock = threading.Lock()
        self.__stream = None
        self.__size = 0
        self.__path = self._choose_path()

    def _reset_after_fork(self):
        """Gives a forked process locks of its own, see :func:`pysimplelog.forking.register_for_fork_reset`."""
        super()._reset_after_fork()
        self.__lock = threading.Lock()

    @property
    def path(self):
        """Path of the file the next record is written to."""
        return self.__path

    @property
    def flushMode(self):
        """The flush mode: ``none``, ``flush``, ``fsync`` or ``fullsync``."""
        return self.__flushMode

    def write(self, text, record):
        """
        Writes the text to the current file, first starting a new file when the current one is full.

        :Parameters:
            #. text (str): The rendered record, with the terminator.
            #. record (LogRecord): The record that was rendered.
        """
        data = text.encode('utf-8', 'backslashreplace')
        with self.__lock:
            if self.__stream is None:
                self.__stream = self._open_stream()
            elif self.__maxBytes is not None and self.__size >= self.__maxBytes:
                self._close_stream()
                self.__path = self._choose_path()
                self.__stream = self._open_stream()
            self.__stream.write(data)
            self.__size += len(data)
            _apply_flush(self.__stream, self.__flushMode)

    def flush(self):
        """
        Flushes the file, whatever the flush mode is.

        :Raises:
            #. OSError: If the buffered data cannot be written.
        """
        with self.__lock:
            if self.__stream is not None:
                self.__stream.flush()

    def set_path(self, basename, extension):
        """
        Changes the base name and the extension of the files, and picks the file to continue in.

        The current file is closed. The new file is chosen like at creation, with the retention settings,
        and is opened by the next record.

        :Parameters:
            #. basename (str): Directory and file name without extension.
            #. extension (str): File extension. A leading or trailing dot is ignored.

        :Raises:
            #. TypeError: If basename or extension is not a string.
            #. ValueError: If basename or extension is empty.
            #. OSError: If the buffered data of the current file cannot be written.
        """
        basename = _check_basename(basename)
        extension = _check_extension(extension)
        with self.__lock:
            self._close_stream()
            self.__basename = basename
            self.__extension = extension
            self.__path = self._choose_path()

    def set_max_size(self, maxSize):
        """
        Changes the largest size of a file. The next record is checked against it.

        :Parameters:
            #. maxSize (None, int, float): Largest size of a file in megabytes. None means no limit.

        :Raises:
            #. TypeError: If maxSize is not None or a number.
            #. ValueError: If maxSize is not greater than zero.
        """
        maxBytes = _check_max_size(maxSize)
        with self.__lock:
            self.__maxBytes = maxBytes

    def set_roll(self, roll):
        """
        Changes the number of files to keep. Old files are deleted the next time a file is chosen, at the next
        rotation or when the base name or extension changes.

        :Parameters:
            #. roll (None, int): Largest number of files to keep, at least 1. None means files are never deleted.

        :Raises:
            #. TypeError: If roll is not None or an integer.
            #. ValueError: If roll is less than 1.
        """
        roll = _check_roll(roll)
        with self.__lock:
            self.__roll = roll

    def set_first_number(self, firstNumber):
        """
        Changes the number of the first file. It is used the next time a file is chosen and no file exists yet.

        :Parameters:
            #. firstNumber (None, int): Number of the first file, at least 0. None means the first file has no number.

        :Raises:
            #. TypeError: If firstNumber is not None or an integer.
            #. ValueError: If firstNumber is less than 0.
        """
        firstNumber = _check_first_number(firstNumber)
        with self.__lock:
            self.__firstNumber = firstNumber

    def set_flush_mode(self, flush):
        """
        Changes the flush mode. The next record is written with it.

        :Parameters:
            #. flush (str, None): ``none`` (or None), ``flush``, ``fsync`` or ``fullsync``, see :func:`validate_flush_mode`.

        :Raises:
            #. TypeError: If flush is not a string or None.
            #. ValueError: If flush is not a valid mode.
        """
        flush = validate_flush_mode(flush)
        with self.__lock:
            self.__flushMode = flush

    def close(self):
        """
        Closes the file. A record written afterwards opens it again.

        :Raises:
            #. OSError: If the buffered data cannot be written.
        """
        with self.__lock:
            self._close_stream()

    def _open_stream(self):
        """Opens the current file for appending and starts the size count from what it already holds."""
        self.__size = self._size_of(self.__path)
        return open(self.__path, 'ab')

    def _close_stream(self):
        """Closes the current file, the stream is dropped even when closing fails."""
        stream, self.__stream = self.__stream, None
        if stream is not None:
            stream.close()

    def _numbered_path(self, number):
        """Returns the path of the file with that number, or the unnumbered file when number is None."""
        if number is None:
            return f"{self.__basename}.{self.__extension}"
        return f"{self.__basename}_{number}.{self.__extension}"

    def _list_existing(self):
        """Returns ``(number, path)`` of the log files that exist, oldest first. The file without a number is the oldest."""
        directory, stem = os.path.split(self.__basename)
        pattern = re.compile(rf"^{re.escape(stem)}(?:_(\d+))?\.{re.escape(self.__extension)}$")
        files = []
        for fileName in os.listdir(directory if len(directory) > 0 else '.'):
            match = pattern.match(fileName)
            path = os.path.join(directory, fileName)
            if match is not None and os.path.isfile(path):
                files.append((None if match.group(1) is None else int(match.group(1)), path))
        files.sort(key=lambda entry: -1 if entry[0] is None else entry[0])
        return files

    def _enforce_retention(self, files, number):
        """
        Deletes old files as the retention settings say and returns the number to continue from.

        This is the only place where old files are deleted. Today it keeps at most *roll* files.
        Other policies, such as the age of a file or the total size, belong here too.
        """
        if self.__roll is None:
            return number
        while len(files) > self.__roll:
            self._delete(files.pop(0)[1])
        if len(files) == self.__roll and self.__maxBytes is not None:
            if self._size_of(files[-1][1]) >= self.__maxBytes:
                # Deleting the oldest makes room for the file about to be started
                self._delete(files.pop(0)[1])
                if number is not None:
                    number += 1
        return number

    @staticmethod
    def _size_of(path):
        """Returns the size of a file in bytes, or 0 when it is missing, for example deleted by another program."""
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    @staticmethod
    def _delete(path):
        """Deletes a file. A failure is ignored: an old file that stays is harmless and must not stop logging."""
        try:
            os.remove(path)
        except OSError:
            pass

    def _choose_path(self):
        """Creates the directory if needed, applies retention, and returns the path of the file to write to."""
        directory = os.path.dirname(self.__basename)
        if len(directory) > 0:
            os.makedirs(directory, exist_ok=True)
        files = self._list_existing()
        number = files[-1][0] if len(files) > 0 else self.__firstNumber
        number = self._enforce_retention(files, number)
        if number is None:
            path = self._numbered_path(None)
            # The unnumbered file counts as number -1, so a full one is followed by number 0
            number = -1
        else:
            path = self._numbered_path(number)
        if self.__maxBytes is not None:
            while os.path.isfile(path) and self._size_of(path) >= self.__maxBytes:
                number += 1
                path = self._numbered_path(number)
        return path
