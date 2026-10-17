"""Invoice reminder preferences and permanent expense/receipt removal."""
import json
import os
import sqlite3
import unittest
from unittest.mock import MagicMock, patch
import test_app
import test_billing
import test_receipts
from app import app, db, DATA
import billing
from billing_emails import run_reminders


class InvoicePreferenceTest(unittest.TestCase):
    setUp=test_billing.BillingTest.setUp
    call=test_billing.BillingTest.call
    login=test_billing.BillingTest.login
    create=test_billing.BillingTest.create
    get=test_billing.BillingTest.get
    action=test_billing.BillingTest.action
    issue=test_billing.BillingTest.issue
    email_config=test_billing.BillingTest.email_config

    def test_create_edit_and_duplicate_preserve_reminder_preference(self):
        doc=self.create(reminders_enabled=False)
        self.assertEqual(doc['reminders_enabled'],0)
        values={key:doc[key] for key in ('kind','client_id','issue_date','due_date','tax_mode','lines','version')}
        r=self.call(self.owner,f"billing/documents/{doc['id']}",values,'PUT')
        self.assertEqual(r.status_code,200,r.json)
        doc=self.get(doc['id']);self.assertEqual(doc['reminders_enabled'],0)
        duplicate=self.action(doc,'duplicate');self.assertEqual(duplicate.status_code,200,duplicate.json)
        self.assertEqual(self.get(duplicate.json['id'])['reminders_enabled'],0)
        values.update(version=doc['version'],reminders_enabled=True)
        self.assertEqual(self.call(self.owner,f"billing/documents/{doc['id']}",values,'PUT').status_code,200)
        self.assertEqual(self.get(doc['id'])['reminders_enabled'],1)
        for bad in ('false',2,None):
            values.update(version=self.get(doc['id'])['version'],reminders_enabled=bad)
            self.assertEqual(self.call(self.owner,f"billing/documents/{doc['id']}",values,'PUT').status_code,400)
        self.assertEqual(self.get(doc['id'])['reminders_enabled'],1)

    def test_recurring_invoices_keep_selected_preference_and_can_override_individually(self):
        doc=self.create(reminders_enabled=True)
        response=self.call(self.owner,'billing/schedules',dict(document_id=doc['id'],interval='monthly',start_date=self.today,terms=14,reminders_enabled=False))
        self.assertEqual(response.status_code,200,response.json)
        with app.app_context():
            self.assertEqual(billing.run_due(self.today),1)
            self.assertEqual(billing.run_due(self.today),0)
            did=db().execute('SELECT id FROM billing_documents WHERE schedule_id=?',(response.json['id'],)).fetchone()['id']
        generated=self.get(did);self.assertEqual(generated['reminders_enabled'],0)
        changed=self.call(self.owner,f'billing/documents/{did}/reminders',dict(version=generated['version'],enabled=True),'PUT')
        self.assertEqual(changed.status_code,200,changed.json)
        self.assertEqual(self.get(did)['reminders_enabled'],1)
        self.assertEqual(self.get(doc['id'])['reminders_enabled'],1)
        template=json.loads(self.owner.get('/api/billing/schedules').json[0]['template'])
        self.assertFalse(template['reminders_enabled'])
        self.assertEqual(self.call(self.owner,f'billing/documents/{did}/reminders',dict(version=generated['version'],enabled=False),'PUT').status_code,409)

    @patch('billing.smtplib.SMTP_SSL')
    def test_scheduler_obeys_per_invoice_switch(self,smtp):
        self.email_config()
        paused=self.issue(self.create(reminders_enabled=False))
        active=self.issue(self.create(reminders_enabled=True))
        result=self.call(self.owner,'billing/reminder-settings',dict(enabled=True,before_days=0,on_due_date=True,after_days=[]),'PUT')
        self.assertEqual(result.status_code,200,result.json)
        with app.app_context():
            self.assertEqual(run_reminders(self.today),1)
            sent=[r['document_id'] for r in db().execute('SELECT document_id FROM billing_outbox')]
            self.assertEqual(sent,[active['id']])
            self.assertEqual(run_reminders(self.today),0)
        self.assertEqual(self.get(paused['id'])['reminders_enabled'],0)

    def test_quote_conversion_and_agent_permissions(self):
        quote=self.issue(self.create(kind='quote'))
        self.action(quote,'accepted');quote=self.get(quote['id'])
        result=self.action(quote,'convert');self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.get(result.json['id'])['reminders_enabled'],1)
        doc=self.create(reminders_enabled=False)
        with app.app_context():
            db().execute("UPDATE users SET permission='read_write' WHERE email='staff@example.test'");db().commit()
        values={key:doc[key] for key in ('kind','client_id','issue_date','due_date','tax_mode','lines','version')}
        self.assertEqual(self.call(self.staff,f"billing/documents/{doc['id']}",values,'PUT').status_code,200)
        updated=self.get(doc['id']);self.assertEqual(updated['reminders_enabled'],0)
        values.update(version=updated['version'],reminders_enabled=True)
        self.assertEqual(self.call(self.staff,f"billing/documents/{doc['id']}",values,'PUT').status_code,403)
        self.assertEqual(self.call(self.staff,'billing/documents',values).status_code,403)
        self.assertEqual(self.call(self.staff,f"billing/documents/{doc['id']}/reminders",dict(version=updated['version'],enabled=True),'PUT').status_code,403)
        self.assertEqual(self.call(self.agent,f"billing/documents/{doc['id']}/reminders",dict(version=updated['version'],enabled=True),'PUT').status_code,403)


