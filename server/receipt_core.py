"""Currency evidence for receipt drafts; never interpret an unqualified $ as USD."""
import re
CODES=('AUD','USD','NZD','CAD','SGD','HKD','FJD','EUR','GBP','JPY','CNY','THB','IDR','MYR','CHF','INR','KRW','AED','ZAR','PHP','VND','TWD','NOK','SEK','DKK','PLN','BRL','MXN')

def markers(text):
    upper=text.upper()
    found=set(re.findall(r'(?<![A-Z])('+'|'.join(CODES)+r')(?![A-Z])',upper))
    # Standalone SG is also a payroll row label (super guarantee). A separated
    # dollar amount, including on the next PDF line, is not an SG$ symbol.
    for pattern,code in [(r'\b(?:AU|A)\s*\$|AUSTRALIAN DOLLARS?','AUD'),(r'\bUS\s*\$|US DOLLARS?|U\.S\. DOLLARS?','USD'),(r'\bNZ\s*\$|NEW ZEALAND DOLLARS?','NZD'),(r'\bCA\s*\$|CANADIAN DOLLARS?','CAD'),(r'\bSG\$|SINGAPORE DOLLARS?','SGD'),(r'\bHK\s*\$|HONG KONG DOLLARS?','HKD'),(r'€|\bEUROS?\b','EUR'),(r'£|POUNDS? STERLING','GBP')]:
        if re.search(pattern,upper):found.add(code)
    return found

def australian_details(text):
    return bool(re.search(r'\bABN[\s:#]*\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b',text,re.I) or (re.search(r'\bGST\b',text,re.I) and re.search(r'\.(?:com|net|org)\.au\b',text,re.I)))

def currency_fields(result,source_text=''):
    # PDF text is independently available. For photos, evidence is transcribed by
    # the vision model and remains a suggestion to review against the image.
    evidence=str(result.get('currency_evidence') or '')[:600]
    source=source_text if source_text.strip() else evidence
    codes=markers(source)
    if len(codes)==1:
        return dict(currency=codes.pop(),currency_status='printed',currency_evidence='Currency marker found in receipt text.' if source_text.strip() else evidence)
    if len(codes)>1:
        return dict(currency='',currency_status='unknown',currency_evidence='Multiple currencies found. Confirm the currency of the amount paid.')
    if australian_details(source):
        return dict(currency='AUD',currency_status='inferred',currency_evidence='Australian ABN or GST and Australian website found; confirm AUD against the receipt.')
    return dict(currency='AUD',currency_status='default',currency_evidence='AUD is the workspace default; no other currency was specified. You can change it.')
