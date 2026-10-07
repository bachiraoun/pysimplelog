"""
Dedicated 'admin_error' logType: pysimplelog's real @logger.catch decorator,
a path-hiding processor, and SIEM opt-in filtering.

The problem this solves:
    1. You want @logger.catch on a handful of sensitive methods/functions,
       and you want ONLY those caught exceptions to reach your SIEM
       collector -- not every plain logger.error() call in the app. A
       brand new logType ('admin_error'), kept separate from the built-in
       'error', plus an opt-in SIEM sink (logTypeFlags={'admin_error':
       True}, defaultFlag=False) solves that part.
    2. A raw traceback always contains the REAL absolute filesystem path
       of every stack frame -- e.g. wherever this app/pysimplelog is
       actually installed on disk. That must never reach a SIEM team.
       A processor added with logger.add_processor() runs a f(record) -> record
       callable on every record, before any sink gets it. redact_text() turns a
       text function into one: it is applied to the message, the exception message
       and full traceback, and every string field, so every sink -- local
       file, stdout, SIEM, all of them -- only ever sees the sanitized text.
       One place, applied once.

Run directly::

    python3 examples/06_admin_error_catch_siem.py
"""
import ntpath
import posixpath
import re

from pysimplelog import Logger, redact_text
from pysimplelog.contrib import siem_sink


# ── processor function, added once with logger.add_processor() ─────────
#
# Your own app would likely have something shaped like this already --
# see the PARAMETERS.* / lazy_loaders.SITE_PACKAGES style example from
# earlier in this conversation. This one is regex-based and generic:
# collapses absolute paths down to just their basename. URLs are left
# untouched. Heuristic, not a guarantee -- good enough to stop the common
# case (your own install path leaking through a traceback) cold.

_TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)"')
_UNIX_PATH_RE = re.compile(r'(?<!:/)(?<![:\w])(?:/[\w.\-]+){2,}')
_WIN_PATH_RE = re.compile(r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)+[^\\/:*?"<>|\r\n]+')


def hide_paths(text, placeholder='<redacted>'):
    """Return *text* with absolute filesystem paths collapsed to just
    their basename -- added with logger.add_processor().

    :Parameters:
        #. text (str): The message or traceback text to scrub.
        #. placeholder (str): Replaces the directory portion of every
           redacted path. Default '<redacted>'.

    :Returns:
        #. redacted (str): The scrubbed text.
    """
    if not text:
        return text

    def _sub_traceback_file(match):
        fullPath = match.group(1)
        base = ntpath.basename(fullPath) if '\\' in fullPath else posixpath.basename(fullPath)
        return 'File "%s/%s"' % (placeholder, base)

    def _make_sub(pathmod):
        def _sub(match):
            base = pathmod.basename(match.group(0))
            return '%s/%s' % (placeholder, base) if base else placeholder
        return _sub

    text = _TRACEBACK_FILE_RE.sub(_sub_traceback_file, text)
    text = _WIN_PATH_RE.sub(_make_sub(ntpath), text)
    text = _UNIX_PATH_RE.sub(_make_sub(posixpath), text)
    return text


def main():
    logger = Logger(name='admin-error-example', logToFile=False, logToStdout=True)

    # 1. A dedicated logType, separate from the built-in 'error'.
    logger.add_log_type('admin_error', name='ADMIN_ERROR',
                         level=logger.logTypeLevels['error'], color='red', attributes=['bold'])

    # 2. SIEM sink is opt-in (defaultFlag=False) and only 'admin_error' is
    #    switched on -- every other logType stays purely local.
    sink = siem_sink.quick_attach(
        logger, protocol='console',
        logTypeFlags={'admin_error': True}, defaultFlag=False,
    )

    # 3. A processor doing the path redaction, then the REAL logger.catch()
    #    from pysimplelog -- no sink-wrapping, no reimplementing catch().
    #    The processor sees the finished record, message AND traceback, before
    #    any sink does, so the local log line and the SIEM-forwarded copy are
    #    identically scrubbed.
    hideInRecord = redact_text(hide_paths)

    def hide_paths_of_admin_errors(record):
        """Hide the paths of admin_error records only, every other record goes on untouched."""
        return hideInRecord(record) if record.logType == 'admin_error' else record

    logger.add_processor(hide_paths_of_admin_errors)

    @logger.catch(logType='admin_error', message='admin action failed')
    def delete_user(userId):
        if userId == 'root':
            raise PermissionError("refusing to delete 'root'")
        print('deleted user %s' % userId)

    print('--- ordinary error: logged locally, NOT forwarded to SIEM ---')
    logger.error('just a routine validation error, nobody paged for this')

    print('\n--- admin_error via logger.catch() and the hide_paths processor: scrubbed everywhere ---')
    delete_user('root')   # swallowed (reraise defaults to False)

    print('\n--- happy path: no exception, nothing forwarded ---')
    delete_user('alice')

    logger.flush(timeout=2.0)
    siem_sink.detach(logger, sink)
    print('\ndone -- neither the local line above nor the [SIEM] line has a real filesystem path')


if __name__ == '__main__':
    main()