class ExpenseRemovalTest(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    call=test_app.AppTest.call
    login=test_app.AppTest.login
    expense=test_app.AppTest.expense
    upload=test_receipts.ReceiptTest.upload

    def accepted(self,status='ready'):
        rid=self.upload().json['id']
        with app.app_context():
            db().execute('INSERT INTO receipt_drafts(receipt_id,data) VALUES (?,?)',(rid,json.dumps({'merchant':'Saved draft','amount':23.45})));db().commit()
        eid=self.expense(self.owner,receipt_id=rid,status=status).json['id']
        cache=DATA/'receipt_previews';cache.mkdir(exist_ok=True)
        for suffix in ('-thumb-v1.png','-thumb-v2.png'):(cache/(rid+suffix)).write_bytes(b'cached image')
        return eid,rid

    def test_accepted_expense_removes_receipt_draft_original_and_previews(self):
        for status in ('review','ready'):
            eid,rid=self.accepted(status)
            r=self.call(self.owner,f'expenses/{eid}',{},'DELETE');self.assertEqual(r.status_code,200,r.json)
            self.assertFalse(any(e['id']==eid for e in self.owner.get('/api/expenses').json))
            for path in ('receipts','receipts?unfiled=1'):
                self.assertFalse(any(r['id']==rid for r in self.owner.get('/api/'+path).json))
            for suffix in ('','/preview','/info'):
                self.assertEqual(self.owner.get('/api/receipts/'+rid+suffix).status_code,404)
            with app.app_context():
                for table,col in [('receipts','id'),('receipt_details','receipt_id'),('receipt_drafts','receipt_id')]:
                    self.assertIsNone(db().execute(f'SELECT 1 FROM {table} WHERE {col}=?',(rid,)).fetchone())
            self.assertFalse((DATA/'receipts'/rid).exists())
            self.assertEqual(list((DATA/'receipt_previews').glob(rid+'-*')),[])

    def test_read_only_cannot_remove_and_shared_legacy_receipt_rolls_back(self):
        eid,rid=self.accepted()
        self.assertEqual(self.call(self.agent,f'expenses/{eid}',{},'DELETE').status_code,403)
        self.assertTrue((DATA/'receipts'/rid).exists())
        with app.app_context():
            db().execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,receipt_id) SELECT user_id,date,'Legacy second expense',amount_cents,scope,category,receipt_id FROM expenses WHERE id=?",(eid,));db().commit()
        self.assertEqual(self.call(self.owner,f'expenses/{eid}',{},'DELETE').status_code,409)
        self.assertEqual(len(self.owner.get('/api/expenses').json),2)
        self.assertTrue((DATA/'receipts'/rid).exists())

    def test_late_ai_result_cannot_restore_deleted_receipt(self):
        eid,rid=self.accepted()
        def finish_reading(*args):
            with sqlite3.connect(DATA/'rounded.sqlite') as other:
                other.execute('PRAGMA foreign_keys=ON')
                other.execute('DELETE FROM expenses WHERE id=?',(eid,))
                other.execute('DELETE FROM receipts WHERE id=?',(rid,))
            (DATA/'receipts'/rid).unlink()
            return json.dumps({'message':{'content':'{"merchant":"Late result","currency":"AUD"}'}}).encode()
        response=MagicMock();response.__enter__.return_value.read.side_effect=finish_reading
        with patch.dict(os.environ,{'OLLAMA_URL':'http://ollama.example.test:11434','OLLAMA_MODEL':'vision-test'}),patch('ai_providers.urllib.request.OpenerDirector.open',return_value=response):
            result=self.call(self.owner,f'receipts/{rid}/extract',{})
        self.assertEqual(result.status_code,404,result.json)
        self.assertEqual(self.owner.get('/api/receipts?unfiled=1').json,[])

    def test_late_pdf_preview_cannot_recreate_cache_after_delete(self):
        from pathlib import Path
        eid,rid=self.accepted()
        for p in (DATA/'receipt_previews').glob(rid+'-*'):p.unlink()
        with app.app_context():
            db().execute("UPDATE receipts SET mime='application/pdf' WHERE id=?",(rid,));db().commit()
        def finish_render(command,**kwargs):
            with sqlite3.connect(DATA/'rounded.sqlite') as other:
                other.execute('PRAGMA foreign_keys=ON')
                other.execute('DELETE FROM expenses WHERE id=?',(eid,))
                other.execute('DELETE FROM receipts WHERE id=?',(rid,))
            (DATA/'receipts'/rid).unlink()
            Path(command[-1]+'.png').write_bytes(b'finished preview')
        with patch('app.inspect_pdf',return_value={'pages':1}),patch('app.subprocess.run',side_effect=finish_render):
            result=self.owner.get(f'/api/receipts/{rid}/preview?thumbnail=1')
        self.assertEqual(result.status_code,404,result.json)
        self.assertEqual(list((DATA/'receipt_previews').glob(rid+'-*')),[])
