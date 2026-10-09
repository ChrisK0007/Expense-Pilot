"""Email template defaults and a small, deliberately limited signature format."""
import base64
import io
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit


DEFAULT_TEMPLATES = {
    'invoice': dict(subject='Invoice from {business}', body="Hi {client},\nI've created invoice {number}, payment before the {due_date} would be appreciated.\nBest regards,\n{full_name}"),
    'quote': dict(subject='Quote from {business}', body="Hi {client},\nI've created a quote for {total}.\nBest regards,\n{full_name}"),
    'reminder_due': dict(subject='Due soon invoice reminder', body='Hi {client},\nThis is an automated email to let you know that invoice {number} from {full_name} for {total} is due on {due_date}. Payment before the due date would be appreciated.\nRegards,\n{full_name}'),
    'reminder_overdue': dict(subject='Overdue invoice reminder', body='Hi {client},\nThis is an automated email to let you know that invoice {number} from {full_name} for {total} is now overdue. Payment would be appreciated.\nRegards,\n{full_name}'),
    'reminder_manual': dict(subject='Invoice from {business} is now overdue', body='Hi {client},\nJust a quick reminder that invoice {number} from {business} for {total} was due on {due_date}. Payment would be much appreciated.\nRegards,\n{full_name}'),
    'receipt_partial': dict(subject='{latest_payment} payment receipt', body="Hi {client},\nThanks for your payment of {latest_payment}. You have an outstanding balance of {balance}. I've attached a receipt / invoice for your records.\nBest regards,\n{full_name}"),
    'receipt_full': dict(subject='{total} payment receipt', body="Hi {client},\nThanks for your payment of {total}. I've attached a receipt / invoice for your records.\nBest regards,\n{full_name}"),
    'statement_all': dict(subject='Statement of Accounts', body='Hi {client},\nPlease find attached your statement of account for the period {date_range}.\nPrompt payment of any outstanding amounts would be much appreciated.\nBest regards,\n{full_name}'),
    'statement_outstanding': dict(subject='Statement of Accounts', body='Hi {client},\nPlease find attached your statement of account.\nPrompt payment of any outstanding amounts would be much appreciated.\nBest regards,\n{full_name}'),
}
FIELD_LABELS = dict(client='Client contact name', business='Your business name', full_name='Your full name',
                    number='Document number', total='Document amount', balance='Invoice outstanding amount',
                    due_date='Due date', latest_payment='Invoice latest payment amount', date_range='Date range', kind='Document type')
COMMON_FIELDS = {'client', 'business', 'full_name'}
TEMPLATE_FIELDS = {
    key: COMMON_FIELDS | ({'date_range'} if key == 'statement_all' else set()) if key.startswith('statement_')
    else COMMON_FIELDS | {'number', 'total', 'due_date', 'kind', 'balance'}
         | ({'latest_payment'} if key.startswith('receipt_') else set())
    for key in DEFAULT_TEMPLATES
}


def validate_template(key, value):
    if key not in DEFAULT_TEMPLATES or not isinstance(value, dict) or set(value) != {'subject', 'body'}:
        raise ValueError('Choose a valid email template with a subject and body.')
    result = {}
    for field, maximum in (('subject', 200), ('body', 10000)):
        text = value[field]
        if not isinstance(text, str) or not text.strip() or len(text) > maximum:
            raise ValueError(f'Email {field} is required and must be at most {maximum:,} characters.')
        if field == 'subject' and any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise ValueError('Email subjects cannot contain control characters.')
        unknown = set(re.findall(r'\{([a-z_]+)\}', text)) - TEMPLATE_FIELDS[key]
        if unknown:
            raise ValueError('Unsupported template fields: ' + ', '.join(sorted(unknown)))
        result[field] = text.strip()
    return result


