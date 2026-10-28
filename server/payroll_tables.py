"""Conservative reader for the Pay Slip Components current-pay/YTD layout.

Unknown columns, deductions or unreconciled totals fall back to normal review.
All arithmetic uses printed totals, never annual pay rates or inferred tax rates.
"""
import re
from datetime import datetime
from decimal import Decimal

MONEY = r'\$((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})'
PAIR = MONEY + r'\s+' + MONEY


def read_components(text):
    lines = [' '.join(line.split()) for line in text.splitlines() if line.strip()]
    heading = 'pay slip components hours/units rate this pay year to date'
    lower = [line.lower() for line in lines]
    if lower.count(heading) != 1:
        return None
    # Never pick one payment out of a bundle, even when its totals reconcile.
    if len(re.findall(r'(?im)^\s*(?:date\s+paid|payment\s+date|pay\s+date)\s*:', text)) != 1:
        return None
    if len(re.findall(r'(?im)^\s*ABN\s*:', text)) != 1:
        return None

    def single(pattern, source):
        matches = [m for line in source if (m := re.fullmatch(pattern, line, re.I))]
        if len(matches) != 1:
            raise ValueError('missing or repeated label')
        return matches[0].groups()

    def values(pattern, source):
        return tuple(Decimal(v.replace(',', '')) for v in single(pattern, source))

    def section(first, last):
        if lower.count(first) != 1 or lower.count(last) != 1:
            raise ValueError('missing or repeated section')
        a, b = lower.index(first), lower.index(last)
        if a >= b:
            raise ValueError('section order')
        return lines[a + 1:b]

    try:
        prefix = lines[:lower.index(heading)]
        abn = next(i for i, line in enumerate(prefix) if re.fullmatch(r'ABN:\s*[\d ]{11,14}', line, re.I))
        # This layout prints the company above its ABN, sometimes on two lines.
        if not 1 <= abn <= 3:
            return None
        employer = ' '.join(prefix[:abn])
        if len(employer) > 200 or re.search(r'[:$]', employer):
            return None
        dates = {}
        for key, label in [('date', 'Date Paid'), ('period_start', 'Period Starting'), ('period_end', 'Period Ending')]:
            value, = single(label + r':\s*(\d{1,2}/\d{1,2}/\d{4})', prefix)
            dates[key] = datetime.strptime(value, '%d/%m/%Y').date().isoformat()
        if dates['period_start'] > dates['period_end']:
            return None
        earnings, = values(r'Gross Earnings:\s*' + MONEY, prefix)
        net, = values(r'Net Payment:\s*' + MONEY, prefix)
        super_total, = values(r'Super Payments:\s*' + MONEY, prefix)
        wages = section('wages and earnings', 'taxes')
        taxes = section('taxes', 'superannuation breakdown')
        supers = section('superannuation breakdown', 'bank payments account this pay')
        current_earnings, ytd_earnings = values(PAIR, wages)
        # Untaxed benefits need individual assessment; do not treat as wages.
        if re.search(r'non[- ]?taxable|tax[- ]?free|reimburse|deduction|salary sacrifice', ' '.join(wages), re.I):
            return None
        tax, ytd_tax = values(r'PAYG\s+' + PAIR, taxes)
        if len(taxes) != 2 or values(PAIR, taxes) != (tax, ytd_tax):
            return None
        sg, ytd_sg = values(r'SG\s+' + PAIR, supers)
        sacrifice = ytd_sacrifice = Decimal(0)
        if any(line.lower().startswith('salary sacrifice super') for line in supers):
            sacrifice, ytd_sacrifice = values(r'Salary Sacrifice Super\s+' + PAIR, supers)
            if len(supers) != 3:
                return None
        elif len(supers) != 2:
            return None
        if values(PAIR, supers) != (sg + sacrifice, ytd_sg + ytd_sacrifice):
            return None
        # Reconcile independently printed summary and component totals, then
        # remove only explicit salary-sacrifice super. Never derive gross from
        # net + PAYG alone: unexplained deductions must prevent the shortcut.
        gross = earnings - sacrifice
        if (earnings != current_earnings or super_total != sg + sacrifice
                or gross - tax != net or min(gross, ytd_earnings - ytd_sacrifice) < 0):
            return None
        result = dict(document_kind='payslip', amounts_basis='period', employer=employer,
                      **dates, gross=float(gross), withheld=float(tax), net=float(net),
                      super=float(sg), ytd_gross=float(ytd_earnings - ytd_sacrifice),
                      ytd_withheld=float(ytd_tax))
        if sacrifice:
            result['extraction_note'] = (
                f'Gross taxable pay is gross earnings (${earnings:,.2f}) less salary-sacrifice '
                f'super (${sacrifice:,.2f}). It reconciles with this payment’s net pay and PAYG. '
                'Check these figures against the original before saving.')
        return result
    except (ValueError, StopIteration):
        return None
