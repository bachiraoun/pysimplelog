"""
A pythonic, simple yet complete system logger supporting simultaneous output to stdout,
a rotating log file, and any number of user-supplied sinks.

pysimplelog supports ANSI text colouring and formatting attributes when the output
stream allows it.  For singleton use, import ``SingleLogger`` in place of ``Logger``.

Installation guide
==================
pysimplelog requires Python 3.6 or later and has no mandatory third-party dependencies
(``pytz`` is optional and only needed when a timezone name is passed to the constructor).
Install from PyPI using pip:

.. code-block:: console

    pip install pysimplelog

Alternatively, fork pysimplelog's `GitHub repository
<https://github.com/bachiraoun/pysimplelog/>`_ and copy the package to
Python's site-packages directory.
"""

try:
    from .__pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from .SimpleLog import Logger, SingleLogger
except ImportError:
    from __pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from SimpleLog import Logger, SingleLogger


def get_version():
    """Get pysimplelog's version number."""
    return __version__

def get_author():
    """Get pysimplelog's author's name."""
    return __author__

def get_email():
    """Get pysimplelog's author's email."""
    return __email__

def get_doc():
    """Get pysimplelog's official online documentation link."""
    return __onlinedoc__

def get_repository():
    """Get pysimplelog's official online repository link."""
    return __repository__

def get_pypi():
    """Get pysimplelog's PyPI link."""
    return __pypi__
