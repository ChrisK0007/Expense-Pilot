"""Opt-in IMAP attachment intake. Messages are never moved, deleted or marked read."""
import email
from email import policy
from email.utils import getaddresses
import hashlib
import imaplib
import io
from pathlib import Path
import re
import secrets
import ssl
import time
from flask import jsonify, request
from workflow_core import body, integer, now


class BoundedIMAP(imaplib.IMAP4_SSL):
    def read(self,size):
        if size>12*1024*1024: raise ValueError('Message exceeds the intake size limit.')
        return super().read(size)


def config():
    from billing import settings
    return settings('mail_intake',dict(host='',port=993,username='',folder='Expense Pilot',senders=[],enabled=False,password_encrypted='',last_attempt=0,last_error='',last_result=''))


def public():
    saved=config()
    return {**{k:v for k,v in saved.items() if k!='password_encrypted'},'password_saved':bool(saved.get('password_encrypted'))}


def store_attachment(uid,filename,raw):
    from app import DATA, db, one, inspect_pdf
    from PIL import Image
    name=Path(filename.replace('\\','/')).name[:160];extension=Path(name).suffix.lower()
    if not raw or len(raw)>10*1024*1024: raise ValueError('Attachment is empty or exceeds 10 MB.')
    if extension=='.pdf': inspect_pdf(raw);mime='application/pdf'
    elif extension in ('.png','.jpg','.jpeg','.webp'):
        with Image.open(io.BytesIO(raw),formats=['PNG','JPEG','WEBP']) as image:
            if image.width*image.height>25000000: raise ValueError('Image exceeds 25 megapixels.')
            mime=Image.MIME[image.format];image.verify()
    else: return None
    fingerprint=hashlib.sha256(raw).hexdigest()
    db().execute('BEGIN IMMEDIATE')
    duplicate=one('SELECT r.id FROM receipts r JOIN receipt_details d ON d.receipt_id=r.id WHERE r.user_id=? AND d.fingerprint=?',(uid,fingerprint))
    if duplicate: db().commit();return duplicate['id']
    rid=secrets.token_hex(20);path=DATA/'receipts'/rid
    try:
        path.write_bytes(raw);path.chmod(0o600)
        db().execute('INSERT INTO receipts VALUES (?,?,?,?)',(rid,uid,name,mime))
        db().execute("INSERT INTO receipt_details(receipt_id,fingerprint,scan_status) VALUES (?,?,'captured')",(rid,fingerprint))
        db().commit()
    except Exception:
        db().rollback();path.unlink(missing_ok=True);raise
    return rid


