"""Public image imports and inline email attachments; no live HTTP or SMTP."""
import io
import base64
import socket
import ssl
import threading
import time
import unittest
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from PIL import Image
import test_app
from app import app
from billing_email_core import add_message_content, signature_image
import signature_images as images


def png(colour='blue'):
    out=io.BytesIO();Image.new('RGB',(40,20),colour).save(out,'PNG');return out.getvalue()


def address(value='93.184.215.14'):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(value,443))]


def response(data=None,status=200,**headers):
    result=MagicMock();result.status=status
    stream=io.BytesIO(png() if data is None else data)
    result.read.side_effect=stream.read
    fields={'Content-Type':'image/png',**headers}
    result.getheader.side_effect=lambda key,default=None:fields.get(key,default)
    return result


class ImageDownloadTest(unittest.TestCase):
    def test_download_follows_public_redirect_and_pins_each_connection(self):
        first=response(status=302,Location='https://cdn.example.test/icon.png')
        second=response()
        with patch.object(images.socket,'getaddrinfo',return_value=address()),patch.object(images,'PinnedHTTPSConnection') as factory:
            factory.return_value.getresponse.side_effect=[first,second]
            actual=images.fetch_image('https://cloud.example.test/s/share/preview?size=100',time.monotonic()+5)
        self.assertEqual(actual,signature_image(png()))
        self.assertEqual([c.args[:2] for c in factory.call_args_list],[('cloud.example.test','93.184.215.14'),('cdn.example.test','93.184.215.14')])
        request=factory.return_value.request.call_args_list[0]
        self.assertEqual(request.args,('GET','/s/share/preview?size=100'))
        self.assertNotIn('Cookie',request.kwargs['headers']);self.assertNotIn('Authorization',request.kwargs['headers'])
        first.close.assert_called_once();second.close.assert_called_once()

    def test_tls_uses_checked_address_and_verifies_original_hostname(self):
        connection=images.PinnedHTTPSConnection('images.example.test','93.184.215.14',2)
        self.assertTrue(connection._context.check_hostname);self.assertEqual(connection._context.verify_mode,ssl.CERT_REQUIRED)
        context=MagicMock();connection._context=context
        with patch.object(images.socket,'create_connection') as connect:
            connection.connect()
        connect.assert_called_once_with(('93.184.215.14',443),2)
        context.wrap_socket.assert_called_once_with(connect.return_value,server_hostname='images.example.test')

    def test_private_mixed_multicast_and_translation_addresses_never_connect(self):
        for value in ['127.0.0.1','10.1.2.3','169.254.169.254','192.168.1.2','100.64.1.2','0.0.0.0','224.0.0.1','::1','fc00::1','fe80::1','ff02::1','::ffff:127.0.0.1','64:ff9b::7f00:1','2002:7f00:1::']:
            with self.subTest(value=value),patch.object(images.socket,'getaddrinfo',return_value=address(value)),patch.object(images,'PinnedHTTPSConnection') as connect:
                with self.assertRaises(images.ImageImportError):images.fetch_image('https://images.example.test/logo',time.monotonic()+5)
                connect.assert_not_called()
        with patch.object(images.socket,'getaddrinfo',return_value=address()+address('10.0.0.1')):
            with self.assertRaises(images.ImageImportError):images.destination('https://mixed.example.test/icon')

    def test_rejects_credentials_ports_other_schemes_and_control_characters(self):
        for url in ['http://example.test/a','file:///tmp/a','https://user:secret@example.test/a','https://example.test:8443/a','https://example.test/a\r\nHost:x','https://[fe80::1%25eth0]/a']:
            with self.subTest(url=url),patch.object(images.socket,'getaddrinfo') as resolve:
                with self.assertRaises(images.ImageImportError):images.destination(url)
                resolve.assert_not_called()

    def test_redirect_cannot_switch_to_private_address_or_http(self):
        for location in ['https://private.example.test/secret','http://public.example.test/a']:
            with self.subTest(location=location),patch.object(images.socket,'getaddrinfo',side_effect=[address(),address('127.0.0.1')]),patch.object(images,'PinnedHTTPSConnection') as factory:
                factory.return_value.getresponse.return_value=response(status=302,Location=location)
                with self.assertRaises(images.ImageImportError):images.fetch_image('https://public.example.test/a',time.monotonic()+5)
                self.assertEqual(factory.call_count,1)

    def test_unusable_content_size_status_redirect_limit_and_timeout(self):
        bad=[response(status=403),response(**{'Content-Type':'text/html'}),response(**{'Content-Length':str(images.MAX_BYTES+1)}),response(**{'Content-Encoding':'gzip'}),response(b'not an image'),response(b'x'*(images.MAX_BYTES+1)),response(status=302,Location='/again')]
        for item in bad:
            with self.subTest(item=item),patch.object(images.socket,'getaddrinfo',return_value=address()),patch.object(images,'PinnedHTTPSConnection') as factory:
                factory.return_value.getresponse.return_value=item
                with self.assertRaises(images.ImageImportError):images.fetch_image('https://images.example.test/a',time.monotonic()+5)
                self.assertLessEqual(factory.call_count,4)
        with patch.object(images.socket,'getaddrinfo',return_value=address()),patch.object(images,'PinnedHTTPSConnection') as factory:
            factory.return_value.getresponse.side_effect=TimeoutError()
            with self.assertRaisesRegex(images.ImageImportError,'timed out'):images.fetch_image('https://images.example.test/a',time.monotonic()+5)

    def test_batch_deduplicates_and_bounds_wait_for_stalled_worker(self):
        with patch.object(images,'fetch_image',return_value=signature_image(png())) as fetch:
            result,errors=images.import_images(['https://images.example.test/a']*2+['cid:missing'])
        self.assertEqual(fetch.call_count,1);self.assertIn('https://images.example.test/a',result);self.assertIn('cid:missing',errors)
        release=threading.Event();finished=threading.Event()
        def slow(*args):
            release.wait(2);finished.set();return signature_image(png())
        try:
            with patch.object(images,'IMPORT_SECONDS',.03),patch.object(images,'fetch_image',side_effect=slow):
                started=time.monotonic();result,errors=images.import_images(['https://images.example.test/slow'])
            self.assertLess(time.monotonic()-started,.5);self.assertFalse(result);self.assertIn('timed out',next(iter(errors.values())))
        finally:
            release.set();finished.wait(1)


