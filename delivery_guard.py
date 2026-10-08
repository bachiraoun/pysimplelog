"""
Remembers that the current thread is delivering records to sinks, so the standard logging bridge can refuse the records that delivery itself makes.
"""

import threading

_STATE = threading.local()


def mark_delivery_thread():
    """Marks the current thread as one that only delivers records to sinks, for as long as it lives."""
    _STATE.isWorker = True


def enter_bridge():
    """Notes that the current thread is passing a standard logging record to a Logger."""
    _STATE.depth = getattr(_STATE, 'depth', 0) + 1


def leave_bridge():
    """Notes that the current thread has finished passing a standard logging record to a Logger."""
    _STATE.depth -= 1


def is_delivering():
    """
    Says whether the current thread is a delivery thread, or is inside the bridge.

    :Returns:
        #. isDelivering (bool): True when a record made now would come from the delivery of another record.
    """
    return getattr(_STATE, 'isWorker', False) or getattr(_STATE, 'depth', 0) > 0
