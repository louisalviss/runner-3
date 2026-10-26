#!/usr/bin/env python3
"""Recheck bounded Flippa-organic DD only with verified historical source + auth.
No new Flippa capture, no provider call during throttle, no website purchase.
"""
from __future__ import annotations
import datetime,fcntl,json,pathlib,subprocess,time
from zoneinfo import ZoneInfo
import semrush_gap_repair as sem
from flippa_semrush_bridge import inspect

ROOT=pathlib.Path('/var/lib/acquisition-radar-scan')
OUT=pathlib.Path('/var/lib/opportunity-daily')
STATE=OUT/'flippa-sem-repair-state.json'
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
FIRST=datetime.date(2026,10,23)

def read(p):
    try:return json.loads(pathlib.Path(p).read_text(encoding='utf8'))
    except (ValueError,OSError):return {}

def eligible(day,root=ROOT,out=OUT):
    v=read(out/(day+'-research-queue.json'))
    if v.get('date_vn')!=day or v.get('schema')!='opportunity-daily-v2':
        return None
    if (v.get('seo') or {}).get('provider_status')!='PASS' or (v.get('seo') or {}).get('terminal_status')!='PASS':
        return None
    if (v.get('flippa') or {}).get('status')!='PASS':
        return None
    if (v.get('flippa_detail') or {}).get('status') not in ('PASS','PASS_EMPTY'):
        return None
    cross=v.get('flippa_semrush') or {}
    if cross.get('status') in ('PASS','PASS_EMPTY'):return None
    if cross.get('status') not in ('PARTIAL','BLOCKED'):return None
    deep=root/('flippa-deep-'+day.replace('-','')+'.json')
    if not deep.is_file():return None
    details=read(deep)
    if not isinstance(details,list) or not details or not all(x.get('status')==200 and x.get('challenge')=='NONE' for x in details):return None
    return {'day':day,'flippa':v['flippa'],'deep':deep,'old_status':cross['status'],'items':len(details)}

def process():
    now=datetime.datetime.now(TZ)
    ticket=sem.handoff_ticket()
    if not ticket:return {'state':'AWAITING_VERIFIED_HUMAN_AUTH'}
    limit=read(sem.COOLDOWN).get('until_epoch')
    try:
        if limit and float(limit)>time.time():
            return {'state':'PROVIDER_COOLDOWN','seconds_remaining':int(float(limit)-time.time())}
    except (ValueError,TypeError):return {'state':'COOLDOWN_INVALID_FAIL_CLOSED'}
    history=read(STATE)
    attempts=history.get('attempts') or {}
    candidates=[]
    # Never backfill current-date Flippa using a historical window.
    for delta in range(max(0,(now.date()-FIRST).days)):
        date=FIRST+datetime.timedelta(days=delta)
        choice=eligible(date.isoformat())
        if choice:candidates.append(choice)
    if not candidates:return {'state':'NO_ELIGIBLE_FLIPPA_CROSS_BACKLOG'}
    choice=next((x for x in candidates if attempts.get(x['day'],{}).get('handoff_event')!=ticket),None)
    if not choice:return {'state':'ALREADY_ATTEMPTED_WITH_HANDOFF','pending_days':[x['day'] for x in candidates]}
    with sem.LOCK.open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'PROVIDER_PIPELINE_BUSY'}
        if sem.handoff_ticket()!=ticket:return {'state':'HANDOFF_CHANGED'}
        check=eligible(choice['day'])
        if not check:return {'state':'SOURCE_NO_LONGER_ELIGIBLE'}
        day=choice['day']
        attempts[day]={'status':'ATTEMPT_STARTED','handoff_event':ticket,'started_at':now.isoformat(),'source_status':choice['old_status']}
        sem.atomic(STATE,{'schema':'flippa-sem-repair-v1','attempts':attempts})
        result={'day':day,'status':'UNVERIFIED','previous':choice['old_status']}
        try:
            new=inspect(day,check['flippa'],check['deep'],output_root=ROOT,max_domains=2,timeout=150)
            result.update({'cross_status':new['status'],'cross_counts':new['counts']})
            if new['status'] in ('PASS','PASS_EMPTY'):
                cmd=['python3','/var/lib/acquisition-radar-scan/opportunity_daily.py','--date',day,'--checkpoint-only']
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=180,check=False)
                result['checkpoint_exit']=run.returncode
                if run.returncode==0:
                    checkup=subprocess.run(['python3','/var/lib/acquisition-radar-scan/daily_acceptance.py','--date',day],capture_output=True,text=True,timeout=30,check=False)
                    result['acceptance_exit']=checkup.returncode
                    result['status']='REPAIRED_ACCEPTANCE_PASS' if checkup.returncode==0 else 'REPAIRED_OTHER_GAPS'
                else:result['status']='CROSS_PASS_CHECKPOINT_PENDING'
            else:
                result['status']='PROVIDER_BLOCKED_OR_PARTIAL'
        except (OSError,ValueError,subprocess.TimeoutExpired) as ex:
            result['reason']=type(ex).__name__
        result['completed_at']=datetime.datetime.now(TZ).isoformat()
        attempts[day]={'handoff_event':ticket,**result}
        sem.atomic(STATE,{'schema':'flippa-sem-repair-v1','attempts':attempts})
        return result

if __name__=='__main__':
    print(json.dumps(process(),ensure_ascii=False))
