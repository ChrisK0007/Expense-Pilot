"""Non-posting checks against payslip net/YTD figures and annual statements."""
from collections import defaultdict
from datetime import date, timedelta
from flask import jsonify, request
from workflow_core import body, checked, preview, fiscal, integer, write_access


def summary(year):
    from app import rows, record_user_id
    year,start,end=fiscal(year)
    payments=rows('SELECT e.*,d.net_cents,d.ytd_gross_cents,d.ytd_withheld_cents,d.version AS details_version FROM employment_income e LEFT JOIN income_details d ON d.income_id=e.id WHERE date BETWEEN ? AND ? ORDER BY date,id',(start,end))
    statements=rows('SELECT * FROM annual_income_checks WHERE user_id=? AND year=?',(record_user_id(),year))
    groups=defaultdict(list)
    for p in payments: groups[p['employer'].strip().casefold()].append(p)
    for s in statements: groups.setdefault(s['employer'].strip().casefold(),[])
    result=[]
    for key,records in groups.items():
        slip=[p for p in records if p['record_kind']!='income_statement']
        flags=[];gaps=[]
        periods=sorted((p for p in slip if p['period_start'] and p['period_end']),key=lambda p:p['period_start'])
        coverage_end=None
        for p in periods:
            if coverage_end and p['period_start']>(date.fromisoformat(coverage_end)+timedelta(days=1)).isoformat():
                gaps.append(dict(start=(date.fromisoformat(coverage_end)+timedelta(days=1)).isoformat(),end=(date.fromisoformat(p['period_start'])-timedelta(days=1)).isoformat()))
            if coverage_end and p['period_start']<=coverage_end: flags.append('Pay periods overlap; check adjustments or duplicate uploads.')
            coverage_end=max(coverage_end or '',p['period_end'])
        if any(not p['period_start'] or not p['period_end'] for p in slip): flags.append('Some pay-period dates are missing; gaps cannot be checked completely.')
        if gaps: flags.append('There are gaps between recorded pay periods. Check missing slips or breaks in employment.')
        latest=next((p for p in reversed(slip) if p['ytd_gross_cents'] is not None or p['ytd_withheld_cents'] is not None),None)
        comparison=None
        if latest:
            through=[p for p in slip if p['date']<=latest['date']]
            comparison=dict(date=latest['date'],gross_difference_cents=None if latest['ytd_gross_cents'] is None else latest['ytd_gross_cents']-sum(p['gross_cents'] for p in through),
                            withheld_difference_cents=None if latest['ytd_withheld_cents'] is None else latest['ytd_withheld_cents']-sum(p['withheld_cents'] for p in through))
            if any(comparison[k] not in (None,0) for k in ('gross_difference_cents','withheld_difference_cents')): flags.append('The latest YTD figures differ from recorded payments through that date.')
        statement=next((s for s in statements if s['employer'].strip().casefold()==key),None)
        total_gross=sum(p['gross_cents'] for p in slip);total_withheld=sum(p['withheld_cents'] for p in slip)
        annual=None if not statement else dict(**statement,gross_difference_cents=statement['gross_cents']-total_gross,withheld_difference_cents=statement['withheld_cents']-total_withheld)
        if annual and (annual['gross_difference_cents'] or annual['withheld_difference_cents']): flags.append('The annual statement differs from recorded payments.')
        result.append(dict(employer=records[0]['employer'] if records else statement['employer'],payments=records,gross_cents=total_gross,withheld_cents=total_withheld,gaps=gaps,flags=list(dict.fromkeys(flags)),ytd=comparison,annual=annual))
    return dict(year=year,employers=result)


def register(app,auth):
    @app.get('/api/workflows/income/<int:year>', endpoint='income_checks_checks')
    @auth('owner','tax_agent')
    def checks(year): return jsonify(summary(year))

    @app.route('/api/workflows/income-details/<int:eid>',methods=['GET','PUT'], endpoint='income_checks_details')
    @auth('owner','tax_agent')
    def details(eid):
        from app import db, one, money, fail, audit
        if request.method=='PUT': write_access();db().execute('BEGIN IMMEDIATE')
        income=one('SELECT * FROM employment_income WHERE id=?',(eid,))
        if not income: fail('Income record not found.',404)
        saved=one('SELECT * FROM income_details WHERE income_id=?',(eid,))
        state=dict(income=income,details=saved)
        if request.method=='GET': return jsonify(**state,token=preview('income-details',state))
        d=body();checked(d.get('token'),'income-details',state)
        values=[]
        for key in ('net','ytd_gross','ytd_withheld'):
            value=None if d.get(key) in ('',None) else money(d[key])
            if value is not None and value<0: fail('Pay figures cannot be negative.')
            values.append(value)
        if one('SELECT 1 FROM bank_reconciliations WHERE income_id=?',(eid,)) and (not saved or saved['net_cents']!=values[0]): fail('Undo the deposit match before changing net pay.',409)
        db().execute('INSERT INTO income_details(income_id,net_cents,ytd_gross_cents,ytd_withheld_cents) VALUES (?,?,?,?) ON CONFLICT(income_id) DO UPDATE SET net_cents=excluded.net_cents,ytd_gross_cents=excluded.ytd_gross_cents,ytd_withheld_cents=excluded.ytd_withheld_cents,version=income_details.version+1',[eid]+values)
        audit('payslip reference figures saved',eid);db().commit();return jsonify(ok=True)

    @app.post('/api/workflows/income/<int:year>/statement', endpoint='income_checks_statement')
    @auth('owner','tax_agent')
    def statement(year):
        from app import db, money, fail, record_user_id, textval, audit
        write_access();year,_,_=fiscal(year);d=body();employer=textval(d.get('employer'),200)
        gross=money(d.get('gross'));withheld=money(d.get('withheld'))
        if not employer or gross<0 or not 0<=withheld<=gross: fail('Enter an employer and valid annual gross/withheld figures.')
        if d.get('reference_only') is not True: fail('Confirm this is a comparison only, not another income payment.')
        db().execute('INSERT INTO annual_income_checks(user_id,year,employer,gross_cents,withheld_cents,notes) VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,year,employer) DO UPDATE SET gross_cents=excluded.gross_cents,withheld_cents=excluded.withheld_cents,notes=excluded.notes',
                     (record_user_id(),year,employer.lower(),gross,withheld,textval(d.get('notes'),2000)))
        audit('annual statement comparison saved',year);db().commit();return jsonify(summary(year))
