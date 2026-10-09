"""Stops a loop: a sink that sends logs over the network may use a library that itself logs, and those logs would come back into the same sink, forever. This remembers when a thread is busy delivering."""

import threading

_STATE = threading.local()


def mark_delivery_thread():
    """Marks the current thread as a delivery thread, one that only writes records to outputs, for as long as it lives."""
    _STATE.isWorker = True


def enter_bridge():
    """Notes that the current thread has started passing a standard logging record to a logger."""
    _STATE.depth = getattr(_STATE, 'depth', 0) + 1


def leave_bridge():
    """Notes that the current thread has finished passing a standard logging record to a logger."""
    _STATE.depth -= 1


def is_delivering():
    """
    Says whether a record made now would come from the delivery of another record.

    Says whether the current thread is a delivery thread, or is inside the bridge.

    :Returns:
        #. isDelivering (bool): True when a record made now would come from the delivery of another record.
    """
    return getattr(_STATE, 'isWorker', False) or getattr(_STATE, 'depth', 0) > 0
