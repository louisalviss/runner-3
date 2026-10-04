#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, re, subprocess
from collections import Counter
from datetime import datetime, timezone

BASE=pathlib.Path('/var/lib/seotrends-public')
SCANS=BASE/'scans'
SERP_RUNNER=pathlib.Path('/var/lib/semrush-research/scripts/serp_dd_live.py')
PYTHON='/opt/chatgpt-bridge/venv/bin/python'
TOOL_INTENT={'calculator','checker','lookup','estimator','estimate','converter','conversion','generator','planner','tool','tools','validator','compare','compress','resize','viewer','tracker','monitor','summarizer','redaction','analytics','api'}

def now_iso(): return datetime.now(timezone.utc).isoformat()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def brand_tokens(domain):
    label=domain.lower().split('.')[0]
    return {label,label.replace('-',''),label.replace('-',' ')}
def is_brand_kw(domain,phrase):
    q=' '+re.sub(r'\s+',' ',phrase.lower())+' '
    return any(b and (' '+b+' ') in q for b in brand_tokens(domain))
def keyword_candidates(domain,raw,maxn=6):
    rows=list(raw.get('rows') or []); scored=[]
    for r in rows:
        phrase=str(r.get('phrase') or '').strip()
        if not phrase or is_brand_kw(domain,phrase): continue
        url=str(r.get('url') or '').lower()
        vol=int(float(r.get('volume') or 0)); traffic=float(r.get('traffic') or 0); kd=float(r.get('keywordDifficulty') or 100)
        toks=set(re.findall(r'[a-z0-9]+',phrase.lower()))
        utility=bool(toks & TOOL_INTENT); landing=('/blog/' not in url and '/news/' not in url and '/article' not in url)
        score=(4 if utility else 0)+(3 if landing else 0)+min(traffic/100,5)+min(vol/1000,5)+max(0,(40-kd)/20)
        scored.append((score,traffic,vol,-kd,phrase,url))
    scored.sort(reverse=True); out=[]; seen=set()
    for _,traffic,vol,nkd,phrase,url in scored:
        key=phrase.lower()
        if key in seen: continue
        seen.add(key); out.append({'keyword':phrase,'volume':vol,'traffic':traffic,'kd':-nkd,'url':url})
        if len(out)>=maxn: break
    return out

def build_serp_queue(day,semrush):
    rows=[]
    for item in semrush.get('items') or []:
        if item.get('status')!='PASS': continue
        domain=str(item.get('domain') or '').lower(); rawp=SCANS/f'{day}-semrush'/f'{domain}.json'
        if not rawp.exists(): continue
        try: raw=load(rawp)
        except Exception: continue
        rows.append({'cluster_id':domain,'domain':domain,'discovery_score':item.get('discovery_score'),'metrics':item.get('metrics') or {},'top_keywords':keyword_candidates(domain,raw)})
    return {'status':'PENDING','date':day,'lane':'seotrends-daily-serp-dd','queue':rows}

def run_serp(queue_path,outdir,timeout):
    if not SERP_RUNNER.exists(): return {'status':'FAIL','reason':'SERP_RUNNER_MISSING'}
    cmd=[PYTHON,str(SERP_RUNNER),'--queue',str(queue_path),'--output-dir',str(outdir),'--queries-per-cluster','2']
    try: p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except subprocess.TimeoutExpired: return {'status':'BLOCKED','reason':'SERP_TIMEOUT'}
    parsed=None
    for line in reversed((p.stdout or '').splitlines()):
        try:
            obj=json.loads(line)
            if isinstance(obj,dict): parsed=obj; break
        except Exception: pass
    if parsed is None: parsed={'status':'FAIL','reason':'SERP_UNPARSEABLE','detail':(p.stderr or p.stdout or '')[-600:]}
    parsed['returncode']=p.returncode; return parsed

