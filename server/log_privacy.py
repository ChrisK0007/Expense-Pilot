"""Redact bearer URLs and labelled credentials before logging handlers receive them.

Installed in both Gunicorn's master and standalone application entry points.
This deliberately leaves request data untouched; proxies need their own policy.
"""
import logging
import re
import traceback

# Match ordinary and URL-encoded links (including links inside query strings).
# Consume the URL suffix too: it can repeat the credential in query parameters.
_QUOTE_URL = re.compile(r'(?P<prefix>(?:/|%2f|%252f)(?:q|%71|%2571)(?:u|%75|%2575)(?:o|%6f|%256f)(?:t|%74|%2574)(?:e|%65|%2565)(?:/|%2f|%252f))[^\s\"\'<>]+', re.IGNORECASE)


# Headers can contain multiple credentials; redact their entire line.
_HEADERS = re.compile(r'(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+')
# Labelled values in JSON, key=value diagnostics and query strings.
_CREDENTIALS = re.compile(
    r"""(?ix)(["']?\b(?:password|current_password|token|csrf|sid|api[_-]?key|access[_-]?token|refresh[_-]?token|setup[_-]?token|csrf[_-]?token|client[_-]?secret|secret)["']?\s*[:=]\s*)"""
    r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s&,;\]}]+)"""
)
_EMAIL = re.compile(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def redact(value):
    value = _QUOTE_URL.sub(lambda match: match['prefix'] + '[REDACTED]', value)
    value = _HEADERS.sub(lambda match: match[1] + '[REDACTED]', value)
    value = _CREDENTIALS.sub(lambda match: match[1] + '[REDACTED]', value)
    return _EMAIL.sub('[REDACTED EMAIL]', value)


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
