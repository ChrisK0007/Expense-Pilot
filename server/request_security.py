"""Validate API request envelopes without changing native cookie authentication."""


def validate(request, fail):
    if not request.path.startswith('/api/') or request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    # Browsers supply this forbidden header. Native clients may omit it.
    # Keep CSRF mandatory as well: metadata alone is not authentication.
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        fail('Cross-site requests are not allowed.', 403)
    if request.is_json and not isinstance(request.get_json(), dict):
        fail('Expected a JSON object.')
