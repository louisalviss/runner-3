#!/opt/chatgpt-bridge/venv/bin/python
from __future__ import annotations
import json, pathlib, socket, time, importlib.util

from runtime_preflight import require_semrush_preflight
from runtime_metrics import SemrushJobMetrics

JOB_METRICS=SemrushJobMetrics('r5_retry_browser')

BROKER_SOCKET='/run/semrush-rpc-broker/control.sock'
BANK=pathlib.Path('/var/lib/semrush-research/config/delta-bank-2026-09-21-r5.json')
RUN=pathlib.Path('/var/lib/semrush-research/runs/delta-2026-09-21-r5')
RAW=RUN/'seed-results.jsonl'; STATE=RUN/'state.json'; SUMMARY=RUN/'theme-summary.json'; UNIVERSE=RUN/'universe-top30.json'; DB='us'

def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def broker_call(req,timeout=180):
    payload=(json.dumps(req,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(timeout)
    started=time.monotonic(); out=None
    try:
        s.connect(BROKER_SOCKET); s.sendall(payload); raw=s.makefile('rb').readline(8*1024*1024)
        if not raw: raise RuntimeError('BROKER_EMPTY_RESPONSE')
        out=json.loads(raw.decode());
        if not isinstance(out,dict): raise RuntimeError('BROKER_INVALID_RESPONSE')
        return out
    except FileNotFoundError as e: raise RuntimeError('BROKER_UNAVAILABLE') from e
    finally:
        JOB_METRICS.observe(req,out,(time.monotonic()-started)*1000.0); s.close()
def rpc_many(calls):
    out=broker_call({'action':'rpc_many','calls':calls})
    if out.get('ok') is not True:
        code=str(out.get('error_code') or out.get('state') or 'BROKER_RPC_FAILED'); detail=str(out.get('detail') or '')[:600]
        raise RuntimeError(code+(':'+detail if detail else ''))
    vals=out.get('results')
    if not isinstance(vals,list): raise RuntimeError('BROKER_RPC_RESULTS_INVALID')
    return vals
def args(seed): return {'phrase':seed,'device':0,'currency':'USD','database':DB,'location':0,'date':''}
def exact_metric(info):
    arr=(info or {}).get('keywords') if isinstance(info,dict) else None; arr=arr if isinstance(arr,list) else []
    return next((x for x in arr if x.get('database')==DB),None)
def ideas_rows(r):
    if isinstance(r,list): return r
    if isinstance(r,dict):
        for k in ('keywords','items','rows','data','results'):
            if isinstance(r.get(k),list): return r[k]
    return []
def load_latest():
    out={}
    if RAW.exists():
        for line in RAW.read_text(encoding='utf-8').splitlines():
            try:r=json.loads(line); out[(r['database'],r['theme_id'],r['seed'])]=r
            except Exception: pass
    return out
def load_items():
    d=json.loads(BANK.read_text(encoding='utf-8')); items=[]; themes=[]; db=d.get('database') or DB
    for t in d.get('themes',[]):
        tt={**t,'database':db}; themes.append(tt)
        for s in t.get('seeds',[]): items.append({'theme_id':t['theme_id'],'label':t.get('label'),'search_channel_fit':t.get('search_channel_fit'),'database':db,'seed':' '.join(str(s).split())})
    return themes,items
def is_bad(r): return (not r) or bool(r.get('error')) or r.get('summary') is None or not isinstance(r.get('ideas'),list)
def write_state(state):
    state['semrush_metrics']=JOB_METRICS.snapshot()
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rebuild(themes,items,latest):
    spec=importlib.util.spec_from_file_location('scanmod','/var/lib/semrush-research/scripts/dropbox_idea_scan_rpc.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rows=[latest[(x['database'],x['theme_id'],x['seed'])] for x in items if (x['database'],x['theme_id'],x['seed']) in latest]
    sums=mod.aggregate(themes,rows)
    SUMMARY.write_text(json.dumps({'created_at':now(),'themes':sums},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    UNIVERSE.write_text(json.dumps({'created_at':now(),'source':'Semrush Keyword RPC via NoxTools single-owner broker','bank_shas':{str(BANK):mod.sha(BANK)},'rows':rows},ensure_ascii=False)+'\n',encoding='utf-8')
    errors=sum(bool(x.get('error')) for x in rows); state=json.loads(STATE.read_text()) if STATE.exists() else {}
    state.update(version=2,transport='semrush-rpc-broker-v1',stage='COMPLETE' if errors==0 else 'BROWSER_RETRY_PENDING',updated_at=now(),seed_total=len(items),seed_done=len(rows)-errors,seed_pending=errors,error_count=errors,endpoint='NoxTools single-owner broker RPC',summary=str(SUMMARY),universe=str(UNIVERSE))
    write_state(state); return errors

def main():
    themes,items=load_items(); latest=load_latest(); pending=[x for x in items if is_bad(latest.get((x['database'],x['theme_id'],x['seed'])))]
    print(json.dumps({'event':'START','transport':'semrush-rpc-broker-v1','total':len(items),'pending':len(pending),'already_good':len(items)-len(pending)}),flush=True)
    if not pending:
        errors=rebuild(themes,items,latest); print(json.dumps({'event':'COMPLETE','retried':0,'errors':errors}),flush=True); return 0
    try:
        runtime_preflight=require_semrush_preflight()
        shallow_payload=runtime_preflight.get('shallow',{}).get('payload') or {}
        state=json.loads(STATE.read_text()) if STATE.exists() else {}
        state.update(runtime_preflight={'status':'PASS','broker':(shallow_payload.get('checks') or {}).get('broker')},updated_at=now())
        state.pop('runtime_preflight_error',None)
        write_state(state)
    except Exception as e:
        state=json.loads(STATE.read_text()) if STATE.exists() else {}
        state.update(stage='BLOCKED_RUNTIME_PREFLIGHT',blocker='SEMRUSH_RUNTIME_PREFLIGHT',runtime_preflight_error=type(e).__name__+':'+str(e)[:1200],updated_at=now())
        write_state(state)
        print(json.dumps({'event':'BLOCKED','reason':'SEMRUSH_RUNTIME_PREFLIGHT','detail':state['runtime_preflight_error']}),flush=True); return 6
    ready=broker_call({'action':'ensure'})
    if ready.get('ok') is not True:
        code=str(ready.get('error_code') or ready.get('state') or 'BROKER_UNAVAILABLE')
        print(json.dumps({'event':'BLOCKED','reason':code,'detail':str(ready.get('detail') or '')[:500]}),flush=True); return 3
    with RAW.open('a',encoding='utf-8') as f:
        for i,item in enumerate(pending,1):
            seed=item['seed']; base=args(seed); calls=[
                {'tag':'info','method':'keywords.GetInfo','args':{k:v for k,v in base.items() if k!='location'}},
                {'tag':'summary','method':'ideas.GetKeywordsSummary','args':{**base,'mode':0,'questions_only':False}},
                {'tag':'ideas','method':'ideas.GetKeywords','args':{**base,'mode':0,'questions_only':False}},
            ]
            vals=None
            for attempt in range(3):
                vals={x.get('tag'):x for x in rpc_many(calls)}; errs=[v.get('error') for v in vals.values() if v.get('error')]
                if not errs: break
                time.sleep(1.0+attempt)
            errs={k:v.get('error') for k,v in (vals or {}).items() if v.get('error')}
            if errs: rec={**item,'exact':None,'summary':None,'ideas':[],'error':'BROKER_RPC:'+json.dumps(errs,ensure_ascii=False)[:700],'scanned_at':now()}
            else: rec={**item,'exact':exact_metric(vals['info'].get('result')),'summary':vals['summary'].get('result'),'ideas':ideas_rows(vals['ideas'].get('result')),'error':None,'scanned_at':now()}
            f.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n'); f.flush(); latest[(item['database'],item['theme_id'],item['seed'])]=rec
            if i%5==0 or i==len(pending):
                remain=sum(is_bad(latest.get((x['database'],x['theme_id'],x['seed']))) for x in items)
                print(json.dumps({'event':'PROGRESS','retried':i,'of':len(pending),'remaining_bad':remain,'last':item['theme_id']+' :: '+seed}),flush=True)
            time.sleep(.15)
    errors=rebuild(themes,items,latest); print(json.dumps({'event':'COMPLETE','retried':len(pending),'errors':errors,'state':str(STATE)}),flush=True); return 0 if errors==0 else 2
if __name__=='__main__': raise SystemExit(main())
