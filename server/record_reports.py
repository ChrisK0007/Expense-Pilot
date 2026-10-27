"""Printable record summaries. Reports never change claims or stored records."""
import calendar
import io
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
import workspace_time

FONT_LOCK = Lock()
INK = colors.HexColor('#24352e')
GREEN = colors.HexColor('#355c46')
MUTED = colors.HexColor('#64716b')
RULE = colors.HexColor('#dce4de')
SCOPE = dict(work='Employment', business='Business', personal='Personal')


def cents(value):
    return int(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def aud(value):
    return 'Rate unavailable' if value is None else f'${value / 100:,.2f}'


def hours(minutes):
    minutes = int(minutes)
    return f'{minutes // 60}h {minutes % 60:02d}m'


def day(value):
    return date.fromisoformat(value).strftime('%d %b %Y')


def stamp(value):
    if not value:
        return '-'
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(workspace_time.zone()).strftime('%d/%m/%Y\n%H:%M')


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.states = []

    def showPage(self):
        self.states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        count = len(self.states)
        for state in self.states:
            self.__dict__.update(state)
            self.setFont('Helvetica', 8)
            self.setFillColor(MUTED)
            self.drawRightString(A4[0] - 18 * mm, 12 * mm, f'{self._pageNumber} of {count}')
            super().showPage()
        super().save()


class Report:
    def __init__(self, title, period):
        self.title, self.period = title, period
        font = 'Helvetica'
        path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if path.exists():
            with FONT_LOCK:
                if 'RecordSans' not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont('RecordSans', str(path)))
            font = 'RecordSans'
        self.styles = {
            'body': ParagraphStyle('record-body', fontName=font, fontSize=9, leading=13, textColor=INK, spaceAfter=7),
            'small': ParagraphStyle('record-small', fontName=font, fontSize=7, leading=10, textColor=INK),
            'title': ParagraphStyle('record-title', fontName=font, fontSize=29, leading=35, textColor=GREEN, spaceAfter=14),
            'heading': ParagraphStyle('record-heading', fontName=font, fontSize=14, leading=19, textColor=GREEN, spaceBefore=14, spaceAfter=9, keepWithNext=True),
            'label': ParagraphStyle('record-label', fontName=font, fontSize=8, leading=11, textColor=colors.white),
        }
        self.story = []

    def p(self, text, style='body'):
        # Treat all user text as text, never ReportLab markup or a remote resource.
        return Paragraph(escape(str(text if text is not None else '')).replace('\n', '<br/>'), self.styles[style])

    def add(self, text, style='body'):
        self.story.append(self.p(text, style))

    def table(self, headers, rows, widths):
        data = [[self.p(v, 'label') for v in headers]] + [[self.p(v, 'small') for v in row] for row in rows]
        table = Table(data, colWidths=[v * mm for v in widths], repeatRows=1, hAlign='LEFT', splitInRow=0)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), GREEN), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 1), (-1, -1), .4, RULE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f7f4')]),
        ]))
        self.story.append(table)
        self.story.append(Spacer(1, 3 * mm))

    def cover(self, person):
        self.story.append(Spacer(1, 12 * mm))
        self.add(person)
        self.add(self.title, 'title')
        self.add(self.period)
        self.add('Generated ' + datetime.now(workspace_time.zone()).strftime('%d %b %Y %H:%M') + ' (' + workspace_time.name() + ')')

    def build(self):
        # A final table's spacing can spill onto a page with no report content.
        while self.story and isinstance(self.story[-1], Spacer):
            self.story.pop()
        out = io.BytesIO()
        def decoration(c, doc):
            c.saveState()
            c.setFillColor(GREEN)
            c.setFont('Helvetica-Bold', 12)
            c.drawString(18 * mm, A4[1] - 16 * mm, 'expense pilot')
            c.setFont('Helvetica', 8)
            c.setFillColor(MUTED)
            c.drawRightString(A4[0] - 18 * mm, A4[1] - 16 * mm, self.period)
            c.setStrokeColor(RULE)
            c.line(18 * mm, 19 * mm, A4[0] - 18 * mm, 19 * mm)
            c.setFont('Helvetica', 7)
            c.drawString(18 * mm, 12 * mm, 'A clearer view of every dollar.  |  ' + self.title)
            c.restoreState()
        SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=27 * mm, bottomMargin=25 * mm,
                          title=self.title, author='Expense Pilot').build(
                              self.story, onFirstPage=decoration, onLaterPages=decoration, canvasmaker=NumberedCanvas)
        return out.getvalue()


