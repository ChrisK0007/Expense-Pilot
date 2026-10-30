"""A point-in-time annual handover, with evidence and an explicit manifest."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from flask import send_file
from workflow_core import fiscal, now


def csv_bytes(records):
    stream=io.StringIO();writer=csv.writer(stream)
    keys=list(dict.fromkeys(k for r in records for k in r))
    if keys: writer.writerow(keys)
    def safe(value):
        if isinstance(value,(dict,list)): value=json.dumps(value,ensure_ascii=False)
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')): return "'"+value
        return value
    writer.writerows([safe(r.get(k,'')) for k in keys] for r in records)
    return stream.getvalue().encode('utf-8-sig')


def report(year,data,outstanding,owner):
    from record_reports import Report, aud
    from expense_core import allocations
    r=Report('Annual handover',f'1 July {year} – 30 June {year+1}');r.cover(owner)
    r.add('A snapshot of your records and supporting evidence. Review outstanding items and confirm the tax treatment with your adviser before lodging.')
    r.add('Records included','heading')
    r.table(['Register','Records'],[[name.replace('_',' ').capitalize(),len(records)] for name,records in data.items()],[140,34])
    r.add('Recorded amounts','heading')
    parts=[allocations(e) for e in data['expenses']]
    r.table(['Measure','AUD'],[['Expense payments, including personal spending and refunds',aud(sum(e['amount_cents'] for e in data['expenses']))],
                             ['Employment expense allocations (before tax treatment)',aud(sum(p[0] for p in parts))],
                             ['Business expense allocations (before tax treatment)',aud(sum(p[1] for p in parts))],
                             ['Employment gross recorded',aud(sum(e['gross_cents'] for e in data['employment']))],
                             ['PAYG withholding recorded',aud(sum(e['withheld_cents'] for e in data['employment']))]],[132,42])
    r.add('Equipment purchases remain in spending. Confirmed depreciation is recorded separately; see equipment and depreciation CSVs. Payslip YTD and annual comparison figures are reference data, not additional income.')
    r.add('Outstanding review','heading')
    if outstanding:
        for item in outstanding[:200]: r.add(f"{item['kind']} #{item['id']} — {item['title']}: {item['detail']}")
        if len(outstanding)>200: r.add('More items are included in outstanding_items.csv.')
    else: r.add('No outstanding items were found in the server review queue at export time.')
    r.add('Adviser questions','heading')
    for q in data['questions']:
        r.add(f"{q['record_type']} #{q['record_id']} — {'Resolved' if q['resolved'] else 'Open'}")
        r.add(q['question']);r.add('Response: '+(q['answer'] or 'Awaiting response'))
    r.add('Evidence and integrity','heading')
    r.add('The ZIP includes the selected year’s linked receipt originals and supporting documents, CSV registers, source checksums and a JSON manifest. Documents without a financial year and unfiled inbox originals are included for adviser review. Passwords, session keys and email credentials are excluded.')
    return r.build()


def build(year):
    from app import DATA, VERSION, db, rows, one, record_user_id, fail
    import review_hub
    year,start,end=fiscal(year);uid=record_user_id();output=tempfile.SpooledTemporaryFile(max_size=16*1024*1024,mode='w+b',dir=DATA)
    try:
        with tempfile.TemporaryDirectory(prefix='.handover-',dir=DATA) as staging:
            db().execute('BEGIN IMMEDIATE')
            try:
                owner=one('SELECT name FROM users WHERE id=?',(uid,))['name']
                data=dict(expenses=rows('SELECT * FROM expenses WHERE date BETWEEN ? AND ? ORDER BY date,id',(start,end)),
                          employment=rows('SELECT e.*,d.net_cents,d.ytd_gross_cents,d.ytd_withheld_cents FROM employment_income e LEFT JOIN income_details d ON d.income_id=e.id WHERE e.date BETWEEN ? AND ? ORDER BY e.date,e.id',(start,end)),
                          invoices=rows('SELECT * FROM billing_documents WHERE issue_date BETWEEN ? AND ? OR id IN (SELECT document_id FROM billing_payments WHERE date BETWEEN ? AND ?)',(start,end,start,end)),
                          invoice_payments=rows('SELECT * FROM billing_payments WHERE date BETWEEN ? AND ?',(start,end)),
                          bank_transactions=rows('SELECT * FROM bank_transactions WHERE date BETWEEN ? AND ?',(start,end)),
                          mileage=rows('SELECT j.*,v.name AS vehicle,v.registration FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id WHERE j.date BETWEEN ? AND ? ORDER BY j.date,j.id',(start,end)),
                          home_office=rows('SELECT * FROM home_office_entries WHERE user_id=? AND date BETWEEN ? AND ? AND deleted=0 ORDER BY date,start_at',(uid,start,end)),
                          home_office_settings=rows('SELECT * FROM home_office_settings WHERE user_id=? AND year=?',(uid,year)),
                          equipment=rows('SELECT * FROM equipment_assets WHERE user_id=? AND acquired<=?',(uid,end)),
                          depreciation=rows('SELECT d.* FROM equipment_depreciation d JOIN equipment_assets a ON a.id=d.asset_id WHERE a.user_id=? AND d.year<=?',(uid,year)),
                          questions=rows('SELECT q.*,u.name AS author FROM record_questions q LEFT JOIN users u ON u.id=q.author_id WHERE q.user_id=? ORDER BY q.id',(uid,)),
                          annual_income_comparisons=rows('SELECT * FROM annual_income_checks WHERE user_id=? AND year=?',(uid,year)),
                          tax_settings=rows('SELECT * FROM tax_settings WHERE year=?',(year,)))
                data['receipt_items']=[dict(expense_id=e['id'],item_number=index+1,**line) for e in data['expenses'] for index,line in enumerate(json.loads(e['items_json']))]
                data['reconciliations']=rows('SELECT r.* FROM bank_reconciliations r JOIN bank_transactions b ON b.id=r.bank_id WHERE b.date BETWEEN ? AND ?',(start,end))
                data['home_office_costs']=rows('SELECT h.* FROM home_office_costs h JOIN expenses e ON e.id=h.expense_id WHERE e.date BETWEEN ? AND ?',(start,end))
                data['home_office_allowances']=rows('SELECT * FROM home_office_allowances WHERE user_id=? AND date BETWEEN ? AND ?',(uid,start,end))
                receipt_ids={r['receipt_id'] for r in data['expenses']+data['employment'] if r['receipt_id']}
                data['supporting_documents']=rows('SELECT * FROM tax_documents WHERE user_id=? AND (year=? OR year IS NULL)',(uid,year))
                # Include older equipment evidence still relevant to the annual register.
                for asset in data['equipment']:
                    if asset['expense_id']:
                        receipt=one('SELECT receipt_id FROM expenses WHERE id=?',(asset['expense_id'],))
                        if receipt and receipt['receipt_id']: receipt_ids.add(receipt['receipt_id'])
                receipt_ids.update(r['id'] for r in rows('SELECT r.id FROM receipts r WHERE r.user_id=? AND NOT EXISTS(SELECT 1 FROM expenses e WHERE e.receipt_id=r.id) AND NOT EXISTS(SELECT 1 FROM employment_income e WHERE e.receipt_id=r.id)',(uid,)))
                receipts=[one('SELECT * FROM receipts WHERE id=?',(rid,)) for rid in sorted(receipt_ids)]
                data['receipt_originals']=receipts
                outstanding=review_hub.attention(year)
                originals=[];total=0
                for group,records in [('receipts',receipts),('documents',data['supporting_documents'])]:
                    for record in records:
                        rid=record['id']
                        if not re.fullmatch(r'[0-9a-f]{40}',rid): fail('Invalid original identifier. Review the evidence before exporting.',409)
                        source=DATA/group/rid
                        if not source.is_file(): fail('A saved original is missing. Restore the evidence before exporting this handover.',409)
                        total+=source.stat().st_size
                        if total>1024**3: fail('This handover exceeds 1 GB of originals. Export smaller document groups separately.',413)
                        target=Path(staging)/(group+'-'+rid)
                        try: os.link(source,target)
                        except OSError: shutil.copyfile(source,target)
                        name=re.sub(r'[^A-Za-z0-9._-]','_',record['filename'])[:120]
                        originals.append((f'originals/{group}/{rid}-{name}',target,record))
                db().commit()
            except Exception:
                db().rollback();raise
            checks={}
            with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                def add(name,content):
                    archive.writestr(name,content);checks[name]=hashlib.sha256(content).hexdigest()
                add('annual-handover.pdf',report(year,data,outstanding,owner))
                for name,records in data.items(): add('registers/'+name+'.csv',csv_bytes(records))
                add('outstanding_items.csv',csv_bytes(outstanding))
                for name,path,record in originals:
                    digest=hashlib.sha256()
                    with path.open('rb') as inp,archive.open(name,'w') as out:
                        for chunk in iter(lambda:inp.read(1024*1024),b''): digest.update(chunk);out.write(chunk)
                    if record.get('sha256') and record['sha256']!=digest.hexdigest(): fail('An original does not match its saved checksum. Handover stopped.',409)
                    checks[name]=digest.hexdigest()
                archive.writestr('manifest.json',json.dumps(dict(product='Expense Pilot',version=VERSION,year=year,created_at=now(),sha256=checks),indent=2))
        output.seek(0);return output
    except Exception:
        output.close();raise


def register(app,auth):
    @app.get('/api/workflows/handover/<int:year>', endpoint='annual_handover_download')
    @auth('owner','tax_agent')
    def download(year):
        stream=build(year)
        response=send_file(stream,mimetype='application/zip',as_attachment=True,download_name=f'expense-pilot-handover-{year}-{year+1}.zip')
        response.call_on_close(stream.close);return response
