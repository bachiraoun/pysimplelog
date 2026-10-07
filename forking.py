"""What a process that was forked needs from the objects that hold locks, sockets and threads of its parent."""

import os
import weakref

# Objects that own a lock. They are weakly held, so registering one never keeps it alive
_OBJECTS = weakref.WeakSet()


def register_for_fork_reset(obj):
    """
    Makes an object get a fresh set of locks in a process that was forked.

    A fork copies every lock in the state it has at that moment. A lock that another thread held then is held for ever in the
    copy, because that thread does not exist in the new process, and the first use of it hangs. The standard ``logging``
    module has the same problem and does the same: the child gets new locks. Nothing else about the object changes.

    :Parameters:
        #. obj: An object with a ``_reset_after_fork`` method that replaces its locks by new ones, and nothing more.
    """
    _OBJECTS.add(obj)


def _reset_all():
    """Runs in the new process right after a fork, before any other thread of it exists."""
    for obj in list(_OBJECTS):
        obj._reset_after_fork()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_reset_all)
