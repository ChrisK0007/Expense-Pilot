import io
import subprocess
import unittest
from unittest.mock import patch
import zipfile
from pypdf import PdfWriter
from PIL import Image
import test_app as base
from app import app, db, DATA
import test_tax_documents
from document_processing import process


def office(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        archive.writestr('[Content_Types].xml','<Types/>')
        for name,value in files.items(): archive.writestr(name,value)
    return out.getvalue()


class PreviewTests(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login
    upload=test_tax_documents.DocumentTests.upload

    def test_pdf_all_pages_render_locally_without_altering_original(self):
        writer=PdfWriter()
        for _ in range(12): writer.add_blank_page(width=100,height=100)
        raw=io.BytesIO();writer.write(raw);raw=raw.getvalue()
        did=self.upload(raw=raw,filename='return.pdf').json['id'];before=set((DATA/'documents').glob('*'))
        response=self.owner.get(f'/api/documents/{did}/view')
        self.assertEqual(response.status_code,200,response.json);self.assertEqual(response.json['pages'],12)
        rendered=self.owner.get(f'/api/documents/{did}/page?page=12')
        self.assertEqual(rendered.status_code,200,rendered.json);self.assertEqual(rendered.mimetype,'image/png')
        self.assertTrue(rendered.data.startswith(b'\x89PNG'));self.assertEqual(rendered.headers['Cache-Control'],'no-store')
        self.assertEqual(rendered.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual((DATA/'documents'/did).read_bytes(),raw);self.assertEqual(before,set((DATA/'documents').glob('*')))
        self.assertEqual(self.owner.get(f'/api/documents/{did}/page?page=13').status_code,422)
        self.assertEqual(self.owner.get(f'/api/documents/{did}/page?page=-1').status_code,400)

    def test_encrypted_and_malformed_pdf_keep_download_available(self):
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.encrypt('private')
        out=io.BytesIO();writer.write(out)
        for raw in (out.getvalue(),b'%PDF-1.7\nmalformed'):
            did=self.upload(raw=raw,filename='private.pdf').json['id']
            response=self.owner.get(f'/api/documents/{did}/view');self.assertEqual(response.status_code,422)
            self.assertEqual(self.owner.get(f'/api/documents/{did}/download').data,raw)

    def test_view_and_page_authorization_owner_isolation_and_missing_file(self):
        did=self.upload().json['id']
        for route in ('view','page'):
            self.assertEqual(app.test_client().get(f'/api/documents/{did}/{route}').status_code,401)
        self.assertEqual(self.agent.get(f'/api/documents/{did}/view').status_code,403)
        with app.app_context():
            uid=db().execute("SELECT id FROM users WHERE email='agent@example.test'").fetchone()[0]
            db().execute('UPDATE tax_documents SET user_id=? WHERE id=?',(uid,did));db().commit()
        for route in ('view','page'):
            self.assertEqual(self.owner.get(f'/api/documents/{did}/{route}').status_code,404)
        did=self.upload(raw=b'Missing original').json['id'];(DATA/'documents'/did).unlink()
        self.assertEqual(self.owner.get(f'/api/documents/{did}/view').status_code,404)

    def test_text_csv_docx_and_xlsx_are_plain_values_with_limits(self):
        raw=b'<script>alert(1)</script>'
        did=self.upload(raw=raw).json['id'];response=self.owner.get(f'/api/documents/{did}/view')
        self.assertEqual(response.json['text'],raw.decode());self.assertEqual(response.mimetype,'application/json')
        csv=process(b'Name,Formula\nExample,=1+2\n','.csv')
        self.assertEqual(csv['sheets'][0]['rows'][1][1],'=1+2')
        self.assertTrue(process(('x\n'*501).encode(),'.csv')['truncated'])
        self.assertTrue(process(b'x'*100001,'.txt')['truncated'])
        doc=office({'word/document.xml':'<document><p><t>Safe &lt;script&gt; text</t></p></document>'})
        self.assertEqual(process(doc,'.docx')['text'],'Safe <script> text')
        book=office({'xl/workbook.xml':'<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Records" r:id="rId1"/></sheets></workbook>',
                     'xl/_rels/workbook.xml.rels':'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
                     'xl/worksheets/sheet1.xml':'<worksheet><sheetData><row><c r="A1" t="inlineStr"><is><t>Plain value</t></is></c><c r="C1"><f>HYPERLINK(&quot;https://invalid.example&quot;)</f></c></row></sheetData></worksheet>'})
        values=process(book,'.xlsx')['sheets'][0]
        self.assertEqual(values['name'],'Records');self.assertEqual(values['rows'][0][0],'Plain value')
        self.assertEqual(values['rows'][0][1],'');self.assertTrue(values['rows'][0][2].startswith('Formula (not calculated)'))
        malicious=office({'word/document.xml':'<!DOCTYPE x [<!ENTITY e "bad">]><document><p><t>&e;</t></p></document>'})
        with self.assertRaises(ValueError): process(malicious,'.docx')

    def test_images_are_reencoded_and_processing_timeouts_are_recoverable(self):
        out=io.BytesIO();Image.new('RGB',(30,20),'red').save(out,'JPEG')
        did=self.upload(raw=out.getvalue(),filename='statement.jpg').json['id']
        self.assertEqual(self.owner.get(f'/api/documents/{did}/view').json['kind'],'image')
        rendered=self.owner.get(f'/api/documents/{did}/page')
        self.assertEqual(rendered.status_code,200);self.assertEqual(Image.open(io.BytesIO(rendered.data)).size,(30,20))
        with patch('document_processing.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',25)):
            response=self.owner.get(f'/api/documents/{did}/view');self.assertEqual(response.status_code,422)
            self.assertIn('limits',response.json['error'])
