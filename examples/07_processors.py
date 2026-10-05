"""
Processors: functions that rewrite every finished log record before any sink sees it.

A processor is ``f(text) -> text`` and receives the WHOLE record, message, data and
traceback included, so one function hides local paths or secrets everywhere: the
terminal, the log file, a SIEM sink, every sink. ``processors`` is a dictionary:
key ``None`` holds the functions run for every log type, every other key is a log
type holding the functions run only for that type.

Run directly::

    python3 examples/07_processors.py
"""
from pysimplelog import Logger


def hide_paths(text):
    """Replace the install folder of the app by three dots."""
    return text.replace('/opt/myapp', '...')


def tag_critical(text):
    """Append a marker to critical records only."""
    return text.rstrip('\n') + '  [PAGE THE ON-CALL]'


def broken(text):
    """A processor with a bug: it is skipped, with one warning on stderr."""
    raise RuntimeError('this processor is broken')


def main():
    # 1. Processors given at creation: None for every log type, a key per log type.
    logger = Logger('processors-example', logToFile=False,
                    processors={None: [hide_paths], 'critical': [tag_critical]})

    print('--- the path is hidden in the message, the data and the traceback ---')
    logger.error('cannot open /opt/myapp/data.txt', data='file=/opt/myapp/data.txt',
                 tback='File "/opt/myapp/run.py", line 3, in <module>')

    print('\n--- a processor for one log type only ---')
    logger.critical('database is down at /opt/myapp/db')
    logger.info('routine message, not tagged')

    # 2. Add and remove later. remove_processor() takes the function only and removes
    #    it from every list it is in.
    print('\n--- add_processor() later, and a broken processor that is skipped ---')
    logger.add_processor(broken)
    logger.error('still logged, and still hidden: /opt/myapp/x')
    logger.error('the warning above is printed once per processor, not per record')

    print('\n--- remove_processor(): the path is visible again ---')
    logger.remove_processor(hide_paths)
    logger.error('now visible: /opt/myapp/y')
    print('\nprocessors:', logger.processors)


if __name__ == '__main__':
    main()
