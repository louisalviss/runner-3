#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, time

CATALOG=[
 "rate calculator","fee calculator","tax calculator","conversion calculator","ratio calculator","flow calculator",
 "weight calculator","dimension calculator","tolerance calculator","pressure calculator","power calculator","energy calculator",
 "volume calculator","area calculator","length calculator","rpm calculator","gear calculator","runtime calculator",
 "eligibility checker","requirement checker","compliance checker","availability checker","status lookup","identifier lookup",
 "date code lookup","age lookup","warranty lookup","recall lookup","service interval lookup","error code lookup",
 "replacement lookup","part finder","product selector","equipment selector","model decoder","serial decoder",
 "cross reference chart","interchange lookup","application lookup","coverage estimator","quantity estimator","configuration tool",
 "consumption calculator","performance calculator","efficiency calculator","loss calculator","yield calculator","mixing calculator",
 "spacing calculator","clearance calculator","load capacity calculator","operating cost calculator","total cost calculator",
 "by zip code lookup","by address lookup","permit lookup","inspection lookup"
]

def norm(s): return ' '.join(str(s or '').lower().split())
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--config-dir',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--count',type=int,default=8)
    a=ap.parse_args()
    seen=set()
    for p in pathlib.Path(a.config_dir).glob('*.json'):
        try:j=json.loads(p.read_text(encoding='utf-8'))
        except Exception:continue
        for t in j.get('themes') or []:
            for s in t.get('seeds') or []: seen.add(norm(s))
    pick=[s for s in CATALOG if norm(s) not in seen][:a.count]
    themes=[{'theme_id':'discovery-'+s.replace(' ','-'),'label':s.title()+' Discovery','seeds':[s]} for s in pick]
    payload={'version':1,'source':'semrush-modifier-root-auto','database':'us',
             'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
             'purpose':'Automatically selected unseen modifier roots for SEO idea discovery.','themes':themes}
    out=pathlib.Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','selected':len(pick),'seeds':pick,'output':str(out)},ensure_ascii=False))
if __name__=='__main__': main()