def verdict_for(item,serp):
    m=item.get('metrics') or {}; traffic=float(m.get('estimated_traffic_sum') or 0); kws=int(m.get('organic_keywords') or 0); nonbrand=int(m.get('nonbrand_keyword_rows') or 0); nb_share=(nonbrand/kws) if kws else 0
    meta={'traffic':traffic,'organic_keywords':kws,'nonbrand_share':round(nb_share,3)}
    if kws<50 or traffic<100: return 'DROP','LOW_DEMAND',meta
    if not serp: return 'BLOCKED','NO_SERP_RESULT',meta
    g=serp.get('serp_gate')
    if g in ('DROP_SERP_SATURATED','DROP_INTENT_MISMATCH'): return 'DROP',g,meta
    if g in ('BLOCKED_NO_SERP','BLOCKED_INCOMPLETE_SERP'): return 'BLOCKED',g,meta
    if g=='WATCH_COMPETITION': return 'WATCH','COMPETITION_REQUIRES_NARROW_GAP',meta
    if g=='SERP_DD_PASS': return 'WATCH','SERP_PASS_FINAL_SEMANTIC_BUSINESS_DD_REQUIRED',meta
    return 'BLOCKED',str(g or 'UNKNOWN_SERP_GATE'),meta

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=datetime.now(timezone.utc).strftime('%Y-%m-%d')); ap.add_argument('--serp-timeout',type=int,default=1200)
    args=ap.parse_args(); day=args.date
    sr=SCANS/f'{day}-semrush-results.json'; outj=SCANS/f'{day}-terminal-verdicts.json'; outm=SCANS/f'{day}-terminal-verdicts.md'
    if not sr.exists():
        payload={'date':day,'status':'BLOCKED','reason':'NO_SEMRUSH_RESULTS','completed_at':now_iso(),'verdicts':[]}; atomic(outj,payload); outm.write_text(f'# SeoTrends terminal — {day}\n\n- status: BLOCKED\n- reason: NO_SEMRUSH_RESULTS\n',encoding='utf-8'); print(json.dumps(payload)); return 3
    semrush=load(sr)
    if semrush.get('status') not in ('PASS','PASS_EMPTY'):
        payload={'date':day,'status':'BLOCKED','reason':'SEMRUSH_'+str(semrush.get('status')),'completed_at':now_iso(),'verdicts':[]}; atomic(outj,payload); outm.write_text(f'# SeoTrends terminal — {day}\n\n- status: BLOCKED\n- reason: {payload["reason"]}\n',encoding='utf-8'); print(json.dumps(payload)); return 3
    q=build_serp_queue(day,semrush); qp=SCANS/f'{day}-serp-dd-queue.json'; atomic(qp,q); serpdir=SCANS/f'{day}-serp-dd'
    srun={'status':'PASS','stage':'EMPTY'} if not q['queue'] else run_serp(qp,serpdir,args.serp_timeout)
    serp_map={}; rp=serpdir/'results.json'
    if rp.exists():
        try: serp_map={x.get('cluster_id'):x for x in (load(rp).get('results') or [])}
        except Exception: serp_map={}
    verdicts=[]
    for item in semrush.get('items') or []:
        domain=str(item.get('domain') or '')
        if item.get('status')!='PASS': verdicts.append({'domain':domain,'verdict':'BLOCKED','reason':'SEMRUSH_ITEM_'+str(item.get('status'))}); continue
        v,reason,metrics=verdict_for(item,serp_map.get(domain)); verdicts.append({'domain':domain,'verdict':v,'reason':reason,'metrics':metrics,'serp_gate':(serp_map.get(domain) or {}).get('serp_gate')})
    counts=Counter(x['verdict'] for x in verdicts); status='PASS' if not counts.get('BLOCKED') and str(srun.get('status')).upper()=='PASS' else 'DEGRADED'
    payload={'date':day,'status':status,'completed_at':now_iso(),'source':'seotrends-daily-terminal-v1','semrush_status':semrush.get('status'),'serp_run':srun,'counts':{k:counts.get(k,0) for k in ('BUILD','WATCH','DROP','BLOCKED')},'verdicts':verdicts,'policy':{'auto_build':False,'serp_pass':'WATCH until semantic/business DD'}}
    atomic(outj,payload)
    lines=[f'# SeoTrends terminal — {day}','',f'- status: {status}',f'- BUILD: {counts.get("BUILD",0)}',f'- WATCH: {counts.get("WATCH",0)}',f'- DROP: {counts.get("DROP",0)}',f'- BLOCKED: {counts.get("BLOCKED",0)}','- auto BUILD: disabled; SERP pass remains WATCH until semantic/business DD','', '## Verdicts','']
    for x in verdicts: lines.append(f'- **{x["domain"]}** — {x["verdict"]} — {x["reason"]}')
    outm.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps({'status':status,'date':day,'counts':payload['counts'],'output':str(outj)},ensure_ascii=False)); return 0 if status=='PASS' else 3

if __name__=='__main__': raise SystemExit(main())
