"""
Redaction: hide secrets by their field name, by their shape in text, or by wrapping the value in ``Secret``. The processors run
before every output, so files, JSON, SIEM and the spool never see the value.

Run directly::

    python3 examples/17_redaction.py
"""
from pysimplelog import Logger, Secret, redact_fields, redact_patterns, hash_secrets


def run():
    logger = Logger('redaction-example', logToFile=False, consoleFormatter='text',
                    processors=[redact_fields(), redact_patterns(), hash_secrets(b'a-key-kept-out-of-the-code')])

    # By name: password, token, authorization, api_key, secret, cookie, credential, ssn, credit_card
    logger.info('login', user='ann', password='hunter2', headers={'Cookie': 'sid=abc', 'Accept': 'text/html'})

    # By shape, in any text
    logger.info('calling https://admin:pw123@db.example.org with password=hunter2')

    # By wrapping: a Secret prints as [REDACTED] everywhere, and hash_secrets turns it into a short code
    logger.info('key in use', key=Secret('sk-live-123'), again=Secret('sk-live-123'))


if __name__ == '__main__':
    run()
