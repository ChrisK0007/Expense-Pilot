import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pypdf import PdfWriter
import test_app as base
from app import app, db, DATA
import tax_documents


class DocumentTests(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login

    def upload(self, client=None, raw=b'Test document\n', filename='statement.txt', **changes):
        client=client or self.owner
        data=dict(title='Private health statement',category='health',year='2025',notes='For tax records')
        data.update(changes);data['file']=(io.BytesIO(raw),filename)
        return client.post('/api/documents',data=data,headers={'X-CSRF-Token':client.get('/api/session').json['csrf']})

    def records(self,client=None): return (client or self.owner).get('/api/documents').json['documents']

    def test_repository_is_separate_from_finances_and_supports_metadata_and_original_download(self):
        before=self.owner.get('/api/tax/2026').json['recorded']
        raw=b'Example health fund statement\n'
        response=self.upload(raw=raw);self.assertEqual(response.status_code,200,response.json)
        did=response.json['id'];document=self.records()[0]
        self.assertEqual(document['year'],2025);self.assertEqual(document['category'],'health')
        self.assertEqual(document['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual((DATA/'documents'/did).stat().st_mode&0o777,0o600)
        download=self.owner.get(f'/api/documents/{did}/download')
        self.assertEqual(download.status_code,200);self.assertEqual(download.data,raw)
        self.assertIn('attachment;',download.headers['Content-Disposition'])
        self.assertEqual(download.mimetype,'application/octet-stream')
        self.assertEqual(download.headers['Cache-Control'],'no-store')
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded'],before)
        change=dict(version=1,title='Health statement 2025-26',category='health',year=2025,notes='Updated')
        self.assertEqual(self.call(self.owner,f'documents/{did}',change,'PUT').status_code,200)
        self.assertEqual(self.call(self.owner,f'documents/{did}',change,'PUT').status_code,409)
        self.assertEqual(self.records()[0]['notes'],'Updated')
        self.assertEqual(self.call(self.owner,f'documents/{did}',dict(version=2),'DELETE').status_code,200)
        self.assertFalse((DATA/'documents'/did).exists());self.assertEqual(self.records(),[])
        self.assertEqual(self.owner.get(f'/api/documents/{did}/download').status_code,404)

    def test_permissions_csrf_and_other_owner_records(self):
        self.assertEqual(app.test_client().get('/api/documents').status_code,401)
        self.assertEqual(self.upload(client=self.agent).status_code,403)
        self.assertEqual(self.owner.post('/api/documents',data={}).status_code,403)
        did=self.upload().json['id']
        for method in ('PUT','DELETE'):
            self.assertEqual(self.call(self.agent,f'documents/{did}',dict(version=1),method).status_code,403)
        with app.app_context():
            uid=db().execute("SELECT id FROM users WHERE email='agent@example.test'").fetchone()[0]
            db().execute("UPDATE users SET permission='read_write' WHERE id=?",(uid,));db().commit()
        self.assertEqual(self.upload(client=self.agent,raw=b'Agent document').status_code,403)
        with app.app_context():
            db().execute('UPDATE tax_documents SET user_id=? WHERE id=?',(uid,did));db().commit()
        self.assertNotIn(did,[d['id'] for d in self.records()])
        self.assertEqual(self.owner.get(f'/api/documents/{did}/download').status_code,404)
        self.assertEqual(self.call(self.owner,f'documents/{did}',dict(version=1),'DELETE').status_code,404)

    def test_duplicate_upload_retains_existing_details_and_no_duplicate_file(self):
        first=self.upload();second=self.upload(title='Replacement title',year='2026')
        self.assertEqual(first.json['id'],second.json['id']);self.assertTrue(second.json['duplicate'])
        self.assertEqual(len(self.records()),1);self.assertEqual(self.records()[0]['title'],'Private health statement')
        self.assertEqual(self.records()[0]['year'],2025)

    def test_files_are_validated_without_receipt_page_limit_or_decryption(self):
        writer=PdfWriter()
        for _ in range(12): writer.add_blank_page(width=595,height=842)
        writer.encrypt('example-password');out=io.BytesIO();writer.write(out)
        response=self.upload(raw=out.getvalue(),filename='../prior-return.pdf',category='tax_return',year='')
        self.assertEqual(response.status_code,200,response.json)
        doc=self.records()[0];self.assertEqual(doc['filename'],'prior-return.pdf');self.assertIsNone(doc['year'])
        self.assertEqual(self.owner.get(f"/api/documents/{doc['id']}/download").data,out.getvalue())
        for raw,filename in [(b'','empty.txt'),(b'<html>bad</html>','file.pdf'),(b'MZpayload','bad.exe'),(b'\x00\x01','bad.txt'),(b'not a zip','file.docx')]:
            self.assertEqual(self.upload(raw=raw,filename=filename).status_code,400,filename)
        self.assertEqual(self.upload(category='invalid').status_code,400)
        self.assertEqual(self.upload(year='2026-27').status_code,400)
        self.assertEqual(self.upload(raw=b'x'*(tax_documents.MAX_FILE+1)).status_code,400)
        for extension,main in [('docx','word/document.xml'),('xlsx','xl/workbook.xml')]:
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                z.writestr('[Content_Types].xml','<Types/>');z.writestr(main,'<document/>')
            self.assertEqual(self.upload(raw=out.getvalue(),filename='test.'+extension).status_code,200)

    def test_backup_restore_includes_originals_and_rejects_missing_document(self):
        from auto_backup import write_archive,verify_archive
        from restore_backup import restore
        raw=b'Document backup content';did=self.upload(raw=raw).json['id']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'backup.zip'
            with app.app_context():
                manifest=write_archive(archive,DATA,'test',verify=True)
            verify_archive(archive,manifest)
            restore(archive,root/'restored')
            self.assertEqual((root/'restored/documents'/did).read_bytes(),raw)
            self.assertEqual((root/'restored/documents'/did).stat().st_mode&0o777,0o600)
            with sqlite3.connect(root/'restored/rounded.sqlite') as c:
                self.assertEqual(c.execute('SELECT title,category,year FROM tax_documents').fetchone(),('Private health statement','health',2025))
            missing=root/'missing.zip'
            with zipfile.ZipFile(archive) as source,zipfile.ZipFile(missing,'w') as target:
                manifest=json.loads(source.read('manifest.json'));manifest['sha256'].pop('data/documents/'+did)
                for name in source.namelist():
                    if name not in ('manifest.json','data/documents/'+did): target.writestr(name,source.read(name))
                target.writestr('manifest.json',json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'Document files'):
                restore(missing,root/'missing-restore')
        response=self.call(self.owner,'data/backup',dict(password='Owner-password-123'))
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as z: self.assertEqual(z.read('data/documents/'+did),raw)

    def test_backup_pins_document_before_concurrent_delete(self):
        from auto_backup import write_archive
        raw=b'Kept during snapshot';did=self.upload(raw=raw).json['id']
        original=zipfile.ZipFile.open;deleted=False
        def during_compression(archive,name,*args,**kwargs):
            nonlocal deleted
            if not deleted and name=='data/rounded.sqlite' and args and args[0]=='w':
                deleted=True
                with sqlite3.connect(DATA/'rounded.sqlite',timeout=1) as c: c.execute('DELETE FROM tax_documents WHERE id=?',(did,))
                (DATA/'documents'/did).unlink()
            return original(archive,name,*args,**kwargs)
        out=io.BytesIO()
        with app.app_context(),patch.object(zipfile.ZipFile,'open',during_compression): write_archive(out,DATA,'test',verify=True)
        self.assertTrue(deleted)
        with zipfile.ZipFile(out) as z: self.assertEqual(z.read('data/documents/'+did),raw)

    def test_workspace_deletion_removes_document_originals(self):
        did=self.upload().json['id']
        response=self.call(self.owner,'account',dict(password='Owner-password-123',confirmation='DELETE WORKSPACE'),'DELETE')
        self.assertEqual(response.status_code,200,response.json)
        self.assertFalse((DATA/'documents'/did).exists())
        with app.app_context(): self.assertEqual(db().execute('SELECT COUNT(*) FROM tax_documents').fetchone()[0],0)

    def test_missing_or_changed_document_stops_backup(self):
        from auto_backup import write_archive,BackupError
        did=self.upload(raw=b'Original statement').json['id']
        path=DATA/'documents'/did
        path.write_bytes(b'Unexpected changed content')
        with app.app_context(),self.assertRaisesRegex(BackupError,'checksum'):
            write_archive(io.BytesIO(),DATA,'test',verify=True)
        path.unlink()
        response=self.call(self.owner,'data/backup',dict(password='Owner-password-123'))
        self.assertEqual(response.status_code,503)
