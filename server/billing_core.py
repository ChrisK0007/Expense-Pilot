"""Pure billing calculations and PDF rendering; all amounts are integer AUD cents."""
import base64
import calendar
import io
import re
import threading
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.sax.saxutils import escape

_FONT_LOCK = threading.Lock()


def decimal_value(value, label, minimum=0, maximum=10000000):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not Decimal(str(minimum)) <= number <= Decimal(str(maximum)):
            raise ValueError()
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'Enter a valid {label}.') from None


def cents(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def calculate_lines(items, tax_mode, gst_registered):
    if tax_mode not in ('none', 'exclusive', 'inclusive'):
        raise ValueError('Choose a valid GST mode.')
    if tax_mode != 'none' and not gst_registered:
        raise ValueError('Enable GST registration in Business settings before charging GST.')
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValueError('Add between 1 and 100 line items.')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Invalid line item.')
        description = str(item.get('description', '')).strip()
        if not description or len(description) > 1000:
            raise ValueError('Each line needs a description of up to 1,000 characters.')
        quantity = decimal_value(item.get('quantity', 1), 'quantity', '0.0001', 100000)
        if quantity.as_tuple().exponent < -4:
            raise ValueError('Quantity supports up to four decimal places.')
        unit = decimal_value(item.get('unit_price', 0), 'unit price')
        if unit.as_tuple().exponent < -2:
            raise ValueError('Unit prices support up to two decimal places.')
        discount = decimal_value(item.get('discount', 0), 'discount percentage', 0, 100)
        tax = str(item.get('tax', 'gst' if tax_mode != 'none' else 'none'))
        if tax not in ('gst', 'gst_free', 'none'):
            raise ValueError('Invalid line GST treatment.')
        if tax_mode == 'none':
            tax = 'none'
        amount = cents(quantity * unit * 100 * (1 - discount / 100))
        gst = cents(Decimal(amount) / 11) if tax_mode == 'inclusive' and tax == 'gst' else (
            cents(Decimal(amount) / 10) if tax_mode == 'exclusive' and tax == 'gst' else 0)
        net = amount - gst if tax_mode == 'inclusive' else amount
        result.append(dict(description=description, quantity=str(quantity), unit_price=str(unit),
                           discount=str(discount), tax=tax, net_cents=net, gst_cents=gst,
                           total_cents=net + gst))
    subtotal = sum(x['net_cents'] for x in result)
    gst = sum(x['gst_cents'] for x in result)
    if subtotal + gst > 1000000000:
        raise ValueError('Document total cannot exceed AUD 10,000,000.')
    return dict(lines=result, subtotal_cents=subtotal, gst_cents=gst, total_cents=subtotal + gst)


def advance_date(value, interval, anchor_day):
    current = date.fromisoformat(value)
    if interval in ('weekly', 'fortnightly'):
        return (current + timedelta(days=7 if interval == 'weekly' else 14)).isoformat()
    months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}[interval]
    month = current.month - 1 + months
    year, month = current.year + month // 12, month % 12 + 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1])).isoformat()


def display_status(doc, today):
    if doc['state'] != 'issued' or doc['kind'] == 'quote':
        return doc['state']
    if doc['balance_cents'] == 0:
        return 'paid'
    if doc['due_date'] < today:
        return 'overdue'
    return 'part_paid' if doc['paid_cents'] else 'unpaid'


def date_au(value):
    return date.fromisoformat(value).strftime('%d/%m/%Y')


def aud(value):
    return f'${value / 100:,.2f}'


