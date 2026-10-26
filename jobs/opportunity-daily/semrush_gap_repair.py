#!/usr/bin/env python3
"""Bounded, source-preserving Semrush/SERP catch-up after verified HUMAN handoff.
Never starts captcha solving, scrapes social media, writes discovery snapshots,
or promotes a candidate to BUY/BUILD. Exactly one historical date each run.
"""
from __future__ import annotations
import datetime,hashlib,fcntl,json,pathlib,os,subprocess,time
from zoneinfo import ZoneInfo

S=pathlib.Path('/var/lib/seotrends-public/scans')
O=pathlib.Path('/var/lib/opportunity-daily')
HANDOFF=pathlib.Path('/run/semrush-user-handoff/active.jsonl')
LOCK=pathlib.Path('/run/seotrends-github-fallback.lock')
STATE=O/'semrush-gap-repair-state.json'
COOLDOWN=pathlib.Path('/var/lib/semrush-research/config/provider-rate-limit.json')
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
FIRST=datetime.date(2026,10,18)
DAY_CAP=25
WINDOW_DAYS=14

def read(path):
    try:return json.loads(path.read_text(encoding='utf8'))
    except (OSError,ValueError):return {}

def atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    os.replace(tmp,path)

def handoff_ticket():
    if not HANDOFF.is_file():return None
    age=time.time()-HANDOFF.stat().st_mtime
    if not (0<=age<=18*3600):return None
    events=[]
    for line in HANDOFF.read_text(encoding='utf8').splitlines()[-16:]:
        try:events.append(json.loads(line))
        except ValueError:pass
    if not any(x.get('event')=='HUMAN_HANDOFF_RESULT' and
               x.get('ok') is True and x.get('status')=='CAPTCHA_ACCEPTED' and
               x.get('same_session') is True and x.get('service')=='semrush' and
               x.get('profile')=='noxtools-main' and x.get('auth_verified') is True
               for x in events):
        return None
    return hashlib.sha256(HANDOFF.read_bytes()).hexdigest()

def eligible(day):
    q=read(S/(day+'-semrush-queue.json'))
    sr=read(S/(day+'-semrush-results.json'))
    te=read(S/(day+'-terminal-verdicts.json'))
    items=q.get('items') or []
    if not (q.get('date')==day and q.get('scan_terminal') is True
            and q.get('scanned')==q.get('added_total')
            and q.get('count')==len(items) and 0<len(items)<=DAY_CAP):
        return None
    if sr.get('status')=='PASS' and te.get('status')=='PASS':return None
    reason=str(sr.get('global_blocker') or '')
    accepted=('NOX_DASHBOARD_CHALLENGE','SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_LOGIN_CHALLENGE','NOX_LOGIN_REQUIRED','SEMRUSH_AUTO_RECOVERY_FAILED','Session expired')
    if sr.get('status')=='BLOCKED' and any(m in reason for m in accepted):
        return {'day':day,'mode':'EXPORT_THEN_SERP','shortlist':len(items),'reason':'PROVIDER_AUTH'}
    # Some historic exports partially succeeded before a transient broker error.
    # Reuse their cached exports and retry only the failed domains; never auto-
    # retry quota/report-limit responses, whose repeated calls could violate caps.
    if sr.get('status')=='PARTIAL':
        failed=[x for x in sr.get('items') or [] if x.get('status')!='PASS']
        transient=('SEMRUSH_BROKER_RUNTIME_ERROR','Something went wrong. Please try again.',
                   'PROFILE_LAUNCH_TIMEOUT','SEMRUSH_RESOURCE_ADMISSION_DENIED')
        quota=('Limits exceeded','SEMRUSH_RATE_LIMIT','SEMRUSH_REPORT_LIMIT','BLOCKED_QUOTA_LIMIT','Report limit reached')
        if failed and len(failed)<=5 and all(any(t in str(x.get('reason') or '') for t in transient)
                                            and not any(q in str(x.get('reason') or '') for q in quota)
                                            for x in failed):
            return {'day':day,'mode':'EXPORT_THEN_SERP','shortlist':len(items),'reason':'PARTIAL_TRANSIENT_ONLY'}
    if sr.get('status')=='PASS' and te.get('status')!='PASS':
        return {'day':day,'mode':'SERP_ONLY','shortlist':len(items),'reason':'TERMINAL_NOT_PASS'}
    return None

