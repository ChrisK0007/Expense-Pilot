import io
import json
import unittest
from unittest.mock import patch
from reportlab.pdfgen import canvas
import test_app as base
from app import app, db, DATA
from home_office_import import parse_pdf, parse_csv


def report_text():
    return '''WFH Logbook Australia
WFH logbook for financial year 2027
Year total : 3h ($2.10)
WFH hours log
Date         WFH     Started   Ended   Breaks    Logged       Updated
2026-07-02   2h      09:00     11:30   30m       2026-07-02   2026-07-03
                                                12:00        08:00
\f
2026-07-03       1h     09:00    10:00       2026-07-03
                                          10:05
WFH notes log
Date         Workday notes                     Logged       Updated
2026-07-02   - Client research                 2026-07-02   2026-07-03
             and preparation                   12:00        08:00
'''


def report_pdf():
    output=io.BytesIO();c=canvas.Canvas(output)
    for page in report_text().split('\f'):
        text=c.beginText(25,800);text.setFont('Courier',8)
        for line in page.splitlines(): text.textLine(line)
        c.drawText(text);c.showPage()
    c.save();return output.getvalue()


CSV=b'Date,Start,End,Break minutes,Scope,Activity,Timezone,Created UTC,Updated UTC\n2026-07-02,09:00,11:00,0,work,Client research,Australia/Brisbane,2026-07-02 11:05:00,2026-07-02 11:05:00\n2026-07-03,09:00,10:00,0,business,Bookkeeping,Australia/Brisbane,,\n'


