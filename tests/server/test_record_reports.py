import io
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfReader
import test_app as base
from app import app, db
import test_home_office as wfh
from record_reports import mileage_totals


class RecordReportTests(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense
    diary = wfh.HomeOfficeTests.diary
    annual = wfh.HomeOfficeTests.annual
    bill = wfh.HomeOfficeTests.bill
    method = wfh.HomeOfficeTests.method

    def pdf_text(self, response):
        self.assertEqual(response.status_code,200, response.data[:200])
        self.assertEqual(response.mimetype,'application/pdf')
        self.assertIn('attachment;',response.headers['Content-Disposition'])
        reader=PdfReader(io.BytesIO(response.data))
        text='\n'.join(page.extract_text() for page in reader.pages)
        for index,page in enumerate(reader.pages,1):
            self.assertIn(f'{index} of {len(reader.pages)}',page.extract_text())
        return text,reader

    def vehicle(self):
        return self.call(self.owner,'vehicles',dict(name='Test car',registration='TEST42')).json['id']

    def journey(self,vid,**extra):
        data=dict(vehicle_id=vid,date='2026-08-01',origin='Home',destination='Client office',purpose='Client visit',scope='business',distance='100',percent=60)
        data.update(extra)
        response=self.call(self.owner,'vehicle-journeys',data)
        self.assertEqual(response.status_code,200,response.json)
        return response.json['id']

    def test_wfh_monthly_totals_pending_status_notes_and_timestamps(self):
        self.bill(work_percent=0,business_percent=0)
        self.diary(start_time='09:00',end_time='10:15',break_minutes=15,activity='Reports <draft> & preparation')
        self.diary(date='2026-10-09',scope='business',start_time='09:00',end_time='11:00')
        self.method(hours_complete=False)
        text,_=self.pdf_text(self.owner.get('/api/home-office/2026/report.pdf'))
        self.assertIn('Pending record checks',text)
        self.assertIn('FY 2026-27',text)
        self.assertIn('3h 00m',text);self.assertIn('$2.10',text)
        self.assertIn('Reports <draft> & preparation',text)
        self.assertIn('Australia/Brisbane',text)
        self.assertIn('15 min',text);self.assertIn('Bill attached; type confirmed',text)
        self.assertIn('recorded forecast: $0.00',text)
        self.method()
        text,_=self.pdf_text(self.agent.get('/api/home-office/2026/report.pdf'))
        self.assertIn('Included in tax forecast',text);self.assertIn('recorded forecast: $2.10',text)
        self.assertEqual(app.test_client().get('/api/home-office/2026/report.pdf').status_code,401)
        self.assertEqual(self.owner.get('/api/home-office/2000/report.pdf').status_code,400)

    def test_empty_and_unknown_rate_wfh_reports_do_not_invent_a_claim(self):
        text,_=self.pdf_text(self.owner.get('/api/home-office/2027/report.pdf'))
        self.assertIn('Rate unavailable',text);self.assertIn('No home-working sessions',text)
        self.assertIn('Not enabled',text);self.assertNotIn('$0.70',text)

    def test_mileage_filters_allocations_rate_and_actual_odometer(self):
        vid=self.vehicle()
        self.journey(vid,odometer_start='1000',odometer_end='1100')
        self.journey(vid,date='2026-08-02',scope='work',distance='20',percent=50,purpose='Employment visit')
        self.journey(vid,date='2026-08-03',scope='personal',distance='10',purpose='Private')
        self.journey(vid,date='2026-09-01',purpose='Outside date range')
        other=self.vehicle();self.journey(other,purpose='Other vehicle secret')
        url=f'/api/vehicles/{vid}/report.pdf?from=2026-08-01&to=2026-08-31&rate=0.91'
        text,_=self.pdf_text(self.agent.get(url))
        for value in ('130.000 km','60.000 km','10.000 km','$63.70','1,000.000','1,100.000','Not recorded','TEST42'):
            self.assertIn(value,text)
        self.assertNotIn('Outside date range',text);self.assertNotIn('Other vehicle secret',text)
        text,_=self.pdf_text(self.owner.get(url+'&scope=business'))
        self.assertIn('$54.60',text);self.assertNotIn('Employment visit',text)
        text,_=self.pdf_text(self.owner.get(url.replace('&rate=0.91','')))
        self.assertIn('No reimbursement rate',text);self.assertNotIn('$63.70',text)
        self.assertEqual(app.test_client().get(url).status_code,401)
        for query in ('from=2026-08-31&to=2026-08-01','from=bad&to=2026-08-01','from=2026-08-01&to=2026-08-31&scope=invalid','from=2026-08-01&to=2026-08-31&rate=NaN','from=2026-08-01&to=2026-08-31&rate=-1','from=2026-08-01&to=2026-08-31&rate=0.00001',''):
            self.assertEqual(self.owner.get(f'/api/vehicles/{vid}/report.pdf?{query}').status_code,400,query)
        self.assertEqual(self.owner.get('/api/vehicles/999999/report.pdf?from=2026-08-01&to=2026-08-31').status_code,404)

    def test_mileage_rounding_sums_line_amounts_and_keeps_partial_private_distance(self):
        trips=[dict(id=i,scope='business',distance_m=101,percent=50) for i in range(3)]
        distances,amounts,lines=mileage_totals(trips,Decimal('.91'))
        self.assertEqual(distances['business'],Decimal('.1515'))
        self.assertEqual(distances['personal'],Decimal('.1515'))
        self.assertEqual(amounts['business'],15)
        self.assertEqual(sum(lines.values()),15)

    def test_long_unicode_reports_repeat_headers_and_preserve_every_row(self):
        vid=self.vehicle()
        with app.app_context():
            for i in range(70):
                db().execute('INSERT INTO vehicle_journeys(vehicle_id,date,origin,destination,purpose,scope,distance_m,percent) VALUES (?,?,?,?,?,?,?,?)',
                             (vid,'2026-08-01','Origin <North> & terminal '+('very long location '*8),'Destination café',f'Purpose record {i:03d} '+('Detailed business activity '*35),'business',1001,100))
            db().commit()
        text,reader=self.pdf_text(self.owner.get(f'/api/vehicles/{vid}/report.pdf?from=2026-08-01&to=2026-08-31'))
        self.assertGreater(len(reader.pages),3)
        for i in range(70): self.assertIn(f'Purpose record {i:03d}',text)
        self.assertIn('Destination café',text)
        for page in reader.pages[1:]: self.assertIn('From / to',page.extract_text())
