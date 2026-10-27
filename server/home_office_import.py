"""Reviewable WFH imports with original evidence and atomic, duplicate-safe saves."""
import csv
import hashlib
import io
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path

from flask import jsonify, request
from werkzeug.exceptions import HTTPException
import workspace_time

MAX_ROWS = 1000
DATE = r'\d{4}-\d{2}-\d{2}'
CLOCK = r'\d{2}:\d{2}'


def minutes(value):
    match = re.fullmatch(r'\s*(?:(\d+(?:\.\d+)?)h)?\s*(?:(\d+)m)?\s*',value)
    if not match or not any(match.groups()): raise ValueError('Unrecognised duration in the report.')
    total = Decimal(match[1] or 0) * 60 + Decimal(match[2] or 0)
    if total != int(total): raise ValueError('The report contains a duration smaller than one minute.')
    return int(total)


def parse_pdf(text):
    if 'WFH Logbook Australia' not in text or 'WFH hours log' not in text:
        raise ValueError('Use a WFH Logbook Australia PDF or an Expense Pilot diary CSV. Scanned PDFs and other report layouts are not supported.')
    match = re.search(r'financial year\s+(\d{4})',text)
    if not match: raise ValueError('The financial year could not be read from this report.')
    year = int(match[1])-1
    section = text.split('WFH hours log',1)[1].split('WFH notes log',1)[0]
    entries=[];current=None
    for line in section.replace('\f','\n').splitlines():
        match = re.match(r'^\s*('+DATE+r')\s+((?:\d+(?:\.\d+)?h)?\s*(?:\d+m)?)\s+('+CLOCK+r')\s+('+CLOCK+r')(.*)$',line)
        if match:
            when,duration,start,end,tail=match.groups()
            dates=re.findall(DATE,tail)
            before=tail.split(dates[0],1)[0].strip() if dates else tail.strip()
            breaks=minutes(before) if before else 0
            current=dict(date=when,start_time=start,end_time=end,break_minutes=breaks,reported_minutes=minutes(duration),
                         activity='',scope='',source_logged=dates[0] if dates else '',source_updated=dates[1] if len(dates)>1 else '')
            entries.append(current)
            if len(entries)>MAX_ROWS: raise ValueError('Import up to 1,000 sessions at a time.')
        elif re.match(r'^\s*'+DATE+r'\s',line):
            raise ValueError('A session row could not be read. No hours were imported. Use a CSV or enter that report manually.')
        elif current and re.fullmatch(r'\s*'+CLOCK+r'(?:\s+'+CLOCK+r')?\s*',line):
            clocks=re.findall(CLOCK,line)
            if current['source_logged']: current['source_logged']+=' '+clocks[0]
            if current['source_updated'] and len(clocks)>1: current['source_updated']+=' '+clocks[1]
    if not entries: raise ValueError('No readable WFH sessions were found in this PDF.')
    # Do not silently import a partial table or trust the report's monetary total.
    total=re.search(r'Year total\s*:\s*([\d.h m]+)\(',text)
    if not total or minutes(total[1].strip()) != sum(e['reported_minutes'] for e in entries):
        raise ValueError('The session hours do not match the report total. No hours were imported. Check the original or use a CSV.')
    notes={};current=None;left=right=None
    if 'WFH notes log' in text:
        for line in text.split('WFH notes log',1)[1].replace('\f','\n').splitlines():
            if 'Workday notes' in line and 'Logged' in line:
                left=line.index('Workday notes');right=line.index('Logged');continue
            if left is None: continue
            match=re.match(r'^\s*('+DATE+r')\s',line)
            if match: current=match[1];notes.setdefault(current,[])
            fragment=line[left:right].strip()
            if current and fragment and not re.fullmatch(r'\d+|'+CLOCK,fragment) and not fragment.startswith('Disclaimer:'):
                notes[current].append(fragment.replace('•','-'))
    for index,e in enumerate(entries):
        e['index']=index;e['activity']='\n'.join(notes.get(e['date'],[]))
        if len(e['activity'])>1000: raise ValueError('A work note is longer than 1,000 characters. Use a shortened CSV entry.')
        if not f'{year}-07-01'<=e['date']<=f'{year+1}-06-30': raise ValueError('A session is outside the report financial year.')
    return dict(format='WFH Logbook Australia PDF',year=year,entries=entries,
                reported_minutes=sum(e['reported_minutes'] for e in entries),source_timezone='Not specified in PDF')


