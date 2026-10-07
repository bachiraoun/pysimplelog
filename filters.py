"""Ready-made record filters, to give to ``Logger.add_filter`` or to ``Logger.set_sink_filter``."""

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


def _check_names(names, what):
    """Checks that at least one name is given and that each is a non-empty string."""
    if len(names) == 0:
        raise ValueError(f"give at least one {what}")
    for name in names:
        if not isinstance(name, str) or len(name) == 0:
            raise TypeError(f"every {what} must be a non-empty string")


def _is_within(name, prefixes):
    """True when *name* is one of the prefixes or inside one: ``urllib3.connectionpool`` is inside ``urllib3``."""
    return any(name == prefix or name.startswith(prefix + '.') for prefix in prefixes)


def match_logger(*names, exclude=False):
    """
    Makes a filter on the name of the logger a record comes from.

    A record of the standard ``logging`` bridge carries the name of the standard logger, ``urllib3.connectionpool`` for example,
    and the name ``urllib3`` matches it and everything inside it, but not ``urllib3x``. Any other record is matched on the name of
    the pysimplelog logger.

    :Parameters:
        #. names (str): One or more names. A record is kept when its logger is one of them or inside one.
        #. exclude (bool): True to drop those records and keep the others.

    :Returns:
        #. filter (callable): ``f(record) -> bool``.

    :Raises:
        #. ValueError: If no name is given.
        #. TypeError: If a name is not a non-empty string, or exclude is not a boolean.

    .. code-block:: python

        logger.add_filter(match_logger("urllib3", "asyncio", exclude=True))      ## silence two noisy libraries
    """
    _check_names(names, 'name')
    if not isinstance(exclude, bool):
        raise TypeError("exclude must be a boolean")

    def keep(record):
        name = record.fields.get('logger_name', record.logger)
        return _is_within(name, names) != exclude
    return keep


def match_module(*names, exclude=False):
    """
    Makes a filter on the module the log call was made in.

    The module is known only when the logger records the caller (``callerInfo=True``). A record without it cannot be told
    apart, so it is kept, whatever *exclude* is: the filter never drops what it cannot judge.

    :Parameters:
        #. names (str): One or more module names. A record is kept when its module is one of them or inside one.
        #. exclude (bool): True to drop those records and keep the others.

    :Returns:
        #. filter (callable): ``f(record) -> bool``.

    :Raises:
        #. ValueError: If no name is given.
        #. TypeError: If a name is not a non-empty string, or exclude is not a boolean.

    .. code-block:: python

        logger = Logger("app", callerInfo=True)
        logger.add_filter(match_module("app.billing"))      ## only what billing logs
    """
    _check_names(names, 'name')
    if not isinstance(exclude, bool):
        raise TypeError("exclude must be a boolean")

    def keep(record):
        caller = record.caller
        if caller is None:
            return True
        return _is_within(caller.moduleName, names) != exclude
    return keep


def match_field(name, *values, exclude=False):
    """
    Makes a filter on the value of a field or of a context value, for the environment, the tenant, the category.

    The name is looked for in the fields of the record and in its context. A record that has neither is not a match: with
    the default it is dropped, and with ``exclude=True`` it is kept.

    :Parameters:
        #. name (str): The name of the field or context value.
        #. values: One or more values. A record matches when the value of *name* equals one of them.
        #. exclude (bool): True to drop the matching records and keep the others.

    :Returns:
        #. filter (callable): ``f(record) -> bool``.

    :Raises:
        #. ValueError: If no value is given.
        #. TypeError: If name is not a non-empty string, or exclude is not a boolean.

    .. code-block:: python

        logger.set_sink_filter("audit", match_field("category", "security", "billing"))
        logger.add_filter(match_field("environment", "test", exclude=True))      ## nothing from the test environment
    """
    if not isinstance(name, str) or len(name) == 0:
        raise TypeError("name must be a non-empty string")
    if len(values) == 0:
        raise ValueError("give at least one value")
    if not isinstance(exclude, bool):
        raise TypeError("exclude must be a boolean")

    def keep(record):
        for source in (record.fields, record.context):
            if name in source and source[name] in values:
                return not exclude
        return exclude
    return keep
