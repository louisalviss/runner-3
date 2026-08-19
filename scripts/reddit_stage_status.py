#!/usr/bin/env python3
import datetime, json, sys
from pathlib import Path

p=Path('ops/reddit-narrator/latest.json')
p.parent.mkdir(parents=True,exist_ok=True)
base={
  'status':'running',
  'episodeId':'reddit-creepiest-unsolved-v1',
  'voice':'vi-VN-NamMinhNeural',
  'resume':'localStorage/same-browser',
  'steps':{'install':'pending','redditFetch':'pending','render':'pending','publish':'pending'},
}
if p.exists():
    try: base.update(json.loads(p.read_text(encoding='utf-8')))
    except Exception: pass
base.setdefault('steps',{})
for k in ('install','redditFetch','render','publish'):
    base['steps'].setdefault(k,'pending')
if len(sys.argv)>=3:
    base['steps'][sys.argv[1]]=sys.argv[2]
if len(sys.argv)>=4:
    base['status']=sys.argv[3]
base['updatedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
p.write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
