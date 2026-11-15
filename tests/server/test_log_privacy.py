"""Exercise the actual Gunicorn log formatter and Flask exception logging."""
import io
import logging
import unittest
from types import SimpleNamespace
from urllib.parse import quote
from gunicorn.config import Config
from gunicorn.glogging import Logger
import log_privacy


class LogPrivacyTest(unittest.TestCase):
    def test_gunicorn_access_preserves_normal_logs_and_redacts_quote_urls(self):
        log_privacy.install()
        config = Config(); config.set('accesslog', '-')
        logger = Logger(config)
        output = io.StringIO(); handler = logging.StreamHandler(output)
        old = logger.access_log.handlers[:]
        logger.access_log.handlers = [handler]
        self.addCleanup(setattr, logger.access_log, 'handlers', old)
        secret = 'bearer-secret-123456789'
        from datetime import timedelta
        for method in ('GET', 'POST'):
            for suffix in ('', '/pdf', '?copy='+secret):
                path = '/quote/'+secret+suffix
                env = {'REQUEST_METHOD': method, 'RAW_URI': path, 'PATH_INFO': path,
                       'SERVER_PROTOCOL': 'HTTP/1.1', 'REMOTE_ADDR': '127.0.0.1',
                       'HTTP_REFERER': 'https://example.test/quote/'+secret,
                       'HTTP_USER_AGENT': 'test'}
                logger.access(SimpleNamespace(status='500 Error', sent=12, headers=[]), [], env, timedelta(seconds=1))
        logger.access(SimpleNamespace(status='200 OK', sent=34, headers=[]), [],
                      {'REQUEST_METHOD': 'GET', 'RAW_URI': '/api/session', 'SERVER_PROTOCOL': 'HTTP/1.1'}, timedelta(seconds=1))
        result = output.getvalue()
        self.assertNotIn(secret, result)
        self.assertIn('GET /api/session HTTP/1.1', result)
        self.assertIn('POST /quote/[REDACTED]', result)
        self.assertIn('500', result)

    def test_encoded_query_links_and_exception_tracebacks(self):
        log_privacy.install()
        output = io.StringIO(); handler = logging.StreamHandler(output)
        logger = logging.getLogger('privacy-test'); logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        link = 'https://example.test/quote/secret-token/pdf?copy=secret-token'
        for value in (link, link.replace('quote', '%71uote'), quote(link, safe=''), quote(quote(link, safe=''), safe='')):
            try:
                raise ValueError('Failed at '+value)
            except ValueError:
                logger.exception('Exception on %s', value)
        self.assertNotIn('secret-token', output.getvalue())
        self.assertIn('ValueError', output.getvalue())
        self.assertIn('[REDACTED]', output.getvalue())
