#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, re, subprocess
from product_keyword_gate import product_keyword_candidates
from collections import Counter
from datetime import datetime, timezone

BASE=pathlib.Path('/var/lib/seotrends-public')
SCANS=BASE/'scans'
SERP_RUNNER=pathlib.Path('/var/lib/semrush-research/scripts/serp_dd_live.py')
PYTHON='/opt/chatgpt-bridge/venv/bin/python'

def now_iso(): return datetime.now(timezone.utc).isoformat()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
def load_profiles(day):
    profiles={}
    p=SCANS/f'{day}-candidates.jsonl'
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try: x=json.loads(line)
            except (ValueError,TypeError): continue
            if x.get('domain'): profiles[str(x['domain']).lower()]=x
    return profiles

def build_serp_queue(day,semrush):
    rows=[]; profiles=load_profiles(day)
    for item in semrush.get('items') or []:
        if item.get('status')!='PASS': continue
        domain=str(item.get('domain') or '').lower(); rawp=SCANS/f'{day}-semrush'/f'{domain}.json'
        if not rawp.exists(): continue
        try: raw=load(rawp)
        except Exception: continue
        kws=product_keyword_candidates(domain,raw,profiles.get(domain))
        if kws: rows.append({'cluster_id':domain,'domain':domain,'discovery_score':item.get('discovery_score'),'metrics':item.get('metrics') or {},'top_keywords':kws})
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
    ap.add_argument('--domains',default='',help='Comma-delimited scoped audit domains; requires --suffix')
    ap.add_argument('--suffix',default='',help='Separate files for scoped historical recheck')
    args=ap.parse_args(); day=args.date
    if args.domains and not args.suffix: ap.error('--domains requires --suffix (never overwrite sealed original)')
    if args.suffix and not re.fullmatch(r'[a-z0-9-]+',args.suffix): ap.error('Invalid suffix')
    suffix=('-'+args.suffix) if args.suffix else ''
    sr=SCANS/f'{day}-semrush-results.json'; outj=SCANS/f'{day}-terminal-verdicts{suffix}.json'; outm=SCANS/f'{day}-terminal-verdicts{suffix}.md'
    if not sr.exists():
        payload={'date':day,'status':'BLOCKED','reason':'NO_SEMRUSH_RESULTS','completed_at':now_iso(),'verdicts':[]}; atomic(outj,payload); outm.write_text(f'# SeoTrends terminal — {day}\n\n- status: BLOCKED\n- reason: NO_SEMRUSH_RESULTS\n',encoding='utf-8'); print(json.dumps(payload)); return 3
    source=load(sr)
    source_status=str(source.get('status') or 'MISSING')
    allowed={x.strip().lower() for x in args.domains.split(',') if x.strip()}
    semrush=source
    if allowed:
        # Scoped audit has its own suffixed output and may operate on independently
        # verified PASS exports from a PARTIAL day, but never seal the full day PASS.
        queue_path=SCANS/f'{day}-semrush-queue.json'
        try: queue=load(queue_path)
        except (OSError,ValueError): queue={}
        inputs=queue.get('items') or []
        eligible=source.get('items') or []
        selected=[x for x in eligible if isinstance(x,dict)
                  and str(x.get('domain') or '').lower() in allowed]
        in_ids=[str(x.get('domain') or '').lower() for x in inputs if isinstance(x,dict)]
        ids=[str(x.get('domain') or '').lower() for x in selected]
        queue_ok=bool(queue.get('date')==day and queue.get('scan_terminal') is True
                      and queue.get('scanned')==queue.get('added_total')
                      and queue.get('count')==len(inputs)
                      and len(in_ids)==len(set(in_ids))
                      and len(ids)==len(allowed) and set(ids)==allowed
                      and set(ids)<=set(in_ids) and all(x.get('status')=='PASS' for x in selected))
        export_ok=queue_ok
        if export_ok:
            for domain in ids:
                try: raw=load(SCANS/f'{day}-semrush'/f'{domain}.json')
                except (OSError,ValueError): export_ok=False;break
                if str(raw.get('domain') or '').lower()!=domain or not isinstance(raw.get('rows'),list):
                    export_ok=False;break
        if not export_ok:
            payload={'date':day,'status':'BLOCKED','reason':'SCOPED_EXPORT_PROVENANCE_UNVERIFIED',
                     'source_overall_status':source_status,'scope':sorted(allowed),
                     'completed_at':now_iso(),'verdicts':[]}
            atomic(outj,payload)
            outm.write_text(f'# SeoTrends terminal scoped — {day}\\n\\n- status: BLOCKED\\n- reason: SCOPED_EXPORT_PROVENANCE_UNVERIFIED\\n',encoding='utf-8')
            print(json.dumps(payload,ensure_ascii=False))
            return 3
        semrush={**source,'status':'PASS_SCOPED_SOURCE','items':selected,
                 'source_overall_status':source_status}
    elif source_status not in ('PASS','PASS_EMPTY'):
        payload={'date':day,'status':'BLOCKED','reason':'SEMRUSH_'+source_status,
                 'completed_at':now_iso(),'verdicts':[]}
        atomic(outj,payload)
        outm.write_text(f'# SeoTrends terminal — {day}\\n\\n- status: BLOCKED\\n- reason: {payload["reason"]}\\n',encoding='utf-8')
        print(json.dumps(payload))
        return 3
    q=build_serp_queue(day,semrush); qp=SCANS/f'{day}-serp-dd-queue{suffix}.json'; atomic(qp,q); serpdir=SCANS/f'{day}-serp-dd-{args.suffix or "product-v2"}'
    srun={'status':'PASS','stage':'EMPTY'} if not q['queue'] else run_serp(qp,serpdir,args.serp_timeout)
    serp_map={}; rp=serpdir/'results.json'
    if rp.exists():
        try: serp_map={x.get('cluster_id'):x for x in (load(rp).get('results') or [])}
        except Exception: serp_map={}
    verdicts=[]; matched={x['domain'] for x in q['queue']}
    for item in semrush.get('items') or []:
        domain=str(item.get('domain') or '')
        if item.get('status')!='PASS': verdicts.append({'domain':domain,'verdict':'BLOCKED','reason':'SEMRUSH_ITEM_'+str(item.get('status'))}); continue
        if domain not in matched:
            m=item.get('metrics') or {}; kws=int(m.get('organic_keywords') or 0)
            v,reason,metrics=('WATCH','NO_MATCHED_PRODUCT_INTENT_KEYWORD',{'traffic':float(m.get('estimated_traffic_sum') or 0),'organic_keywords':kws})
        else: v,reason,metrics=verdict_for(item,serp_map.get(domain))
        verdicts.append({'domain':domain,'verdict':v,'reason':reason,'metrics':metrics,'serp_gate':(serp_map.get(domain) or {}).get('serp_gate'),'product_intent_checked':domain in matched})
    counts=Counter(x['verdict'] for x in verdicts); status=('PASS_SCOPED' if allowed else 'PASS') if not counts.get('BLOCKED') and str(srun.get('status')).upper()=='PASS' else 'DEGRADED'
    payload={'date':day,'status':status,'completed_at':now_iso(),'source':'seotrends-daily-terminal-product-v2','semrush_status':semrush.get('status'),'source_overall_status':source_status,'serp_run':srun,'counts':{k:counts.get(k,0) for k in ('BUILD','WATCH','DROP','BLOCKED')},'verdicts':verdicts,'policy':{'auto_build':False,'serp_pass':'WATCH until semantic/business DD','product_intent':'required; unmatched stays WATCH','scope':sorted(allowed) if allowed else 'all'}}
    atomic(outj,payload)
    lines=[f'# SeoTrends terminal — {day}','',f'- status: {status}',f'- BUILD: {counts.get("BUILD",0)}',f'- WATCH: {counts.get("WATCH",0)}',f'- DROP: {counts.get("DROP",0)}',f'- BLOCKED: {counts.get("BLOCKED",0)}','- auto BUILD: disabled; SERP pass remains WATCH until semantic/business DD','', '## Verdicts','']
    for x in verdicts: lines.append(f'- **{x["domain"]}** — {x["verdict"]} — {x["reason"]}')
    outm.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps({'status':status,'date':day,'counts':payload['counts'],'output':str(outj)},ensure_ascii=False)); return 0 if status in ('PASS','PASS_SCOPED') else 3

if __name__=='__main__': raise SystemExit(main())
