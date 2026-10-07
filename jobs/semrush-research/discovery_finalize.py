#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, time

def ts(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--serp-results',required=True)
    ap.add_argument('--registry',required=True)
    ap.add_argument('--summary',required=True)
    a=ap.parse_args()
    serp=json.loads(pathlib.Path(a.serp_results).read_text(encoding='utf-8'))
    regp=pathlib.Path(a.registry)
    reg=json.loads(regp.read_text(encoding='utf-8')) if regp.exists() else {'version':1,'records':[]}
    existing={(r.get('cluster_id'),r.get('project')):r for r in reg.get('records') or []}
    added=0
    verdicts={}
    survivors=[]
    for x in serp.get('results') or []:
        key=(x.get('cluster_id'),x.get('project'))
        rec={'project':x.get('project'),'cluster_id':x.get('cluster_id'),'label':x.get('label'),
             'serp_gate':x.get('serp_gate'),'avg_exact_tool_top10':x.get('avg_exact_tool_top10'),
             'top_keywords':[k.get('keyword') for k in (x.get('top_keywords') or []) if k.get('keyword')],
             'tested_at':serp.get('created_at') or ts(),'source_results':a.serp_results}
        if key not in existing: added+=1
        existing[key]=rec
        g=str(x.get('serp_gate') or 'UNKNOWN'); verdicts[g]=verdicts.get(g,0)+1
        if g=='SERP_DD_PASS': survivors.append(rec)
    reg={'version':1,'updated_at':ts(),'purpose':'Canonical anti-repeat registry for exact SERP-tested SEO discovery candidates.',
         'records':sorted(existing.values(),key=lambda r:(str(r.get('project')),str(r.get('cluster_id'))))}
    atomic(regp,reg)
    summary={'version':1,'updated_at':ts(),'verdicts':verdicts,'survivor_count':len(survivors),
             'survivors':survivors,'registry_added':added,'registry_total':len(reg['records'])}
    atomic(pathlib.Path(a.summary),summary)
    print(json.dumps({'status':'PASS',**summary},ensure_ascii=False))
if __name__=='__main__': main()
