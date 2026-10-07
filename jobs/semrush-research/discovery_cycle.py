#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys, time

def ts(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)

def run(script,*args):
    cmd=[sys.executable,str(pathlib.Path(__file__).with_name(script)),*map(str,args)]
    cp=subprocess.run(cmd,capture_output=True,text=True)
    if cp.returncode:
        raise RuntimeError(f'{script} rc={cp.returncode}: {(cp.stderr or cp.stdout)[-2000:]}')
    last=''
    for line in cp.stdout.splitlines():
        if line.strip(): last=line
    try:return json.loads(last) if last else {}
    except Exception:return {'stdout':cp.stdout[-4000:]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-dir',required=True)
    ap.add_argument('--config-dir',required=True)
    ap.add_argument('--tested-registry',required=True)
    ap.add_argument('--seed-bank')
    ap.add_argument('--auto-seed-count',type=int,default=8)
    ap.add_argument('--database',default='us')
    ap.add_argument('--queries-per-cluster',type=int,default=2)
    ap.add_argument('--max-serp-candidates',type=int,default=8)
    a=ap.parse_args()

    run_dir=pathlib.Path(a.run_dir); run_dir.mkdir(parents=True,exist_ok=True)
    discovery=run_dir/'discovery'; final=discovery/'final-summary.json'; cycle_state=run_dir/'discovery-cycle-state.json'
    if final.exists():
        summary=json.loads(final.read_text(encoding='utf-8'))
        state={'version':1,'stage':'RESUME_NO_BACKTRACK','updated_at':ts(),'run_dir':str(run_dir),
               'survivor_count':summary.get('survivor_count',0),'final_summary':str(final)}
        atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0

    bank=pathlib.Path(a.seed_bank) if a.seed_bank else pathlib.Path(a.config_dir)/(run_dir.name+'.json')
    try:
        if not bank.exists():
            run('modifier_seed_bank.py','--config-dir',a.config_dir,'--output',bank,'--count',a.auto_seed_count)

        universe=run_dir/'universe.json'
        if not universe.exists():
            run('live_collect.py','--seed-bank',bank,'--run-dir',run_dir,'--database',a.database)
        if not universe.exists():
            raise RuntimeError('UNIVERSE_NOT_READY')

        stage=run('discovery_stage.py','--input',universe,'--config-dir',a.config_dir,
                  '--tested-registry',a.tested_registry,'--output-dir',discovery,
                  '--max-serp-candidates',a.max_serp_candidates)
        if int(stage.get('queue_count') or 0)==0:
            state={'version':1,'stage':'COMPLETE_NO_CANDIDATE','updated_at':ts(),'run_dir':str(run_dir),
                   'seed_bank':str(bank),'universe':str(universe),'discovery_state':stage}
            atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0

        serp_dir=discovery/'serp'; results=serp_dir/'results.json'
        if not results.exists():
            run('serp_dd_live.py','--queue',discovery/'serp-dd-queue.json','--output-dir',serp_dir,
                '--queries-per-cluster',a.queries_per_cluster)
        if not results.exists():
            raise RuntimeError('SERP_RESULTS_NOT_READY')

        summary=run('discovery_finalize.py','--serp-results',results,'--registry',a.tested_registry,'--summary',final)
        survivors=int(summary.get('survivor_count') or 0)
        state={'version':1,'stage':'COMPLETE_WITH_SURVIVOR' if survivors else 'COMPLETE_NO_SURVIVOR',
               'updated_at':ts(),'run_dir':str(run_dir),'seed_bank':str(bank),'universe':str(universe),
               'queue_count':stage.get('queue_count',0),'survivor_count':survivors,'final_summary':str(final)}
        atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0
    except Exception as e:
        state={'version':1,'stage':'BLOCKED','updated_at':ts(),'run_dir':str(run_dir),
               'error':type(e).__name__+':'+str(e)[:1800]}
        atomic(cycle_state,state); print(json.dumps({'status':'BLOCKED',**state},ensure_ascii=False)); return 2

if __name__=='__main__':
    raise SystemExit(main())
