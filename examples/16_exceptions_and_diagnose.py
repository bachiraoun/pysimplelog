"""
Exceptions: ``logger.exception()`` keeps the whole chain, and ``diagnose`` adds the values of the variables on each line,
hiding the sensitive ones.

Run directly::

    python3 examples/16_exceptions_and_diagnose.py
"""
import io
import json

from pysimplelog import Logger

# Python quotes the source line of a failing call in a traceback, so a secret is passed from a constant and not written there
PASSWORD = 'hunter' + '2'


def charge(password, amount, quantity):
    return amount * quantity + password


def run():
    stream = io.StringIO()
    logger = Logger('exceptions-example', logToFile=False, logToStdout=False, diagnose=True)
    logger.add(stream, format='json')

    try:
        try:
            charge(PASSWORD, 19.9, 3)
        except TypeError as error:
            raise RuntimeError('payment failed') from error
    except RuntimeError:
        logger.exception('Payment calculation failed', order_id=7)

    record = json.loads(stream.getvalue())
    print('type    :', record['exception']['type'])
    print('message :', record['exception']['message'])
    print('fields  :', record['fields'])
    print(record['exception']['stacktrace'])


if __name__ == '__main__':
    run()
