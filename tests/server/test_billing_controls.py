"""Service edits, invoice identities and isolated reminder overrides; mail is mocked."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from unittest.mock import patch
import test_billing
from flask import g
import billing
from app import app, db
from billing_emails import run_reminders


class BillingControlsTest(unittest.TestCase):
    setUp = test_billing.BillingTest.setUp
    call = test_billing.BillingTest.call
    login = test_billing.BillingTest.login
    create = test_billing.BillingTest.create
    get = test_billing.BillingTest.get
    action = test_billing.BillingTest.action
    issue = test_billing.BillingTest.issue
    pay = test_billing.BillingTest.pay
    email_config = test_billing.BillingTest.email_config

    def remove(self, doc):
        return self.call(self.owner, f"billing/documents/{doc['id']}", {'version':doc['version']}, 'DELETE')

    def renumber(self, doc, number, client=None):
        return self.call(client or self.owner, f"billing/documents/{doc['id']}/number", {'version':doc['version'],'number':number}, 'PUT')

    def options(self, doc, options, enabled=True):
        return self.call(self.owner, f"billing/documents/{doc['id']}/reminders", {'version':doc['version'],'enabled':enabled,'options':options}, 'PUT')

    def test_service_edit_changes_future_lines_and_preserves_existing_documents(self):
        result=self.call(self.owner,'billing/services',dict(description='Flight test',unit_price='450',tax='gst'))
        sid=result.json['id'];service=self.owner.get('/api/billing/services').json[0]
        doc=self.create(lines=[dict(description=service['description'],quantity='1',unit_price='450',tax=service['tax'])])
        changed=dict(description='Flight test and report',unit_price='495.50',tax='gst_free',version=service['version'])
        self.assertEqual(self.call(self.owner,f'billing/services/{sid}',changed,'PUT').status_code,200)
        saved=self.owner.get('/api/billing/services').json[0]
        self.assertEqual((saved['description'],saved['unit_cents'],saved['tax']),('Flight test and report',49550,'gst_free'))
        self.assertEqual(self.get(doc['id'])['lines'],doc['lines'])
        self.assertEqual(self.call(self.owner,f'billing/services/{sid}',changed,'PUT').status_code,409)
        for bad in ({'unit_price':'-1'},{'description':''},{'tax':'bogus'}):
            self.assertEqual(self.call(self.owner,f'billing/services/{sid}',{**changed,'version':saved['version'],**bad},'PUT').status_code,400)
        self.assertEqual(self.call(self.agent,f'billing/services/{sid}',{**changed,'version':saved['version']},'PUT').status_code,403)
        self.assertEqual(self.call(self.owner,f'billing/services/{sid}',{'version':saved['version']},'DELETE').status_code,200)
        self.assertEqual(self.get(doc['id'])['total_cents'],49500)
        self.assertEqual(self.call(self.owner,f'billing/services/{sid}',changed,'PUT').status_code,404)

    def test_deleted_numbers_reuse_latest_first_without_reusing_live_void_or_quote_numbers(self):
        a,b,c=self.create(),self.create(),self.issue(self.create())
        self.action(c,'void')
        self.assertEqual(self.remove(a).status_code,200)
        self.assertEqual(self.remove(b).status_code,200)
        quote=self.create(kind='quote');self.assertEqual(quote['number'],'QUO-0001')
        self.assertEqual(self.create()['number'],b['number'])
        self.assertEqual(self.create()['number'],a['number'])
        self.assertEqual(self.create()['number'],'INV-0004')
        self.assertEqual(self.get(c['id'])['number'],c['number'])

    def test_custom_numbers_unique_and_renumbering_preserves_payments_and_pdf(self):
        doc=self.issue(self.create(number='FLIGHT-42'))
        self.assertEqual(self.pay(doc,'20').status_code,200);doc=self.get(doc['id'])
        self.assertEqual(self.renumber(doc,'TEST-2026-42').status_code,200)
        saved=self.get(doc['id'])
        self.assertEqual(saved['number'],'TEST-2026-42')
        self.assertEqual(saved['payments'],doc['payments'])
        self.assertEqual(saved['lines'],doc['lines'])
        self.assertIn('TEST-2026-42.pdf',self.owner.get(f"/api/billing/documents/{doc['id']}/pdf").headers['Content-Disposition'])
        self.assertEqual(self.renumber(doc,'STALE').status_code,409)
        other=self.create()
        self.assertEqual(self.renumber(other,'test-2026-42').status_code,409)
        for number in ('','../bad','bad\nnumber','a'*51,None):
            self.assertEqual(self.renumber(other,number).status_code,400)
        self.assertEqual(self.renumber(other,'READONLY',self.agent).status_code,403)
        self.assertEqual(self.renumber(self.create(kind='quote'),'QUOTE').status_code,400)
        self.assertEqual(self.remove(saved).status_code,200)
        self.assertEqual(self.create()['number'],'TEST-2026-42')

    def test_reclaimed_number_claimed_by_manual_edit_and_duplicate_allocates_another(self):
        old=self.create();live=self.create();self.remove(old)
        self.assertEqual(self.renumber(live,old['number']).status_code,200)
        live=self.get(live['id'])
        duplicate=self.action(live,'duplicate');self.assertEqual(duplicate.status_code,200)
        self.assertEqual(self.get(duplicate.json['id'])['number'],'INV-0003')
        self.assertEqual(self.create()['number'],'INV-0004')

    def test_number_allocation_is_atomic_across_workers(self):
        old=self.create();self.remove(old)
        def create_invoice():
            with app.app_context():
                g.user={'id':1,'role':'owner'}
                values=billing.validate_document(dict(client_id=self.cid,issue_date=self.today,due_date=self.today,tax_mode='none',lines=[dict(description='Concurrent',quantity=1,unit_price=10,tax='none')]))
                db().execute('BEGIN IMMEDIATE')
                did=billing.insert_document(values);db().commit()
                return billing.document(did)['number']
        with ThreadPoolExecutor(max_workers=2) as pool:
            numbers=list(pool.map(lambda _:create_invoice(),range(2)))
        self.assertEqual(set(numbers),{'INV-0001','INV-0002'})

    @patch('billing.deliver', return_value=('sent',''))
    def test_custom_reminders_are_isolated_and_renumbering_does_not_resend(self,send):
        self.email_config()
        future=(date.fromisoformat(self.today)+timedelta(days=2)).isoformat()
        target=self.issue(self.create(due_date=future));other=self.issue(self.create(due_date=future))
        options=dict(schedule=dict(before_days=2,on_due_date=False,after_days=[5]),templates={
            'reminder_due':dict(subject='Flight test {number}',body='Hello {client}, balance {balance} is due {due_date}.'),
            'reminder_manual':dict(subject='Personal follow-up {number}',body='Please arrange {balance}.')})
        self.assertEqual(self.options(target,options).status_code,200)
        self.call(self.owner,'billing/reminder-settings',dict(enabled=True,before_days=3,on_due_date=True,after_days=[7]),'PUT')
        with app.app_context():
            self.assertEqual(run_reminders(self.today),1)
        sent=send.call_args.args;self.assertIn(target['number'],sent[1]);self.assertIn('$110.00',sent[2])
        self.assertEqual(self.get(other['id'])['emails'],[])
        target=self.get(target['id']);self.assertEqual(self.renumber(target,'RENAMED-42').status_code,200)
        with app.app_context():self.assertEqual(run_reminders(self.today),0)
        target=self.get(target['id'])
        draft=self.owner.get(f"/api/billing/documents/{target['id']}/email-draft?kind=reminder_manual").json
        self.assertEqual(draft['subject'],'Personal follow-up RENAMED-42')
        self.call(self.owner,'billing/reminder-settings',dict(enabled=False,before_days=3,on_due_date=True,after_days=[7]),'PUT')
        with app.app_context():self.assertEqual(run_reminders((date.fromisoformat(future)+timedelta(days=5)).isoformat()),0)

    def test_override_reset_preservation_duplicate_recurring_and_validation(self):
        doc=self.create()
        options={'schedule':{'before_days':1,'on_due_date':False,'after_days':[10]},'templates':{'reminder_overdue':{'subject':'Follow-up {number}','body':'Balance {balance}'}}}
        self.assertEqual(self.options(doc,options).status_code,200);doc=self.get(doc['id'])
        # Draft edits and the simple on/off switch must not erase customisation.
        payload={k:doc[k] for k in ('kind','client_id','issue_date','due_date','tax_mode','lines','version')}
        self.assertEqual(self.call(self.owner,f"billing/documents/{doc['id']}",payload,'PUT').status_code,200);doc=self.get(doc['id'])
        self.call(self.owner,f"billing/documents/{doc['id']}/reminders",dict(version=doc['version'],enabled=False),'PUT');doc=self.get(doc['id'])
        self.assertEqual(doc['reminder_options'],options)
        duplicate=self.action(doc,'duplicate');self.assertEqual(self.get(duplicate.json['id'])['reminder_options'],options)
        schedule=self.call(self.owner,'billing/schedules',dict(document_id=doc['id'],interval='monthly',start_date=self.today,terms=14))
        self.assertEqual(schedule.status_code,200)
        with app.app_context():
            self.assertEqual(billing.run_due(self.today),1)
            generated=billing.document(billing.one('SELECT id FROM billing_documents WHERE schedule_id=?',(schedule.json['id'],))['id'])
        self.assertEqual(generated['reminder_options'],options)
        self.assertEqual(self.options(doc,{}).status_code,200)
        self.assertEqual(self.get(doc['id'])['reminder_options'],{})
        self.assertEqual(self.get(generated['id'])['reminder_options'],options)
        for bad in ({'schedule':{'before_days':0,'on_due_date':False,'after_days':[]}}, {'templates':{'invoice':{'subject':'No','body':'No'}}}, {'templates':{'reminder_due':{'subject':'Invalid {secret}','body':'Body'}}}, {'schedule':{'before_days':True,'on_due_date':True,'after_days':[]}}, {'schedule':{'before_days':2,'on_due_date':False,'after_days':[1,2,3,4,5,6,7]}}):
            self.assertEqual(self.options(self.get(doc['id']),bad).status_code,400)
        self.assertEqual(self.agent.get(f"/api/billing/documents/{doc['id']}/reminders").status_code,403)

    @patch('billing.deliver', return_value=('unknown','simulated uncertain delivery'))
    def test_uncertain_delivery_blocks_number_edit_and_delete(self,send):
        self.email_config();doc=self.issue(self.create())
        self.call(self.owner,'billing/reminder-settings',dict(enabled=True,before_days=0,on_due_date=True,after_days=[]),'PUT')
        with app.app_context():self.assertEqual(run_reminders(self.today),1)
        doc=self.get(doc['id'])
        self.assertEqual(self.renumber(doc,'NEW-NUMBER').status_code,409)
        self.assertEqual(self.remove(doc).status_code,409)
        self.assertEqual(self.create()['number'],'INV-0002')

    @patch('billing.deliver', return_value=('sent',''))
    def test_upgrade_keeps_legacy_reminder_claim_after_renumber(self,send):
        self.email_config();doc=self.issue(self.create())
        self.call(self.owner,'billing/reminder-settings',dict(enabled=True,before_days=0,on_due_date=True,after_days=[]),'PUT')
        with app.app_context():
            self.assertEqual(run_reminders(self.today),1)
            db().execute('UPDATE billing_outbox SET automation_key=?',(f"{doc['number']}:{doc['due_date']}:{self.today}",))
            from migrations.m009_billing_controls import upgrade
            upgrade(db());db().commit()
        doc=self.get(doc['id']);self.assertEqual(self.renumber(doc,'UPGRADED').status_code,200)
        with app.app_context():self.assertEqual(run_reminders(self.today),0)
        send.assert_called_once()
