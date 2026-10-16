#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, subprocess, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE=pathlib.Path('/var/lib/seotrends-public'); SCANS=BASE/'scans'; SEM=BASE/'scripts/semrush_daily.py'; TERM=BASE/'scripts/terminal_funnel.py'
REPORT=BASE/'backfill-repair-latest.json'
COOLDOWN=pathlib.Path('/var/lib/semrush-research/config/provider-rate-limit.json')
def cooldown_remaining():
    try:
        obj=json.loads(COOLDOWN.read_text())
        return max(0,int(float(obj.get('until_epoch') or 0)-time.time()))
    except (OSError,ValueError,TypeError):return 0
def load(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {}
def atomic(path,payload):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def run(cmd,timeout):
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    return {'rc':p.returncode,'stdout':(p.stdout or '')[-1000:],'stderr':(p.stderr or '')[-1000:]}
def quota_blocked(day):
    term=load(SCANS/f'{day}-serp-dd-product-v2/state.json')
    sem=load(SCANS/f'{day}-semrush-results.json')
    return (term.get('stage')=='BLOCKED_QUOTA_LIMIT' or
            'SEMRUSH_REPORT_LIMIT' in str(sem.get('global_blocker') or '') or
            '-2004' in str(sem.get('global_blocker') or ''))

def auth_blocked(day):
    sem=load(SCANS/f'{day}-semrush-results.json')
    term=load(SCANS/f'{day}-serp-dd-product-v2/state.json')
    markers=('SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_LOGIN_CHALLENGE',
             'NOX_DASHBOARD_CHALLENGE','NOX_LOGIN_REQUIRED',
             'SEMRUSH_ONE_SHOT_RECOVERY_FAILED')
    return ((sem.get('status')=='BLOCKED' and
             any(x in str(sem.get('global_blocker') or '') for x in markers)) or
            (term.get('stage')=='BLOCKED_LIVE_AUTH' and
             any(x in str(term.get('blocker') or '') for x in markers)))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--days',type=int,default=14); ap.add_argument('--exclude-today',action='store_true'); a=ap.parse_args()
    today=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date(); report=[]
    for delta in range(0,a.days+1):
        d=today-timedelta(days=delta)
        if a.exclude_today and d==today: continue
        day=d.isoformat(); q=SCANS/f'{day}-semrush-queue.json'
        if not q.exists(): continue
        sr=SCANS/f'{day}-semrush-results.json'; tr=SCANS/f'{day}-terminal-verdicts.json'
        before=load(sr).get('status'); terminal_before=load(tr).get('status')
        rec={'date':day,'before':before,'terminal_before':terminal_before}
        if cooldown_remaining()>0:
            rec['status']='BLOCKED_RATE_LIMIT'
            rec['retry_after_seconds']=cooldown_remaining()
            report.append(rec)
            break
        if auth_blocked(day):
            # Only a verified handoff resume may reopen this provider-auth gate.
            rec['status']='BLOCKED_LIVE_AUTH'
            report.append(rec)
            break
        if before not in ('PASS','PASS_EMPTY'):
            try: rec['semrush']=run(['python3',str(SEM),'--date',day],1200)
            except subprocess.TimeoutExpired: rec['semrush']={'rc':124,'stderr':'timeout'}
        after=load(sr).get('status'); rec['after']=after
        if after in ('PASS','PASS_EMPTY') and terminal_before!='PASS':
            try: rec['terminal']=run(['python3',str(TERM),'--date',day],1500)
            except subprocess.TimeoutExpired: rec['terminal']={'rc':124,'stderr':'timeout'}
        terminal_after=load(tr).get('status'); rec['terminal_after']=terminal_after
        rec['changed']=(before!=after) or (terminal_before!=terminal_after)
        report.append(rec)
        if auth_blocked(day):
            rec['status']='BLOCKED_LIVE_AUTH'
            break
        if quota_blocked(day):
            rec['status']='BLOCKED_QUOTA_LIMIT'
            break
        if cooldown_remaining()>0:
            rec['status']='BLOCKED_RATE_LIMIT'
            rec['retry_after_seconds']=cooldown_remaining()
            break
    payload={'status':(report[-1]['status'] if report and report[-1].get('status') in ('BLOCKED_RATE_LIMIT','BLOCKED_QUOTA_LIMIT','BLOCKED_LIVE_AUTH') else 'PASS'),'generated_at':datetime.now(timezone.utc).isoformat(),'window_days':a.days,'exclude_today':a.exclude_today,'checked':len(report),'changed_dates':[r['date'] for r in report if r.get('changed')],'report':report}
    atomic(REPORT,payload); print(json.dumps(payload,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