def poll():
    from app import db, one
    from billing import save_settings, secret_box
    saved=config()
    if not saved.get('enabled') or time.time()-saved.get('last_attempt',0)<300: return
    owner=one("SELECT id FROM users WHERE role='owner' AND active=1 ORDER BY id LIMIT 1")
    if not owner: return
    saved['last_attempt']=time.time();save_settings('mail_intake',saved);db().commit()
    imported=0;failed=0;client=None
    try:
        client=BoundedIMAP(saved['host'],saved['port'],ssl_context=ssl.create_default_context(),timeout=20)
        client.login(saved['username'],secret_box().decrypt(saved['password_encrypted'].encode()).decode())
        folder='"'+saved['folder'].replace('\\','\\\\').replace('"','\\"')+'"'
        if client.select(folder,readonly=True)[0]!='OK': raise ValueError('Mailbox folder could not be opened.')
        validity=client.response('UIDVALIDITY')[1]
        if not validity or not validity[0]: raise ValueError('Mailbox did not supply UIDVALIDITY.')
        namespace=hashlib.sha256((saved['host']+'\0'+saved['username']+'\0'+saved['folder']+'\0'+validity[0].decode('ascii')).encode()).hexdigest()
        status,data=client.uid('search',None,'ALL')
        if status!='OK': raise ValueError('Mailbox search failed.')
        # The intake folder should contain only candidate receipts. Each tick
        # advances across unprocessed UIDs, including older messages.
        attempted=0
        for uid in data[0].split():
            if not re.fullmatch(rb'\d+',uid): continue
            key=namespace+':'+uid.decode()
            if one('SELECT 1 FROM mail_intake_messages WHERE user_id=? AND message_key=?',(owner['id'],key)): continue
            attempted+=1
            if attempted>20: break
            state='processed';detail='No supported attachments.'
            try:
                status,parts=client.uid('fetch',uid,'(RFC822.SIZE)')
                size=re.search(rb'RFC822.SIZE (\d+)',b' '.join(p for p in parts if isinstance(p,bytes)))
                if status!='OK' or not size or int(size[1])>12*1024*1024: raise ValueError('Message exceeds 12 MB or its size is unavailable.')
                status,parts=client.uid('fetch',uid,'(BODY.PEEK[])')
                raw=next((p[1] for p in parts if isinstance(p,tuple)),None)
                if status!='OK' or not raw or len(raw)>12*1024*1024: raise ValueError('Message could not be read within the size limit.')
                message=email.message_from_bytes(raw,policy=policy.default)
                senders=[address.lower() for _,address in getaddresses(message.get_all('From',[]))]
                if len(senders)!=1 or senders[0] not in saved['senders']:
                    state='skipped';detail='Sender is not on the intake allow-list.'
                else:
                    ids=[]
                    for part in message.walk():
                        filename=part.get_filename()
                        if not filename or part.is_multipart(): continue
                        if len(ids)>=20: raise ValueError('Message contains more than 20 supported attachments.')
                        ident=store_attachment(owner['id'],filename,part.get_payload(decode=True) or b'')
                        if ident: ids.append(ident)
                    imported+=len(ids);detail='Saved document IDs: '+', '.join(ids) if ids else detail
            except Exception as exc:
                db().rollback();failed+=1;state='failed';detail=str(exc)[:300] if isinstance(exc,ValueError) else 'Attachment intake failed. Check the original message and upload it manually.'
            db().execute('INSERT OR IGNORE INTO mail_intake_messages VALUES (?,?,?,?,?)',(owner['id'],key,state,detail,now()));db().commit()
        saved['last_error']='';saved['last_result']=f'{imported} attachment(s) saved or deduplicated; {failed} message(s) need review.'
    except Exception:
        db().rollback();saved['last_error']='Could not read the intake mailbox. Check the host, app password, folder and access permissions.'
    finally:
        if client:
            try: client.logout()
            except Exception: pass
        # Do not overwrite credentials edited while network I/O was in progress.
        current=config()
        current.update({k:saved.get(k,'') for k in ('last_attempt','last_error','last_result')})
        save_settings('mail_intake',current);db().commit()


def register(app,auth):
    @app.route('/api/workflows/mail-intake',methods=['GET','PUT'], endpoint='mail_intake_settings')
    @auth('owner')
    def settings():
        from app import db, rows, fail, textval, record_user_id, audit
        from billing import save_settings, secret_box
        if request.method=='PUT':
            d=body();saved=config();host=textval(d.get('host'),250);username=textval(d.get('username'),250);folder=textval(d.get('folder'),200)
            if any(c in host+username+folder for c in '\r\n\0') or not re.fullmatch(r'[A-Za-z0-9.:-]+',host): fail('Enter a mail host, username and folder without control characters.')
            senders=d.get('senders')
            if not isinstance(senders,list) or not 1<=len(senders)<=100 or any(not isinstance(s,str) or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',s) for s in senders): fail('Enter 1–100 exact sender email addresses.')
            password=d.get('password','')
            if not isinstance(password,str) or len(password)>1000: fail('Invalid mailbox password.')
            encrypted=secret_box().encrypt(password.encode()).decode() if password else saved.get('password_encrypted','')
            if not username or not folder or not encrypted or not isinstance(d.get('enabled'),bool): fail('Enter the mailbox credentials and choose whether intake is enabled.')
            saved.update(host=host,port=integer(d.get('port',993),'IMAP TLS port',1,65535),username=username,folder=folder,senders=[s.lower() for s in senders],password_encrypted=encrypted,enabled=d['enabled'],last_attempt=0,last_error='')
            save_settings('mail_intake',saved);audit('mail intake settings saved','IMAP');db().commit()
        return jsonify(config=public(),history=rows('SELECT status,detail,at FROM mail_intake_messages WHERE user_id=? ORDER BY at DESC LIMIT 100',(record_user_id(),)))

    @app.post('/api/workflows/mail-intake/check', endpoint='mail_intake_check')
    @auth('owner')
    def check():
        from app import db, fail
        from billing import save_settings
        saved=config()
        if not saved.get('enabled'): fail('Enable and configure the intake mailbox first.')
        saved['last_attempt']=0;save_settings('mail_intake',saved);db().commit()
        return jsonify(ok=True,message='Mailbox check queued. Results appear here after the next background check.')