def process():
    now=datetime.datetime.now(TZ).date()
    event=handoff_ticket()
    if not event:return {'state':'AWAITING_VERIFIED_HUMAN_AUTH'}
    limit=read(COOLDOWN).get('until_epoch')
    try:
        if limit and float(limit)>time.time():
            return {'state':'PROVIDER_COOLDOWN','seconds_remaining':int(float(limit)-time.time())}
    except (ValueError,TypeError):pass
    st=read(STATE)
    attempts=st.get('attempts') or {}
    days=[]
    for delta in range((now-FIRST).days+1):
        date=FIRST+datetime.timedelta(days=delta)
        if (now-date).days>WINDOW_DAYS:continue
        item=eligible(date.isoformat())
        if item:days.append(item)
    if not days:return {'state':'NO_ELIGIBLE_BACKLOG','handoff_verified':True}
    chosen=None
    for x in days:
        if attempts.get(x['day'],{}).get('handoff_event')!=event:
            chosen=x;break
    if not chosen:return {'state':'EVENT_ALREADY_USED_FOR_ALL_PENDING_DAYS','remaining':len(days)}
    LOCK.parent.mkdir(parents=True,exist_ok=True)
    with LOCK.open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'SOURCE_PIPELINE_BUSY'}
        if handoff_ticket()!=event:return {'state':'HANDOFF_CHANGED'}
        if not eligible(chosen['day']):return {'state':'SOURCE_ALREADY_RECOVERED'}
        day=chosen['day']
        attempts[day]={'handoff_event':event,'status':'ATTEMPT_STARTED','mode':chosen['mode'],
                       'started_at':datetime.datetime.now(TZ).isoformat(),'shortlist':chosen['shortlist']}
        atomic(STATE,{'schema':'semrush-gap-repair-v1','attempts':attempts})
        result={'day':day,'mode':chosen['mode'],'status':'NOT_RECOVERED','shortlist':chosen['shortlist']}
        try:
            if chosen['mode']=='EXPORT_THEN_SERP':
                proc=subprocess.run(['python3','/var/lib/seotrends-public/scripts/semrush_daily.py','--date',day,'--per-domain-timeout','180'],capture_output=True,text=True,timeout=950,check=False)
                result['semrush_exit']=proc.returncode
            sr=read(S/(day+'-semrush-results.json'))
            result['semrush_status']=sr.get('status')
            result['semrush_pass_count']=sr.get('pass_count')
            if sr.get('status')=='PASS':
                proc=subprocess.run(['python3','/var/lib/seotrends-public/scripts/terminal_funnel.py','--date',day],capture_output=True,text=True,timeout=480,check=False)
                result['serp_exit']=proc.returncode
                te=read(S/(day+'-terminal-verdicts.json'))
                result['serp_status']=te.get('status')
                if te.get('status')=='PASS':
                    p=subprocess.run(['python3','/var/lib/acquisition-radar-scan/opportunity_daily.py','--date',day,'--checkpoint-only'],capture_output=True,text=True,timeout=150,check=False)
                    result['daily_checkpoint_exit']=p.returncode
                    result['status']='RECOVERED_CHECKPOINTED' if p.returncode==0 else 'RECOVERED_CHECKPOINT_PENDING'
                    subprocess.run(['python3','/var/lib/acquisition-radar-scan/daily_acceptance.py','--date',day],capture_output=True,text=True,timeout=30)
        except (OSError,subprocess.TimeoutExpired) as err:
            result['reason']=type(err).__name__
        result['completed_at']=datetime.datetime.now(TZ).isoformat()
        attempts[day]={'handoff_event':event,**result}
        atomic(STATE,{'schema':'semrush-gap-repair-v1','attempts':attempts})
        try:subprocess.run(['python3','/var/lib/acquisition-radar-scan/audit_gap_ledger.py'],capture_output=True,text=True,timeout=30,check=False)
        except (OSError,subprocess.TimeoutExpired):pass
        return result

if __name__=='__main__':
    print(json.dumps(process(),ensure_ascii=False))
