"""Simple write-offs and receipt links preserve tax balances and evidence boundaries."""
import io
import json
import sqlite3
import unittest
from PIL import Image
import test_app
import test_beta14
import test_beta13
from app import app, db, one


class Beta15Test(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    call=test_app.AppTest.call
    login=test_app.AppTest.login
    expense=test_app.AppTest.expense
    imported=test_beta14.Beta14Test.imported
    commit=test_beta14.Beta14Test.commit
    profile=test_beta14.Beta14Test.profile
    inputs=test_beta14.Beta14Test.inputs
    suggest=test_beta14.Beta14Test.suggest
    treatment=test_beta14.Beta14Test.treatment
    aid=test_beta13.Beta13Test.aid
    share=test_beta13.Beta13Test.share

    def asset(self, **kw):
        d=dict(name='Tablet',acquired='2025-10-22',cost=1799,work_percent=0,business_percent=100,confirm_capital=True)
        d.update(kw)
        r=self.call(self.owner,'workflows/equipment',d)
        self.assertEqual(r.status_code,200,r.json)
        return r.json['id']

    def view(self, aid, year=2025):
        return next(a for a in self.owner.get('/api/workflows/equipment?year='+str(year)).json['assets'] if a['id']==aid)

    def receipt(self, colour='white'):
        raw=io.BytesIO();Image.new('RGB',(12,12),colour).save(raw,'PNG');raw.seek(0)
        r=self.owner.post('/api/receipts',data={'file':(raw,'purchase.png')},headers={'X-CSRF-Token':self.owner.get('/api/session').json['csrf']})
        self.assertEqual(r.status_code,200,r.json)
        return r.json['id']

    def link(self, aid, **kw):
        return self.call(self.owner,f'workflows/equipment/{aid}/evidence',dict(version=self.view(aid)['version'],**kw),'PUT')

    def test_import_one_choice_fills_writeoff_without_guessing_older_balance(self):
        row=dict(name='Tablet',acquired='2025-10-22',cost='1799',opening='',decline='',closing='',method='manual',rate='',work_percent='0',business_percent='100')
        source=self.imported([row]);r=self.commit(source,[dict(row,fully_claimed=True)])
        self.assertEqual(r.status_code,200,r.json);a=self.view(r.json['asset_ids'][0])
        self.assertEqual((a['opening_cents'],a['current']['amount_cents'],a['closing_cents']),(179900,179900,0))
        self.assertEqual(self.view(a['id'],2026)['closing_cents'],0)
        self.assertEqual(self.owner.get('/api/tax/2026').json['forecast']['business_deductions_cents'],0)
        old=dict(row,name='Older tablet',acquired='2023-10-22');source=self.imported([old])
        self.assertEqual(self.commit(source,[dict(old,fully_claimed=True)]).status_code,400)
        r=self.commit(source,[dict(old,opening=200,fully_claimed=True)]);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.view(r.json['asset_ids'][0])['current']['amount_cents'],20000)

    def test_record_completed_claim_keeps_original_cost_and_no_future_deduction(self):
        aid=self.asset(recorded_writeoff=dict(year=2025))
        a=self.view(aid);self.assertEqual(a['current']['amount_cents'],179900);self.assertEqual(a['closing_cents'],0)
        self.assertEqual(self.owner.get('/api/tax/2025').json['recorded']['business_deductions_cents'],179900)
        self.assertTrue(self.view(aid,2024)['history_unavailable'])
        self.assertEqual(self.owner.get('/api/tax/2026').json['forecast']['business_deductions_cents'],0)
        self.share([2025]);self.assertEqual(self.agent.get('/api/adviser/2025').status_code,200)

    def test_register_uses_same_suggestion_and_stale_profile_checks_as_expense(self):
        self.profile('simplified');d=self.inputs();tax=self.treatment(d)
        aid=self.asset(name=d['name'],acquired=d['date'],cost=d['amount'],work_percent=50,business_percent=25,tax_treatment=tax)
        self.assertEqual(self.view(aid,2026)['current']['amount_cents'],50000)
        self.profile('general')
        r=self.call(self.owner,'workflows/equipment',dict(name='Changed',acquired=d['date'],cost=500,work_percent=50,business_percent=25,confirm_capital=True,tax_treatment=tax))
        self.assertEqual(r.status_code,409)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM equipment_assets')['n'],1)

    def test_attach_unfiled_original_keeps_amounts_and_removes_inbox_alert(self):
        aid=self.asset(recorded_writeoff=dict(year=2025));rid=self.receipt();before=self.view(aid)
        with app.app_context():
            db().execute("UPDATE receipt_details SET scan_status='failed',scan_error='Old read error' WHERE receipt_id=?",(rid,));db().commit()
        r=self.link(aid,receipt_id=rid);self.assertEqual(r.status_code,200,r.json)
        after=self.view(aid)
        for k in ('cost_cents','current','history','calculation','imported'): self.assertEqual(before[k],after[k])
        self.assertEqual(after['receipt_id'],rid);self.assertIsNone(after['expense_id'])
        self.assertNotIn(rid,[r['id'] for r in self.owner.get('/api/receipts?unfiled=1').json])
        self.assertNotIn(rid,[r['id'] for r in self.owner.get('/api/workflows/attention/2025').json['items']])
        self.assertEqual(self.call(self.owner,f'receipts/{rid}',{},'DELETE').status_code,409)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',dict(date='2025-10-22',amount=1799,merchant='Store',scope='business',category='Equipment',work_percent=0,business_percent=100)).status_code,409)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/extract',dict(unfiled_only=True)).status_code,409)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM expenses')['n'],0)

    def test_link_filed_purchase_excludes_ordinary_claim_atomically(self):
        aid=self.asset(recorded_writeoff=dict(year=2025));rid=self.receipt()
        eid=self.expense(self.owner,date='2025-10-22',amount=1799,category='Equipment',work_percent=0,business_percent=100,receipt_id=rid,status='ready').json['id']
        r=self.link(aid,receipt_id=rid);self.assertEqual(r.status_code,200,r.json)
        a=self.view(aid);self.assertEqual(a['expense_id'],eid);self.assertEqual(a['receipt_id'],rid)
        self.assertEqual(self.owner.get('/api/tax/2025').json['recorded']['business_deductions_cents'],179900)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM expenses')['n'],1)

    def test_later_purchase_link_moves_evidence_and_unlink_keeps_purchase_excluded(self):
        aid=self.asset(recorded_writeoff=dict(year=2025));rid=self.receipt();self.assertEqual(self.link(aid,receipt_id=rid).status_code,200)
        eid=self.expense(self.owner,date='2025-10-22',amount=1799,category='Equipment',work_percent=0,business_percent=100,status='ready').json['id']
        self.assertEqual(self.link(aid,expense_id=eid).status_code,200)
        a=self.view(aid);self.assertIsNone(a['evidence_receipt_id']);self.assertEqual(a['receipt_id'],rid)
        with app.app_context(): self.assertEqual(one('SELECT receipt_id FROM expenses WHERE id=?',(eid,))['receipt_id'],rid)
        r=self.call(self.owner,f'workflows/equipment/{aid}/evidence',dict(version=a['version']),'DELETE');self.assertEqual(r.status_code,200)
        self.assertEqual(self.view(aid)['expense_id'],eid);self.assertIsNone(self.view(aid)['receipt_id'])
        self.assertIn(rid,[r['id'] for r in self.owner.get('/api/receipts?unfiled=1').json])
        self.assertEqual(self.owner.get('/api/tax/2025').json['recorded']['business_deductions_cents'],179900)

    def test_mismatched_purchase_conflict_and_stale_link_do_not_mutate(self):
        aid=self.asset();rid=self.receipt();other=self.receipt('blue')
        eid=self.expense(self.owner,date='2025-10-22',amount=1800,category='Equipment',work_percent=0,business_percent=100,receipt_id=rid).json['id']
        self.assertEqual(self.link(aid,receipt_id=rid).status_code,409)
        self.assertIsNone(self.view(aid)['expense_id']);self.assertIsNone(self.view(aid)['receipt_id'])
        version=self.view(aid)['version'];self.assertEqual(self.link(aid,receipt_id=other).status_code,200)
        self.assertEqual(self.call(self.owner,f'workflows/equipment/{aid}/evidence',dict(version=version,receipt_id=rid),'PUT').status_code,409)
        self.assertEqual(self.view(aid)['receipt_id'],other)
        with app.app_context(): self.assertEqual(one('SELECT receipt_id FROM expenses WHERE id=?',(eid,))['receipt_id'],rid)

    def test_receipt_cannot_be_shared_between_assets_or_foreign_owner(self):
        aid=self.asset();another=self.asset(name='Other');rid=self.receipt()
        self.assertEqual(self.link(aid,receipt_id=rid).status_code,200)
        self.assertEqual(self.link(another,receipt_id=rid).status_code,409)
        foreign=self.receipt('red')
        with app.app_context():
            uid=one("SELECT id FROM users WHERE email='agent@example.test'")['id'];db().execute('UPDATE receipts SET user_id=? WHERE id=?',(uid,foreign));db().commit()
        self.assertEqual(self.link(another,receipt_id=foreign).status_code,404)
        self.assertNotIn(foreign,[r['id'] for r in self.owner.get(f'/api/workflows/equipment/{another}/evidence').json['receipts']])
        for client in (self.agent,app.test_client()):
            self.assertIn(client.get(f'/api/workflows/equipment/{aid}/evidence').status_code,(401,403))

    def test_linked_original_visible_only_in_shared_tax_years_and_export(self):
        aid=self.asset(recorded_writeoff=dict(year=2025));rid=self.receipt();self.assertEqual(self.link(aid,receipt_id=rid).status_code,200)
        self.share([2025]);data=self.agent.get('/api/adviser/2025').json['records'];self.assertIn(rid,[r['id'] for r in data['originals']])
        response=self.agent.get(f'/api/adviser/2025/source/receipt/{rid}');self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.agent.get(f'/api/adviser/2024/source/receipt/{rid}').status_code,403)
        self.share([]);self.assertEqual(self.agent.get(f'/api/adviser/2025/source/receipt/{rid}').status_code,403)
        with app.app_context():
            # DB-level protection also covers alternate API entry points.
            with self.assertRaises(sqlite3.IntegrityError):
                db().execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,receipt_id) VALUES (?, '2025-10-22','Duplicate',179900,'business','Equipment',?)",(one("SELECT id FROM users WHERE role='owner'")['id'],rid))
            db().rollback()