def parse_csv(raw):
    if len(raw)>2*1024*1024: raise ValueError('Use a diary CSV no larger than 2 MB.')
    try:
        reader=csv.reader(io.StringIO(raw.decode('utf-8-sig')));header=None;entries=[]
        for row in reader:
            if header is None:
                if {'Date','Start','End','Activity'}<=set(row): header=row
                continue
            if not row or row[0] in ('Bill ID','Allowance ID','Source','History UTC'): break
            item=dict(zip(header,row))
            if not item.get('Date'): continue
            def text(key):
                value=item.get(key,'')
                return value[1:] if len(value)>1 and value[0]=="'" and value[1] in '=+-@\t\r' else value
            entry=dict(index=len(entries),date=text('Date'),start_time=text('Start'),end_time=text('End'),
                       break_minutes=int(item.get('Break minutes') or 0),scope=text('Scope'),activity=text('Activity'),
                       source_logged=text('Created UTC'),source_updated=text('Updated UTC'),timezone=text('Timezone'))
            if len(entry['activity'])>1000: raise ValueError('Keep each work description within 1,000 characters.')
            entries.append(entry)
            if len(entries)>MAX_ROWS: raise ValueError('Import up to 1,000 sessions at a time.')
        if not header or not entries: raise ValueError('Use an Expense Pilot diary CSV, including its Date, Start, End and Activity headings.')
        return dict(format='Expense Pilot diary CSV',year=None,entries=entries,reported_minutes=None,source_timezone='Saved row timezone; source timestamps are UTC')
    except (UnicodeError,csv.Error,ValueError) as exc:
        raise ValueError(str(exc) if isinstance(exc,ValueError) else 'The diary CSV could not be read.') from None


def uploaded_report():
    from app import fail
    from document_processing import process
    from tax_documents import inspect_file, MAX_FILE
    upload=request.files.get('file')
    if not upload: fail('Choose a WFH report to import.')
    raw=upload.read(MAX_FILE+1);filename,content_type=inspect_file(upload.filename or '',raw)
    extension=Path(filename).suffix.lower()
    try:
        if extension=='.pdf': parsed=parse_pdf(process(raw,extension,'extract')['text'])
        elif extension=='.csv': parsed=parse_csv(raw)
        else: raise ValueError('Choose a WFH Logbook Australia PDF or an Expense Pilot diary CSV.')
    except ValueError as exc: fail(str(exc),422)
    return raw,filename,content_type,parsed


def reference(digest,index):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'expense-pilot:wfh-import:'+digest+':'+str(index)))


def duplicate_or_overlap(values,ref):
    from app import one
    from home_office import owner_id
    old=one('SELECT id,deleted,scope FROM home_office_entries WHERE user_id=? AND client_ref=?',(owner_id(),ref))
    if old: return ('removed' if old['deleted'] else 'duplicate'),old
    matches=one('SELECT id,scope FROM home_office_entries WHERE user_id=? AND deleted=0 AND start_at=? AND end_at=? AND break_minutes=?',
                (owner_id(),values['start_at'],values['end_at'],values['break_minutes']))
    if matches: return 'duplicate',matches
    overlap=one('SELECT id,scope FROM home_office_entries WHERE user_id=? AND deleted=0 AND start_at<? AND end_at>?',
                (owner_id(),values['end_at'],values['start_at']))
    return ('overlap',overlap) if overlap else ('ready',None)


