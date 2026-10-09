Context
=======

Fields describe one event. **Context** describes where the event happens: the request being served, the user, the job, the
step. You set it once, and every record made afterwards carries it, without passing it to each call.

Bind values to a logger
-----------------------

``bind`` gives you a logger that adds its values to every record:

.. code-block:: python

    from pysimplelog import logger

    log = logger.bind(request_id="r-42", user="ann")
    log.info("Request received")
    log.error("Authorisation failed", reason="expired")

.. code-block:: text

    2026-10-08 21:30:00.100 | INFO     | pysimplelog | Request received request_id=r-42 user=ann
    2026-10-08 21:30:00.101 | ERROR    | pysimplelog | Authorisation failed request_id=r-42 user=ann reason=expired

The values come before the fields on the line. In JSON they are kept apart, in ``context`` and ``fields``. ``bind`` does not
change ``logger``, it gives a new object, and binding again adds to what is already bound.

Context for a block of code
---------------------------

``context`` does the same for everything that happens inside a ``with`` block, whichever logger makes the record, and also in the
functions that block calls:

.. code-block:: python

    from pysimplelog import logger, context

    def charge():
        logger.info("Charging")

    with context(request_id="r-42"):
        logger.info("Order created")
        with context(step="payment"):
            charge()
        logger.info("Back to the order")

.. code-block:: text

    ... | INFO     | pysimplelog | Order created request_id=r-42
    ... | INFO     | pysimplelog | Charging request_id=r-42 step=payment
    ... | INFO     | pysimplelog | Back to the order request_id=r-42

Blocks nest. An inner value replaces an outer one with the same name until its block ends, and the outer value is back afterwards,
also when the block ends with an error.

As a decorator, and in asynchronous code
----------------------------------------

The same ``context(...)`` can decorate a function, so every call runs inside it, and can be used with ``async with``:

.. code-block:: python

    import asyncio
    from pysimplelog import logger, context

    @context(job="nightly")
    def run():
        logger.info("Running the job")

    async def handle(number):
        async with context(task=number):
            await asyncio.sleep(0)
            logger.info("Handled")

    async def main():
        await asyncio.gather(handle(1), handle(2))

    run()
    asyncio.run(main())

Each asynchronous task keeps its own values. A generator function cannot be decorated, because its block would end when the
generator is made, so use a ``with`` block inside it.

Threads
-------

A plain ``threading.Thread`` starts with no context. Wrap the function you give it with ``keep_context``, which hands over the
values of the code that starts the thread. It works with executors too:

.. code-block:: python

    import threading
    from pysimplelog import logger, context, keep_context

    def work():
        logger.info("In the thread")

    with context(request_id="r-42"):
        thread = threading.Thread(target=keep_context(work))
        thread.start()
        thread.join()

Values for the whole program
----------------------------

Values that are the same for every record, such as the service, the environment or the host, are added by a processor, and
reach the records of the standard ``logging`` package as well:

.. code-block:: python

    import socket
    from pysimplelog import logger, add_context

    logger.add_processor(add_context(service="checkout", environment="production", host=socket.gethostname()))
    logger.info("Started")

Give a function as a value to compute it for each record, such as the current request:
``add_context(request_id=lambda: current_request_id())``. A name the call already has in its context is left as it is.

Good to know
------------

* The values are held, not copied. A list you put in the context and change later is written changed, which a sink that
  writes after the call has returned can show.
* Context does not cross into another process. A child made with ``fork`` has the values of the moment it was made, and one made
  with ``spawn`` has none.
* ``redact_fields`` also looks inside the context, see :doc:`processors_and_filters`.

Next: :doc:`exceptions`.