def pdf_document(doc):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

    out = io.BytesIO()
    seller = doc['business']
    client = doc['client']
    colour = seller.get('accent', '#355c46')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
        colour = '#355c46'
    ink, muted, accent = colors.HexColor('#252b3b'), colors.HexColor('#737b8d'), colors.HexColor(colour)
    font = 'Helvetica'
    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if font_path.exists():
        with _FONT_LOCK:
            if 'InvoiceSans' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('InvoiceSans', str(font_path)))
        font = 'InvoiceSans'
    normal = ParagraphStyle('body', fontName=font, fontSize=9, leading=13, textColor=ink, spaceAfter=5)
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=11, textColor=muted)
    title = ParagraphStyle('title', parent=normal, fontSize=25, leading=29, textColor=accent, spaceAfter=8)
    right = ParagraphStyle('right', parent=normal, alignment=TA_RIGHT)
    white = ParagraphStyle('white', parent=small, textColor=colors.white)
    def p(value, style=normal):
        # Escape user content before the ReportLab paragraph parser sees it.
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)
    # A restrained two-column layout, matching the supplied invoice reference.
    rule = colors.HexColor('#e2e5eb')
    label_style = ParagraphStyle('label', parent=small, textColor=accent, spaceAfter=8)
    headline = ParagraphStyle('headline', parent=right, fontSize=15, leading=19, textColor=ink)
    left = []
    logo = seller.get('logo', '')
    if logo:
        im = Image(io.BytesIO(base64.b64decode(logo)))
        factor = min(44 * mm / im.imageWidth, 24 * mm / im.imageHeight)
        im.drawWidth, im.drawHeight = im.imageWidth * factor, im.imageHeight * factor
        im.hAlign = 'LEFT'
        left += [im, Spacer(1, 5 * mm)]
    left.append(p(seller.get('name', 'Your business')))
    for key in ('address', 'phone', 'email'):
        if seller.get(key): left.append(p(seller[key]))
    if seller.get('abn'): left.append(p('ABN: ' + seller['abn']))
    label = 'QUOTE' if doc['kind'] == 'quote' else ('TAX INVOICE' if seller.get('gst_registered') else 'INVOICE')
    if doc.get('receipt'):
        label = 'PAYMENT RECEIPT'
    if doc['state'] in ('draft', 'void'): label = doc['state'].upper() + ' ' + label
    right_side = [p(label, headline), Spacer(1, 5 * mm)]
    buyer = '\n'.join(str(client.get(k, '')) for k in ('name', 'contact', 'address', 'email') if client.get(k))
    if client.get('abn'): buyer += '\nABN: ' + client['abn']
    right_side += [p(buyer, right), Spacer(1, 3 * mm)]
    metadata = [('Number', doc['number']), ('Issued', date_au(doc['issue_date'])),
                ('Valid until' if doc['kind']=='quote' else 'Due', date_au(doc['due_date'])),
                ('Total', 'AU ' + aud(doc['total_cents']))]
    if doc.get('reference'): metadata.append(('Reference', doc['reference']))
    details = Table([[p(k),p(v,right)] for k,v in metadata], colWidths=[23*mm,48*mm])
    details.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,-1),.35,rule),('VALIGN',(0,0),(-1,-1),'TOP'),
                                ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
    right_side.append(details)
    top = Table([[left,right_side]], colWidths=[103*mm,71*mm])
    top.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                            ('RIGHTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),12),
                            ('LINEBELOW',(0,0),(-1,-1),.4,rule)]))
    story = [top, Spacer(1, 4*mm)]
    # Notes precede the item table, for flight-test dates and candidate details.
    if doc.get('notes'):
        story += [p(doc['notes']), Spacer(1, 5*mm)]
    taxable = doc['tax_mode'] != 'none'
    headings = ['DESCRIPTION', 'QUANTITY', 'RATE', 'GST', 'TOTAL'] if taxable else ['DESCRIPTION','QUANTITY','RATE','TOTAL']
    table_data = [[p(x, label_style if i==0 else ParagraphStyle('column'+str(i),parent=label_style,alignment=TA_RIGHT)) for i,x in enumerate(headings)]]
    for line in doc['lines']:
        description = line['description']
        if Decimal(line['discount']): description += f"\nDiscount: {line['discount']}%"
        cells = [p(description),p(line['quantity'],right),p(aud(cents(Decimal(line['unit_price'])*100)),right)]
        if taxable: cells.append(p('10%' if line['tax']=='gst' else 'GST-free' if line['tax']=='gst_free' else 'No GST',right))
        cells.append(p(aud(line['total_cents']),right));table_data.append(cells)
    widths = [80*mm,20*mm,27*mm,20*mm,27*mm] if taxable else [93*mm,24*mm,27*mm,30*mm]
    line_table = Table(table_data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    line_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(0,-1),10),
        ('TOPPADDING',(0,1),(-1,-1),8),('BOTTOMPADDING',(0,1),(-1,-1),8),
        ('LINEBELOW',(0,0),(-1,-1),.4,rule)]))
    story += [line_table,Spacer(1,3*mm)]
    totals = [('Subtotal (ex GST)', doc['subtotal_cents']),('GST',doc['gst_cents'])] if taxable else []
    totals.append(('Total', doc['total_cents']))
    if doc['kind']=='invoice' and doc.get('paid_cents'):
        totals += [('Payments recorded',doc['paid_cents']),('Balance due',doc['balance_cents'])]
    total_table = Table([[p(k,right),p('AU '+aud(v),right)] for k,v in totals],colWidths=[131*mm,43*mm])
    total_table.setStyle(TableStyle([('LINEBELOW',(0,-1),(-1,-1),.5,rule),('RIGHTPADDING',(0,0),(-1,-1),0)]))
    note = 'Rates include GST where applicable.' if doc['tax_mode']=='inclusive' else 'Rates exclude GST.' if taxable else 'No GST has been charged'
    story += [KeepTogether([total_table,p(note,ParagraphStyle('tax-note',parent=small,alignment=TA_RIGHT))])]
    if doc.get('receipt'):
        story += [Spacer(1, 6 * mm), p('PAYMENTS RECEIVED', label_style)]
        payment_rows = [[p('Date', small), p('Reference', small), p('Amount AUD', right)]]
        payment_rows += [[p(date_au(row['date'])), p(row['reference']), p(aud(row['amount_cents']), right)] for row in doc['payments']]
        payment_table = Table(payment_rows, colWidths=[30 * mm, 101 * mm, 43 * mm], repeatRows=1)
        payment_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                         ('LINEBELOW', (0, 0), (-1, 0), .4, rule), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        story.append(payment_table)
    if doc['kind']=='invoice' and doc.get('payment_details'):
        payment_heading=Table([[p('PAYMENT DETAILS',label_style)]],colWidths=[174*mm])
        payment_heading.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('LINEBELOW',(0,0),(-1,-1),.4,rule)]))
        story += [Spacer(1,8*mm),KeepTogether([payment_heading,Spacer(1,3*mm),p(doc['payment_details'])])]
    def footer(canvas, layout):
        canvas.saveState()
        canvas.setStrokeColor(accent)
        canvas.line(18 * mm, 17 * mm, 192 * mm, 17 * mm)
        canvas.setFont(font, 8)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 12 * mm, doc['number'] + ' | AUD')
        canvas.drawRightString(192 * mm, 12 * mm, f'Page {layout.page}')
        canvas.restoreState()
    SimpleDocTemplate(out, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                      topMargin=18 * mm, bottomMargin=24 * mm, title=doc['number'],
                      author=seller.get('name', '')).build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def pdf_statement(statement):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

    out = io.BytesIO()
    seller, client = statement['business'], statement['client']
    accent = seller.get('accent', '#355c46')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
        accent = '#355c46'
    accent, ink, muted, rule = (colors.HexColor(value) for value in (accent, '#252b3b', '#737b8d', '#e2e5eb'))
    font = 'Helvetica'
    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if font_path.exists():
        with _FONT_LOCK:
            if 'InvoiceSans' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('InvoiceSans', str(font_path)))
        font = 'InvoiceSans'
    normal = ParagraphStyle('statement-body', fontName=font, fontSize=8.5, leading=12, textColor=ink, spaceAfter=4)
    small = ParagraphStyle('statement-small', parent=normal, fontSize=7.5, leading=10, textColor=muted)
    right = ParagraphStyle('statement-right', parent=normal, alignment=TA_RIGHT)
    title = ParagraphStyle('statement-title', parent=normal, fontSize=22, leading=27, textColor=accent, spaceAfter=10)
    def p(value, style=normal):
        return Paragraph(escape(str(value if value is not None else '')).replace('\n', '<br/>'), style)
    seller_lines = [p(seller.get('name', ''))]
    if seller.get('logo'):
        logo = Image(io.BytesIO(base64.b64decode(seller['logo'])))
        factor = min(42 * mm / logo.imageWidth, 22 * mm / logo.imageHeight)
        logo.drawWidth, logo.drawHeight = logo.imageWidth * factor, logo.imageHeight * factor
        logo.hAlign = 'LEFT'
        seller_lines.insert(0, logo)
    for key in ('address', 'email', 'phone'):
        if seller.get(key):
            seller_lines.append(p(seller[key], small))
    if seller.get('abn'):
        seller_lines.append(p('ABN: ' + seller['abn'], small))
    buyer = [p('TO', small)] + [p(client[k]) for k in ('name', 'contact', 'address', 'email') if client.get(k)]
    header = Table([[seller_lines, buyer]], colWidths=[87 * mm, 87 * mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 12), ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
    all_rows = statement['mode'] == 'all'
    subtitle = ('All invoices and payments | ' + date_au(statement['start']) + ' to ' + date_au(statement['end'])) if all_rows else 'Outstanding invoices | As at ' + date_au(statement['end'])
    story = [p('Statement of account', title), p(subtitle, small), Spacer(1, 5 * mm), header]
    if all_rows:
        story += [p('Opening balance: AU ' + aud(statement['opening_cents']), right), Spacer(1, 3 * mm)]
        headings = ['Date', 'Invoice', 'Details', 'Invoiced', 'Paid', 'Balance']
        widths = [24, 29, 41, 25, 25, 30]
        data = [[p(value, small) for value in headings]]
        for row in statement['rows']:
            data.append([p(date_au(row['date'])), p(row['number']), p(row['description']),
                         p(aud(row['debit_cents']) if row['debit_cents'] else '-', right),
                         p(aud(row['credit_cents']) if row['credit_cents'] else '-', right), p(aud(row['balance_cents']), right)])
    else:
        headings = ['Issued', 'Invoice', 'Due', 'Total', 'Paid', 'Outstanding']
        widths = [24, 30, 24, 32, 32, 32]
        data = [[p(value, small) for value in headings]]
        for row in statement['rows']:
            data.append([p(date_au(row['date'])), p(row['number']), p(date_au(row['due_date'])),
                         p(aud(row['amount_cents']), right), p(aud(row['paid_cents']), right), p(aud(row['balance_cents']), right)])
    table = Table(data, colWidths=[width * mm for width in widths], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, 0), .6, accent),
                               ('LINEBELOW', (0, 1), (-1, -1), .25, rule), ('TOPPADDING', (0, 0), (-1, -1), 7),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LEFTPADDING', (0, 0), (-1, -1), 2),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 5)]))
    story.append(table)
    if not statement['rows']:
        story += [Spacer(1, 4 * mm), p('No invoice or payment activity in this period.' if all_rows else 'No outstanding invoices.')]
    summary = [('Invoiced in period' if all_rows else 'Invoice total', statement['invoice_cents']),
               ('Payments in period' if all_rows else 'Payments received', statement['payment_cents']),
               ('Closing balance' if all_rows else 'Total outstanding', statement['closing_cents'])]
    totals = Table([[p(label, right), p('AU ' + aud(amount), right)] for label, amount in summary], colWidths=[131 * mm, 43 * mm])
    totals.setStyle(TableStyle([('LINEABOVE', (0, -1), (-1, -1), .6, accent), ('TOPPADDING', (0, -1), (-1, -1), 8)]))
    story.append(KeepTogether([Spacer(1, 6 * mm), totals]))
    if seller.get('payment_details'):
        story += [Spacer(1, 7 * mm), p('PAYMENT DETAILS', small), p(seller['payment_details'])]
    def footer(canvas, layout):
        canvas.saveState()
        canvas.setStrokeColor(accent)
        canvas.line(18 * mm, 17 * mm, 192 * mm, 17 * mm)
        canvas.setFillColor(muted)
        canvas.setFont(font, 8)
        canvas.drawString(18 * mm, 12 * mm, 'Statement | AUD | ' + date_au(statement['end']))
        canvas.drawRightString(192 * mm, 12 * mm, f'Page {layout.page}')
        canvas.restoreState()
    SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                      bottomMargin=24 * mm, title='Statement of account', author=seller.get('name', '')).build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
