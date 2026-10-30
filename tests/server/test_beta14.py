"""Equipment decision boundaries, atomic imports and stable category identities."""
import io
import json
import unittest
from unittest.mock import patch
from decimal import Decimal
import test_app
from app import app,db,one
import equipment_calculations as calc
import equipment_import

class Beta14Test(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    call=test_app.AppTest.call
    login=test_app.AppTest.login
    expense=test_app.AppTest.expense

    def profile(self,mode='general',year=2026):
        old=self.owner.get(f'/api/workflows/equipment/tax-profile/{year}').json
        r=self.call(self.owner,f'workflows/equipment/tax-profile/{year}',dict(version=old['version'],mode=mode,confirmed=True,sole_trader=True,small_business=True,whole_regime=True),'PUT')
        self.assertEqual(r.status_code,200,r.json);return r.json

    def inputs(self,**kw):
        d=dict(date='2026-07-01',first_use='2026-07-01',amount=500,category='Equipment',name='Earphones',work_percent=50,business_percent=25,gst_credit=0,
               asset_confirmed=True,purpose_confirmed=True,eligible_asset=True,not_grouped=True,previous_use=False,life=2,basis='Reviewed effective life and actual work use',depreciation_method='prime_cost')
        d.update(kw);return d

    def suggest(self,d): return self.call(self.owner,'workflows/equipment/suggest',d)

    def treatment(self,d):
        r=self.suggest(d);self.assertEqual(r.status_code,200,r.json);self.assertTrue(r.json['ready'],r.json)
        return dict(d,method=r.json['method'],profile_version=r.json['profile']['version'],confirmed=True,expense_basis={k:d[k] for k in ('date','amount','work_percent','business_percent')})

    def test_full_cost_and_mainly_income_thresholds(self):
        self.profile()
        r=self.suggest(self.inputs());self.assertEqual(r.json['method'],'prime_cost');self.assertEqual(r.json['full_cost_cents'],50000)
        for amount,work,expected in [(300,50,'prime_cost'),(300,51,'immediate_employee'),(300.01,75,'prime_cost')]:
            r=self.suggest(self.inputs(amount=amount,work_percent=work,business_percent=0));self.assertEqual(r.json['method'],expected,r.json)
        self.assertFalse(self.suggest(self.inputs(amount=300,work_percent=75,business_percent=0,not_grouped=False)).json['ready'])
        self.assertFalse(self.suggest(self.inputs(purpose_confirmed=False)).json['ready'])
        self.assertFalse(self.suggest(self.inputs(previous_use=True)).json['ready'])
        self.assertIsNone(self.suggest(self.inputs(life='',name='AirPods')).json['life_suggestion'])
        self.assertEqual(self.suggest(self.inputs(life='',name='iPad')).json['life_suggestion'],2)

    def test_simplified_regime_mixed_employment_use_and_permanent_limit(self):
        self.profile('simplified');d=self.inputs();r=self.suggest(d)
        self.assertEqual(r.json['method'],'immediate_business');self.assertEqual(r.json['work_cents']+r.json['business_cents'],37500)
        self.assertFalse(self.suggest(self.inputs(amount=20000)).json['ready'])
        self.assertTrue(self.suggest(self.inputs(amount=19999.99)).json['ready'])
        self.profile('simplified',2027)
        self.assertTrue(self.suggest(self.inputs(date='2027-07-01',first_use='2027-07-01')).json['ready'])
        self.assertIsNone(calc.instant_limit(2023));self.assertEqual(calc.instant_limit(2030),2000000)
        bad=self.call(self.owner,'workflows/equipment/tax-profile/2028',dict(version=0,mode='simplified',confirmed=True),'PUT')
        self.assertEqual(bad.status_code,400)

    def test_atomic_expense_asset_no_double_claim_and_stale_profile(self):
        self.profile('simplified');d=self.inputs();tax=self.treatment(d)
        r=self.expense(self.owner,**{k:d[k] for k in ('date','amount','category','work_percent','business_percent')},merchant='Electronic store',tax_treatment=tax)
        self.assertEqual(r.status_code,200,r.json)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        self.assertEqual(a['expense_id'],r.json['id']);self.assertEqual(a['current']['amount_cents'],50000)
        f=self.owner.get('/api/tax/2026').json
        self.assertEqual(f['forecast']['work_deductions_cents'],25000);self.assertEqual(f['forecast']['business_deductions_cents'],12500)
        self.assertEqual(f['recorded']['work_deductions_cents'],0)
        self.profile('general')
        r=self.expense(self.owner,**{k:d[k] for k in ('date','amount','category','work_percent','business_percent')},tax_treatment=tax)
        self.assertEqual(r.status_code,409,r.json)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM expenses')['n'],1)
        r=self.call(self.owner,'expenses/'+str(a['expense_id']),dict(date=d['date'],amount=500,category='Equipment',merchant='Store',scope='split',work_percent=50,business_percent=25,reimbursed=True),'PUT')
        self.assertEqual(r.status_code,409)

    def test_mismatched_receipt_basis_cannot_attach_tax_decision(self):
        self.profile();d=self.inputs();tax=self.treatment(d)
        r=self.expense(self.owner,date=d['date'],amount=600,category='Equipment',work_percent=50,business_percent=25,tax_treatment=tax)
        self.assertEqual(r.status_code,409)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM expenses')['n'],0)

    def test_receipt_treatment_is_atomic_and_rejects_different_existing_payment(self):
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(12,12),'white').save(raw,'PNG');raw.seek(0)
        token=self.owner.get('/api/session').json['csrf']
        uploaded=self.owner.post('/api/receipts',data={'file':(raw,'equipment.png')},headers={'X-CSRF-Token':token})
        self.assertEqual(uploaded.status_code,200,uploaded.json);rid=uploaded.json['id']
        self.profile('simplified');d=self.inputs();tax=self.treatment(d)
        existing=self.expense(self.owner,date=d['date'],amount=600,category='Equipment',work_percent=50,business_percent=25).json['id']
        data=dict(d,merchant='Electronic store',scope='split',status='ready',tax_treatment=tax)
        r=self.call(self.owner,f'receipts/{rid}/expense',dict(data,existing_expense_id=existing));self.assertEqual(r.status_code,409,r.json)
        with app.app_context():
            self.assertIsNone(one('SELECT receipt_id FROM expenses WHERE id=?',(existing,))['receipt_id'])
            self.assertEqual(one('SELECT count(*) n FROM equipment_assets')['n'],0)
        r=self.call(self.owner,f'receipts/{rid}/expense',data);self.assertEqual(r.status_code,200,r.json)
        with app.app_context():
            self.assertEqual(one('SELECT receipt_id FROM expenses WHERE id=?',(r.json['id'],))['receipt_id'],rid)
            self.assertEqual(one('SELECT expense_id FROM equipment_assets')['expense_id'],r.json['id'])
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',data).status_code,409)

    def test_profile_and_import_access_owner_only(self):
        for client in (self.agent,app.test_client()):
            for path in ('workflows/equipment/imports','workflows/equipment/tax-profile/2026'):
                self.assertIn(client.get('/api/'+path).status_code,(401,403))
            self.assertIn(self.call(client,'workflows/equipment/suggest',self.inputs()).status_code,(401,403))

    def imported(self,rows=None):
        rows=rows or [dict(name='Travel equipment',acquired='2023-03-10',cost='600',opening='200',decline='80',closing='120',method='diminishing_value',rate='40',work_percent='50',business_percent='25')]
        import csv
        out=io.StringIO();writer=csv.DictWriter(out,fieldnames=('year',*equipment_import.FIELDS));writer.writeheader()
        for row in rows: writer.writerow(dict(year=2025,**row))
        token=self.owner.get('/api/session').json['csrf']
        with patch('equipment_import.threading.Thread.start',lambda thread:thread.run()):
            r=self.owner.post('/api/workflows/equipment/imports',data={'file':(io.BytesIO(out.getvalue().encode()),'example.csv')},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['status'],'review',r.json);return r.json

    def commit(self,source,rows=None,**kw):
        return self.call(self.owner,'workflows/equipment/imports/'+source['id']+'/commit',dict(version=source['version'],year=2025,rows=rows or source['data']['rows'],confirmed=True,aud_confirmed=True,**kw))

    def test_import_carry_forward_preserves_cost_and_prior_years(self):
        source=self.imported();r=self.commit(source);self.assertEqual(r.status_code,200,r.json)
        a=self.owner.get('/api/workflows/equipment?year=2025').json['assets'][0]
        self.assertEqual((a['cost_cents'],a['opening_cents'],a['current']['amount_cents'],a['closing_cents']),(60000,20000,8000,12000))
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        self.assertEqual((a['opening_cents'],a['current']['amount_cents'],a['closing_cents']),(12000,4800,7200))
        self.assertEqual(len(a['history']),1)
        self.assertEqual(self.owner.get('/api/tax/2024').json['recorded']['work_deductions_cents'],0)
        self.assertEqual(self.owner.get('/api/tax/2026').json['forecast']['work_deductions_cents'],2400)
        self.assertTrue(self.commit(source).json['already_imported'])
        r=self.call(self.owner,f"workflows/equipment/{a['id']}/year/2024",dict(version=a['version'],amount=10,confirmed=True,notes='No'), 'PUT');self.assertEqual(r.status_code,409)
        docs=self.owner.get('/api/documents').json['documents'];doc=next(x for x in docs if x['id']==source['document_id'])
        self.assertEqual(self.call(self.owner,'documents/'+doc['id'],dict(version=doc['version']),'DELETE').status_code,409)

    def test_import_requires_matching_expense_resolution_and_links_once(self):
        e=self.expense(self.owner,date='2025-07-01',amount=600,category='Equipment',work_percent=50,business_percent=25).json['id']
        source=self.imported([dict(name='New equipment',acquired='2025-07-01',cost='600',opening='600',decline='240',closing='360',method='diminishing_value',rate='40',work_percent='50',business_percent='25')])
        self.assertEqual(self.commit(source).status_code,409)
        rows=[dict(source['data']['rows'][0],expense_id=e)]
        result=self.commit(source,rows);self.assertEqual(result.status_code,200,result.json)
        asset=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        self.assertEqual(asset['expense_id'],e)
        self.assertEqual(self.owner.get('/api/tax/2025').json['recorded']['work_deductions_cents'],12000)
        old=self.owner.get('/api/workflows/equipment?year=2024').json['assets'][0]
        self.assertTrue(old['history_unavailable'])
        r=self.call(self.owner,f"workflows/equipment/{asset['id']}/use/2024",dict(version=asset['version'],work_percent=60,business_percent=20,notes='Before cutover'),'PUT')
        self.assertEqual(r.status_code,400)

    def test_bad_import_is_atomic_and_duplicate_schedule_reuses_original(self):
        source=self.imported();rows=source['data']['rows'];bad=dict(rows[0],name='Broken',closing='119')
        self.assertEqual(self.commit(source,rows+[bad]).status_code,400)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM equipment_assets')['n'],0)
        self.assertEqual(self.imported()['id'],source['id'])
        self.assertEqual(self.commit(source).status_code,200)
        # Re-reading does not silently import or duplicate assets.
        with patch('equipment_import.threading.Thread.start',lambda thread:thread.run()):
            again=self.call(self.owner,'workflows/equipment/imports/'+source['id'],{},'PUT').json
        self.assertEqual(self.commit(again).status_code,409)

    def test_written_off_retained_without_future_claim_and_manual_pool_not_inferred(self):
        row=dict(name='Previously written off tablet',acquired='2025-08-01',cost='1500',opening='1500',decline='1500',closing='0',method='written_off',rate='',work_percent='0',business_percent='100')
        source=self.imported([row]);self.assertEqual(self.commit(source).status_code,200)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        self.assertEqual(a['closing_cents'],0);self.assertFalse(a['needs_review']);self.assertEqual(self.owner.get('/api/tax/2026').json['forecast']['business_deductions_cents'],0)
        with app.app_context():
            with self.assertRaises(Exception): equipment_import.validate(dict(row,closing='1'),2025)

    def test_ai_partial_result_rejected_and_original_retained_after_failure(self):
        from PIL import Image
        data=io.BytesIO();Image.new('RGB',(20,20),'white').save(data,'PNG');data.seek(0)
        token=self.owner.get('/api/session').json['csrf']
        with patch('equipment_import.threading.Thread.start',lambda thread:thread.run()),patch('ai_providers.configured',return_value=True),patch('ai_providers.extract',return_value=dict(rows=[{}],total_asset_rows=2)):
            r=self.owner.post('/api/workflows/equipment/imports',data={'file':(data,'example.png')},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['status'],'failed');self.assertIn('complete schedule',r.json['error'])
        with app.app_context():
            self.assertTrue((equipment_import.tax_documents.folder()/r.json['document_id']).exists());self.assertEqual(one('SELECT count(*) n FROM equipment_assets')['n'],0)

    def test_abandoned_import_original_can_be_deleted(self):
        source=self.imported()
        docs=self.owner.get('/api/documents').json['documents'];doc=next(x for x in docs if x['id']==source['document_id'])
        r=self.call(self.owner,'documents/'+doc['id'],dict(version=doc['version']),'DELETE');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.owner.get('/api/workflows/equipment/imports/'+source['id']).status_code,404)
        with app.app_context(): self.assertFalse((equipment_import.tax_documents.folder()/source['document_id']).exists())

    def test_shared_category_labels_export_as_safe_values(self):
        import csv,zipfile
        self.assertEqual(self.call(self.owner,'categories',dict(name='=SUM(1,2)')).status_code,200)
        self.expense(self.owner,category='=SUM(1,2)',work_percent=100,business_percent=0)
        self.assertEqual(self.call(self.owner,'categories/rename',dict(category='=SUM(1,2)',previous='=SUM(1,2)',name='Custom equipment'),'PUT').status_code,200)
        with app.app_context(): aid=one("SELECT id FROM users WHERE email='agent@example.test'")['id']
        self.assertEqual(self.call(self.owner,f'users/{aid}/sharing',dict(years=[2026],documents=[]),'PUT').status_code,200)
        exported=self.agent.get('/api/adviser/2026/export');self.assertEqual(exported.status_code,200)
        with zipfile.ZipFile(io.BytesIO(exported.data)) as z:
            labels=list(csv.reader(io.StringIO(z.read('registers/category_labels.csv').decode('utf-8-sig'))))
            self.assertEqual(labels[0],['category','label']);self.assertEqual(labels[1],["'=SUM(1,2)",'Custom equipment'])
            rows=list(csv.DictReader(io.StringIO(z.read('registers/expenses.csv').decode('utf-8-sig'))))
            self.assertEqual(rows[0]['category'],'Custom equipment');self.assertEqual(rows[0]['category_key'],"'=SUM(1,2)")

    def test_category_rename_retains_identity_and_prevents_collisions(self):
        eid=self.expense(self.owner,category='Equipment').json['id']
        r=self.call(self.owner,'categories/rename',dict(category='Equipment',previous='Equipment',name='Tools & devices'),'PUT')
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['labels']['Equipment'],'Tools & devices')
        self.assertEqual(self.owner.get('/api/session').json['category_labels']['Equipment'],'Tools & devices')
        self.assertEqual(self.owner.get('/api/expenses').json[0]['category'],'Equipment')
        self.assertEqual(self.call(self.owner,'categories',dict(name='TOOLS & DEVICES')).status_code,409)
        self.assertEqual(self.call(self.owner,'categories/rename',dict(category='Equipment',previous='Equipment',name='Other label'),'PUT').status_code,409)
        self.assertEqual(self.call(self.owner,'categories/rename',dict(category='Equipment',previous='Tools & devices',name='Meals'),'PUT').status_code,409)
        self.assertEqual(self.call(self.agent,'categories/rename',dict(category='Equipment',previous='Tools & devices',name='Bad'),'PUT').status_code,403)
        self.assertEqual(self.call(self.owner,'categories/rename',dict(category='Meals',previous='Meals',name='Overnight food'),'PUT').status_code,200)
        self.assertEqual(self.expense(self.owner,category='Meals').status_code,200)
