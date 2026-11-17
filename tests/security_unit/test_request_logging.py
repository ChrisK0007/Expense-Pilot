"""Regression tests for request envelopes and secret-safe Python logging."""
import io
import logging
from types import SimpleNamespace
import unittest
from urllib.parse import quote

import log_privacy
import request_security


class Rejected(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


class RequestEnvelopeTest(unittest.TestCase):
    def check(self, payload, *, method="POST", headers=None, is_json=True, path="/api/login"):
        req = SimpleNamespace(path=path, method=method, headers=headers or {},
                              is_json=is_json, get_json=lambda: payload)
        request_security.validate(req, lambda *args: self.reject(*args))

    def reject(self, *args):
        raise Rejected(*args)

    def test_non_object_json_is_rejected_without_coercion(self):
        for value in (None, [], ["value"], "value", 1, True):
            with self.subTest(value=value), self.assertRaises(Rejected) as error:
                self.check(value)
            self.assertEqual(error.exception.status, 400)

    def test_browser_cross_site_request_is_rejected_even_with_csrf_header(self):
        with self.assertRaises(Rejected) as error:
            self.check({}, headers={"Sec-Fetch-Site": "cross-site", "X-CSRF-Token": "synthetic"})
        self.assertEqual(error.exception.status, 403)

    def test_native_same_origin_multipart_and_reads_are_preserved(self):
        self.check({})
        self.check({}, headers={"Sec-Fetch-Site": "same-origin"})
        self.check(None, is_json=False)
        self.check(None, method="GET")
        self.check(None, path="/quote/synthetic")


class CredentialLogTest(unittest.TestCase):
    def test_labelled_credentials_headers_and_email_are_removed(self):
        cases = [
            'Authorization: Bearer synthetic-credential',
            'Cookie: session=synthetic-credential; other=another',
            '{"password": "synthetic-credential", "status": 401}',
            "{'api_key': 'synthetic-credential'}",
            'GET /api/login?access_token=synthetic-credential&status=401',
            'setup_token=synthetic-credential',
            'sid=synthetic-credential',
        ]
        for value in cases:
            with self.subTest(value=value):
                clean = log_privacy.redact(value)
                self.assertNotIn("synthetic-credential", clean)
                self.assertIn("[REDACTED]", clean)
        self.assertNotIn("person@example.test", log_privacy.redact("user=person@example.test"))
        self.assertEqual(log_privacy.redact("GET /api/session 200"), "GET /api/session 200")

    def test_quote_links_still_redact_after_encoding(self):
        link = "https://example.test/quote/synthetic-secret/pdf?copy=synthetic-secret"
        for value in (link, quote(link, safe=""), quote(quote(link, safe=""), safe="")):
            self.assertNotIn("synthetic-secret", log_privacy.redact(value))

    def test_formatter_receives_redacted_message_exception_and_stack(self):
        previous = logging.getLogRecordFactory()
        self.addCleanup(logging.setLogRecordFactory, previous)
        log_privacy.install()
        installed = logging.getLogRecordFactory()
        log_privacy.install()
        self.assertIs(installed, logging.getLogRecordFactory())
        output = io.StringIO()
        logger = logging.getLogger("security-unit-regression")
        handler = logging.StreamHandler(output)
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        message_secret = 'synthetic-message-secret'
        try:
            raise ValueError("password=synthetic-exception-secret")
        except ValueError:
            logger.exception("request failed: api_key=%s", message_secret, stack_info=True)
        clean = output.getvalue()
        self.assertNotIn("synthetic-exception-secret", clean)
        self.assertNotIn("synthetic-message-secret", clean)
        self.assertIn("ValueError", clean)
