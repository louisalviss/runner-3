#!/opt/chatgpt-bridge/venv/bin/python
from __future__ import annotations
import argparse, json, pathlib, re, socket, time
from urllib.parse import urlparse
from collections import Counter

from runtime_preflight import require_semrush_preflight
from runtime_metrics import SemrushJobMetrics

JOB_METRICS=SemrushJobMetrics('serp_dd_live')

BROKER_SOCKET='/run/semrush-rpc-broker/control.sock'
SOCIAL={'youtube.com','www.youtube.com','reddit.com','www.reddit.com','facebook.com','www.facebook.com','quora.com','www.quora.com','tiktok.com','www.tiktok.com'}
TOOL_WORDS={'calculator','calc','checker','lookup','estimator','estimate','converter','conversion','generator','planner','tool','tools','template','checklist','cost','quote'}
ARTICLE_WORDS={'blog','guide','how-to','howto','article','news','learn','resources','resource','tips'}
STOP={'the','a','an','to','of','for','and','or','in','on','with','how','do','you','your','is','are','what','calculate','calculator','online'}

def ts(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def persist_state(path,state):
    state['semrush_metrics']=JOB_METRICS.snapshot(); atomic(path,state)
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
        code=str(out.get('error_code') or out.get('state') or 'BROKER_RPC_FAILED')
        detail=str(out.get('detail') or '')[:600]
        raise RuntimeError(code+(':'+detail if detail else ''))
    vals=out.get('results')
    if not isinstance(vals,list): raise RuntimeError('BROKER_RPC_RESULTS_INVALID')
    return vals
def norm_domain(d):
    d=(d or '').lower().strip(); return d[4:] if d.startswith('www.') else d
def qtokens(q): return [x for x in re.findall(r'[a-z0-9]+',(q or '').lower()) if len(x)>=3 and x not in STOP]
def classify_serp(keyword,rows):
    organic=[]; seen=set()
    for r in sorted(rows or [],key=lambda x:(999 if x.get('position') is None else x.get('position'), str(x.get('url') or ''))):
        if r.get('kind') is not None: continue
        u=str(r.get('url') or '')
        if not u or u in seen: continue
        seen.add(u); organic.append(r)
    top10=[x for x in organic if isinstance(x.get('position'),int) and x.get('position')<=10]
    if len(top10)<10: top10=organic[:10]
    toks=qtokens(keyword); exact_tools=[]; articles=[]; socials=[]
    for r in top10:
        u=str(r.get('url') or '').lower(); d=norm_domain(str(r.get('domain') or urlparse(u).netloc)); path=urlparse(u).path.lower()
        hay=' '.join([d.replace('.',' '),path.replace('-',' ').replace('_',' ')])
        hit=sum(1 for t in toks if t in hay); has_tool=any(w in hay for w in TOOL_WORDS)
        is_social=d in {norm_domain(x) for x in SOCIAL}; is_article=any('/'+w+'/' in path or w in path.split('/') for w in ARTICLE_WORDS) and not has_tool
        if is_social: socials.append(d)
        elif has_tool or hit>=2: exact_tools.append(d)
        elif is_article: articles.append(d)
    domains=[norm_domain(str(x.get('domain') or '')) for x in top10 if x.get('domain')]
    c=Counter(domains); repeats=max(c.values()) if c else 0
    feature_codes=sorted({int(f) for r in (rows or []) for f in (r.get('features') or []) if isinstance(f,int)})
    nonorganic=sum(1 for r in (rows or []) if r.get('kind') is not None)
    return {'keyword':keyword,'organic_count':len(organic),'top10_domains':domains,'top10_unique_domains':len(set(domains)),'exact_tool_top10':len(exact_tools),'exact_tool_domains':sorted(set(exact_tools)),'article_top10':len(articles),'social_top10':len(socials),'max_domain_repeat_top10':repeats,'serp_feature_entries':nonorganic,'feature_codes':feature_codes,'top10':[{'position':x.get('position'),'domain':norm_domain(str(x.get('domain') or '')),'url':x.get('url')} for x in top10]}
def gate(serps):
    if not serps: return 'BLOCKED_NO_SERP'
    if any(int(x.get('organic_count') or 0) < 5 for x in serps): return 'BLOCKED_INCOMPLETE_SERP'
    avg_tool=sum(x['exact_tool_top10'] for x in serps)/len(serps); avg_article=sum(x['article_top10'] for x in serps)/len(serps); avg_social=sum(x['social_top10'] for x in serps)/len(serps)
    top3_tool=sum(sum(1 for r in x['top10'][:3] if any(d==r['domain'] for d in x['exact_tool_domains'])) for x in serps)/len(serps)
    if avg_tool>=7 or (avg_tool>=6 and top3_tool>=2): return 'DROP_SERP_SATURATED'
    if avg_tool<=1 and (avg_article+avg_social)>=5: return 'DROP_INTENT_MISMATCH'
    if avg_tool>=5: return 'WATCH_COMPETITION'
    return 'SERP_DD_PASS'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--queue',required=True); ap.add_argument('--output-dir',required=True); ap.add_argument('--queries-per-cluster',type=int,default=2)
    a=ap.parse_args(); out=pathlib.Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    rawp=out/'raw-serps.jsonl'; resultp=out/'results.json'; statep=out/'state.json'
    q=json.loads(pathlib.Path(a.queue).read_text()); rows=q if isinstance(q,list) else q.get('queue') or q.get('clusters') or []
    done={}
    if rawp.exists():
        for line in rawp.read_text().splitlines():
            try:r=json.loads(line); done[(r['cluster_id'],r['keyword'])]=r
            except Exception: pass
    state={'version':2,'transport':'semrush-rpc-broker-v1','stage':'SERP_DD_RUNNING','cluster_total':len(rows),'queries_per_cluster':a.queries_per_cluster,'raw_done':len(done),'updated_at':ts()}; persist_state(statep,state)
    pending=[]
    for r in rows:
        kws=[]
        for x in r.get('top_keywords') or []:
            kw=str(x.get('keyword') or '').strip()
            if kw and kw not in kws: kws.append(kw)
            if len(kws)>=a.queries_per_cluster: break
        for kw in kws:
            if (r['cluster_id'],kw) not in done: pending.append((r['cluster_id'],kw))
    try:
        if pending:
            try:
                runtime_preflight=require_semrush_preflight()
                shallow_payload=runtime_preflight.get('shallow',{}).get('payload') or {}
                state['runtime_preflight']={'status':'PASS','broker':(shallow_payload.get('checks') or {}).get('broker')}
            except Exception as e:
                state.update(stage='BLOCKED_RUNTIME_PREFLIGHT',blocker='SEMRUSH_RUNTIME_PREFLIGHT',runtime_preflight_error=type(e).__name__+':'+str(e)[:1200],updated_at=ts()); persist_state(statep,state)
                print(json.dumps({'status':'BLOCKED','reason':'SEMRUSH_RUNTIME_PREFLIGHT','state':state},ensure_ascii=False)); return 6
            ready=broker_call({'action':'ensure'})
            if ready.get('ok') is not True:
                code=str(ready.get('error_code') or ready.get('state') or 'BROKER_UNAVAILABLE')
                state.update(stage='BLOCKED_BROKER_BUSY' if code=='SEMRUSH_RESOURCE_ADMISSION_DENIED' else 'BLOCKED_LIVE_AUTH',blocker=code,updated_at=ts()); persist_state(statep,state)
                print(json.dumps({'status':'BLOCKED','reason':code,'state':state},ensure_ascii=False)); return 3
            state.update(server=ready.get('server'),updated_at=ts()); persist_state(statep,state)
        else:
            state['runtime_preflight']={'status':'SKIPPED_NO_PENDING'}
            persist_state(statep,state)
        with rawp.open('a',encoding='utf-8') as f:
            for i in range(0,len(pending),6):
                batch=pending[i:i+6]
                calls=[{'tag':cid+'\t'+kw,'method':'serp.GetURLs','args':{'phrase':kw,'device':0,'currency':'USD','database':'us','location':0,'date':''}} for cid,kw in batch]
                vals=rpc_many(calls); by={v.get('tag'):v for v in vals}
                for cid,kw in batch:
                    v=by.get(cid+'\t'+kw,{})
                    rec={'cluster_id':cid,'keyword':kw,'status':v.get('status'),'rows':v.get('result') or [],'error':v.get('error')}
                    f.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n'); done[(cid,kw)]=rec
                f.flush(); state.update(raw_done=len(done),updated_at=ts()); persist_state(statep,state)
        output=[]
        for r in rows:
            serps=[]; errors=[]; kws=[]
            for x in r.get('top_keywords') or []:
                kw=str(x.get('keyword') or '').strip()
                if kw and kw not in kws: kws.append(kw)
                if len(kws)>=a.queries_per_cluster: break
            for kw in kws:
                rec=done.get((r['cluster_id'],kw))
                if not rec: continue
                if rec.get('error'): errors.append({'keyword':kw,'error':rec.get('error')})
                else: serps.append(classify_serp(kw,rec.get('rows') or []))
            g=gate(serps); avg_tool=round(sum(x['exact_tool_top10'] for x in serps)/len(serps),2) if serps else None
            output.append({**r,'serp_gate':g,'avg_exact_tool_top10':avg_tool,'serps':serps,'errors':errors})
        atomic(resultp,{'created_at':ts(),'source_queue':str(pathlib.Path(a.queue)),'transport':'semrush-rpc-broker-v1','cluster_count':len(output),'results':output})
        counts=dict(Counter(x['serp_gate'] for x in output)); state.update(stage='SERP_DD_READY',cluster_done=len(output),gate_counts=counts,results=str(resultp),updated_at=ts()); persist_state(statep,state)
        print(json.dumps({'status':'PASS','stage':'SERP_DD_READY','clusters':len(output),'gate_counts':counts,'results':str(resultp),'transport':'semrush-rpc-broker-v1'},ensure_ascii=False)); return 0
    except Exception as e:
        state.update(stage='FAILED',error=type(e).__name__+':'+str(e)[:400],updated_at=ts()); persist_state(statep,state); print(json.dumps({'status':'FAIL','state':state},ensure_ascii=False)); return 1
if __name__=='__main__': raise SystemExit(main())