class SignaturePasteTest(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    login=test_app.AppTest.login
    call=test_app.AppTest.call

    def signature(self):
        return '<table><tr><td><img alt="Photo" width="90" src="https://cloud.example.test/s/sample/preview"></td><td><b>Example Pilot</b><br>Flight examiner<br><a href="mailto:pilot@example.test">Email</a><br><a href="https://social.example.test/profile"><img width="20" alt="Social one" src="https://icons.example.test/one.png"></a><a href="https://social.example.test/second"><img width="20" alt="Social two" src="https://icons.example.test/two.png"></a></td></tr></table>'

    def test_three_hosted_images_preserve_links_save_and_embed_in_outgoing_email(self):
        values=[signature_image(png(c)) for c in ('red','green','blue')]
        def fetch(url,deadline):return values[0 if '/s/' in url else 1 if 'one.png' in url else 2]
        with patch.object(images,'fetch_image',side_effect=fetch) as download:
            r=self.call(self.owner,'billing/signature-paste',dict(html=self.signature()))
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0);self.assertEqual(download.call_count,3)
        html=r.json['html'];self.assertEqual(html.count('data:image/png;base64,'),3)
        self.assertIn('width="90"',html);self.assertIn('width="20"',html);self.assertIn('https://social.example.test/profile',html);self.assertNotIn('cloud.example.test',html)
        with patch.object(images,'fetch_image',side_effect=AssertionError('Must not fetch on save or send')):
            saved=self.call(self.owner,'billing/email-templates',dict(signature_html=html),'PUT')
            self.assertEqual(saved.status_code,200,saved.json);self.assertEqual(saved.json['signature_html'],html)
            self.assertEqual(self.owner.get('/api/billing/email-templates').json['signature_html'],html)
            message=EmailMessage();add_message_content(message,'Invoice message',html)
        content=message.get_body(preferencelist=('html',)).get_content()
        self.assertEqual(content.count('src="cid:'),3);self.assertNotIn('data:image',content)
        self.assertEqual([p.get_payload(decode=True) for p in message.walk() if p.get_content_type()=='image/png'],[base64.b64decode(value.split(',',1)[1]) for value in values])

    def test_partial_failure_keeps_correct_images_and_named_reason(self):
        def fetch(url,deadline):
            if '/s/' in url:raise images.ImageImportError('Image requires sign-in. Use Add image.')
            return signature_image(png('red' if 'one.png' in url else 'green'))
        with patch.object(images,'fetch_image',side_effect=fetch):
            r=self.call(self.owner,'billing/signature-paste',dict(html=self.signature()))
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],1)
        self.assertEqual(r.json['image_errors'][0]['image'],'Photo');self.assertIn('sign-in',r.json['image_errors'][0]['reason'])
        self.assertIn('[Add image: Photo]',r.json['html']);self.assertEqual(r.json['html'].count('<img'),2);self.assertNotIn('cloud.example.test',r.json['html'])

    def test_embedded_and_clipboard_images_need_no_network(self):
        token=self.owner.get('/api/session').json['csrf']
        with patch.object(images,'fetch_image',side_effect=AssertionError('No download expected')):
            r=self.call(self.owner,'billing/signature-paste',dict(html='<img src="'+signature_image(png())+'">'))
            self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0)
            r=self.owner.post('/api/billing/signature-paste',data={'html':'<img src="https://images.example.test/clipboard.png">','images':(io.BytesIO(png()),'logo.png')},headers={'X-CSRF-Token':token})
            self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0)

    def test_denied_and_invalid_requests_never_start_downloads(self):
        with patch.object(images,'fetch_image',side_effect=AssertionError('No download expected')):
            self.assertEqual(self.call(self.agent,'billing/signature-paste',dict(html=self.signature())).status_code,403)
            self.assertEqual(self.owner.post('/api/billing/signature-paste',json={'html':self.signature()}).status_code,403)
            self.assertEqual(self.call(self.owner,'billing/signature-paste',dict(html='<img src="https://example.test/a">'*4)).status_code,400)
            r=self.call(self.owner,'billing/signature-paste',dict(html='<script><img src="https://example.test/a"></script><p>Safe text</p>'))
            self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0)
