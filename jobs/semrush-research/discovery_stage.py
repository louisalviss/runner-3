#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, subprocess, sys, time

def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def atomic(path: pathlib.Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)

def toks(s):
    return {x for x in re.findall(r'[a-z0-9]+', str(s or '').lower()) if len(x)>=2}

GENERIC={'calculator','calculation','calculate','tool','tools','lookup','finder','find','checker','check','estimator','estimate','selector','selection','sizing','size','cost','price','pricing','serial','number','numbers','model','address','compatibility','compatible','capacity','load','value','values','fitment','cross','reference','spec','specs','specification','material','materials','configuration','requirements','requirement','quantity','replacement','replace','equivalent','part','parts','free','online','chart','guide','search','by','for','of','the','and','in','on','to','with'}

def desc(s):
    return {x for x in toks(s) if x not in GENERIC}

def load_tested(path):
    p=pathlib.Path(path)
    if not p.exists(): return []
    data=json.loads(p.read_text(encoding='utf-8'))
    out=[]
    for r in data.get('records') or []:
        vals=[r.get('label',''),r.get('project','')]+list(r.get('top_keywords') or [])
        for v in vals:
            d=desc(v)
            if d: out.append(d)
    return out

def was_tested(subject, tested):
    s=desc(subject)
    if not s: return True
    for d in tested:
        if s <= d or d <= s:
            return True
    return False

def slug(s):
    base=re.sub(r'[^a-z0-9]+','-',str(s).lower()).strip('-')[:48] or 'candidate'
    return base+'-'+hashlib.sha1(str(s).encode()).hexdigest()[:8]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',nargs='+',required=True)
    ap.add_argument('--config-dir',required=True)
    ap.add_argument('--tested-registry',required=True)
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--min-keyword-volume',type=int,default=100)
    ap.add_argument('--max-kd',type=float,default=29)
    ap.add_argument('--min-cluster-volume',type=int,default=500)
    ap.add_argument('--min-serp-volume',type=int,default=1000)
    ap.add_argument('--max-serp-candidates',type=int,default=8)
    a=ap.parse_args()

    out=pathlib.Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    candidates=out/'candidates.json'
    miner=pathlib.Path(__file__).with_name('modifier_mine.py')
    cmd=[sys.executable,str(miner),'--input',*a.input,'--output',str(candidates),'--config-dir',a.config_dir,
         '--min-volume',str(a.min_keyword_volume),'--max-kd',str(a.max_kd),
         '--min-cluster-volume',str(a.min_cluster_volume),'--top','200']
    cp=subprocess.run(cmd,capture_output=True,text=True)
    if cp.returncode:
        state={'version':1,'stage':'BLOCKED_MINER','updated_at':ts(),'returncode':cp.returncode,'stderr':cp.stderr[-2000:]}
        atomic(out/'state.json',state); print(json.dumps(state)); return cp.returncode

    mined=json.loads(candidates.read_text(encoding='utf-8'))
    tested=load_tested(a.tested_registry)
    shortlist=[]
    skipped_tested=[]
    for c in mined.get('clusters') or []:
        if was_tested(c.get('subject',''),tested):
            skipped_tested.append(c.get('subject')); continue
        total=int(c.get('total_volume') or 0)
        if total < a.min_serp_volume: continue
        if int(c.get('keyword_count') or 0) < 2 and total < 5000: continue
        top=[]
        for x in c.get('top_keywords') or []:
            kw=str(x.get('keyword') or '').strip()
            if not kw: continue
            top.append({'keyword':kw,'volume':int(x.get('volume') or 0),'kd':x.get('kd'),'cpc':x.get('cpc') or 0})
            if len(top)>=8: break
        if not top: continue
        sid=slug(c['subject'])
        shortlist.append({
          'project':'discovery-'+sid,
          'cluster_id':'discovery-'+sid+'-001',
          'label':c['subject'],
          'total_volume':int(c.get('total_volume') or 0),
          'median_kd':c.get('median_kd'),
          'weighted_cpc':c.get('weighted_cpc') or 0,
          'head_share':c.get('head_share') or 0,
          'score':c.get('score') or 0,
          'top_keywords':top,
          'gate_tier':'MODIFIER_DISCOVERY',
          'next':'exact SERP DD; promote only if SERP survives'
        })
        if len(shortlist)>=a.max_serp_candidates: break

    queue={'status':'PENDING' if shortlist else 'EMPTY','lane':'semrush-modifier-discovery','created_at':ts(),
           'passed_projects':[x['project'] for x in shortlist],'queue':shortlist}
    atomic(out/'serp-dd-queue.json',queue)
    stage='SERP_DD_PENDING' if shortlist else 'COMPLETE_NO_CANDIDATE'
    state={'version':1,'stage':stage,'updated_at':ts(),'input_count':len(a.input),
           'raw_rows':mined.get('raw_rows',0),'qualified_rows':mined.get('qualified_rows',0),
           'mined_clusters':mined.get('cluster_count',0),'skipped_tested_count':len(skipped_tested),
           'queue_count':len(shortlist),'queue':str(out/'serp-dd-queue.json'),'candidates':str(candidates)}
    atomic(out/'state.json',state)
    print(json.dumps({'status':'PASS',**state},ensure_ascii=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
