"""Import public HTTPS signature images once, never while previewing or sending mail."""
import concurrent.futures
import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit

from billing_email_core import signature_image

MAX_BYTES = 2 * 1024 * 1024
IMPORT_SECONDS = 8
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='signature-image')
_slots = threading.BoundedSemaphore(4)


class ImageImportError(ValueError):
    pass


def public_address(value):
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast:
        return False
    if address.version == 6 and (address.ipv4_mapped or address.sixtofour or address.teredo
            or address in ipaddress.ip_network('64:ff9b::/96')
            or address in ipaddress.ip_network('64:ff9b:1::/48')):
        return False
    return True


def destination(url):
    try:
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ValueError()
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            raise ValueError()
        host = parsed.hostname.encode('idna').decode('ascii')
        if '%' in host or not host or '\\' in host:
            raise ValueError()
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not public_address(item[4][0]) for item in addresses):
            raise ValueError()
        preferred = next((item for item in addresses if item[0] == socket.AF_INET), addresses[0])
        return host, preferred[4][0], parsed.path or '/', parsed.query
    except (ValueError, UnicodeError, OSError):
        raise ImageImportError('Use a public HTTPS image link, or upload the image with Add image.') from None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the checked address while validating TLS against the original host."""
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _stop_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def fetch_image(url, deadline):
    """Bound redirects, response size and wall time; never pass cookies or credentials."""
    try:
        for redirect in range(4):
            host, address, path, query = destination(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            connection = PinnedHTTPSConnection(host, address, timeout=min(3, remaining))
            timer = None
            try:
                connection.connect()
                timer = threading.Timer(max(0, deadline-time.monotonic()), _stop_socket, args=(connection.sock,))
                timer.daemon = True
                timer.start()
                connection.request('GET', path + ('?' + query if query else ''), headers={
                    'Accept': 'image/png,image/jpeg,image/webp', 'Accept-Encoding': 'identity',
                    'User-Agent': 'Expense-Pilot-Signature/1', 'Connection': 'close'})
                response = connection.getresponse()
                try:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader('Location')
                        if not location or redirect == 3:
                            raise ImageImportError('The image link redirects too many times. Use Add image instead.')
                        url = urljoin(url, location)
                        continue
                    if response.status != 200:
                        raise ImageImportError('The image host refused the download or requires sign-in. Use Add image instead.')
                    if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                        raise ImageImportError('The image host returned an unsupported download. Use Add image instead.')
                    if response.getheader('Content-Type', '').split(';')[0].strip().lower() not in ('image/png', 'image/jpeg', 'image/webp', 'application/octet-stream'):
                        raise ImageImportError('This link opens a page rather than a PNG, JPEG or WebP image. Use Add image instead.')
                    length = response.getheader('Content-Length')
                    if length is not None and (not length.isdigit() or int(length) > MAX_BYTES):
                        raise ImageImportError('The linked image exceeds 2 MB. Use a smaller image.')
                    data = bytearray()
                    while len(data) <= MAX_BYTES:
                        if time.monotonic() >= deadline:
                            raise TimeoutError()
                        chunk = response.read(min(65536, MAX_BYTES + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                    return signature_image(bytes(data))
                finally:
                    response.close()
            finally:
                if timer:
                    timer.cancel()
                connection.close()
    except ImageImportError:
        raise
    except (TimeoutError, socket.timeout):
        raise ImageImportError('The image download timed out. Try pasting again or use Add image.') from None
    except (OSError, http.client.HTTPException):
        raise ImageImportError('The image could not be downloaded. Use Add image instead.') from None
    except ValueError as error:
        raise ImageImportError(str(error)) from None


def import_images(sources):
    """At most three URLs, shared deadline, bounded workers even if DNS stalls."""
    if len(sources) > 3:
        raise ImageImportError('Use at most three signature images.')
    deadline = time.monotonic() + IMPORT_SECONDS
    pending, resolved, errors = {}, {}, {}
    for source in dict.fromkeys(sources):
        if not source.lower().startswith('https://'):
            errors[source] = 'This image was not included in the clipboard. Use Add image to replace it.'
            continue
        if not _slots.acquire(blocking=False):
            errors[source] = 'Image importing is busy. Try pasting again or use Add image.'
            continue
        try:
            future = _pool.submit(fetch_image, source, deadline)
        except BaseException:
            _slots.release()
            raise
        future.add_done_callback(lambda completed: _slots.release())
        pending[source] = future
    for source, future in pending.items():
        try:
            resolved[source] = future.result(timeout=max(0, deadline-time.monotonic()))
        except concurrent.futures.TimeoutError:
            future.cancel()
            errors[source] = 'The image download timed out. Try pasting again or use Add image.'
        except ImageImportError as error:
            errors[source] = str(error)
    return resolved, errors
