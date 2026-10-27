"""Explicit receipt AI selection. Secrets and provider calls stay on the server."""
import base64
import hashlib
import ipaddress
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from cryptography.fernet import Fernet, InvalidToken
from flask import jsonify, request

MODES = {'none': 'No AI', 'local_ollama': 'Local Ollama', 'remote_ollama': 'Existing / remote Ollama', 'cloud': 'Cloud AI'}
CLOUD = {'openai': 'https://api.openai.com/v1', 'anthropic': 'https://api.anthropic.com/v1'}
OLLAMA_READ_TIMEOUT = 300
CLOUD_READ_TIMEOUT = 150


class AIError(ValueError):
    pass


def config():
    from billing import settings
    url, model = os.environ.get('OLLAMA_URL', '').rstrip('/'), os.environ.get('OLLAMA_MODEL', '')
    return settings('receipt_ai', dict(mode='remote_ollama' if url and model else 'none',
                    url=url, model=model, provider='openai', key_encrypted='', cloud_consent=False))


def box():
    from app import DATA
    key = hashlib.sha256(b'Expense Pilot receipt AI v1\0' + (DATA/'session.key').read_bytes()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def configured(c=None):
    c = c or config()
    return c['mode'] != 'none' and bool(c['model']) and (bool(c['key_encrypted']) and c['cloud_consent'] if c['mode'] == 'cloud' else bool(c['url']))


def public_config():
    c = config()
    return {k: v for k, v in c.items() if k != 'key_encrypted'} | {'key_saved': bool(c['key_encrypted']), 'configured': configured(c), 'label': MODES[c['mode']]}


def validate_url(value):
    if not isinstance(value, str) or len(value) > 500 or any(ord(c) < 33 for c in value):
        raise AIError('Enter a valid Ollama server address.')
    try:
        u = urlsplit(value); port = u.port
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
            raise ValueError()
        if u.scheme == 'http':
            # Owner-selected LAN/Docker services are intentional; public hosts need TLS.
            try: local = ipaddress.ip_address(u.hostname).is_private
            except ValueError: local = '.' not in u.hostname or u.hostname.endswith(('.local', '.internal', '.test'))
            if not local: raise AIError('Use HTTPS for a remote Ollama server, or a trusted private LAN/Docker address.')
    except (ValueError, TypeError):
        raise AIError('Use an Ollama base URL without credentials, a path or query parameters.') from None
    return value.rstrip('/')


def save(data):
    from billing import save_settings
    if not isinstance(data, dict): raise AIError('Expected AI settings.')
    old = config(); mode = data.get('mode')
    if mode not in MODES: raise AIError('Choose an AI mode.')
    provider = data.get('provider', old['provider'])
    if provider not in CLOUD: raise AIError('Choose a supported cloud provider.')
    model = data.get('model', '').strip() if isinstance(data.get('model', ''), str) else ''
    if len(model) > 200 or any(ord(c) < 33 for c in model): raise AIError('Enter a valid model ID.')
    url = 'http://ollama:11434' if mode == 'local_ollama' else data.get('url', old['url'])
    if mode in ('local_ollama', 'remote_ollama'): url = validate_url(url)
    # A key must never silently follow a different provider or host.
    same_target = mode == old['mode'] and provider == old['provider'] and url == old['url']
    encrypted = old['key_encrypted'] if same_target else ''
    secret = data.get('api_key', '')
    if not isinstance(secret, str) or len(secret) > 4096 or any(ord(c) < 33 for c in secret): raise AIError('Enter a valid API key.')
    if data.get('clear_key') is True: encrypted = ''
    elif secret: encrypted = box().encrypt(secret.encode()).decode()
    if mode != 'none' and not model: raise AIError('Choose a model before enabling AI.')
    consent = mode == 'cloud' and data.get('cloud_consent') is True
    if mode == 'cloud' and (not consent or not encrypted):
        raise AIError('Enter an API key and confirm that receipt data may be sent to this cloud provider and charges may apply.')
    result = dict(mode=mode, provider=provider, url=url, model=model, key_encrypted=encrypted, cloud_consent=consent)
    save_settings('receipt_ai', result)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AIError('AI endpoint redirected. Enter its direct address; no data or key was forwarded.')


def fetch(c, path, payload=None):
    headers = {'Content-Type': 'application/json'}
    try: key = box().decrypt(c['key_encrypted'].encode()).decode() if c['key_encrypted'] else ''
    except InvalidToken: raise AIError('The saved AI key cannot be read. Re-enter it in Settings.') from None
    cloud = c['mode'] == 'cloud'
    if cloud and c['provider'] == 'anthropic': headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    elif key: headers['Authorization'] = 'Bearer ' + key
    url = (CLOUD[c['provider']] if cloud else c['url']) + path
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    timeout = (CLOUD_READ_TIMEOUT if cloud else OLLAMA_READ_TIMEOUT) if payload else 20
    timeout_message = ('Ollama did not finish reading this document within 5 minutes. Check the selected model and Ollama server load in Settings. '
                       if not cloud else 'The AI service took too long to read this document. ')
    timeout_message += 'The original is saved; retry from Document inbox or enter the figures manually.'
    if not payload: timeout_message = 'The AI connection test timed out. Check the server address and whether the AI service is running.'
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024: raise AIError('AI response exceeded the supported size.')
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        message = {401: 'AI authentication failed. Check your API key.', 403: 'The AI provider denied access. Check your key permissions.', 404: 'AI endpoint or model not found. Check Settings.', 429: 'AI quota or rate limit reached. Retry later or check provider billing.'}.get(exc.code, 'AI provider could not complete the request. Retry or enter the receipt manually.')
        raise AIError(message) from None
    except TimeoutError:
        raise AIError(timeout_message) from None
    except (OSError, ValueError) as exc:
        if isinstance(exc, AIError): raise
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
            raise AIError(timeout_message) from None
        raise AIError('Cannot reach the selected AI service or read its response. Check the address, TLS and model; manual entry remains available.') from None


def models():
    c = config()
    if c['mode'] == 'none': return []
    result = fetch(c, '/models' if c['mode'] == 'cloud' else '/api/tags')
    items = result.get('data', []) if c['mode'] == 'cloud' else result.get('models', [])
    return sorted({str(x.get('id') if c['mode'] == 'cloud' else x.get('name')) for x in items if isinstance(x, dict) and (x.get('id') if c['mode'] == 'cloud' else x.get('name'))})[:500]


def extract(prompt, images):
    c = config()
    if not configured(c): raise AIError('AI is disabled. Choose an AI mode in Settings or enter the receipt manually.')
    if c['mode'] in ('local_ollama', 'remote_ollama'):
        msg = {'role': 'user', 'content': prompt}
        if images: msg['images'] = images
        result = fetch(c, '/api/chat', {'model': c['model'], 'stream': False, 'think': False, 'format': 'json', 'messages': [msg], 'options': {'temperature': 0, 'num_predict': 2048}})
        if result.get('done_reason') == 'length':
            raise AIError('Ollama reached its response limit before completing this document. Try another model or enter the figures manually.')
        content = result.get('message', {}).get('content', '')
    elif c['provider'] == 'openai':
        content = [{'type': 'input_text', 'text': prompt}] + [{'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + x} for x in images]
        result = fetch(c, '/responses', {'model': c['model'], 'store': False, 'max_output_tokens': 4096, 'text': {'format': {'type': 'json_object'}}, 'input': [{'role': 'user', 'content': content}]})
        if result.get('status') != 'completed': raise AIError('AI did not finish reading the receipt. Try another model or enter it manually.')
        content = ''.join(p.get('text', '') for o in result.get('output', []) if o.get('type') == 'message' for p in o.get('content', []) if p.get('type') == 'output_text')
    else:
        content = [{'type': 'text', 'text': prompt}] + [{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': x}} for x in images]
        result = fetch(c, '/messages', {'model': c['model'], 'max_tokens': 4096, 'messages': [{'role': 'user', 'content': content}]})
        if result.get('stop_reason') != 'end_turn': raise AIError('AI did not finish reading the receipt. Try another model or enter it manually.')
        content = ''.join(x.get('text', '') for x in result.get('content', []) if x.get('type') == 'text')
    try:
        value = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip()))
        if not isinstance(value, dict): raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError): raise AIError('AI returned unreadable receipt fields. Retry or enter the details manually.') from None


def register(app, auth):
    @app.route('/api/ai/settings', methods=['GET', 'PUT'])
    @auth('owner')
    def ai_settings():
        from app import audit, db, fail
        if request.method == 'PUT':
            try: save(request.get_json())
            except AIError as exc: fail(str(exc))
            audit('AI settings updated', 'receipt AI'); db().commit()
        return jsonify(public_config())

    @app.post('/api/ai/test')
    @auth('owner')
    def ai_test():
        from app import fail
        try: choices = models()
        except AIError as exc: fail(str(exc), 502)
        c = config()
        return jsonify(ok=True, models=choices, selected_available=c['model'] in choices,
                       message='AI is disabled.' if c['mode'] == 'none' else 'Connected. No receipts were sent. Choose a vision-capable model; model listing does not verify image support.')
