"""Redact public quote bearer URLs before Python logging handlers receive them.

Installed in both Gunicorn's master and standalone application entry points.
This deliberately leaves request data untouched; proxies need their own policy.
"""
import logging
import re
import traceback

# Match ordinary and URL-encoded links (including links inside query strings).
# Consume the URL suffix too: it can repeat the credential in query parameters.
_QUOTE_URL = re.compile(r'(?P<prefix>(?:/|%2f|%252f)(?:q|%71|%2571)(?:u|%75|%2575)(?:o|%6f|%256f)(?:t|%74|%2574)(?:e|%65|%2565)(?:/|%2f|%252f))[^\s\"\'<>]+', re.IGNORECASE)


def redact(value):
    return _QUOTE_URL.sub(lambda match: match['prefix'] + '[REDACTED]', value)


def install():
    previous = logging.getLogRecordFactory()
    if getattr(previous, '_quote_privacy', False):
        return

    def record_factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(''.join(traceback.format_exception(*record.exc_info)))
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return record

    record_factory._quote_privacy = True
    logging.setLogRecordFactory(record_factory)
