API Reference
=============

Core
----

.. automodule:: pysimplelog.SimpleLog
    :members:
    :undoc-members:
    :show-inheritance:

SIEM / Syslog Forwarding (pysimplelog.contrib)
-----------------------------------------------

Optional, zero-mandatory-dependency add-on for forwarding log records to a
SIEM (Security Information and Event Management) or syslog collector. See
:doc:`getting_started` for a quick example, or the ``examples/`` directory
in the source distribution for runnable end-to-end scripts covering
console, UDP, TCP, and HTTP collectors.

.. automodule:: pysimplelog.contrib.siem_sink
    :members:
    :undoc-members:
    :show-inheritance:

.. automodule:: pysimplelog.contrib.siem_transport
    :members:
    :undoc-members:
    :show-inheritance:
