"""Cross-ledger review, concurrency, access and recovery regression tests."""
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch
import test_app
from app import app,db,one,rows,DATA


class WorkflowTest(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    call=test_app.AppTest.call
    login=test_app.AppTest.login
    expense=test_app.AppTest.expense

    def create_expense(self,**kw):
        r=self.expense(self.owner,category='Other',**kw);self.assertEqual(r.status_code,200,r.json);return r.json['id']

    def bank(self,amount):
        with app.app_context():
            account=db().execute("INSERT INTO accounts(name,bank) VALUES ('Checking','Test')").lastrowid
            feed=db().execute("INSERT INTO pocketsmith_accounts(remote_user_id,remote_id,name,currency,local_account_id,enabled) VALUES ('1',?,'Checking','AUD',?,1)",(str(account),account)).lastrowid
            bid=db().execute("INSERT INTO bank_transactions(feed_account_id,remote_user_id,remote_id,date,payee,amount_cents,currency,source_status,fingerprint,last_seen) VALUES (?,'1',?,'2026-10-08','Payment',?,'AUD','posted','test','now')",(feed,str(feed),amount)).lastrowid
            db().commit();return bid

    def match(self,payload):
        p=self.call(self.owner,'workflows/reconciliation/preview',payload);self.assertEqual(p.status_code,200,p.json)
        r=self.call(self.owner,'workflows/reconciliation/apply',{**payload,'token':p.json['token']});self.assertEqual(r.status_code,200,r.json);return p.json

    def invoice(self,amount):
        with app.app_context():
            cid=db().execute("INSERT INTO billing_clients(name) VALUES ('Example client')").lastrowid
            ident=db().execute("INSERT INTO billing_documents(kind,number,state,client_id,client,business,issue_date,due_date,tax_mode,lines,subtotal_cents,gst_cents,total_cents,created_at) VALUES ('invoice',?,'issued',?,'{}','{}','2026-10-01','2026-10-31','none','[]',?,0,?,'2026-10-01')",('INV-'+str(cid),cid,amount,amount)).lastrowid
            db().commit();return ident

    def pay(self,**updates):
        data=dict(employer='Example employer',date='2026-10-08',gross='1000',withheld='200',record_kind='payslip',period_start='2026-09-25',period_end='2026-10-08');data.update(updates)
        r=self.call(self.owner,'employment',data);self.assertEqual(r.status_code,200,r.json);return r.json['id']

    def details(self,ident,**values):
        p=self.owner.get('/api/workflows/income-details/'+str(ident)).json
        result=self.call(self.owner,'workflows/income-details/'+str(ident),{**values,'token':p['token']},'PUT');self.assertEqual(result.status_code,200,result.json)

    def test_read_routes_and_permissions(self):
        for path in ['attention/2026','rules','reconciliation','income/2026','equipment?year=2026','journeys?date=2026-10-08','questions','question-records?kind=expense']:
            self.assertEqual(self.agent.get('/api/workflows/'+path).status_code,200,path)
            self.assertEqual(app.test_client().get('/api/workflows/'+path).status_code,401,path)
        for path in ['mail-intake','offsite-backup']:
            self.assertEqual(self.owner.get('/api/workflows/'+path).status_code,200,path)
            self.assertEqual(self.agent.get('/api/workflows/'+path).status_code,403,path)
        for path in ['rules','reconciliation/apply','journeys/apply','equipment']:
            self.assertEqual(self.call(self.agent,'workflows/'+path,{}).status_code,403,path)

    def test_rule_preview_atomic_apply_undo_and_stale_record(self):
        eid=self.create_expense(merchant='Office Shop',amount='12',status='ready')
        r=self.call(self.owner,'workflows/rules',dict(merchant='office shop',category='Equipment',work_percent=70,business_percent=20));rid=r.json['id']
        plan=self.call(self.owner,f'workflows/rules/{rid}/preview',{}).json
        self.assertEqual(plan['before'][0]['category'],'Other')
        self.assertEqual(plan['after'][0]['status'],'review')
        result=self.call(self.owner,f'workflows/rules/{rid}/apply',dict(token=plan['token']));self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.call(self.owner,f'workflows/rules/{rid}/apply',dict(token=plan['token'])).status_code,409)
        self.assertEqual(self.call(self.owner,'workflows/rules/undo/'+str(result.json['change_id']),{}).status_code,200)
        with app.app_context(): self.assertEqual(one('SELECT category FROM expenses WHERE id=?',(eid,))['category'],'Other')
        p=self.call(self.owner,f'workflows/rules/{rid}/preview',{}).json
        with app.app_context(): db().execute('UPDATE expenses SET notes=? WHERE id=?',('Changed after preview',eid));db().commit()
        self.assertEqual(self.call(self.owner,f'workflows/rules/{rid}/apply',dict(token=p['token'])).status_code,409)

    def test_itemised_allocations_budgets_export_and_legacy_edit_guard(self):
        eid=self.create_expense(amount='100',status='ready',work_percent=0,business_percent=100)
        p=self.owner.get(f'/api/workflows/items/{eid}').json
        lines=[dict(description='Training book',amount=60,category='Training',work_percent=100,business_percent=0),dict(description='Home item',amount=40,category='Other',work_percent=0,business_percent=0)]
        result=self.call(self.owner,f'workflows/items/{eid}',dict(token=p['token'],items=lines),'PUT');self.assertEqual(result.status_code,200,result.json)
        from expense_core import allocations
        with app.app_context(): self.assertEqual(allocations(one('SELECT * FROM expenses WHERE id=?',(eid,))),(6000,0))
        export=self.owner.get('/api/export').data.decode('utf-8-sig');self.assertIn('Training',export);self.assertIn('60.00',export)
        result=self.call(self.owner,f'expenses/{eid}',dict(date='2026-10-08',merchant='Cafe',amount=101,category='Other',scope='business',percent=100),'PUT')
        self.assertEqual(result.status_code,409,result.json)
        p=self.owner.get(f'/api/workflows/items/{eid}').json;lines[0]['amount']=59
        self.assertEqual(self.call(self.owner,f'workflows/items/{eid}',dict(token=p['token'],items=lines),'PUT').status_code,400)

    def test_one_deposit_multiple_invoices_partial_payments_and_undo(self):
        a,b=self.invoice(10000),self.invoice(12000);bid=self.bank(15000)
        self.match(dict(bank_id=bid,kind='invoice',allocations=[dict(id=a,amount=100),dict(id=b,amount=50)]))
        with app.app_context():
            self.assertEqual(one('SELECT SUM(amount_cents) n FROM billing_payments WHERE reversed_at IS NULL')['n'],15000)
            self.assertEqual(one('SELECT COUNT(*) n FROM expenses')['n'],0)
            pid=one('SELECT id FROM billing_payments')['id']
        self.assertEqual(self.call(self.owner,f'billing/payments/{pid}/reverse',dict(reason='test',version=2)).status_code,409)
        b2=self.bank(8000)
        self.assertEqual(self.call(self.owner,'workflows/reconciliation/preview',dict(bank_id=b2,kind='invoice',allocations=[dict(id=b,amount=80)])).status_code,400)
        self.assertEqual(self.call(self.owner,f'workflows/reconciliation/{bid}/undo',dict(reason='Wrong deposit')).status_code,200)
        with app.app_context(): self.assertEqual(one('SELECT COUNT(*) n FROM billing_payments WHERE reversed_at IS NULL')['n'],0)

    def test_payslip_deposit_needs_net_and_never_adds_income(self):
        eid=self.pay();bid=self.bank(76000);payload=dict(bank_id=bid,kind='salary',allocations=[dict(id=eid,amount=760)])
        self.assertEqual(self.call(self.owner,'workflows/reconciliation/preview',payload).status_code,400)
        self.details(eid,net=760,ytd_gross=1000,ytd_withheld=200);self.match(payload)
        self.assertEqual(len(self.owner.get('/api/employment').json),1)
        self.assertEqual(self.call(self.owner,f'employment/{eid}',{},'DELETE').status_code,409)
        again=self.bank(76000);payload['bank_id']=again
        self.assertEqual(self.call(self.owner,'workflows/reconciliation/preview',payload).status_code,400)

    def test_purchase_partial_matches_and_refund_preserve_original(self):
        eid=self.create_expense(amount=100);bid=self.bank(-6000)
        self.match(dict(bank_id=bid,kind='expense',allocations=[dict(id=eid,amount=60)]))
        bid2=self.bank(-4000);self.match(dict(bank_id=bid2,kind='expense',allocations=[dict(id=eid,amount=40)]))
        refund=self.bank(2500);self.match(dict(bank_id=refund,kind='refund',allocations=[dict(id=eid,amount=25)]))
        expenses=self.owner.get('/api/expenses').json
        self.assertEqual(sum(e['amount_cents'] for e in expenses),7500)
        self.assertEqual(next(e for e in expenses if e['amount_cents']<0)['status'],'review')
        self.assertEqual(self.call(self.owner,f'expenses/{eid}',{},'DELETE').status_code,409)

    def test_income_gap_ytd_and_statement_comparisons_do_not_post(self):
        a=self.pay();self.details(a,net=800,ytd_gross=2500,ytd_withheld=500)
        self.pay(date='2026-11-05',period_start='2026-10-23',period_end='2026-11-05')
        d=self.owner.get('/api/workflows/income/2026').json['employers'][0]
        self.assertEqual(d['gaps'][0],dict(start='2026-10-09',end='2026-10-22'))
        self.assertEqual(d['ytd']['gross_difference_cents'],150000)
        r=self.call(self.owner,'workflows/income/2026/statement',dict(employer='Example employer',gross=2500,withheld=500,reference_only=True));self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(len(self.owner.get('/api/employment').json),2)

    def test_equipment_avoids_double_deductions_and_carries_forward(self):
        eid=self.create_expense(amount=1000,status='ready',work_percent=100,business_percent=0)
        a=self.call(self.owner,'workflows/equipment',dict(expense_id=eid,name='Laptop',acquired='2026-10-08',cost=1000,work_percent=100,business_percent=0,confirm_capital=True));self.assertEqual(a.status_code,200,a.json);aid=a.json['id']
        tax=self.owner.get('/api/tax/2026').json;self.assertEqual(tax['recorded']['work_deductions_cents'],0)
        p=self.call(self.owner,f'workflows/equipment/{aid}/year/2026',dict(version=1,amount=200,notes='Reviewed annual calculation',confirmed=True),'PUT');self.assertEqual(p.status_code,200,p.json)
        tax=self.owner.get('/api/tax/2026').json;self.assertEqual(tax['recorded']['work_deductions_cents'],20000)
        a=self.owner.get('/api/workflows/equipment?year=2027').json['assets'][0];self.assertEqual(a['opening_cents'],80000)
        self.assertEqual(self.call(self.owner,f'workflows/equipment/{aid}/year/2027',dict(version=a['version'],amount=801,notes='Invalid',confirmed=True),'PUT').status_code,400)
        self.assertEqual(self.call(self.owner,f'expenses/{eid}',{},'DELETE').status_code,409)

    def test_readonly_agent_questions_are_the_only_financial_exception(self):
        eid=self.create_expense()
        r=self.call(self.agent,'workflows/questions',dict(record_type='expense',record_id=eid,question='What was the business purpose?'));self.assertEqual(r.status_code,200,r.json)
        q=self.owner.get('/api/workflows/questions').json[0]
        self.assertEqual(self.call(self.owner,'workflows/questions',dict(id=q['id'],version=q['version'],answer='Client meeting',resolved=True),'PUT').status_code,200)
        self.assertEqual(self.call(self.owner,'workflows/questions',dict(id=q['id'],version=q['version'],answer='Stale',resolved=True),'PUT').status_code,409)
        self.assertEqual(self.call(self.agent,'workflows/rules',{}).status_code,403)

    def test_merge_split_undo_preserve_distance_and_upload_identity(self):
        vehicle=self.call(self.owner,'vehicles',dict(name='Car')).json['id']
        ids=[]
        for origin,destination in [('A','B'),('B','C')]:
            r=self.call(self.owner,'vehicle-journeys',dict(vehicle_id=vehicle,date='2026-10-08',origin=origin,destination=destination,purpose='Client visit',scope='business',distance=10,percent=100));self.assertEqual(r.status_code,200,r.json);ids.append(r.json['id'])
        payload=dict(action='merge',ids=ids);p=self.call(self.owner,'workflows/journeys/preview',payload).json
        result=self.call(self.owner,'workflows/journeys/apply',{**payload,'token':p['token']});self.assertEqual(result.status_code,200,result.json)
        ledger=self.owner.get('/api/workflows/journeys?date=2026-10-08').json['journeys'];self.assertEqual(len(ledger),1);self.assertEqual(ledger[0]['distance_m'],20000);self.assertNotIn(ledger[0]['id'],ids)
        payload=dict(action='split',ids=[ledger[0]['id']],first_distance=7,split_place='Rest stop');p=self.call(self.owner,'workflows/journeys/preview',payload).json
        split=self.call(self.owner,'workflows/journeys/apply',{**payload,'token':p['token']});self.assertEqual(split.status_code,200,split.json)
        self.assertEqual(self.call(self.owner,'workflows/journeys/undo/'+str(split.json['change_id']),{}).status_code,200)
        self.assertEqual(self.call(self.owner,'workflows/journeys/undo/'+str(result.json['change_id']),{}).status_code,200)
        self.assertEqual([r['id'] for r in self.owner.get('/api/workflows/journeys?date=2026-10-08').json['journeys']],ids)

    def test_personal_drive_confirmation_clears_attention(self):
        vehicle=self.call(self.owner,'vehicles',dict(name='Car')).json['id']
        r=self.call(self.owner,'vehicle-journeys',dict(vehicle_id=vehicle,date='2026-10-08',origin='A',destination='B',purpose='',scope='personal',distance=10,percent=0));ident=r.json['id']
        payload=dict(action='classify',ids=[ident],scope='personal',purpose='',percent=0);p=self.call(self.owner,'workflows/journeys/preview',payload).json
        self.assertEqual(self.call(self.owner,'workflows/journeys/apply',{**payload,'token':p['token']}).status_code,200)
        self.assertFalse(any(r['kind']=='journey' for r in self.owner.get('/api/workflows/attention/2026').json['items']))

    def test_handover_pdf_manifest_and_no_secrets(self):
        self.create_expense(amount=40,merchant='=UNTRUSTED()')
        result=self.owner.get('/api/workflows/handover/2026');self.assertEqual(result.status_code,200)
        with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
            self.assertIn('annual-handover.pdf',archive.namelist());self.assertTrue(archive.read('annual-handover.pdf').startswith(b'%PDF'))
            manifest=json.loads(archive.read('manifest.json'));self.assertEqual(set(manifest['sha256']),set(archive.namelist())-{'manifest.json'})
            self.assertNotIn('session.key',' '.join(archive.namelist()))
            self.assertIn("'=UNTRUSTED()",archive.read('registers/expenses.csv').decode('utf-8-sig'))
        result.close()

    def test_mail_attachment_deduplication_is_draft_only(self):
        from reportlab.pdfgen import canvas
        import mail_intake
        source=io.BytesIO();c=canvas.Canvas(source);c.drawString(20,700,'Synthetic invoice $50.00');c.save()
        with app.app_context():
            uid=one("SELECT id FROM users WHERE role='owner'")['id']
            a=mail_intake.store_attachment(uid,'invoice.pdf',source.getvalue());b=mail_intake.store_attachment(uid,'invoice.pdf',source.getvalue());self.assertEqual(a,b)
            self.assertEqual(one('SELECT COUNT(*) n FROM expenses')['n'],0)
            self.assertEqual((DATA/'receipts'/a).read_bytes(),source.getvalue())
        evidence=self.owner.get('/api/workflows/evidence/'+a);self.assertEqual(evidence.status_code,200,evidence.json)

    def test_encrypted_copy_and_isolated_restore_reject_tampering(self):
        import auto_backup,offsite_backup
        self.create_expense(amount=50)
        with tempfile.TemporaryDirectory() as tmp,app.app_context():
            folder=Path(tmp);source=folder/'source.zip';key=b'x'*32
            auto_backup.write_archive(source,DATA,'test',verify=True)
            encrypted=folder/'copy.epb';offsite_backup.encrypt(source,encrypted,key)
            stage=folder/'test';stage.mkdir();result=offsite_backup.restore_test(encrypted,key,stage);self.assertIn('1 expense',result)
            self.assertEqual(one('SELECT COUNT(*) n FROM expenses')['n'],1)
            raw=bytearray(encrypted.read_bytes());raw[-18]^=1;encrypted.write_bytes(raw)
            with self.assertRaises(Exception): offsite_backup.decrypt(encrypted,folder/'tampered.zip',key)
            self.assertFalse((folder/'tampered.zip').exists())


