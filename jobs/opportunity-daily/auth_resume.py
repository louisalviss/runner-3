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
        auth_triggers={'SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_DASHBOARD_CHALLENGE',
                       'NOX_LOGIN_REQUIRED','SEMRUSH_PROXY_SESSION_EXPIRED'}
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
                                         'NOX_LOGIN_REQUIRED','SEMRUSH_HUMAN_HANDOFF_ACTIVE',
                                         'SEMRUSH_AUTO_RECOVERY_FAILED','SEMRUSH_AUTO_RECOVERY_RETRY_FAILED',
                                         'Session expired, access again from Dashboard')):
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


# Reconcile source-complete recovery through the EXISTING hourly resume timer.
# This never calls the provider, starts a browser, resets systemd failure history
# or bypasses any Semrush/NoxTools authorization gate.
POST_OUT=pathlib.Path('/var/lib/opportunity-daily')
POST_ROOT=pathlib.Path('/var/lib/acquisition-radar-scan')
POST_PROFILE_ID='c97a7500-3b11-403f-ac43-2566cdcd3fa2'
POST_CHECKPOINT=POST_ROOT/'opportunity_daily.py'
POST_ACCEPTANCE=POST_ROOT/'daily_acceptance.py'
POST_AUDIT=POST_ROOT/'audit_gap_ledger.py'

def _sha(path):
    try:return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:return None

def _newer_published_day(day):
    for p in POST_OUT.glob('????-??-??-dropbox-publish.json'):
        other=p.name[:10]
        if other>day and load(p).get('status')=='PASS':
            return other
    return ''

def _flippa_source_verified(day):
    stamp=day.replace('-','')
    source=load(POST_ROOT/('flippa-'+stamp+'-daily-state.json'))
    detail=load(POST_ROOT/('flippa-deep-'+stamp+'-state.json'))
    observed_path=POST_ROOT/('flippa-deep-'+stamp+'.json')
    try:observed=json.loads(observed_path.read_text(encoding='utf8'))
    except (OSError,ValueError):return False
    rows=source.get('pages') or []
    return bool(
        source.get('profile_id')==POST_PROFILE_ID and
        source.get('first_done') is True and source.get('recent_done') is True and
        len(set(source.get('recent_ids') or []))==500 and rows and
        all(isinstance(x,dict) and x.get('status')==200 and x.get('challenge')=='NONE' for x in rows) and
        detail.get('date')==day and detail.get('status')=='PASS' and
        detail.get('profile_id')==POST_PROFILE_ID and
        isinstance(observed,list) and len(observed)==detail.get('items') and
        all(isinstance(x,dict) and x.get('profile_id')==POST_PROFILE_ID and
            x.get('status')==200 and x.get('challenge')=='NONE' for x in observed)
    )

