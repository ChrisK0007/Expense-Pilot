"""Read-only PocketSmith v2 client. Never forwards credentials to redirects or links."""
import json
from http.client import HTTPException
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from urllib import error, parse, request

BASE = 'https://api.pocketsmith.com/v2'
MAX_PAGES = 50
MAX_ROWS = 50000
MAX_RESPONSE = 8 * 1024 * 1024


class FeedError(Exception):
    def __init__(self, message, retry_seconds=0):
        super().__init__(message)
        self.retry_seconds = retry_seconds


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_seconds(value):
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        try:
            seconds = int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            seconds = 300
    return max(30, min(seconds, 86400))


class Client:
    def __init__(self, key):
        self.key = key
        self.opener = request.build_opener(NoRedirect())
        self.deadline = time.monotonic() + 60

    def get(self, path, params=None):
        if not re.fullmatch(r'/(?:me|users/[1-9][0-9]*/transaction_accounts|transaction_accounts/[1-9][0-9]*/transactions)', path):
            raise FeedError('Invalid PocketSmith resource.')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise FeedError('Sync took too long. Select fewer accounts or a later start date and try again.')
        url = BASE + path + ('?' + parse.urlencode(params) if params else '')
        req = request.Request(url, headers={'X-Developer-Key': self.key, 'Accept': 'application/json',
                                           'User-Agent': 'Expense-Pilot-bank-feeds'}, method='GET')
        try:
            with self.opener.open(req, timeout=min(10, remaining)) as response:
                data = response.read(MAX_RESPONSE + 1)
                if len(data) > MAX_RESPONSE:
                    raise FeedError('PocketSmith returned too much data. Try a later start date.')
                return json.loads(data, parse_float=Decimal), response.headers
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                raise FeedError('PocketSmith access was denied. Check or replace your developer key.') from None
            if exc.code == 429:
                raise FeedError('PocketSmith is limiting requests. Sync will be available after the retry time.',
                                retry_seconds(exc.headers.get('Retry-After'))) from None
            if exc.code == 404:
                raise FeedError('A PocketSmith account is unavailable. Refresh the account list in connection settings.') from None
            raise FeedError('PocketSmith could not complete the request. Try again later.') from None
        except (error.URLError, TimeoutError, OSError, HTTPException):
            raise FeedError('Could not reach PocketSmith. Check the connection and try again.') from None
        except (ValueError, UnicodeError):
            raise FeedError('PocketSmith returned an invalid response. Try again later.') from None

    def collection(self, path, params=None):
        result, page = [], 1
        while page <= MAX_PAGES:
            data, headers = self.get(path, {**(params or {}), 'per_page': 1000, 'page': page})
            if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                raise FeedError('PocketSmith returned an invalid collection.')
            result.extend(data)
            if len(result) > MAX_ROWS:
                raise FeedError('Too many transactions. Select a later start date.')
            links = re.findall(r'<([^<>]+)>\s*;\s*rel="([^"]+)"', headers.get('Link', ''))
            next_urls = [url for url, rel in links if 'next' in rel.split()]
            if next_urls:
                url = parse.urlsplit(next_urls[0])
                try:
                    next_page = int(parse.parse_qs(url.query)['page'][0])
                except (KeyError, ValueError, IndexError):
                    raise FeedError('PocketSmith returned an invalid next page.') from None
                if (len(next_urls) != 1 or url.scheme != 'https' or url.netloc != 'api.pocketsmith.com'
                        or url.path != '/v2' + path or url.fragment or next_page != page + 1 or not data):
                    raise FeedError('PocketSmith returned an unexpected pagination link.')
            else:
                try:
                    total = int(headers.get('Total', len(result)))
                    if total < 0:
                        raise ValueError()
                except (TypeError, ValueError):
                    raise FeedError('PocketSmith returned an invalid result count.') from None
                if total <= len(result) and (headers.get('Total') is not None or len(data) < 1000):
                    return result
                if not data:
                    raise FeedError('PocketSmith returned an incomplete collection. Nothing was synced.')
            page += 1
        raise FeedError('Too many transaction pages. Select a later start date.')
