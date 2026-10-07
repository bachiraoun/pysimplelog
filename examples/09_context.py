"""
Context: values attached to every record, from ``bind()`` and from ``with logger.context(...)`` blocks.

The values are written in the ``context`` of the record, apart from its fields, and follow the flow of
the program through ``contextvars``: every function a block calls, and each asynchronous task, keeps its own.

Run directly::

    python3 examples/09_context.py
"""
import asyncio

from pysimplelog import Logger


async def handle_request(logger, requestId):
    with logger.context(request_id=requestId):
        logger.info('request received')
        await asyncio.sleep(0)            # other requests run now, each keeps its own request_id
        charge(logger)
        logger.info('request done')


def charge(logger):
    # No argument carries the request: the function only logs, and the record still knows it.
    with logger.context(step='payment'):
        logger.info('charging')


async def main(logger):
    await asyncio.gather(*(handle_request(logger, f'req-{n}') for n in range(2)))


def run():
    logger = Logger('context-example', logToFile=False, consoleFormatter=None)

    print('--- bind(): fixed values for one logger object ---')
    logger.bind(service='orders', environment='production').info('service started')

    print('\n--- context(): values for a block, also across asynchronous tasks ---')
    asyncio.run(main(logger))


if __name__ == '__main__':
    run()
