"""
Reads the PYSIMPLELOG_ environment variables that set up a logger, so a program is configured without changing its code.
"""

import os

try:
    from .formatters import resolve_formatter
except ImportError:
    from formatters import resolve_formatter

ENV_PREFIX = 'PYSIMPLELOG_'
COLOR_MODES = ('auto', 'always', 'never')


class _NotGiven:
    """The default of an argument that the environment may set, so a value the caller gave can be told apart."""

    def __repr__(self):
        return "<default>"


NOT_GIVEN = _NotGiven()


def read_environment():
    """
    Reads the variables that configure the console of a logger.

    ``PYSIMPLELOG_LEVEL`` is a number or the key or name of a log type, such as ``DEBUG``. ``PYSIMPLELOG_FORMAT`` is
    ``pretty``, ``text``, ``json`` or a template such as ``{timestamp} {message}``. ``PYSIMPLELOG_COLOR`` is
    ``auto``, ``always`` or ``never``. A variable that is empty or not set is ignored.

    :Returns:
        #. settings (dict): ``stdoutMinLevel`` (float, str), ``consoleFormatter`` (str) and ``consoleColor`` (str),
           only for the variables that are set.

    :Raises:
        #. ValueError: If ``PYSIMPLELOG_FORMAT`` is not a format, or ``PYSIMPLELOG_COLOR`` is not a colour mode. The
           message names the variable.
    """
    settings = {}
    level = os.environ.get(f"{ENV_PREFIX}LEVEL", '').strip()
    if level != '':
        try:
            settings['stdoutMinLevel'] = float(level)
        except ValueError:
            settings['stdoutMinLevel'] = level
    formatter = os.environ.get(f"{ENV_PREFIX}FORMAT", '').strip()
    if formatter != '':
        try:
            resolve_formatter(formatter)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{ENV_PREFIX}FORMAT is not a format: {error}") from None
        settings['consoleFormatter'] = formatter
    color = os.environ.get(f"{ENV_PREFIX}COLOR", '').strip().lower()
    if color != '':
        if color not in COLOR_MODES:
            raise ValueError(f"{ENV_PREFIX}COLOR must be one of {COLOR_MODES}, got {color!r}")
        settings['consoleColor'] = color
    return settings
