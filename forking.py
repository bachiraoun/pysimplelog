"""A copy of a program made with ``fork`` has the locks of its parent in whatever state they were, and a lock that another thread held would stay locked forever. This gives the copy fresh locks."""

import os
import weakref

# Objects that own a lock. They are weakly held, so registering one never keeps it alive
_OBJECTS = weakref.WeakSet()


def register_for_fork_reset(obj):
    """
    Asks for an object's locks to be renewed in a forked process. The object needs a ``_reset_after_fork`` method.

    A fork copies every lock in the state it has at that moment. A lock that another thread held then is held for ever in the
    copy, because that thread does not exist in the new process, and the first use of it hangs. The standard ``logging``
    module has the same problem and does the same: the child gets new locks. Nothing else about the object changes.

    .. code-block:: python

        class Worker:
            def __init__(self):
                self.lock = threading.Lock()
                register_for_fork_reset(self)

            def _reset_after_fork(self):
                self.lock = threading.Lock()

    :Parameters:
        #. obj: An object with a ``_reset_after_fork`` method that replaces its locks by new ones, and nothing more.
    """
    _OBJECTS.add(obj)


def _reset_all():
    """Renews the locks of every registered object, in a process that was just forked."""
    for obj in list(_OBJECTS):
        obj._reset_after_fork()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_all)
