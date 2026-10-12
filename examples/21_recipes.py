"""
Recipes: your own log types, and a function that sends errors somewhere else.

Run directly::

    python3 examples/21_recipes.py
"""
from functools import partial

from pysimplelog import Logger


def make_sender(sent):
    """Returns a sink that keeps what it would send. A real one would post to Slack, call a webhook or send an email."""
    def send(text, record):
        sent.append(f"{record.severity}: {record.message}")
    return send


def run():
    logger = Logger('recipes', logToFile=False, consoleFormatter='text')

    # Your own log types, called like methods
    logger.add_log_type('success', name='SUCCESS', level=25, color='green')
    logger.add_log_type('trace', name='TRACE', level=5, color='grey')
    success = partial(logger.log, 'success')
    success("order {} shipped", 42)

    # Only errors and above go to the function
    sent = []
    logger.add(make_sender(sent), name='alerts', level='ERROR')
    logger.info("this one stays on the console")
    logger.error("payment failed for order {}", 42)
    print('sent:', sent)


if __name__ == '__main__':
    run()
