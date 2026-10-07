#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, re, subprocess, sys, time

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

def run_round(run_dir):
    m=re.search(r"(?:^|[-_])r(\d+)(?:[-_]|$)",pathlib.Path(run_dir).name,re.I)
    return int(m.group(1)) if m else None

def sync_candidates(a,run_dir):
    if a.skip_candidate_sync: return {'status':'SKIPPED'}
    lifecycle=pathlib.Path(a.candidate_lifecycle) if a.candidate_lifecycle else pathlib.Path(a.config_dir)/'candidate-lifecycle-v1.json'
    args=['--tested-registry',a.tested_registry,
          '--lifecycle',lifecycle,
          '--output',a.candidate_registry_out,
          '--dropbox-path',a.candidate_dropbox_path,
          '--dropbox-tested-path',a.tested_dropbox_path,
          '--dropbox-env-file',a.dropbox_env_file]
    rr=run_round(run_dir)
    if rr is not None: args += ['--terminal-round',rr]
    return run('candidate_registry_sync.py',*args)

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
    ap.add_argument('--candidate-lifecycle')
    ap.add_argument('--candidate-registry-out',default='/var/lib/semrush-research/state/candidate-registry.md')
    ap.add_argument('--candidate-dropbox-path',default='/Apps/remotely-save/AI/AI-MEMORY/FLOWS/SEO/Semrush Candidate Registry.md')
    ap.add_argument('--tested-dropbox-path',default='/Apps/remotely-save/AI/AI-MEMORY/FLOWS/SEO/Semrush Tested Registry.json')
    ap.add_argument('--dropbox-env-file',default='/etc/vps-control/dropbox.env')
    ap.add_argument('--skip-candidate-sync',action='store_true')
    a=ap.parse_args()

    run_dir=pathlib.Path(a.run_dir); run_dir.mkdir(parents=True,exist_ok=True)
    discovery=run_dir/'discovery'; final=discovery/'final-summary.json'; cycle_state=run_dir/'discovery-cycle-state.json'
    try:
        if final.exists():
            summary=json.loads(final.read_text(encoding='utf-8'))
            candidate_sync=sync_candidates(a,run_dir)
            state={'version':1,'stage':'RESUME_NO_BACKTRACK','updated_at':ts(),'run_dir':str(run_dir),
                   'survivor_count':summary.get('survivor_count',0),'final_summary':str(final),'candidate_registry_sync':candidate_sync}
            atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0

        bank=pathlib.Path(a.seed_bank) if a.seed_bank else pathlib.Path(a.config_dir)/(run_dir.name+'.json')
        if not bank.exists():
            run('modifier_seed_bank.py','--config-dir',a.config_dir,'--output',bank,'--count',a.auto_seed_count)

        bank_data=json.loads(bank.read_text(encoding='utf-8'))
        if not (bank_data.get('themes') or []):
            candidate_sync=sync_candidates(a,run_dir)
            state={'version':1,'stage':'COMPLETE_CATALOG_EXHAUSTED','updated_at':ts(),'run_dir':str(run_dir),
                   'seed_bank':str(bank),'candidate_registry_sync':candidate_sync}
            atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0

        universe=run_dir/'universe.json'
        if not universe.exists():
            run('live_collect.py','--seed-bank',bank,'--run-dir',run_dir,'--database',a.database)
        if not universe.exists(): raise RuntimeError('UNIVERSE_NOT_READY')

        stage=run('discovery_stage.py','--input',universe,'--config-dir',a.config_dir,
                  '--tested-registry',a.tested_registry,'--output-dir',discovery,
                  '--max-serp-candidates',a.max_serp_candidates)
        if int(stage.get('queue_count') or 0)==0:
            candidate_sync=sync_candidates(a,run_dir)
            state={'version':1,'stage':'COMPLETE_NO_CANDIDATE','updated_at':ts(),'run_dir':str(run_dir),
                   'seed_bank':str(bank),'universe':str(universe),'discovery_state':stage,'candidate_registry_sync':candidate_sync}
            atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0

        serp_dir=discovery/'serp'; results=serp_dir/'results.json'
        if not results.exists():
            run('serp_dd_live.py','--queue',discovery/'serp-dd-queue.json','--output-dir',serp_dir,
                '--queries-per-cluster',a.queries_per_cluster)
        if not results.exists(): raise RuntimeError('SERP_RESULTS_NOT_READY')

        summary=run('discovery_finalize.py','--serp-results',results,'--registry',a.tested_registry,'--summary',final)
        candidate_sync=sync_candidates(a,run_dir)
        survivors=int(summary.get('survivor_count') or 0)
        state={'version':1,'stage':'COMPLETE_WITH_SURVIVOR' if survivors else 'COMPLETE_NO_SURVIVOR',
               'updated_at':ts(),'run_dir':str(run_dir),'seed_bank':str(bank),'universe':str(universe),
               'queue_count':stage.get('queue_count',0),'survivor_count':survivors,'final_summary':str(final),
               'candidate_registry_sync':candidate_sync}
        atomic(cycle_state,state); print(json.dumps({'status':'PASS',**state},ensure_ascii=False)); return 0
    except Exception as e:
        state={'version':1,'stage':'BLOCKED','updated_at':ts(),'run_dir':str(run_dir),
               'error':type(e).__name__+':'+str(e)[:1800]}
        atomic(cycle_state,state); print(json.dumps({'status':'BLOCKED',**state},ensure_ascii=False)); return 2

if __name__=='__main__':
    raise SystemExit(main())