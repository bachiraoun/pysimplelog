"""Ready-made record filters, to give to ``Logger.add_filter`` or to a sink."""

import random


def sample(rate):
    """
    Makes a filter that keeps a random share of the records.

    :Parameters:
        #. rate (int, float): The share of records to keep, from 0 (none) to 1 (all). 0.1 keeps about one in ten.

    :Returns:
        #. filter (callable): ``f(record) -> bool``, to give to ``Logger.add_filter`` or ``Logger.set_sink_filter``.

    :Raises:
        #. TypeError: If rate is not a number. A boolean is not accepted.
        #. ValueError: If rate is not between 0 and 1.

    .. code-block:: python

        ## Keep about one record in ten
        logger.add_filter(sample(0.1))
    """
    if not isinstance(rate, (int, float)) or isinstance(rate, bool):
        raise TypeError("rate must be a number")
    if not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")

    def keep(record):
        return random.random() < rate
    return keep
