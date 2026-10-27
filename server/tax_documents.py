"""Private file repository; originals are downloaded, never executed or sent to AI."""
import hashlib
import io
import os
from pathlib import Path
import re
import secrets
import zipfile
from flask import g, jsonify, request, send_file

MAX_FILE = 10 * 1024 * 1024
CATEGORIES = dict(tax_return='Tax returns', health='Private health statements',
                  income='Income statements', super='Superannuation', insurance='Insurance',
                  banking='Bank and investment statements', correspondence='Tax correspondence', other='Other documents')
TYPES = {'.pdf':'application/pdf', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
         '.webp':'image/webp', '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         '.csv':'text/csv', '.txt':'text/plain'}


def folder():
    from app import DATA
    path = DATA / 'documents'
    path.mkdir(exist_ok=True, mode=0o700)
    return path


def values(data):
    from app import fail, textval
    title=textval(data.get('title'),200)
    category=data.get('category','other')
    if not title: fail('Enter a document title.')
    if not isinstance(category,str) or category not in CATEGORIES: fail('Choose a document category.')
    year=data.get('year')
    if year in ('',None): year=None
    else:
        if not re.fullmatch(r'\d{4}',str(year)) or not 1900<=int(year)<=2099: fail('Choose a valid financial year or leave it unassigned.')
        year=int(year)
    return title,category,year,textval(data.get('notes'),3000)


def inspect_file(filename, raw):
    """Validate container/signature only. No rendering, extraction or document execution."""
    from app import fail
    filename=Path(filename.replace('\\','/')).name
    filename=''.join(c for c in filename if ord(c)>=32 and ord(c)!=127)[:240]
    extension=Path(filename).suffix.lower()
    if extension not in TYPES: fail('Use PDF, PNG, JPG, WebP, DOCX, XLSX, CSV or TXT files.')
    if not raw or len(raw)>MAX_FILE: fail('Choose a non-empty document no larger than 10 MB.')
    valid=True
    if extension=='.pdf': valid=raw.lstrip()[:5]==b'%PDF-'
    elif extension=='.png': valid=raw.startswith(b'\x89PNG\r\n\x1a\n')
    elif extension in ('.jpg','.jpeg'): valid=raw.startswith(b'\xff\xd8\xff')
    elif extension=='.webp': valid=raw[:4]==b'RIFF' and raw[8:12]==b'WEBP'
    elif extension in ('.docx','.xlsx'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names=archive.namelist()
                main='word/document.xml' if extension=='.docx' else 'xl/workbook.xml'
                valid='[Content_Types].xml' in names and main in names and len(names)<=10000 and not any(n.lower().endswith('vbaproject.bin') for n in names)
        except (zipfile.BadZipFile,ValueError,OSError): valid=False
    else:
        try:
            raw.decode('utf-8-sig')
            valid=b'\0' not in raw
        except UnicodeDecodeError: valid=False
    if not valid: fail('The file does not match its type. Choose the original document.')
    return filename,TYPES[extension]


def register(app, auth):
    from app import audit, db, fail, one, rows, record_user_id

    def document(did):
        if not re.fullmatch(r'[0-9a-f]{40}',did): fail('Document not found.',404)
        row=one('SELECT * FROM tax_documents WHERE id=? AND user_id=?',(did,record_user_id()))
        if not row: fail('Document not found.',404)
        return row

    @app.route('/api/documents',methods=['GET','POST'],endpoint='documents_collection')
    @auth('owner','tax_agent')
    def collection():
        uid=record_user_id()
        if request.method=='GET':
            records=rows('SELECT d.*,u.name AS uploaded_by_name FROM tax_documents d LEFT JOIN users u ON u.id=d.uploaded_by WHERE d.user_id=? ORDER BY d.created_at DESC,d.id',(uid,))
            return jsonify(documents=records,categories=CATEGORIES,max_file_bytes=MAX_FILE)
        upload=request.files.get('file')
        if not upload: fail('Choose a document to upload.')
        metadata=values(request.form)
        raw=upload.read(MAX_FILE+1)
        filename,content_type=inspect_file(upload.filename or '',raw)
        digest=hashlib.sha256(raw).hexdigest()
        db().execute('BEGIN IMMEDIATE')
        previous=one('SELECT id FROM tax_documents WHERE user_id=? AND sha256=?',(uid,digest))
        if previous:
            db().commit();return jsonify(id=previous['id'],duplicate=True)
        did=secrets.token_hex(20);path=folder()/did;created=False
        try:
            with path.open('xb') as out:
                created=True
                os.chmod(path,0o600);out.write(raw);out.flush();os.fsync(out.fileno())
            directory_fd=os.open(path.parent,os.O_RDONLY)
            try: os.fsync(directory_fd)
            finally: os.close(directory_fd)
            db().execute('INSERT INTO tax_documents(id,user_id,title,category,year,notes,filename,content_type,size_bytes,sha256,uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (did,uid,*metadata,filename,content_type,len(raw),digest,g.user['id']))
            audit('document uploaded',did);db().commit()
        except BaseException:
            db().rollback()
            if created: path.unlink(missing_ok=True)
            raise
        return jsonify(id=did,duplicate=False)

    @app.route('/api/documents/<did>',methods=['PUT','DELETE'],endpoint='document_change')
    @auth('owner','tax_agent')
    def change(did):
        data=request.get_json()
        if not isinstance(data,dict): fail('Enter valid document details.')
        db().execute('BEGIN IMMEDIATE');old=document(did)
        if type(data.get('version')) is not int or data['version']!=old['version']: fail('This document changed. Reload before saving.',409)
        if request.method=='DELETE':
            # Unlink under the same reservation that backup staging uses to pin files.
            # Commit first so a failed commit cannot discard the only file.
            db().execute('DELETE FROM tax_documents WHERE id=?',(did,));audit('document deleted',did);db().commit()
            (folder()/did).unlink(missing_ok=True)
        else:
            fields=values(data)
            db().execute('UPDATE tax_documents SET title=?,category=?,year=?,notes=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(*fields,did))
            audit('document details updated',did);db().commit()
        return jsonify(ok=True)

    @app.get('/api/documents/<did>/download',endpoint='document_download')
    @auth('owner','tax_agent')
    def download(did):
        # Open while protected from deletion; the open handle survives unlink on Linux.
        db().execute('BEGIN IMMEDIATE');row=document(did)
        try: handle=(folder()/did).open('rb')
        except FileNotFoundError: fail('The original file is missing. Restore it from a backup.',404)
        try:
            audit('document downloaded',did);db().commit()
            response=send_file(handle,mimetype='application/octet-stream',as_attachment=True,download_name=row['filename'])
            response.call_on_close(handle.close)
            return response
        except BaseException:
            handle.close();raise
