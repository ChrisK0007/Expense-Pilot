"""Linked and embedded signature roundtrips without live HTTP or SMTP."""
import io
import unittest
from email.message import EmailMessage
from unittest.mock import patch
from PIL import Image
import test_app
from billing_email_core import add_message_content, clean_signature, signature_image


def png():
    out=io.BytesIO();Image.new('RGB',(40,20),'blue').save(out,'PNG');return out.getvalue()


class SignatureImagesTest(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    login=test_app.AppTest.login
    call=test_app.AppTest.call

    def signature(self):
        return '<table><tr><td><img alt="Photo" style="width:90px;height:90px" src="https://cloud.example.test/s/sample/preview?x=1&amp;y=2"></td><td style="padding-left:12px"><b>Example Pilot</b><br><a href="mailto:pilot@example.test">Email</a><a href="https://social.example.test/profile"><img width="20" height="20" alt="Social one" src="https://icons.example.test/one.png"></a><a href="https://social.example.test/second"><img style="width:20px" alt="Social two" src="https://icons.example.test/two.png"></a></td></tr></table>'

    def test_links_and_proportions_survive_paste_save_reopen_and_email_without_server_network(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('No image downloads')):
            r=self.call(self.owner,'billing/signature-paste',dict(html=self.signature()))
            self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0)
            html=r.json['html'];self.assertEqual(html.count('referrerpolicy="no-referrer"'),3)
            self.assertIn('width:90px;height:auto',html);self.assertIn('width:20px',html)
            self.assertNotIn('height="20"',html);self.assertNotIn('height:90px',html)
            self.assertIn('padding-left:12px',html);self.assertIn('https://social.example.test/profile',html)
            self.assertIn('preview?x=1&amp;y=2',html)
            saved=self.call(self.owner,'billing/email-templates',dict(signature_html=html),'PUT')
            self.assertEqual(saved.status_code,200,saved.json);self.assertEqual(saved.json['signature_html'],html)
            self.assertEqual(self.owner.get('/api/billing/email-templates').json['signature_html'],html)
            message=EmailMessage();add_message_content(message,'Invoice message',html)
        content=message.get_body(preferencelist=('html',)).get_content()
        self.assertIn(html,content);self.assertNotIn('src="cid:',content)
        self.assertFalse([p for p in message.walk() if p.get_content_maintype()=='image'])

    def test_invalid_links_remain_replaceable_and_scripts_never_survive(self):
        for url in ['http://example.test/a','//example.test/a','javascript:alert(1)','file:///tmp/a','https://user:password@example.test/a','https://example.test:8443/a','https://127.0.0.1/a','https://[::1]/a','https://localhost/a','https://box.local/a','https://example.test/a\r\nheader:x','https://[broken/a']:
            with self.subTest(url=url):
                r=self.call(self.owner,'billing/signature-paste',dict(html='<img alt="Photo" src="'+url+'" onerror="alert(1)"><script>bad()</script>'))
                self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],1)
                self.assertEqual(r.json['image_errors'][0]['image'],'Photo');self.assertIn('[Add image: Photo]',r.json['html'])
                self.assertNotIn('<img',r.json['html']);self.assertNotIn('onerror',r.json['html']);self.assertNotIn('bad()',r.json['html'])

    def test_existing_embedded_images_remain_inline_attachments_alongside_linked_images(self):
        html='<img width="90" height="90" src="'+signature_image(png())+'"><img width="20" src="https://icons.example.test/one.png">'
        clean=clean_signature(html)[0];self.assertEqual(clean_signature(clean)[0],clean)
        message=EmailMessage();add_message_content(message,'Message',clean)
        content=message.get_body(preferencelist=('html',)).get_content()
        self.assertIn('src="cid:expense-pilot-signature-0"',content);self.assertIn('https://icons.example.test/one.png',content)
        self.assertEqual(len([p for p in message.walk() if p.get_content_type()=='image/png']),1)
        self.assertNotIn('height="90"',content)

    def test_clipboard_file_fills_missing_image_without_replacing_https_reference(self):
        token=self.owner.get('/api/session').json['csrf']
        html='<img src="https://images.example.test/photo.png"><img src="cid:logo">'
        r=self.owner.post('/api/billing/signature-paste',data={'html':html,'images':(io.BytesIO(png()),'logo.png')},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0)
        self.assertIn('https://images.example.test/photo.png',r.json['html']);self.assertEqual(r.json['html'].count('data:image/png;base64,'),1)

    def test_extra_clipboard_copy_does_not_replace_linked_image(self):
        token=self.owner.get('/api/session').json['csrf']
        r=self.owner.post('/api/billing/signature-paste',data={'html':'<img src="https://images.example.test/photo.png">','images':(io.BytesIO(png()),'photo.png')},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0)
        self.assertIn('https://images.example.test/photo.png',r.json['html']);self.assertNotIn('data:image',r.json['html'])

    def test_height_only_and_unsized_images_roundtrip_without_forcing_two_dimensions(self):
        for size in ['height="40"','style="height:40px"','']:
            html=clean_signature('<img '+size+' src="https://images.example.test/photo.png">')[0]
            self.assertEqual(clean_signature(html)[0],html);self.assertIn('object-fit:contain',html)
            if size:
                self.assertIn('width:auto',html);self.assertIn('height:40px',html)
            else:self.assertIn('height:auto;max-width:300px',html)

    def test_rejects_unauthorised_requests_and_excess_images(self):
        self.assertEqual(self.call(self.agent,'billing/signature-paste',dict(html=self.signature())).status_code,403)
        self.assertEqual(self.owner.post('/api/billing/signature-paste',json={'html':self.signature()}).status_code,403)
        self.assertEqual(self.call(self.owner,'billing/signature-paste',dict(html='<img src="https://example.test/a">'*4)).status_code,400)

    def test_csp_allows_https_images_without_relaxing_other_directives(self):
        response=self.owner.get('/');policy=response.headers['Content-Security-Policy'];response.close()
        self.assertIn("img-src 'self' blob: data: https:;",policy)
        for directive in ["script-src 'self';","style-src 'self';","connect-src 'self';","object-src 'none';"]:self.assertIn(directive,policy)
