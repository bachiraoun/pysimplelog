"""
Turns the plain-English values of Logger.add() into the numbers and sinks that the sink classes take.
"""

import os
import re

try:
    from .sinks import FileSink
except ImportError:
    from sinks import FileSink

SIZE_UNITS_IN_MEGABYTES = {'kb': 1 / 1024, 'mb': 1, 'gb': 1024}
DURATION_UNITS_IN_SECONDS = {'second': 1, 'seconds': 1, 'minute': 60, 'minutes': 60, 'hour': 3600,
                             'hours': 3600, 'day': 86400, 'days': 86400, 'week': 604800, 'weeks': 604800}
_AMOUNT_RE = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*$')


def _parse_amount(text, units, description):
    """Returns the amount of a text such as ``500 MB`` in the base unit of *units*."""
    match = _AMOUNT_RE.match(text)
    if match is None or match.group(2).lower() not in units:
        raise ValueError(f"{description} must look like '500 MB' with a unit in {sorted(units)}, got {text!r}")
    return float(match.group(1)) * units[match.group(2).lower()]


def parse_size(rotation):
    """
    Converts the size at which a file is rotated into megabytes.

    :Parameters:
        #. rotation (str, int, float): A text such as ``"500 MB"`` with the unit KB, MB or GB, or a number of megabytes.

    :Returns:
        #. megabytes (float): The size in megabytes.

    :Raises:
        #. TypeError: If *rotation* is not a text or a number.
        #. ValueError: If the text has no known unit. A time of day such as ``"00:00"`` is not supported.
    """
    if isinstance(rotation, bool) or not isinstance(rotation, (str, int, float)):
        raise TypeError("rotation must be a text such as '500 MB' or a number of megabytes")
    if isinstance(rotation, str):
        return _parse_amount(rotation, SIZE_UNITS_IN_MEGABYTES, "rotation")
    return float(rotation)


def parse_duration(retention):
    """
    Converts the age after which a rotated file is deleted into seconds.

    :Parameters:
        #. retention (str): A text such as ``"30 days"`` with the unit seconds, minutes, hours, days or weeks.

    :Returns:
        #. seconds (float): The age in seconds.

    :Raises:
        #. ValueError: If the text has no known unit.
    """
    return _parse_amount(retention, DURATION_UNITS_IN_SECONDS, "retention")


def build_file_sink(path, formatter, rotation, retention, compression):
    """
    Builds the sink of a log file from a path and the plain-English options of Logger.add().

    :Parameters:
        #. path (str, os.PathLike): The file, with an extension, for example ``logs/app.log``.
        #. formatter (None, str, callable): How a record becomes text, see :func:`pysimplelog.formatters.resolve_formatter`.
        #. rotation (None, str, int, float): The size at which the file is rotated, see :func:`parse_size`.
        #. retention (None, str, int): A text such as ``"30 days"`` deletes rotated files that age. A whole
           number keeps that many files.
        #. compression (None, str): ``'gz'`` compresses a file when it is rotated.

    :Returns:
        #. sink (FileSink): The sink.

    :Raises:
        #. ValueError: If the path has no extension, or *retention* is given without *rotation*.
        #. TypeError: If *retention* is neither a text nor a whole number.
    """
    basename, extension = os.path.splitext(os.fspath(path))
    if extension == '':
        raise ValueError(f"the file {str(path)!r} needs an extension, for example 'app.log'")
    maxSize = None if rotation is None else parse_size(rotation)
    if retention is not None and maxSize is None:
        raise ValueError("retention needs rotation: without it the file is never rotated, so there is nothing to delete")
    maxAge = None
    roll = None
    if isinstance(retention, str):
        maxAge = parse_duration(retention)
    elif isinstance(retention, int) and not isinstance(retention, bool):
        roll = retention
    elif retention is not None:
        raise TypeError("retention must be a text such as '30 days' or a number of files")
    # A file that never rotates keeps its plain name, numbers only tell the files of a rotation apart
    firstNumber = None if maxSize is None else 0
    return FileSink(basename, extension=extension, formatter=formatter, maxSize=maxSize, roll=roll,
                    firstNumber=firstNumber, compress=compression, maxAge=maxAge)