def post_recovery_plan(day,now=None):
    """Pure, bounded decision. The only repair targets are same-day derivatives."""
    now=now or datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    try:date=datetime.date.fromisoformat(day)
    except ValueError:return {'state':'INVALID_DAY'}
    age=(now.date()-date).days
    if age<0 or age>1:return {'state':'NOT_CURRENT_RECOVERY_WINDOW'}
    if age==0 and (now.hour,now.minute)<(10,5):
        return {'state':'WAIT_DAILY_ACCEPTANCE_WINDOW'}
    qpath=SEO/(day+'-semrush-queue.json')
    spath=SEO/(day+'-semrush-results.json')
    tpath=SEO/(day+'-terminal-verdicts.json')
    q=load(qpath);sem=load(spath);ter=load(tpath)
    items=q.get('items') or []
    passed=sem.get('items') or []
    verdicts=ter.get('verdicts') or []
    if not (q.get('date')==day and q.get('scan_terminal') is True and
            isinstance(items,list) and len(items)>0 and q.get('count')==len(items) and
            q.get('scanned')==q.get('added_total') and q.get('pending')==0 and
            sem.get('date')==day and sem.get('status')=='PASS' and
            sem.get('queue_count')==len(items) and sem.get('pass_count')==len(items) and
            sem.get('fail_count')==0 and sem.get('not_run_count')==0 and
            isinstance(passed,list) and len(passed)==len(items) and
            all(isinstance(x,dict) and x.get('status')=='PASS' for x in passed) and
            ter.get('date')==day and ter.get('status')=='PASS' and
            ter.get('semrush_status')=='PASS' and isinstance(verdicts,list) and
            len(verdicts)==len(items)):
        return {'state':'SOURCE_NOT_INDEPENDENTLY_PASS'}
    manifest_path=POST_OUT/(day+'-manifest.json')
    receipt_path=POST_OUT/(day+'-acceptance.json')
    pub_path=POST_OUT/(day+'-dropbox-publish.json')
    manifest=load(manifest_path)
    receipt=load(receipt_path)
    pub=load(pub_path)
    latest_source=max(spath.stat().st_mtime_ns,tpath.stat().st_mtime_ns)
    fresh=(manifest_path.is_file() and receipt_path.is_file() and
           manifest_path.stat().st_mtime_ns>=latest_source and
           receipt_path.stat().st_mtime_ns>=manifest_path.stat().st_mtime_ns)
    complete=(fresh and manifest.get('date')==day and
              manifest.get('status')!='PARTIAL_BLOCKED' and
              receipt.get('date')==day and receipt.get('status')=='PASS' and
              all((receipt.get('checks') or {}).values()) and
              len(receipt.get('checks') or {})==11 and
              pub.get('day')==day and pub.get('status')=='PASS')
    fingerprint=hashlib.sha256(('|'.join(str(_sha(p) or '') for p in
                (qpath,spath,tpath,POST_ROOT/('flippa-'+day.replace('-','')+'-daily-state.json'),
                 POST_ROOT/('flippa-deep-'+day.replace('-','')+'-state.json'),
                 manifest_path))).encode()).hexdigest()
    if not complete:
        if not _flippa_source_verified(day):
            return {'state':'FLIPPA_PROVENANCE_BLOCKED'}
        newer=_newer_published_day(day)
        if newer:return {'state':'NEWER_DAILY_REPORT_ALREADY_PUBLISHED','newer_day':newer}
        return {'state':'CHECKPOINT_REQUIRED','fingerprint':fingerprint}
    audit_day=now.date() if now.hour>=10 else now.date()-datetime.timedelta(days=1)
    ledger=load(POST_OUT/('gap-ledger-'+audit_day.isoformat()+'.json'))
    day_record=next((x for x in ledger.get('daily') or [] if x.get('day')==day),None)
    fingerprints=(day_record or {}).get('evidence_sha256') or {}
    current={'queue':_sha(qpath),'semrush':_sha(spath),'serp':_sha(tpath),
             'daily':_sha(POST_OUT/(day+'-research-queue.json'))}
    ledger_stale=(not day_record or
                  any(fingerprints.get(k)!=v for k,v in current.items()) or
                  day_record.get('acceptance')!=receipt.get('status') or
                  any(x.get('day')==day for x in ledger.get('pending_semrush') or []))
    return {'state':'AUDIT_REQUIRED' if ledger_stale else 'ALREADY_RECONCILED',
            'fingerprint':fingerprint,'audit_day':audit_day.isoformat()}

