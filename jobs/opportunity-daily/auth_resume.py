#!/usr/bin/env python3
"""Resume the SAME day's stored Semrush shortlist only after a genuine completed human handoff.
Never refresh the discovery corpus, bypass CAPTCHA, auto-login or replay a previous day.
"""
from __future__ import annotations
import datetime,json,pathlib,subprocess,hashlib,fcntl,os
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
    q=SEO/(day+'-semrush-queue.json')
    s=SEO/(day+'-semrush-results.json')
    z=load(q);r=load(s)
    if z.get('date')!=day or z.get('scan_terminal') is not True or not z.get('items') or z.get('count')!=len(z['items']) or z.get('scanned')!=z.get('added_total'):
        return {'state':'NO_COMPLETE_SAME_DAY_QUEUE'}
    if r.get('status')=='PASS':
        return {'state':'ALREADY_PASS'}
    if r.get('status')!='BLOCKED':
        return {'state':'NOT_AUTH_BLOCKED','reason':r.get('status')}
    reason=str(r.get('global_blocker') or '')
    if not any(t in reason for t in ('SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_LOGIN_CHALLENGE','NOX_LOGIN_FORM_MISSING','SEMRUSH_HUMAN_HANDOFF_ACTIVE')):
        return {'state':'NOT_HUMAN_AUTH_BLOCKER'}
    if not LOG.is_file() or LOG.stat().st_mtime <= s.stat().st_mtime:
        return {'state':'NO_NEW_HUMAN_HANDOFF'}
    events=[]
    for line in LOG.read_text(encoding='utf8').splitlines()[-8:]:
        try:events.append(json.loads(line))
        except ValueError:pass
    if not any(x.get('event')=='HUMAN_HANDOFF_RESULT' and x.get('status')=='CAPTCHA_ACCEPTED' and x.get('ok') is True and x.get('same_session') is True for x in events):
        return {'state':'NO_ACCEPTED_SAME_SESSION_HANDOFF'}
    if datetime.datetime.fromtimestamp(LOG.stat().st_mtime,ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()!=day:
        return {'state':'STALE_HANDOFF_DAY'}
    ticket=hashlib.sha256((str(LOG.stat().st_mtime_ns)+'|'+str(s.stat().st_mtime_ns)+'|'+day).encode()).hexdigest()
    if load(MARKER).get('ticket')==ticket:
        return {'state':'ALREADY_ATTEMPTED_AFTER_HANDOFF'}
    return {'state':'READY','ticket':ticket,'items':len(z['items'])}

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
        p=subprocess.run([PYTHON,'/var/lib/seotrends-public/scripts/semrush_daily.py','--date',day,'--per-domain-timeout','180'],capture_output=True,text=True,timeout=1500)
        sem=load(SEO/(day+'-semrush-results.json'))
        result={'day':day,'ticket':check['ticket'],'export_status':sem.get('status'),'export_pass':sem.get('pass_count'),'state':'RETRY_FAILED'}
        if sem.get('status')=='PASS':
            t=subprocess.run([PYTHON,'/var/lib/seotrends-public/scripts/terminal_funnel.py','--date',day],text=True,capture_output=True,timeout=1200)
            term=load(SEO/(day+'-terminal-verdicts.json'))
            result['serp_status']=term.get('status')
            if term.get('status')=='PASS':
                result['state']='SOURCE_RECOVERED'
                # This already-existing daily merger uses the cached Flippa source, and now auto-publishes.
                op=subprocess.run([PYTHON,'/var/lib/acquisition-radar-scan/opportunity_daily.py','--date',day,'--run-flippa'],capture_output=True,text=True,timeout=360)
                result['daily_returncode']=op.returncode
                result['daily_output_tail']=(op.stdout or '')[-300:]
                if op.returncode!=0: result['state']='SOURCE_RECOVERED_DAILY_PARTIAL'
        m=MARKER.with_suffix('.tmp');m.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');m.replace(MARKER)
        return {k:v for k,v in result.items() if k!='ticket'}

if __name__=='__main__':
    day=datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
    print(json.dumps(resume(day),ensure_ascii=False))
