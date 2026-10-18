"""Australian resident individual planning estimates, integer cents.
Sources (checked 8 October 2026):
https://moneysmart.gov.au/work-and-tax/income-tax
https://www.legislation.gov.au/C2004A03348/2026-07-01/2026-07-01/text/original/epub/OEBPS/document_1/document_1.html
https://www.ato.gov.au/api/public/content/0-1b51c2a4-d678-43de-bb9e-0d2ffc632bd5
Medicare defaults to a clearly labelled 2% provision; exemptions, family / low-income
reductions need an explicit override. HELP and MLS require other_tax provision.
"""
from decimal import Decimal, ROUND_HALF_UP

def rounded(value):
    return int(Decimal(value).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def estimate(taxable_cents, year, withheld_cents=0, instalments_cents=0, medicare_override=None, other_tax_cents=0, set_aside_cents=0):
    if year not in (2024,2025,2026,2027): raise ValueError('Supported financial years are 2024–25 to 2027–28.')
    # ATO individual taxable income is whole dollars; round down, not nearest.
    income=max(0,int(taxable_cents)//100)*100
    first=Decimal('0.16') if year<2026 else Decimal('0.15') if year==2026 else Decimal('0.14')
    rates=[(1820000,4500000,first),(4500000,13500000,Decimal('.30')),(13500000,19000000,Decimal('.37')),(19000000,None,Decimal('.45'))]
    tax=rounded(sum(Decimal(max(0,min(income,upper if upper else income)-lower))*rate for lower,upper,rate in rates))
    lito=70000 if income<=3750000 else max(0,rounded(Decimal(70000)-Decimal(income-3750000)*Decimal('.05'))) if income<=4500000 else max(0,rounded(Decimal(32500)-Decimal(income-4500000)*Decimal('.015')))
    lito=min(tax,lito); tax-=lito
    medicare=rounded(Decimal(income)*Decimal('.02')) if medicare_override is None else medicare_override
    total=tax+medicare+other_tax_cents
    balance=total-withheld_cents-instalments_cents
    return dict(taxable_cents=income,income_tax_cents=tax,lito_cents=lito,medicare_cents=medicare,other_tax_cents=other_tax_cents,total_tax_cents=total,withheld_cents=withheld_cents,instalments_cents=instalments_cents,balance_cents=balance,set_aside_cents=set_aside_cents,additional_to_save_cents=max(0,balance-set_aside_cents))
