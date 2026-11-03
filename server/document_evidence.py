"""Source matches are evidence locations, never a confidence score or approval."""
import json
from flask import jsonify


def register(app,auth):
    @app.get('/api/workflows/evidence/<rid>', endpoint='document_evidence_evidence')
    @auth('owner','tax_agent')
    def evidence(rid):
        from app import DATA, receipt, one
        from document_processing import process
        r=receipt(rid);saved=one('SELECT extraction FROM receipt_details WHERE receipt_id=?',(rid,))
        extracted=json.loads(saved['extraction'] or '{}') if saved else {}
        pages=[];notice='Source highlights are text matches on up to the first 20 pages; check the label, column and current-pay basis in the original.'
        if r['mime']=='application/pdf':
            try: pages=process((DATA/'receipts'/rid).read_bytes(),'.pdf','evidence')['pages']
            except ValueError as exc: notice=str(exc)
        else: notice='This image has no local text layer. Review the original; no source position is inferred.'
        fields=[];flags=[]
        keys=('employer','date','gross','withheld','net','ytd_gross','ytd_withheld') if extracted.get('document_kind') in ('payslip','income_statement') else ('merchant','date','amount','currency')
        for key in keys:
            value=extracted.get(key);matches=[]
            if value not in ('',None):
                variants=[str(value).casefold()]
                if key in ('amount','gross','withheld','net','ytd_gross','ytd_withheld'):
                    try: variants += [f'{float(value):.2f}',f'{float(value):,.2f}']
                    except (ValueError,TypeError,OverflowError): pass
                if key=='date' and isinstance(value,str) and len(value)==10: variants.append(value[8:10]+'/'+value[5:7]+'/'+value[:4])
                for index,page in enumerate(pages,1):
                    words=page['words']
                    for i,word in enumerate(words):
                        for count in range(1,min(12,len(words)-i)+1):
                            chunk=words[i:i+count];text=' '.join(w['text'] for w in chunk).casefold().strip('$ ')
                            if text in variants:
                                matches.append(dict(page=index,x=min(w['x'] for w in chunk),y=min(w['y'] for w in chunk),right=max(w['right'] for w in chunk),bottom=max(w['bottom'] for w in chunk)))
                                break
                        if len(matches)>=30: break
                    if len(matches)>=30: break
            if value in ('',None) and key not in ('net','ytd_gross','ytd_withheld'): flags.append(key.replace('_',' ').capitalize()+' is missing.')
            fields.append(dict(key=key,value=value,matches=matches))
        gross,withheld,net=(extracted.get(k) for k in ('gross','withheld','net'))
        if all(isinstance(v,(float,int)) for v in (gross,withheld)) and withheld>gross: flags.append('Withholding exceeds gross pay.')
        if all(isinstance(v,(float,int)) for v in (gross,withheld,net)) and net>gross-withheld+0.01: flags.append('Net pay exceeds gross less withholding; check allowances, deductions and the selected columns.')
        if extracted.get('currency') not in (None,'AUD'): flags.append('The extracted currency is not AUD. Review the currency evidence before using these amounts.')
        return jsonify(fields=fields,flags=flags,pages=[dict(width=p['width'],height=p['height']) for p in pages],notice=notice)