def signature_image(raw):
    from PIL import Image, UnidentifiedImageError
    if len(raw) > 100 * 1024:
        raise ValueError('Signature images must be under 100 KB.')
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in ('PNG', 'JPEG', 'WEBP') or img.width > 300 or img.height > 600:
                raise ValueError('Use a PNG, JPEG or WebP image no wider than 300 px and no taller than 600 px.')
            img.load()
            out = io.BytesIO()
            img.convert('RGBA').save(out, format='PNG', optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('Choose a valid signature image.') from None
    if len(out.getvalue()) > 100 * 1024:
        raise ValueError('Use a smaller signature image; the embedded image must be under 100 KB.')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


def safe_link(value):
    return (not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and urlsplit(value).scheme.lower() in ('https', 'http', 'mailto', 'tel'))


class SignatureParser(HTMLParser):
    tags = {'p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'span', 'font', 'a', 'img', 'small', 'big', 'mark'}
    blocked = {'script', 'style', 'iframe', 'object', 'svg', 'math', 'template'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.plain, self.stack = [], [], []
        self.skip, self.images = 0, 0

    def handle_starttag(self, tag, attrs):
        if self.skip or tag in self.blocked:
            self.skip += 1
            return
        if tag not in self.tags:
            return
        attributes, clean = dict(attrs), {}
        if tag == 'a':
            href = attributes.get('href', '')
            if safe_link(href):
                clean.update(href=href, rel='noopener noreferrer')
        if tag == 'font':
            if re.fullmatch(r'#[0-9a-fA-F]{6}', attributes.get('color', '')):
                clean['color'] = attributes['color']
            if attributes.get('size') in ('1', '2', '3', '4', '5', '6', '7'):
                clean['size'] = attributes['size']
        if tag in ('span', 'font', 'p', 'div', 'mark'):
            styles = []
            for item in attributes.get('style', '').split(';'):
                name, _, value = item.partition(':')
                name, value = name.strip().lower(), value.strip().lower()
                if name in ('color', 'background-color') and re.fullmatch(r'#[0-9a-f]{6}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)', value):
                    styles.append(f'{name}:{value}')
                if name == 'font-size' and value in ('10px', '12px', '14px', '16px', '18px', '20px', '24px'):
                    styles.append(f'{name}:{value}')
            if styles:
                clean['style'] = ';'.join(styles)
        if tag == 'img':
            self.images += 1
            if self.images > 3:
                raise ValueError('Use at most three signature images.')
            source = attributes.get('src', '')
            match = re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', source)
            if not match:
                return
            try:
                clean['src'] = signature_image(base64.b64decode(match[1], validate=True))
            except (ValueError, TypeError):
                raise ValueError('Invalid signature image. Use the image upload button.') from None
            clean['alt'] = attributes.get('alt', 'Signature image')[:200]
            self.plain.append('[' + clean['alt'] + ']')
        self.parts.append('<' + tag + ''.join(' ' + key + '="' + escape(value, quote=True) + '"' for key, value in clean.items()) + '>')
        if tag not in ('br', 'img'):
            self.stack.append(tag)
        if tag in ('br', 'p', 'div'):
            self.plain.append('\n')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ('br', 'img'):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1
            return
        if tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.parts.append('</' + current + '>')
                if current == tag:
                    break
        if tag in ('p', 'div'):
            self.plain.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(escape(data))
            self.plain.append(data)


def clean_signature(value):
    if not isinstance(value, str) or len(value) > 450000:
        raise ValueError('Use at most three images under 100 KB each and 5,000 characters of text.')
    parser = SignatureParser()
    parser.feed(value)
    html = ''.join(parser.parts) + ''.join('</' + tag + '>' for tag in reversed(parser.stack))
    plain = re.sub(r'\n{3,}', '\n\n', ''.join(parser.plain)).strip()
    if len(html) > 450000 or len(plain) > 5000:
        raise ValueError('Use at most three images under 100 KB each and 5,000 characters of text.')
    return html, plain


def add_message_content(outgoing, message, signature_html=''):
    html, plain = clean_signature(signature_html)
    outgoing.set_content(message + ('\n\n' + plain if plain else ''))
    if not html:
        return
    images = []
    def embed(match):
        cid = f'expense-pilot-signature-{len(images)}'
        images.append((cid, base64.b64decode(match[1])))
        return 'src="cid:' + cid + '"'
    html = re.sub(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', embed, html)
    outgoing.add_alternative('<html><body><div>' + escape(message).replace('\n', '<br>')
                             + '</div><br><div>' + html + '</div></body></html>', subtype='html')
    alternative = outgoing.get_payload()[-1]
    for cid, data in images:
        alternative.add_related(data, maintype='image', subtype='png', cid='<' + cid + '>')
