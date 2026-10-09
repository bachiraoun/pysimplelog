"""
Files: ``add()`` writes to a file in one call, with rotation, retention, compression and the JSON layout.

Run directly::

    python3 examples/14_files_and_rotation.py
"""
import os
import tempfile

from pysimplelog import Logger


def run():
    folder = tempfile.mkdtemp(prefix='pysimplelog-example-')
    logger = Logger('files-example', logToFile=False, logToStdout=False)

    # Text file, a new file every 1 KB, the last 3 kept
    textName = logger.add(os.path.join(folder, 'app.log'), rotation='1 KB', retention=3)
    # One JSON object per line, errors only
    jsonName = logger.add(os.path.join(folder, 'errors.jsonl'), format='json', level='ERROR')

    for number in range(60):
        logger.info('a line that is long enough to fill the file quickly {}', number)
    logger.error('something failed', order_id=5)

    # remove() stops an output and closes its file
    logger.remove(textName)
    logger.remove(jsonName)

    for name in sorted(os.listdir(folder)):
        print(f'{name:16s} {os.path.getsize(os.path.join(folder, name)):6d} bytes')


if __name__ == '__main__':
    run()
