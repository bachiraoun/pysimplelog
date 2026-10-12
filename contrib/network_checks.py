"""Checks shared by the network transports: whether an address stays on this machine, and a warning when records travel in clear text."""

import ipaddress
import sys


def is_local_host(host):
    """
    Says whether a host name or address stays on this machine.

    :Parameters:
        #. host (str): A host name or an IP address.

    :Returns:
        #. isLocal (bool): True for ``localhost`` and for a loopback address, False otherwise.
    """
    if host == 'localhost' or host.endswith('.localhost'):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def warn_if_cleartext(destination, host):
    """
    Writes one warning on the error stream when records go without encryption to another machine.

    :Parameters:
        #. destination (str): Where the records go, such as ``http://collector:8088/x``. It must not hold a token.
        #. host (str): The host of the destination.
    """
    if is_local_host(host):
        return
    try:
        sys.stderr.write(f"pysimplelog WARNING: records are sent to {destination} without encryption, "
                         "anyone on the network can read them\n")
    except (OSError, ValueError):
        # The error stream is closed or broken, and a warning must never stop the logger
        pass
