#!/usr/bin/env python3
"""Resume the SAME day's stored Semrush shortlist only after a verified human handoff.
Never refresh the discovery corpus, bypass CAPTCHA, auto-login or replay a previous day.
"""
from __future__ import annotations
import datetime,json,pathlib,subprocess,hashlib,fcntl,os,time,argparse
from zoneinfo import ZoneInfo
SEO=pathlib.Path('/var/lib/seotrends-public/scans')
LOG=pathlib.Path('/run/semrush-user-handoff/active.jsonl')
MARKER=pathlib.Path('/var/lib/opportunity-daily/semrush-auth-resume-attempt.json')
LOCK=pathlib.Path('/run/seotrends-github-fallback.lock')
PYTHON='python3'

def load(path):
    try:return json.loads(path.read_text(encoding='utf8'))
    except (OSError,ValueError):return {}

def decision(day):
    """One handoff event authorizes at most one recovery attempt for a bounded pending batch."""
    today=datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    try: target=datetime.date.fromisoformat(day)
    except ValueError: return {'state':'INVALID_DAY'}
    age_days=(today-target).days
    if not 0 <= age_days <= 7:
        return {'state':'OUTSIDE_RECOVERY_WINDOW'}
    q=SEO/(day+'-semrush-queue.json')
    s=SEO/(day+'-semrush-results.json')
    t=SEO/(day+'-terminal-verdicts.json')
    z=load(q); r=load(s); terminal=load(t)
    if (z.get('date')!=day or z.get('scan_terminal') is not True
        or not z.get('items') or z.get('count')!=len(z['items'])
        or z.get('scanned')!=z.get('added_total')):
        return {'state':'NO_COMPLETE_SAME_DAY_QUEUE'}
    if r.get('status')=='PASS':
        if terminal.get('status')=='PASS':
            return {'state':'ALREADY_PASS'}
        last=terminal.get('serp_run') or {}
        evidence=last.get('state') or {}
        trigger=str((evidence.get('runtime_recovery') or {}).get('trigger') or '')
        auth_triggers={'SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_DASHBOARD_CHALLENGE','NOX_LOGIN_REQUIRED'}
        if not (evidence.get('stage')=='BLOCKED_LIVE_AUTH' and
                (trigger in auth_triggers or evidence.get('blocker') in
                 (auth_triggers | {'SEMRUSH_ONE_SHOT_RECOVERY_FAILED'}))):
            return {'state':'NOT_AUTH_BLOCKED_SERP','reason':evidence.get('blocker')}
        mode='SERP_ONLY'
        last_attempt=t
    elif r.get('status')=='BLOCKED':
        if age_days>1:
            return {'state':'OUTSIDE_EXPORT_RECOVERY_WINDOW'}
        reason=str(r.get('global_blocker') or '')
        if not any(x in reason for x in ('SEMRUSH_LIVE_AUTH_UNAVAILABLE', 'NOX_LOGIN_CHALLENGE',
                                         'NOX_LOGIN_FORM_MISSING','NOX_DASHBOARD_CHALLENGE',
                                         'NOX_LOGIN_REQUIRED','SEMRUSH_HUMAN_HANDOFF_ACTIVE')):
            return {'state':'NOT_HUMAN_AUTH_BLOCKER'}
        mode='EXPORT_THEN_SERP'
        last_attempt=s
    else:
        return {'state':'NOT_AUTH_BLOCKED','reason':r.get('status')}
    if not LOG.is_file() or not last_attempt.is_file() or LOG.stat().st_mtime <= last_attempt.stat().st_mtime:
        return {'state':'NO_NEW_HUMAN_HANDOFF'}
    events=[]
    for line in LOG.read_text(encoding='utf8').splitlines()[-12:]:
        try: events.append(json.loads(line))
        except ValueError: pass
    valid=[x for x in events if x.get('event')=='HUMAN_HANDOFF_RESULT'
           and x.get('status')=='CAPTCHA_ACCEPTED' and x.get('ok') is True
           and x.get('same_session') is True and x.get('service')=='semrush'
           and x.get('profile')=='noxtools-main' and x.get('auth_verified') is True]
    if not valid:
        return {'state':'NO_ACCEPTED_SAME_SESSION_HANDOFF'}
    age=time.time()-LOG.stat().st_mtime
    if not 0 <= age <= 18*3600:
        return {'state':'STALE_HANDOFF'}
    ticket=hashlib.sha256((str(LOG.stat().st_mtime_ns)+'|'+day+'|'+mode).encode()).hexdigest()
    if load(MARKER).get('ticket')==ticket:
        return {'state':'ALREADY_ATTEMPTED_AFTER_HANDOFF'}
    return {'state':'READY','ticket':ticket,'items':len(z['items']),'mode':mode}

