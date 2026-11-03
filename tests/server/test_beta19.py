"""Draft recovery, PDF design, explicit email files and automatic deduction boundaries."""
import io
import json
import unittest
from unittest.mock import patch
from PIL import Image
from pypdf import PdfReader
import test_billing
import test_beta14
from app import app, db, one


class Beta19Test(unittest.TestCase):
    setUp=test_billing.BillingTest.setUp
    call=test_billing.BillingTest.call
    login=test_billing.BillingTest.login
    expense=test_billing.BillingTest.expense
    create=test_billing.BillingTest.create
    get=test_billing.BillingTest.get
    action=test_billing.BillingTest.action
    issue=test_billing.BillingTest.issue
    pay=test_billing.BillingTest.pay
    email_config=test_billing.BillingTest.email_config
    profile=test_beta14.Beta14Test.profile
    inputs=test_beta14.Beta14Test.inputs
    suggest=test_beta14.Beta14Test.suggest
    treatment=test_beta14.Beta14Test.treatment

    def payload(self,**kw):
        return dict(kind='invoice',client_id=self.cid,issue_date=self.today,due_date=self.today,tax_mode='none',lines=[dict(description='Flight examination',quantity=2,quantity_type='Hours',unit_price=300,tax='none')],**kw)

    def test_autosave_conflict_atomic_consumption_and_paid_lock(self):
        key='billing/editor-drafts/new-invoice';payload=self.payload()
        r=self.call(self.owner,key,dict(version=0,payload=payload),'PUT');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.call(self.owner,key,dict(version=0,payload=payload),'PUT').status_code,409)
        self.assertEqual(self.call(self.agent,key,dict(version=1,payload=payload),'PUT').status_code,403)
        bad={**payload,'client_id':999,'editor_draft':dict(key='new-invoice',version=1)}
        self.assertEqual(self.call(self.owner,'billing/documents',bad).status_code,400)
        self.assertEqual(self.owner.get('/api/'+key).json['version'],1)
        payload['editor_draft']=dict(key='new-invoice',version=1)
        r=self.call(self.owner,'billing/documents',payload);self.assertEqual(r.status_code,200,r.json)
        self.assertIsNone(self.owner.get('/api/'+key).json['payload'])
        doc=self.issue(self.get(r.json['id']));self.assertEqual(self.pay(doc,600).status_code,200)
        r=self.call(self.owner,'billing/editor-drafts/document-'+str(doc['id']),dict(version=0,payload={**payload,'version':doc['version']}),'PUT')
        self.assertEqual(r.status_code,409)

    def test_design_preview_and_quantity_types(self):
        r=self.call(self.owner,'billing/services',dict(description='Instruction',unit_price=150,tax='none',quantity_type='Flight tests'));self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.owner.get('/api/billing/services').json[0]['quantity_type'],'Flight tests')
        before=self.owner.get('/api/billing/documents').json
        for layout in ('classic','modern','compact'):
            design=dict(layout=layout,font='serif' if layout=='classic' else 'sans',accent='#385D76',show_quantity=True,show_unit=True,show_rate=False,show_reference=False,show_client_address=False)
            self.assertEqual(self.call(self.owner,'billing/design',design,'PUT').status_code,200)
            preview=self.call(self.owner,'billing/preview',self.payload())
            self.assertEqual(preview.status_code,200,preview.json)
            pdf=PdfReader(io.BytesIO(preview.data));text=' '.join(p.extract_text() for p in pdf.pages)
            self.assertIn('Hours',text);self.assertIn('Flight examination',text)
            self.assertNotIn('Unit price',text)
        self.assertEqual(self.owner.get('/api/billing/documents').json,before)
        document=self.create(lines=self.payload()['lines'],tax_mode='none')
        self.assertEqual(document['lines'][0]['quantity_type'],'Hours')
        snapshot=document['business']
        self.call(self.owner,'billing/design',dict(layout='modern'),'PUT')
        self.assertEqual(self.get(document['id'])['business'],snapshot)
        self.assertEqual(self.call(self.owner,'billing/design',dict(layout='unsupported'),'PUT').status_code,400)

    def upload(self,did):
        stream=io.BytesIO();Image.new('RGB',(15,15),'white').save(stream,'PNG');stream.seek(0)
        token=self.owner.get('/api/session').json['csrf']
        return self.owner.post(f'/api/billing/documents/{did}/attachments',data={'file':(stream,'support.png')},headers={'X-CSRF-Token':token})

    def test_attachments_are_explicit_document_bound_and_audited(self):
        self.email_config();a=self.create();b=self.create()
        file=self.upload(a['id']).json[0]
        self.assertEqual(file['mime'],'image/jpeg')
        self.assertEqual(self.agent.get(f"/api/billing/documents/{a['id']}/attachments").status_code,403)
        def send(doc,ids):
            draft=self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft").json
            data=dict(recipient='client@example.test',subject='Your invoice',body='Please find attached',version=draft['version'],request_key=draft['request_key'],message_kind='document',copy_self=False,attachment_ids=ids)
            return self.call(self.owner,f"billing/documents/{doc['id']}/send",data)
        with patch('billing.deliver',return_value=('sent','')) as deliver:
            self.assertEqual(send(b,[file['id']]).status_code,409);deliver.assert_not_called()
            r=send(a,[]);self.assertEqual(r.status_code,200,r.json);self.assertNotIn('attachments',deliver.call_args.kwargs)
            r=send(self.get(a['id']),[file['id']]);self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(deliver.call_args.kwargs['attachments'][0]['id'],file['id'])
        with app.app_context():
            manifest=json.loads(one('SELECT attachments_json FROM billing_outbox ORDER BY id DESC')['attachments_json'])
            self.assertEqual(manifest[0]['sha256'],file['sha256'])
        token=self.owner.get('/api/session').json['csrf']
        invalid=self.owner.post(f"/api/billing/documents/{a['id']}/attachments",data={'file':(io.BytesIO(b'<script>unsafe</script>'),'fake.png')},headers={'X-CSRF-Token':token})
        self.assertEqual(invalid.status_code,400)

    def test_notifications_enabling_skips_backlog_and_delivery_is_once(self):
        import workspace_preferences
        event=lambda key:dict(key=key,kind='invoicePaid',title='Invoice paid',details='Open your invoice')
        prefs=self.owner.get('/api/workspace-preferences').json
        prefs['notifications']['invoicePaid']['email']=True
        with patch('notifications.collect',return_value=[event('old')]):
            saved=self.call(self.owner,'workspace-preferences',prefs,'PUT');self.assertEqual(saved.status_code,200,saved.json)
        self.assertEqual(self.call(self.owner,'workspace-preferences',prefs,'PUT').status_code,409)
        self.email_config()
        with app.app_context(),patch('notifications.collect',return_value=[event('old'),event('new')]),patch('billing.deliver',return_value=('sent','')) as send:
            workspace_preferences.process_emails();workspace_preferences.process_emails();self.assertEqual(send.call_count,1)
            self.assertFalse(send.call_args.kwargs['copy'])
        self.assertEqual(self.agent.get('/api/workspace-preferences').status_code,403)
        prefs=saved.json;prefs['notifications']['invoicePaid']['bell']=False
        self.assertEqual(self.call(self.owner,'workspace-preferences',prefs,'PUT').status_code,200)
        with patch('notifications.collect',return_value=[event('new')]):self.assertEqual(self.owner.get('/api/workspace-notifications').json['items'],[])

    def test_automatic_estimate_without_annual_question_and_no_double_claim(self):
        d=self.inputs(automatic=True,life='',basis='',name='AirPods hearing protection',depreciation_method='diminishing_value')
        r=self.suggest(d);self.assertEqual(r.status_code,200,r.json);r=r.json
        self.assertTrue(r['ready']);self.assertEqual(r['method'],'diminishing_value');self.assertTrue(r['profile']['assumed']);self.assertEqual(float(r['calculation']['life']),3)
        self.assertEqual(r['annual_cents'],25000)
        tax=self.treatment(d)
        e=self.expense(self.owner,date=d['date'],category='Equipment',amount=500,work_percent=50,business_percent=25,tax_treatment=tax)
        self.assertEqual(e.status_code,200,e.json)
        forecast=self.owner.get('/api/tax/2026').json
        self.assertEqual(forecast['recorded']['work_deductions_cents'],0)
        self.assertEqual(forecast['forecast']['work_deductions_cents']+forecast['forecast']['business_deductions_cents'],25000)
        self.assertEqual(self.suggest({**d,'name':'Laptop repair'}) .json['status'],'ordinary')
        self.profile('simplified');self.assertEqual(self.suggest(d).json['annual_cents'],37500)
        self.profile('general');small={**d,'amount':300,'work_percent':100,'business_percent':0}
        self.assertEqual(self.suggest(small).json['method'],'immediate_employee')
        self.assertEqual(self.suggest({**small,'not_grouped':False}).json['method'],'diminishing_value')

    def test_pending_special_treatment_is_not_an_ordinary_claim(self):
        d=self.inputs(automatic=True,previous_use=True,life='',basis='')
        r=self.suggest(d).json;self.assertEqual(r['status'],'manual_review')
        tax={**d,'confirmed':True,'pending_review':True,'profile_version':r['profile']['version'],'expense_basis':{k:d[k] for k in ('date','amount','work_percent','business_percent')}}
        e=self.expense(self.owner,date=d['date'],category='Equipment',amount=500,work_percent=50,business_percent=25,tax_treatment=tax)
        self.assertEqual(e.status_code,200,e.json)
        report=self.owner.get('/api/tax/2026').json
        self.assertEqual(report['forecast']['work_deductions_cents']+report['forecast']['business_deductions_cents'],0)

    @patch('billing.smtplib.SMTP_SSL')
    def test_selected_files_are_real_mime_attachments(self,smtp):
        import billing
        from flask import g
        self.email_config()
        with app.test_request_context():
            g.user=one("SELECT * FROM users WHERE role='owner'")
            state,error=billing.deliver('client@example.test','Invoice','Hello',b'%PDF-1.4 example','invoice.pdf',copy=True,copy_self=False,attachments=[dict(mime='image/jpeg',content=b'image bytes',filename='receipt.jpg')])
        self.assertEqual(state,'sent',error)
        message=smtp.return_value.send_message.call_args.args[0]
        files=list(message.iter_attachments())
        self.assertEqual([f.get_filename() for f in files],['invoice.pdf','receipt.jpg'])
        self.assertEqual(files[1].get_payload(decode=True),b'image bytes')
        self.assertIsNone(message['Bcc'])
