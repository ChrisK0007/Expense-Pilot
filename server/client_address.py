"""Resolve the real client address behind an explicitly trusted reverse proxy.

Without TRUSTED_PROXIES every request is attributed to its direct peer, exactly
as before. Behind a reverse proxy or tunnel (Nginx Proxy Manager, SWAG,
cloudflared, Caddy) that peer is always the proxy, so every visitor would share
one sign-in rate-limit bucket and a stranger could lock everyone out.

TRUSTED_PROXIES lists the proxy addresses or networks, comma separated, e.g.
"172.17.0.5" or "172.18.0.2". X-Forwarded-For is read only when the direct
peer is trusted, and walked from the right, skipping trusted hops, so a value a
client supplies itself can never be selected over the address a trusted proxy
recorded. Requests that bypass the proxy keep their real peer address.
"""
import ipaddress
import os


def networks(value):
    result = []
    for item in (value or '').split(','):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            raise ValueError(f'TRUSTED_PROXIES contains an invalid address or network: {item!r}') from None
    return tuple(result)


def _address(value):
    value = value.strip()
    if value.startswith('[') and ']' in value:
        value = value[1:value.index(']')]
    elif value.count(':') == 1:
        value = value.split(':', 1)[0]
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _trusted(address, trusted):
    return address is not None and any(address.version == n.version and address in n for n in trusted)


def resolve(peer, forwarded_for, trusted):
    """Return the client address to use for rate limiting."""
    current = _address(peer or '')
    if not trusted or not _trusted(current, trusted) or not forwarded_for:
        return peer
    for hop in reversed(forwarded_for.split(',')):
        address = _address(hop)
        if address is None:
            # A malformed hop ends the chain we can vouch for.
            return str(current)
        current = address
        if not _trusted(current, trusted):
            return str(current)
    return str(current)


class TrustedProxyMiddleware:
    def __init__(self, app, trusted):
        self.app, self.trusted = app, trusted

    def __call__(self, environ, start_response):
        peer = environ.get('REMOTE_ADDR', '')
        environ['expense_pilot.peer_addr'] = peer
        environ['REMOTE_ADDR'] = resolve(peer, environ.get('HTTP_X_FORWARDED_FOR', ''), self.trusted)
        return self.app(environ, start_response)


def install(app, value=None):
    trusted = networks(os.environ.get('TRUSTED_PROXIES', '') if value is None else value)
    if trusted:
        app.wsgi_app = TrustedProxyMiddleware(app.wsgi_app, trusted)
    return trusted