def resume(day,dry_run=False):
    check=decision(day)
    if check['state']!='READY' or dry_run:
        return {'day':day,**check}
    LOCK.parent.mkdir(exist_ok=True,parents=True)
    with LOCK.open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'day':day,'state':'SOURCE_SCANNER_BUSY'}
        recheck=decision(day)
        if recheck['state']!='READY':return {'day':day,**recheck}
        MARKER.parent.mkdir(exist_ok=True,parents=True)
        pending={'day':day,'ticket':check['ticket'],'state':'ATTEMPT_STARTED','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        temp=MARKER.with_suffix('.tmp');temp.write_text(json.dumps(pending)+'\n');temp.replace(MARKER)
        result={'day':day,'ticket':check['ticket'],'mode':check['mode'],'state':'AUTH_RECOVERY_FAILED'}
        try:
            # One broker-owned recovery after a verified human CAPTCHA event.
            auth=subprocess.run(['/usr/local/bin/semrush-noxtools-login'],capture_output=True,text=True,timeout=210,check=False)
            try: outcome=json.loads((auth.stdout or '').strip())
            except ValueError: outcome={}
            result['auth_state']=str(outcome.get('state') or 'UNVERIFIED')[:80]
            if auth.returncode!=0 or outcome.get('ok') is not True:
                result['state']='AUTH_RECOVERY_FAILED'
            else:
                result['state']='SOURCE_RECOVERY_PARTIAL'
                if check['mode']=='EXPORT_THEN_SERP':
                    subprocess.run([PYTHON,'/var/lib/seotrends-public/scripts/semrush_daily.py','--date',day,'--per-domain-timeout','180'],capture_output=True,text=True,timeout=1500,check=False)
                sem=load(SEO/(day+'-semrush-results.json'))
                result['export_status']=sem.get('status')
                result['export_pass']=sem.get('pass_count')
                if sem.get('status')=='PASS':
                    subprocess.run([PYTHON,'/var/lib/seotrends-public/scripts/terminal_funnel.py','--date',day],capture_output=True,text=True,timeout=1400,check=False)
                    term=load(SEO/(day+'-terminal-verdicts.json'))
                    result['serp_status']=term.get('status')
                    result['serp_blocker']=str((term.get('serp_run') or {}).get('reason') or '')[:100]
                    result['state']='SOURCE_RECOVERED' if term.get('status')=='PASS' else 'SOURCE_RECOVERY_PARTIAL'
                    op=subprocess.run([PYTHON,'/var/lib/acquisition-radar-scan/opportunity_daily.py','--date',day,'--checkpoint-only'],capture_output=True,text=True,timeout=360,check=False)
                    result['daily_returncode']=op.returncode
                    if op.returncode!=0: result['state']='CHECKPOINT_PUBLISH_FAILED'
        except (subprocess.TimeoutExpired, OSError) as exc:
            result['state']='RECOVERY_EXECUTION_FAILED'
            result['error_type']=type(exc).__name__
        m=MARKER.with_suffix('.tmp');m.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');m.replace(MARKER)
        return {k:v for k,v in result.items() if k!='ticket'}

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--date',default='')
    ap.add_argument('--dry-run',action='store_true')
    args=ap.parse_args()
    today=datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    day=args.date or today.isoformat()
    if not args.date and decision(day).get('state')=='NO_COMPLETE_SAME_DAY_QUEUE':
        day=(today-datetime.timedelta(days=1)).isoformat()
    print(json.dumps(resume(day,dry_run=args.dry_run),ensure_ascii=False))