def register(app,auth):
    from app import db,fail
    from home_office import entry_values,financial_year,owner_id
    import home_office
    from tax_documents import store_original,folder

    @app.post('/api/home-office/import/preview')
    @auth('owner','tax_agent')
    def preview_import():
        raw,filename,content_type,parsed=uploaded_report();digest=hashlib.sha256(raw).hexdigest()
        zone=workspace_time.validate(request.form.get('timezone') or workspace_time.name())
        intervals=[]
        for item in parsed['entries']:
            item['timezone']=item.get('timezone') or zone;item['issues']=[]
            try:
                value=entry_values({**item,'scope':item['scope'] or 'work','activity':item['activity'] or 'Pending review'})
                item['minutes']=(value['end_at']-value['start_at'])//60-value['break_minutes']
                item['status'],item['existing']=duplicate_or_overlap(value,reference(digest,item['index']))
                if item['status']=='ready' and any(value['start_at']<end and value['end_at']>start for start,end in intervals):
                    item['status']='overlap';item['issues'].append('This row overlaps another session in this file. Select only the correct hours.')
                intervals.append((value['start_at'],value['end_at']))
                if item.get('reported_minutes') is not None and item['reported_minutes']!=item['minutes']:
                    item['issues'].append('Reported hours do not match these times and breaks. Review before selecting this row.')
                    if item['status']=='ready': item['status']='invalid'
            except HTTPException as exc:
                item.update(status='invalid',minutes=None,existing=None);item['issues'].append(exc.description)
        return jsonify(**parsed,filename=filename,sha256=digest,timezone=zone)

    @app.post('/api/home-office/import')
    @auth('owner','tax_agent')
    def commit_import():
        raw,filename,content_type,parsed=uploaded_report();digest=hashlib.sha256(raw).hexdigest()
        try: selected=json.loads(request.form.get('entries','null'))
        except ValueError: fail('Review the import and try again.')
        if request.form.get('confirmed')!='true' or not isinstance(selected,list) or not 1<=len(selected)<=MAX_ROWS:
            fail('Select and confirm at least one reviewed session.')
        source={e['index']:e for e in parsed['entries']};seen=set();new=[];skipped=[];did=None;duplicate=True
        db().execute('BEGIN IMMEDIATE')
        try:
            for item in selected:
                index=item.get('index') if isinstance(item,dict) else None
                if type(index) is not int or index not in source or index in seen: fail('The selected report rows are invalid.')
                seen.add(index);ref=reference(digest,index)
                value=entry_values(item)
                status,old=duplicate_or_overlap(value,ref)
                if status in ('duplicate','removed'):
                    skipped.append(dict(index=index,status=status,id=old['id']));continue
                if status=='overlap' or any(value['start_at']<v['end_at'] and value['end_at']>v['start_at'] for _,_,v in new):
                    fail('A selected session overlaps existing or selected hours. Review the rows; nothing was imported.',409)
                new.append((index,ref,value))
            if new:
                years=sorted({financial_year(v['date']) for _,_,v in new})
                did,duplicate=store_original(raw,filename,content_type,(('WFH import — '+filename)[:200],'other',years[0] if len(years)==1 else None,'Original report supporting imported WFH hours.'))
                for index,ref,value in new:
                    fingerprint=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
                    names=','.join(value);marks=','.join('?' for _ in value)
                    cursor=db().execute(f'INSERT INTO home_office_entries(user_id,client_ref,fingerprint,{names}) VALUES (?,?,?,{marks})',
                                        (owner_id(),ref,fingerprint,*value.values()))
                    provenance=dict(document_id=did,filename=filename,sha256=digest,format=parsed['format'],
                                    original=source[index],source_timezone=parsed['source_timezone'])
                    home_office.history('entry:'+str(cursor.lastrowid),'entry imported',after={**value,'import_source':provenance})
            db().commit()
        except BaseException:
            db().rollback()
            if did and not duplicate: (folder()/did).unlink(missing_ok=True)
            raise
        return jsonify(imported=len(new),skipped=skipped,document_id=did,years=sorted({financial_year(v['date']) for _,_,v in new}))