class ImportTests(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login

    def upload(self, endpoint='preview', raw=CSV, filename='diary.csv', entries=None, client=None, **changes):
        client=client or self.owner
        data=dict(file=(io.BytesIO(raw),filename),timezone='Australia/Brisbane')
        if entries is not None: data.update(entries=json.dumps(entries),confirmed='true')
        data.update(changes)
        return client.post('/api/home-office/import'+('/preview' if endpoint=='preview' else ''),data=data,
                           headers={'X-CSRF-Token':client.get('/api/session').json['csrf']})

    def annual(self): return self.owner.get('/api/home-office/2026').json

    def test_pdf_parser_preserves_missing_notes_breaks_and_source_timestamps(self):
        parsed=parse_pdf(report_text());rows=parsed['entries']
        self.assertEqual(parsed['reported_minutes'],180);self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['break_minutes'],30)
        self.assertEqual(rows[0]['activity'],'- Client research\nand preparation')
        self.assertEqual(rows[0]['source_logged'],'2026-07-02 12:00')
        self.assertEqual(rows[0]['source_updated'],'2026-07-03 08:00')
        self.assertEqual(rows[1]['activity'],'');self.assertEqual(rows[1]['scope'],'')
        for text in (report_text().replace('3h ($','4h ($'),report_text().replace('WFH Logbook Australia','Unknown'),report_text().replace('2026-07-03       1h','2026-07-03       unknown')):
            with self.assertRaises(ValueError): parse_pdf(text)

    def test_actual_pdf_preview_is_read_only_and_requires_review_and_missing_details(self):
        raw=report_pdf();before=set((DATA/'documents').glob('*'))
        preview=self.upload(raw=raw,filename='hours.pdf');self.assertEqual(preview.status_code,200,preview.json)
        entries=preview.json['entries'];self.assertEqual(len(entries),2);self.assertEqual(sum(e['minutes'] for e in entries),180)
        self.assertEqual(self.annual()['entries'],[]);self.assertEqual(before,set((DATA/'documents').glob('*')))
        self.assertEqual(self.upload('save',raw=raw,filename='hours.pdf',entries=entries,confirmed='false').status_code,400)
        self.assertEqual(self.upload('save',raw=raw,filename='hours.pdf',entries=entries).status_code,400)
        for e in entries: e['scope']='work'
        saved=self.upload('save',raw=raw,filename='hours.pdf',entries=entries)
        self.assertEqual(saved.status_code,200,saved.json);self.assertEqual(saved.json['imported'],2)
        did=saved.json['document_id'];self.assertEqual((DATA/'documents'/did).read_bytes(),raw)
        self.assertEqual(self.annual()['settings']['method'],'none')
        entry=next(e for e in self.annual()['entries'] if e['date']=='2026-07-02')
        source=entry['import_source'];self.assertEqual(source['original']['source_logged'],'2026-07-02 12:00')
        self.assertEqual(source['document_id'],did);self.assertNotEqual(entry['created_at'],'2026-07-02 12:00:00')
        pdf=self.owner.get('/api/home-office/2026/report.pdf')
        from pypdf import PdfReader
        self.assertIn('Imported source records','\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.data)).pages))

    def test_csv_import_retry_and_edited_deleted_sessions_are_not_duplicated(self):
        entries=self.upload().json['entries'];saved=self.upload('save',entries=entries)
        self.assertEqual(saved.status_code,200,saved.json);self.assertEqual(saved.json['imported'],2)
        self.assertEqual(self.annual()['minutes'],dict(work=120,business=60))
        retry=self.upload('save',entries=entries).json
        self.assertEqual(retry['imported'],0);self.assertEqual(len(retry['skipped']),2)
        first=next(e for e in self.annual()['entries'] if e['date']=='2026-07-02')
        change={**entries[0],'activity':'Edited work description','version':first['version']}
        self.assertEqual(self.call(self.owner,'home-office/entries/'+str(first['id']),change,'PUT').status_code,200)
        self.assertEqual(self.upload('save',entries=entries).json['imported'],0)
        self.assertEqual(self.call(self.owner,'home-office/entries/'+str(first['id']),dict(version=2),'DELETE').status_code,200)
        preview=self.upload().json;self.assertEqual(preview['entries'][0]['status'],'removed')
        self.assertEqual(self.upload('save',entries=entries).json['imported'],0)
        self.assertEqual(len(self.annual()['entries']),1)
        self.assertEqual(len(self.owner.get('/api/documents').json['documents']),1)

    def test_overlapping_batch_rolls_back_every_record_and_file(self):
        entries=self.upload().json['entries'];entries[1].update(date=entries[0]['date'],start_time='10:00',end_time='12:00')
        before=set((DATA/'documents').glob('*'));response=self.upload('save',entries=entries)
        self.assertEqual(response.status_code,409,response.json);self.assertEqual(self.annual()['entries'],[])
        self.assertEqual(before,set((DATA/'documents').glob('*')))
        self.assertEqual(self.owner.get('/api/documents').json['documents'],[])

    def test_existing_session_conflicts_are_flagged_and_identical_different_file_skipped(self):
        entries=self.upload().json['entries'];self.assertEqual(self.upload('save',entries=entries[:1]).status_code,200)
        duplicate=CSV.replace(b'Client research',b'Different description')
        preview=self.upload(raw=duplicate).json;self.assertEqual(preview['entries'][0]['status'],'duplicate')
        response=self.upload('save',raw=duplicate,entries=preview['entries'])
        self.assertEqual(response.json['imported'],1);self.assertEqual(len(response.json['skipped']),1)
        overlap=CSV.replace(b'09:00,11:00',b'10:00,12:00');preview=self.upload(raw=overlap).json
        self.assertEqual(preview['entries'][0]['status'],'overlap')
        self.assertEqual(self.upload('save',raw=overlap,entries=preview['entries']).status_code,409)

    def test_csv_round_trip_keeps_literal_formula_prefix_and_stops_before_other_sections(self):
        entries=self.upload().json['entries'];entries[0]['activity']='=research, not a formula'
        self.assertEqual(self.upload('save',entries=entries).status_code,200)
        raw=self.owner.get('/api/home-office/2026/export').data
        parsed=parse_csv(raw);self.assertEqual(len(parsed['entries']),2)
        self.assertIn('=research, not a formula',[e['activity'] for e in parsed['entries']])
        self.assertEqual(self.upload(raw=raw).status_code,200)

    def test_import_permissions_csrf_input_validation_and_atomic_cleanup(self):
        self.assertEqual(self.upload(client=self.agent).status_code,403)
        self.assertEqual(self.owner.post('/api/home-office/import/preview').status_code,403)
        anonymous=app.test_client();self.assertEqual(self.call(anonymous,'home-office/import/preview',{}).status_code,401)
        self.assertEqual(self.upload(raw=b'Unknown,format\n1,2\n').status_code,422)
        self.assertEqual(self.upload(raw=b'%PDF-broken',filename='broken.pdf').status_code,422)
        entries=self.upload().json['entries'];before=set((DATA/'documents').glob('*'))
        with patch('home_office.history',side_effect=RuntimeError('injected write failure')):
            with self.assertRaisesRegex(RuntimeError,'injected'): self.upload('save',entries=entries)
        self.assertEqual(self.annual()['entries'],[]);self.assertEqual(before,set((DATA/'documents').glob('*')))
        invalid=[{**entries[0],'index':True}]
        self.assertEqual(self.upload('save',entries=invalid).status_code,400)
        entries[0]['activity']='';self.assertEqual(self.upload('save',entries=entries).status_code,200)
        self.assertIn('',[e['activity'] for e in self.annual()['entries']])

    def test_same_file_overlaps_are_visible_during_review(self):
        raw=CSV.replace(b'2026-07-03,09:00,10:00',b'2026-07-02,10:00,12:00')
        preview=self.upload(raw=raw);self.assertEqual(preview.status_code,200,preview.json)
        self.assertEqual(preview.json['entries'][1]['status'],'overlap')
