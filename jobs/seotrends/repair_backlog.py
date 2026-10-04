#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, subprocess
from datetime import datetime, timedelta, timezone

BASE=pathlib.Path('/var/lib/seotrends-public'); SCANS=BASE/'scans'; SEM=BASE/'scripts/semrush_daily.py'; TERM=BASE/'scripts/terminal_funnel.py'
REPORT=BASE/'backfill-repair-latest.json'
def load(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {}
def atomic(path,payload):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def run(cmd,timeout):
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    return {'rc':p.returncode,'stdout':(p.stdout or '')[-1000:],'stderr':(p.stderr or '')[-1000:]}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--days',type=int,default=14); ap.add_argument('--exclude-today',action='store_true'); a=ap.parse_args()
    today=datetime.now(timezone.utc).date(); report=[]
    for delta in range(a.days,-1,-1):
        d=today-timedelta(days=delta)
        if a.exclude_today and d==today: continue
        day=d.isoformat(); q=SCANS/f'{day}-semrush-queue.json'
        if not q.exists(): continue
        sr=SCANS/f'{day}-semrush-results.json'; tr=SCANS/f'{day}-terminal-verdicts.json'
        before=load(sr).get('status'); terminal_before=load(tr).get('status')
        rec={'date':day,'before':before,'terminal_before':terminal_before}
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
    payload={'status':'PASS','generated_at':datetime.now(timezone.utc).isoformat(),'window_days':a.days,'exclude_today':a.exclude_today,'checked':len(report),'changed_dates':[r['date'] for r in report if r.get('changed')],'report':report}
    atomic(REPORT,payload); print(json.dumps(payload,ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
