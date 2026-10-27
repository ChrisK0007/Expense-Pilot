import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from PIL import Image
import test_app as base
from app import app, db


class HomeOfficeTests(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense

    def diary(self, **changes):
        payload = dict(date='2026-10-08', start_time='09:00', end_time='17:00',
                       break_minutes=0, scope='work', activity='Client preparation',
                       timezone='Australia/Brisbane', client_ref=str(uuid.uuid4()))
        payload.update(changes)
        return self.call(self.owner, 'home-office/entries', payload), payload

    def annual(self, year=2026):
        response = self.owner.get(f'/api/home-office/{year}')
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def method(self, method='fixed', year=2026, **changes):
        payload = dict(version=self.annual(year)['settings']['version'], method=method,
                       eligible=True, hours_complete=True, costs_complete=True,
                       incurred_types=['phone','internet'])
        payload.update(changes)
        response = self.call(self.owner, f'home-office/{year}/settings', payload, 'PUT')
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def bill(self, kind='phone_internet', **changes):
        self._bill_number=getattr(self,'_bill_number',0)+1
        image = io.BytesIO(); Image.new('RGB', (10,10), (self._bill_number,42,90)).save(image, 'PNG'); image.seek(0)
        csrf = self.owner.get('/api/session').json['csrf']
        receipt = self.owner.post('/api/receipts', data={'file': (image,'bill.png')}, headers={'X-CSRF-Token':csrf})
        payload = dict(category='Phone & internet', amount='100', scope='split',
                       work_percent=60, business_percent=40, status='ready', receipt_id=receipt.json['id'])
        payload.update(changes)
        response = self.expense(self.owner, **payload)
        self.assertEqual(response.status_code, 200, response.json)
        eid = response.json['id']
        response = self.call(self.owner, f'home-office/costs/{eid}', dict(version=0,kind=kind,basis='Usage diary: 60% employment, 40% business.'), 'PUT')
        self.assertEqual(response.status_code, 200, response.json)
        return eid

    def test_diary_notes_are_optional_and_stay_empty(self):
        result,_=self.diary(activity='')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.owner.get('/api/home-office/2026').json['entries'][0]['activity'],'')

    def test_fixed_rate_replaces_covered_allocations_and_counts_each_scope_once(self):
        eid=self.bill()
        self.assertEqual(self.diary(start_time='07:00',end_time='17:00')[0].status_code,200)
        self.assertEqual(self.diary(date='2026-10-09',start_time='09:00',end_time='14:00',scope='business')[0].status_code,200)
        annual=self.method()
        self.assertTrue(annual['active']);self.assertEqual(annual['hourly'],dict(work=700,business=350))
        tax=self.owner.get('/api/tax/2026').json
        self.assertEqual(tax['recorded']['work_deductions_cents'],700)
        self.assertEqual(tax['recorded']['business_deductions_cents'],350)
        original=next(e for e in self.owner.get('/api/expenses').json if e['id']==eid)
        self.assertEqual(original['amount_cents'],10000)
        self.assertEqual((original['work_percent'],original['business_percent']),(60,40))

    def test_actual_cost_requests_are_rejected_and_disabled_claim_preserves_ordinary_expenses(self):
        self.bill();self.diary()
        response=self.call(self.owner,'home-office/2026/settings',dict(version=0,method='actual'),'PUT')
        self.assertEqual(response.status_code,400)
        self.method('none')
        tax=self.owner.get('/api/tax/2026').json
        self.assertEqual(tax['recorded']['work_deductions_cents'],6000)
        self.assertEqual(tax['recorded']['business_deductions_cents'],4000)
        self.assertEqual(tax['home_office']['hourly'],dict(work=0,business=0))

    def test_legacy_actual_cost_election_stays_pending_without_mutating_saved_records(self):
        self.bill();self.diary()
        legacy=dict(method='actual',eligible=True,hours_complete=True,costs_complete=True,
                    actual_complete=True,incurred_types=['phone','internet'],standard_other_cents=234)
        with app.app_context():
            uid=db().execute("SELECT id FROM users WHERE role='owner'").fetchone()[0]
            db().execute('INSERT INTO home_office_settings(user_id,year,data) VALUES (?,2026,?)',(uid,json.dumps(legacy)));db().commit()
        annual=self.annual()
        self.assertTrue(annual['settings']['needs_fixed_review']);self.assertFalse(annual['active'])
        self.assertNotIn('actual',annual);self.assertNotIn('standard_comparison',annual)
        tax=self.owner.get('/api/tax/2026').json
        self.assertEqual(tax['recorded']['work_deductions_cents'],0)
        with app.app_context():
            self.assertEqual(json.loads(db().execute('SELECT data FROM home_office_settings').fetchone()[0]),legacy)
        self.assertTrue(self.method()['active'])
        self.assertFalse(self.annual()['settings']['needs_fixed_review'])
        history=self.owner.get('/api/home-office/history').json
        self.assertEqual(json.loads(history[0]['before_json'])['method'],'actual')
        self.assertEqual(json.loads(history[0]['before_json'])['standard_other_cents'],234)

    def test_fixed_rate_evidence_needs_neither_allocations_nor_apportionment_notes(self):
        eid=self.bill(work_percent=0,business_percent=0);self.diary()
        response=self.call(self.owner,f'home-office/costs/{eid}',dict(version=1,kind='phone_internet',basis=''),'PUT')
        self.assertEqual(response.status_code,200)
        annual=self.method();self.assertTrue(annual['active'])
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['work_deductions_cents'],560)
        with app.app_context():
            # A retired actual-cost assessment on a covered bill cannot block hours.
            db().execute('UPDATE home_office_costs SET claim_base_cents=999999 WHERE expense_id=?',(eid,));db().commit()
        self.assertTrue(self.annual()['active'])

    def test_new_bill_evidence_is_atomic_idempotent_and_not_a_separate_deduction(self):
        image=io.BytesIO();Image.new('RGB',(8,8),'orange').save(image,'PNG');image.seek(0)
        receipt=self.owner.post('/api/receipts',data={'file':(image,'power.png')},headers={'X-CSRF-Token':self.owner.get('/api/session').json['csrf']}).json['id']
        data=dict(date='2026-10-08',merchant='Power supplier',amount='100',kind='electricity',receipt_id=receipt,
                  client_ref=str(uuid.uuid4()),personally_paid=True)
        bad=self.call(self.owner,'home-office/bills',dict(data,personally_paid=False))
        self.assertEqual(bad.status_code,400)
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        response=self.call(self.owner,'home-office/bills',data)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.call(self.owner,'home-office/bills',data).json['id'],response.json['id'])
        self.assertEqual(self.call(self.owner,'home-office/bills',dict(data,amount='200')).status_code,409)
        self.assertEqual(self.call(self.agent,'home-office/bills',data).status_code,403)
        records=self.owner.get('/api/expenses').json;self.assertEqual(len(records),1)
        self.assertEqual((records[0]['work_percent'],records[0]['business_percent']),(0,0))
        self.diary();self.assertTrue(self.method(incurred_types=['electricity'])['active'])
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['work_deductions_cents'],560)

    def test_incomplete_evidence_holds_claim_pending_until_explicit_completion(self):
        self.bill();self.diary()
        annual=self.method(costs_complete=False)
        self.assertEqual(annual['status'],'needs_review')
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['work_deductions_cents'],0)
        self.assertTrue(self.method()['active'])

    def test_reimbursed_bills_are_neither_deductions_nor_fixed_rate_evidence(self):
        self.bill(reimbursed=True);self.diary()
        annual=self.method()
        self.assertFalse(annual['active'])
        self.assertEqual(annual['extras'],dict(work=0,business=0))
        self.assertTrue(any('Attach a bill' in issue for issue in annual['fixed_issues']))

    def test_equipment_uses_assessed_amount_and_changed_bill_requires_review(self):
        self.bill();self.diary()
        eid=self.bill(kind='asset',category='Equipment',amount='1200')
        annual=self.method();self.assertEqual(annual['extras'],dict(work=0,business=0))
        response=self.call(self.owner,f'home-office/costs/{eid}',dict(version=1,kind='asset',claim_base='300',basis='Assessed annual depreciation and usage diary.',reviewed=True),'PUT')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.annual()['extras'],dict(work=18000,business=12000))
        with app.app_context():
            db().execute('UPDATE expenses SET amount_cents=10000 WHERE id=?',(eid,));db().commit()
        annual=self.annual();self.assertFalse(annual['active'])
        self.assertEqual(annual['extras'],dict(work=0,business=0))
        self.assertTrue(any('original bill changed' in issue for issue in annual['fixed_issues']))

    def test_diary_idempotency_overlap_and_stale_edits(self):
        response,payload=self.diary();self.assertEqual(response.status_code,200,response.json)
        eid=response.json['id']
        retry=self.call(self.owner,'home-office/entries',payload)
        self.assertEqual(retry.json['id'],eid)
        self.assertEqual(self.diary(scope='business',start_time='16:00',end_time='18:00')[0].status_code,409)
        self.assertEqual(self.call(self.owner,f'home-office/entries/{eid}',dict(payload,version=1,break_minutes=30),'PUT').status_code,200)
        self.assertEqual(self.call(self.owner,f'home-office/entries/{eid}',dict(payload,version=1),'PUT').status_code,409)
        self.assertEqual(self.call(self.owner,f'home-office/entries/{eid}',dict(version=2),'DELETE').status_code,200)
        self.assertEqual(self.call(self.owner,'home-office/entries',payload).status_code,409)
        self.assertEqual(self.annual()['entries'],[])
        self.assertEqual(len(self.owner.get('/api/home-office/history').json),3)

    def test_dst_ambiguity_and_nonexistent_times_are_explicit(self):
        response,_=self.diary(date='2026-10-04',timezone='Australia/Sydney',start_time='02:15',end_time='04:00')
        self.assertEqual(response.status_code,400)
        response,_=self.diary(date='2026-04-05',timezone='Australia/Sydney',start_time='02:00',end_time='03:00')
        self.assertEqual(response.status_code,400)
        response,_=self.diary(date='2026-04-05',timezone='Australia/Sydney',start_time='02:00',end_time='03:00',start_occurrence='first')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.annual(2025)['minutes']['work'],120)

    def test_year_boundaries_and_historical_rates(self):
        self.diary(date='2024-06-30',start_time='23:00',end_time='24:00')
        self.diary(date='2024-07-01',start_time='00:00',end_time='01:00')
        self.assertEqual(self.annual(2023)['hourly']['work'],67)
        self.assertEqual(self.annual(2024)['hourly']['work'],70)
        self.assertIsNone(self.annual(2027)['rate_cents'])
        self.assertEqual(self.diary(date='2099-10-08')[0].status_code,400)

    def test_allowances_add_income_once_and_salary_override_replaces_recorded_total(self):
        self.call(self.owner,'employment',dict(date='2026-10-08',employer='Test employer',gross='1000',withheld='200'))
        for included in (True,False):
            response=self.call(self.owner,'home-office/allowances',dict(date='2026-10-08',employer='Test employer',amount='50',included_in_pay=included))
            self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['salary_cents'],105000)
        response=self.call(self.owner,'tax/2026',dict(annual_salary='160000'),'PUT')
        self.assertEqual(response.json['forecast']['salary_cents'],16000000)
        self.assertEqual(response.json['recorded']['salary_cents'],105000)

    def test_authorization_and_csv_formula_escape(self):
        self.assertEqual(app.test_client().get('/api/home-office/2026').status_code,401)
        self.assertEqual(self.agent.get('/api/home-office/2026').status_code,200)
        self.assertEqual(self.call(self.agent,'home-office/2026/settings',{},'PUT').status_code,403)
        self.assertEqual(self.owner.post('/api/home-office/entries',json={}).status_code,403)
        self.diary(activity='=HYPERLINK("example")')
        export=self.agent.get('/api/home-office/2026/export')
        self.assertEqual(export.status_code,200)
        records=list(csv.reader(io.StringIO(export.data.decode('utf-8-sig'))))
        self.assertTrue(any("'=HYPERLINK" in cell for row in records for cell in row))

    def test_detected_phone_category_needs_confirmed_evidence_and_unlink_preserves_bill(self):
        eid=self.bill();self.diary()
        self.assertTrue(self.method()['active'])
        response=self.call(self.owner,f'home-office/costs/{eid}',dict(version=1),'DELETE')
        self.assertEqual(response.status_code,200,response.json)
        annual=self.annual()
        self.assertFalse(annual['active'])
        self.assertFalse(annual['costs'][0]['classification_confirmed'])
        self.assertEqual(annual['costs'][0]['home_office_kind'],'phone_internet')
        self.assertEqual(annual['costs'][0]['amount_cents'],10000)
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['work_deductions_cents'],0)
        self.assertEqual(self.call(self.owner,f'home-office/costs/{eid}',dict(version=1),'DELETE').status_code,409)

    def test_backup_restore_preserves_home_office_records_and_attached_evidence(self):
        from restore_backup import restore
        self.bill();self.diary();self.method()
        self.call(self.owner,'home-office/allowances',dict(date='2026-10-08',employer='Test employer',amount='50',included_in_pay=True))
        tables=('home_office_entries','home_office_settings','home_office_costs','home_office_allowances','home_office_history')
        with app.app_context():
            before={t:[tuple(r) for r in db().execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in tables}
            receipt_paths=[r['id'] for r in db().execute('SELECT id FROM receipts')]
        response=self.call(self.owner,'data/backup',{'password':'Owner-password-123'})
        self.assertEqual(response.status_code,200,response.json)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'backup.zip';archive.write_bytes(response.data)
            target=root/'restore';target.mkdir();restore(archive,target)
            with sqlite3.connect(target/'rounded.sqlite') as connection:
                for table in tables:
                    self.assertEqual(connection.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall(),before[table])
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
                self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(),[])
            for path in receipt_paths:
                self.assertTrue((target/'receipts'/Path(path).name).is_file())