def home_office_pdf(annual, person):
    year = annual['year']
    report = Report('WFH logbook', f'FY {year}-{str(year + 1)[-2:]}')
    report.cover(person)
    report.add(day(annual['start']) + ' - ' + day(annual['end']))
    rate = annual['rate_cents']
    entries = sorted(annual['entries'], key=lambda e: (e['date'], e['start_at'], e['id']))
    report.add('Fixed-rate summary', 'heading')
    report.table(['Workspace', 'Recorded hours', 'Hourly deduction estimate'], [
        [SCOPE[s], hours(annual['minutes'][s]), aud(annual['hourly'][s])] for s in ('work', 'business')
    ] + [['Total', hours(sum(annual['minutes'].values())), aud(sum(annual['hourly'].values())) if rate is not None else 'Rate unavailable']], [49, 50, 75])
    status = {'not_selected': 'Not enabled', 'active': 'Included in tax forecast', 'needs_review': 'Pending record checks'}[annual['status']]
    report.add('Claim status: ' + status)
    report.add('Rate: ' + (f'{rate}c per recorded hour.' if rate is not None else 'Not confirmed for this year; no rate assumed.'))
    included = sum(annual['fixed'].values()) if annual['active'] else 0
    report.add('Home-office deduction included in recorded forecast: ' + aud(included) + '.')
    if sum(annual['extras'].values()):
        report.add('Separately assessed deductions outside the hourly rate: ' + aud(sum(annual['extras'].values())) + '. Included only when claim checks are complete.')
    report.add('These amounts are deductions from income, not tax refunds or reimbursements. Annual tax overrides may replace the recorded forecast.')
    report.add('Records supporting this logbook', 'heading')
    report.add('Keep a bill or receipt for each covered running-cost type you personally incurred. Covered bills are evidence; their cost and work-use percentages do not determine the hourly deduction. They cannot also be claimed separately.')
    report.add('The diary lists recorded sessions after breaks. Original creation and update timestamps are retained; generating this report does not establish that older entries were recorded at the time. Keep supporting records for any late entries.')
    report.add('Logged/updated timestamps below use ' + workspace_time.name() + '. Session times use the timezone shown on each row.')
    report.add('ATO fixed-rate guidance: ' + annual['source'], 'small')
    report.add('Rule reference checked ' + day(annual['rules_checked']) + '. CSV export contains the full relevant edit history.', 'small')
    report.story.append(PageBreak())
    report.add('Year at a glance', 'heading')
    monthly = defaultdict(lambda: dict(work=0, business=0))
    for e in entries:
        monthly[e['date'][:7]][e['scope']] += (e['end_at'] - e['start_at']) // 60 - e['break_minutes']
    months = []
    for index in range(12):
        month = (index + 6) % 12 + 1
        month_year = year if month >= 7 else year + 1
        values = monthly[f'{month_year}-{month:02d}']
        estimate = sum(cents(Decimal(m) * rate / 60) for m in values.values()) if rate is not None else None
        months.append([calendar.month_name[month] + ' ' + str(month_year), hours(values['work']), hours(values['business']), hours(sum(values.values())), aud(estimate)])
    report.table(['Month', 'Employment', 'Business', 'Total hours', 'Estimate'], months, [46, 32, 32, 32, 32])
    report.add('Monthly estimates are rounded. The annual estimate is calculated from total recorded minutes for each workspace.', 'small')
    report.add('Hours diary', 'heading')
    if entries:
        report.table(['Date / ID', 'Workspace', 'Session / zone', 'Break', 'Net hours', 'Logged', 'Updated'], [
            [day(e['date']) + f"\n#{e['id']}", SCOPE[e['scope']], e['start_time'] + ' - ' + e['end_time'] + '\n' + e['timezone'],
             str(e['break_minutes']) + ' min', hours((e['end_at'] - e['start_at']) // 60 - e['break_minutes']),
             stamp(e['created_at']), stamp(e['updated_at'])] for e in entries
        ], [24, 24, 32, 15, 23, 28, 28])
        report.add('Work performed / notes', 'heading')
        report.table(['Date / ID', 'Workspace', 'Work performed'], [
            [day(e['date']) + f"\n#{e['id']}", SCOPE[e['scope']], e['activity']] for e in entries
        ], [30, 30, 114])
    else:
        report.add('No home-working sessions recorded for this financial year.')
    report.add('Bill evidence and separate deductions', 'heading')
    if annual['costs']:
        from home_office import COVERED, KINDS
        report.table(['Date / supplier', 'Type', 'Record status'], [
            [day(e['date']) + '\n' + e['merchant'], KINDS[e['home_office_kind']],
             ('Evidence only' if e['home_office_kind'] in COVERED else 'Separate deduction') + '\n' +
             ('Bill attached' if e['receipt_id'] else 'Bill missing') +
             ('; type confirmed' if e['classification_confirmed'] else '; confirm type') +
             ('; reimbursed - excluded' if e['reimbursed'] else '') + ('; expense needs review' if e['status'] != 'ready' else '')]
            for e in annual['costs']
        ], [65, 49, 60])
    else:
        report.add('No bills linked.')
    if annual['fixed_issues'] or annual['warnings']:
        report.add('Outstanding checks', 'heading')
        for issue in annual['fixed_issues'] + annual['warnings']:
            report.add('- ' + issue)
    return report.build()


def mileage_totals(journeys, rate):
    distance = {s: Decimal(0) for s in SCOPE}
    amounts = {s: 0 for s in SCOPE}
    line_amounts = {}
    for j in journeys:
        full = Decimal(j['distance_m']) / 1000
        allocated = full * Decimal(j['percent']) / 100 if j['scope'] != 'personal' else Decimal(0)
        distance['personal'] += full - allocated
        if j['scope'] != 'personal':
            distance[j['scope']] += allocated
        amount = cents(allocated * rate * 100) if rate is not None else 0
        amounts[j['scope']] += amount
        line_amounts[j['id']] = amount
    return distance, amounts, line_amounts


def mileage_pdf(vehicle, person, workplace, journeys, start, end, scope, rate=None):
    report = Report('Mileage report', day(start) + ' - ' + day(end))
    report.cover(person)
    report.add(vehicle['name'] + (' (' + vehicle['registration'] + ')' if vehicle['registration'] else ''))
    if workplace:
        report.add(workplace)
    report.add('Journeys included: ' + ('all workspaces' if scope == 'all' else SCOPE[scope]) + f". {len(journeys)} recorded {'journey' if len(journeys) == 1 else 'journeys'}.")
    distance, amounts, line_amounts = mileage_totals(journeys, rate)
    report.add('Distance summary', 'heading')
    rate_label = f'${rate:.4f}'.rstrip('0').rstrip('.') + '/km' if rate is not None else 'Not set'
    report.table(['Type', 'Allocated distance', 'Rate', 'Reimbursement estimate'], [
        [SCOPE[s], f'{distance[s]:,.3f} km', rate_label if s != 'personal' else '-', aud(amounts[s]) if rate is not None and s != 'personal' else '-'] for s in SCOPE
    ] + [['Total', f'{sum(distance.values()):,.3f} km', '', aud(sum(amounts.values())) if rate is not None else '-']], [34, 45, 37, 58])
    report.add('Employment/business distance uses the saved use percentage for each journey. The remainder is personal. This summary covers only the vehicle, dates and workspace selected.')
    if rate is not None:
        report.add('The optional reimbursement rate was entered by the person generating this report. Amounts are rounded per journey and totalled. This is not an ATO rate selection or a tax deduction calculation; no annual kilometre cap has been applied.')
    else:
        report.add('No reimbursement rate was entered. This report records distances only.')
    report.add('Odometer readings appear only where they were saved on a journey. Missing readings are shown as "Not recorded"; GPS distances are not presented as dashboard readings. Trips still only on a phone are not included.')
    report.add('Generated from saved journey records. Review classifications, purposes and any gaps before using the report for reimbursement or tax records.')
    report.story.append(PageBreak())
    if not journeys:
        report.add('Journeys', 'heading')
        report.add('No journeys match this vehicle, date range and workspace.')
    groups = defaultdict(list)
    for j in journeys:
        groups[j['date'][:7]].append(j)
    for month, group in sorted(groups.items()):
        report.add(datetime.strptime(month, '%Y-%m').strftime('%B %Y'), 'heading')
        rows = []
        for j in group:
            odometer = 'Not recorded' if j['odometer_start'] is None else f"{j['odometer_start']/1000:,.3f}\nto {j['odometer_end']/1000:,.3f}"
            full = Decimal(j['distance_m']) / 1000
            use = f"{j['percent']}%" if j['scope'] != 'personal' else '0%'
            rows.append([day(j['date']), (j['origin'] or '-') + '\nTO\n' + (j['destination'] or '-'),
                         SCOPE[j['scope']] + '\n' + (j['purpose'] or '-'), odometer,
                         f'{full:,.3f} km\n{use} work use',
                         aud(line_amounts[j['id']]) if rate is not None and j['scope'] != 'personal' else '-'])
        report.table(['Date', 'From / to', 'Purpose', 'Odometer km', 'Distance / use', 'Amount'], rows, [21, 43, 38, 25, 27, 20])
    return report.build()
