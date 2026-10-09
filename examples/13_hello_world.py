"""
Hello world: the shared ``logger`` needs no setup, and ``{}`` fills a message with values.

Run directly::

    python3 examples/13_hello_world.py
"""
from pysimplelog import logger


def run():
    logger.info("Application started")
    logger.warning("Disk is {}% full", 91)
    logger.error("Could not reach {host}", host="db.example.org")

    # Values passed as keywords stay on the record as fields, apart from the text
    logger.info("User {} logged in", 7, user_id=7, service="auth")

    # Debug is shown by default. Run with PYSIMPLELOG_LEVEL=INFO to hide it, without changing this file
    logger.debug("A detail for the developer")


if __name__ == '__main__':
    run()