def _post_reconcile_locked(day,now=None,dry_run=False):
    plan=post_recovery_plan(day,now)
    state=plan['state']
    if dry_run:return {'day':day,'state':'DRY_RUN','would':state}
    if state not in ('CHECKPOINT_REQUIRED','AUDIT_REQUIRED'):
        return {'day':day,'state':state}
    checkpoint_exit=None
    acceptance_exit=None
    if state=='CHECKPOINT_REQUIRED':
        previous=(load(MARKER).get('post_recovery') or {})
        if (previous.get('fingerprint')==plan['fingerprint'] and
                previous.get('state') in ('STARTED','CHECKPOINT_FAILED',
                                          'ACCEPTANCE_FAILED','POST_VERIFY_FAILED')):
            return {'day':day,'state':'ALREADY_ATTEMPTED_THIS_EVIDENCE'}
        marker=load(MARKER)
        marker['post_recovery']={'day':day,'fingerprint':plan['fingerprint'],'state':'STARTED'}
        MARKER.parent.mkdir(parents=True,exist_ok=True)
        tmp=MARKER.with_suffix('.tmp');tmp.write_text(json.dumps(marker)+'\n');tmp.replace(MARKER)
        try:
            checkpoint=subprocess.run([PYTHON,str(POST_CHECKPOINT),'--date',day,
                                       '--checkpoint-only'],capture_output=True,text=True,
                                      timeout=420,check=False)
            checkpoint_exit=checkpoint.returncode
            if checkpoint_exit!=0:
                state='CHECKPOINT_FAILED'
            else:
                accepted=subprocess.run([PYTHON,str(POST_ACCEPTANCE),'--date',day],
                                        capture_output=True,text=True,timeout=50,check=False)
                acceptance_exit=accepted.returncode
                if acceptance_exit!=0:state='ACCEPTANCE_FAILED'
        except (OSError,subprocess.TimeoutExpired) as exc:
            state='POST_VERIFY_FAILED'
    if state in ('CHECKPOINT_FAILED','ACCEPTANCE_FAILED','POST_VERIFY_FAILED'):
        marker=load(MARKER)
        marker['post_recovery']={'day':day,'fingerprint':plan.get('fingerprint'),
                                  'state':state}
        tmp=MARKER.with_suffix('.tmp');tmp.write_text(json.dumps(marker)+'\n');tmp.replace(MARKER)
        return {'day':day,'state':state,'checkpoint_exit':checkpoint_exit,
                'acceptance_exit':acceptance_exit}
    next_plan=post_recovery_plan(day,now)
    if next_plan['state']=='AUDIT_REQUIRED':
        try:
            audit=subprocess.run([PYTHON,str(POST_AUDIT)],capture_output=True,text=True,
                                 timeout=60,check=False)
            audit_exit=audit.returncode
        except (OSError,subprocess.TimeoutExpired):
            audit_exit=-1
        if audit_exit!=0:
            return {'day':day,'state':'AUDIT_FAILED','audit_exit':audit_exit}
    final=post_recovery_plan(day,now)
    result={'day':day,'state':('RECONCILED_PASS' if final['state']=='ALREADY_RECONCILED'
                            else 'POST_VERIFY_FAILED'),'checkpoint_exit':checkpoint_exit,
            'acceptance_exit':acceptance_exit,'verified':final['state']=='ALREADY_RECONCILED'}
    if state=='CHECKPOINT_REQUIRED':
        marker=load(MARKER)
        marker['post_recovery']={'day':day,'fingerprint':plan['fingerprint'],
                                  'state':result['state']}
        tmp=MARKER.with_suffix('.tmp');tmp.write_text(json.dumps(marker)+'\n');tmp.replace(MARKER)
    return result

def post_recovery(day,now=None,dry_run=False,lock_owned=False):
    if dry_run:return _post_reconcile_locked(day,now,True)
    if lock_owned:return _post_reconcile_locked(day,now)
    LOCK.parent.mkdir(exist_ok=True,parents=True)
    with LOCK.open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'day':day,'state':'SOURCE_SCANNER_BUSY'}
        return _post_reconcile_locked(day,now)


def resume(day,dry_run=False):
    check=decision(day)
    if check['state']=='ALREADY_PASS':
        follow=post_recovery(day,dry_run=dry_run)
        return {'day':day,'state':'ALREADY_PASS','post_recovery':follow}
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
        if result['state']=='SOURCE_RECOVERED' and result.get('daily_returncode')==0:
            result['post_recovery']=post_recovery(day,lock_owned=True)
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