class SigninAlertTest(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    call=test_app.AppTest.call
    login=test_app.AppTest.login

    def signin(self,ip,password='Owner-password-123'):
        client=app.test_client();token=client.get('/api/session').json['csrf']
        result=client.post('/api/login',json=dict(email='owner@example.test',password=password),headers={'X-CSRF-Token':token,'X-Forwarded-For':'203.0.113.99'},environ_overrides={'REMOTE_ADDR':ip})
        return client,result

    def test_only_successful_signins_enrol_ip_and_browser_sessions_are_visible(self):
        self.assertEqual(self.signin('203.0.113.2','wrong')[1].status_code,401)
        with app.app_context(): self.assertIsNone(one("SELECT * FROM known_signin_ips WHERE ip='203.0.113.2'"))
        client,r=self.signin('203.0.113.2');self.assertEqual(r.status_code,200,r.json)
        history=client.get('/api/security/signins').json['events'];self.assertEqual(history[0]['ip'],'203.0.113.2');self.assertTrue(history[0]['is_new'])
        self.signin('203.0.113.2');history=client.get('/api/security/signins').json['events'];self.assertFalse(history[0]['is_new'])
        self.assertTrue(client.get('/api/security/sessions').json)
        self.assertEqual(client.get('/api/security/devices').json,[])
        sessions=self.owner.get('/api/security/sessions').json;target=next(s for s in sessions if not s['current'])
        self.assertEqual(self.call(self.agent,'security/sessions',dict(id=target['id']),'DELETE').status_code,404)

    def test_coalescing_failure_cooldown_and_disable(self):
        import signin_alerts
        self.signin('203.0.113.4');self.signin('203.0.113.5')
        with app.app_context(),patch('billing.mail_settings',return_value=dict(host='mail.test',from_email='alerts@example.test')),patch('billing.deliver',return_value=('failed','Delivery failed')) as deliver:
            signin_alerts.process();first=deliver.call_count;self.assertGreater(first,0)
            self.assertTrue(any('203.0.113.4' in str(c) and '203.0.113.5' in str(c) for c in deliver.call_args_list))
            signin_alerts.process();self.assertEqual(deliver.call_count,first)
        self.assertEqual(self.call(self.owner,'security/signins',dict(enabled=False),'PUT').status_code,200)
        client,r=self.signin('203.0.113.6');self.assertEqual(r.status_code,200)
        self.assertEqual(client.get('/api/security/signins').json['events'][0]['state'],'recorded')
