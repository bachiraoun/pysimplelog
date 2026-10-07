"""
Processors: functions that rewrite every log record before any sink sees it.

A processor is ``f(record) -> record``. It receives the whole record, message, fields and
traceback included, so one function hides local paths or secrets everywhere: the terminal, the
log file, a SIEM sink, every sink. Processors run for every record, in the order they were added.
To treat some records differently, test ``record.logType`` inside the function.

``redact_text`` turns a text function into a processor, and ``redact_fields`` hides the value of
sensitive keys such as passwords and tokens.

Run directly::

    python3 examples/07_processors.py
"""
from pysimplelog import Logger, redact_fields, redact_text


def hide_paths(text):
    """Replace the install folder of the app by three dots."""
    return text.replace('/opt/myapp', '...')


def tag_critical(record):
    """Append a marker to the message of critical records only."""
    if record.logType == 'critical':
        return record._replace(message=f"{record.message}  [PAGE THE ON-CALL]")
    return record


def broken(record):
    """A processor with a bug: the record is dropped, with one warning on stderr."""
    raise RuntimeError('this processor is broken')


def main():
    # 1. Processors given at creation.
    logger = Logger('processors-example', logToFile=False,
                    processors=[redact_text(hide_paths), tag_critical])

    print('--- the path is hidden in the message, the fields and the traceback ---')
    logger.error('cannot open /opt/myapp/data.txt', file='/opt/myapp/data.txt',
                 exc_info='File "/opt/myapp/run.py", line 3, in <module>')

    print('\n--- a processor that looks at the log type ---')
    logger.critical('database is down at /opt/myapp/db')
    logger.info('routine message, not tagged')

    # 2. Add and remove later. remove_processor() takes the function only.
    print('\n--- redact_fields() hides the value of sensitive keys, at any depth ---')
    logger.add_processor(redact_fields())
    logger.info('login', user='mike', password='hunter2', session={'api_key': 'k-123'})

    print('\n--- a broken processor drops the record rather than let it through ---')
    logger.add_processor(broken)
    logger.error('this record is not written')
    logger.error('the warning is printed once per processor, not per record')
    print('records dropped by processors:', logger.processorFailures)

    print('\n--- remove_processor(): records flow again ---')
    logger.remove_processor(broken)
    logger.info('visible again')
    print('\nprocessors:', logger.processors)


if __name__ == '__main__':
    main()
