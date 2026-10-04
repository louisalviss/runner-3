#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, subprocess
from datetime import datetime, timedelta, timezone

BASE=pathlib.Path('/var/lib/seotrends-public'); SCANS=BASE/'scans'; SEM=BASE/'scripts/semrush_daily.py'; TERM=BASE/'scripts/terminal_funnel.py'
def load(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {}
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
        sr=SCANS/f'{day}-semrush-results.json'; status=load(sr).get('status'); rec={'date':day,'before':status}
        if status not in ('PASS','PASS_EMPTY'):
            try: rec['semrush']=run(['python3',str(SEM),'--date',day],1200)
            except subprocess.TimeoutExpired: rec['semrush']={'rc':124,'stderr':'timeout'}
        status2=load(sr).get('status'); rec['after']=status2; tr=SCANS/f'{day}-terminal-verdicts.json'; tstat=load(tr).get('status')
        if status2 in ('PASS','PASS_EMPTY') and tstat!='PASS':
            try: rec['terminal']=run(['python3',str(TERM),'--date',day],1500)
            except subprocess.TimeoutExpired: rec['terminal']={'rc':124,'stderr':'timeout'}
        rec['terminal_status']=load(tr).get('status'); report.append(rec)
    print(json.dumps({'status':'PASS','checked':len(report),'report':report},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
