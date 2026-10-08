"""
Switches off the records of the loggers under a namespace, for every logger of the process.
"""

import os
import threading

try:
    from .environment import ENV_PREFIX
except ImportError:
    from environment import ENV_PREFIX

NAMESPACE_ENV_NAME = f"{ENV_PREFIX}NAMESPACE_DISABLE"

_LOCK = threading.Lock()
# Replaced as a whole and never changed in place, so a log call reads it without a lock
_DISABLED = frozenset()
_isEnvironmentRead = False


def _check_namespace(namespace):
    """Raises ValueError unless the namespace is a dotted name such as ``payments`` or ``payments.stripe``."""
    if not isinstance(namespace, str):
        raise TypeError("namespace must be a string")
    if namespace == '' or '' in namespace.split('.'):
        raise ValueError(f"namespace must be a dotted name without empty parts, got {namespace!r}")


def _names_in_environment():
    """Returns the namespaces in the environment variable, in order, without blank pieces and without checking them."""
    text = os.environ.get(NAMESPACE_ENV_NAME, '')
    return [name.strip() for name in text.split(',') if name.strip() != '']


def _update_environment(namespace, isAdded):
    """Adds a namespace to the environment variable, or removes it, so processes started later inherit the change."""
    names = [name for name in _names_in_environment() if name != namespace]
    if isAdded:
        names.append(namespace)
    if len(names) > 0:
        os.environ[NAMESPACE_ENV_NAME] = ','.join(names)
    else:
        os.environ.pop(NAMESPACE_ENV_NAME, None)


def _load_environment():
    """
    Adds the namespaces of ``PYSIMPLELOG_NAMESPACE_DISABLE`` to the disabled ones, once per process.

    The variable is a comma separated list. A process that is already running never sees a change of it.
    """
    global _DISABLED, _isEnvironmentRead
    with _LOCK:
        if _isEnvironmentRead:
            return
        # Set before the check so that a bad value raises once, and not at every later log call
        _isEnvironmentRead = True
        names = _names_in_environment()
        for name in names:
            try:
                _check_namespace(name)
            except ValueError as error:
                raise ValueError(f"{NAMESPACE_ENV_NAME}: {error}") from None
        _DISABLED = _DISABLED | frozenset(names)


def disable(namespace, env=False):
    """
    Drops the records of every logger named *namespace* or under it, such as ``payments.stripe`` for ``payments``.

    It applies to every logger of the process, including the ones made later, and to the records that the
    standard logging bridge forwards under that name. :func:`pysimplelog.simple_log.Logger.force_log` is not
    affected. Other processes are not affected by default: a child made by ``fork`` gets a copy of the list as
    it was, a child made by ``spawn`` starts with an empty one. With *env* True the namespace is also added to
    the environment variable ``PYSIMPLELOG_NAMESPACE_DISABLE``, a comma separated list that every process
    started afterwards reads once. A process that is already running never sees it. It can also be set
    outside the program, for example ``export PYSIMPLELOG_NAMESPACE_DISABLE="payments,urllib3"``.

    .. code-block:: python

        import pysimplelog

        ## An application silences a noisy library
        pysimplelog.disable("payments")
        ## ... and the processes it starts later
        pysimplelog.disable("urllib3", env=True)
        ## A library can be quiet until the application asks for it
        pysimplelog.disable("mylib")
        pysimplelog.enable("mylib")

    :Parameters:
        #. namespace (str): A dotted name, for example ``payments``.
        #. env (bool): True also writes the namespace to ``os.environ`` for the processes started later.

    :Raises:
        #. TypeError: If *namespace* is not a string, or *env* is not a boolean.
        #. ValueError: If *namespace* is empty or has an empty part, or the environment variable is wrong.
    """
    global _DISABLED
    _check_namespace(namespace)
    if not isinstance(env, bool):
        raise TypeError("env must be a boolean")
    _load_environment()
    with _LOCK:
        _DISABLED = _DISABLED | {namespace}
    if env:
        _update_environment(namespace, True)


def enable(namespace, env=False):
    """
    Takes back a :func:`disable` of exactly the same namespace, whether it came from a call or from the
    environment variable. Nothing happens when it was not disabled.

    :Parameters:
        #. namespace (str): The namespace given to :func:`disable`.
        #. env (bool): True also removes the namespace from ``PYSIMPLELOG_NAMESPACE_DISABLE`` in ``os.environ``,
           for the processes started later.

    :Raises:
        #. TypeError: If *namespace* is not a string, or *env* is not a boolean.
        #. ValueError: If *namespace* is empty or has an empty part, or the environment variable is wrong.
    """
    global _DISABLED
    _check_namespace(namespace)
    if not isinstance(env, bool):
        raise TypeError("env must be a boolean")
    _load_environment()
    with _LOCK:
        _DISABLED = _DISABLED - {namespace}
    if env:
        _update_environment(namespace, False)


def is_disabled(name):
    """
    Says whether a logger name is under a disabled namespace.

    :Parameters:
        #. name (str): A logger name, for example ``payments.stripe``.

    :Returns:
        #. isDisabled (bool): True when the name or one of its dotted prefixes was disabled.

    :Raises:
        #. ValueError: If the environment variable is wrong, the first time only.
    """
    if not _isEnvironmentRead:
        _load_environment()
    disabled = _DISABLED
    if len(disabled) == 0:
        return False
    parts = name.split('.')
    return any('.'.join(parts[:count]) in disabled for count in range(1, len(parts) + 1))
