Processors and filters
======================

Two small hooks sit between your log call and the sinks.

* A **processor** is a function ``f(record) -> record`` that changes a record. It is where secrets are removed and extra
  values are added.
* A **filter** is a function ``f(record) -> bool`` that drops a record when it returns ``False``.

Every record passes the processors first, then the filters, then the sinks.

Keep secrets out of the logs
----------------------------

Nothing is hidden unless you ask. Add the protection you need:

.. code-block:: python

    from pysimplelog import logger, redact_fields, redact_patterns

    logger.add_processor(redact_fields())            ## by name: password, token, api_key, ... in fields and context
    logger.add_processor(redact_patterns())          ## by shape: URLs with a password, Bearer tokens, JWTs, password=...

    logger.info("login", user="ann", password="hunter2")
    logger.info("calling https://admin:hunter2@db.example.org with Authorization: Bearer abc.def.ghi")

.. code-block:: text

    ... | INFO     | pysimplelog | login user=ann password=[REDACTED]
    ... | INFO     | pysimplelog | calling https://admin:[REDACTED]@db.example.org with Authorization: [REDACTED] [REDACTED]

* ``redact_fields`` looks at the **names**. A name counts if it contains one of the words, so ``token`` also hides
  ``access_token`` and ``API-Token``. It looks inside dictionaries and lists, in fields and in context. Give your own words:
  ``redact_fields(DEFAULT_SENSITIVE_NAMES + ("session_id",))``.
* ``redact_patterns`` looks at **text**: the message, the exception, and every text in the fields. It hides only the secret
  part, and leaves the words around it. Choose patterns (``redact_patterns(["bearer", "jwt"])``) or add your own
  (``custom={"order": r"ORD-\d{6}"}``).
* ``redact_text(function)`` turns any text function into a processor, for example to hide folder paths.

If a processor raises, the record is **dropped** for every sink, never let through unredacted. One warning per processor is
written, and ``logger.processorFailures`` counts them.

A value you never want printed
------------------------------

Wrap it in ``Secret``. Every text made from it is ``[REDACTED]``, in every format, and it cannot be pickled by mistake:

.. code-block:: python

    from pysimplelog import Secret

    config = {"user": "admin", "key": Secret("hunter2")}
    logger.info("connecting", config=config)

.. code-block:: text

    ... | INFO     | pysimplelog | connecting config={'user': 'admin', 'key': [REDACTED]}

The record keeps the wrapper, so code that is allowed to can call ``secret.reveal()``. ``hash_secrets()`` is a processor that
replaces every ``Secret`` by a short hash, so two records with the same secret can be matched without showing it:

.. code-block:: python

    from pysimplelog import hash_secrets
    logger.add_processor(hash_secrets())              ## token=hmac:9f2a41c07b3d

The one limit
-------------

The message text is built **before** the processors run. A secret you put into the message, as in
``logger.info("token {}", token)`` or an f-string, is already in the text. ``redact_patterns`` can find the shapes it knows;
otherwise keep the secret out of the message and pass it as a field, or as a ``Secret``.

Add your own processor
----------------------

A processor returns a copy of the record, changed with ``_replace``:

.. code-block:: python

    def add_region(record):
        return record._replace(fields={**record.fields, "region": "eu-west"})

    logger.add_processor(add_region)
    logger.info("hello")
    logger.remove_processor(add_region)

Drop records with a filter
--------------------------

.. code-block:: python

    from pysimplelog import sample, match_logger, match_field

    logger.add_filter(lambda record: record.fields.get("path") != "/health")     ## no health checks
    logger.add_filter(sample(0.1))                                              ## about one record in ten
    logger.add_filter(match_logger("urllib3", "asyncio", exclude=True))         ## silence two libraries

    name = logger.add("audit.log")
    logger.set_sink_filter(name, match_field("category", "security"))           ## one sink, one category

* ``match_logger`` compares logger names by their dotted parts: ``urllib3`` also matches ``urllib3.connectionpool``, and not
  ``urllib3x``.
* ``match_module`` does the same for the module of the caller (it needs ``callerInfo``).
* ``match_field`` keeps the records whose field or context value is one of the values you give.
* Each takes ``exclude=True`` to drop the matches instead.
* A filter that raises keeps the record and is counted in ``logger.filterFailures``.
* ``logger.set_sink_filter(name, None)`` removes a sink's filter.

Next: :doc:`production`.
