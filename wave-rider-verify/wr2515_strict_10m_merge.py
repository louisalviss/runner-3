import json, math, os
from collections import Counter
from pathlib import Path

IN=Path(os.environ.get('IN_DIR','/tmp/all'))
OLD=Path(os.environ.get('OLD_DIR','/tmp/old10'))
OUT=Path(os.environ.get('OUT_DIR','/tmp/final')); OUT.mkdir(parents=True,exist_ok=True)

def load_jsonl(p):
    out=[]
    with open(p) as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out

summaries=[]; failures=[]; integrity=[]; trades=[]
for p in sorted(IN.glob('summary-*.json')): summaries+=json.load(open(p))
for p in sorted(IN.glob('failures-*.json')): failures+=json.load(open(p))
for p in sorted(IN.glob('integrity-*.json')): integrity+=json.load(open(p))
for p in sorted(IN.glob('trades-*.jsonl')): trades+=load_jsonl(p)
if not summaries and not failures: raise SystemExit('no shard outputs')
completed={r['symbol'] for r in summaries}; failed={r['symbol'] for r in failures}
if completed & failed: raise SystemExit('symbol both completed and failed')
if len(completed)+len(failed)!=654: raise SystemExit(f'shard coverage mismatch completed={len(completed)} failed={len(failed)}')
trades.sort(key=lambda a:(a['signal_time'],a['symbol'],a['side']))
old=load_jsonl(OLD/'trades.jsonl'); old.sort(key=lambda a:(a['signal_time'],a['symbol'],a['side']))

def key(a): return (a['symbol'],a['signal_time'],a['side'])
def unique_map(xs,name):
    c=Counter(map(key,xs)); dup=[k for k,n in c.items() if n>1]
    if dup: raise SystemExit(f'{name} duplicate keys: {dup[:20]}')
    return {key(a):a for a in xs}
newm=unique_map(trades,'new'); oldm=unique_map(old,'old')
ks_new=set(newm); ks_old=set(oldm); common=ks_new&ks_old
fields=['entry','stop','target','exit_time','exit_reason','R']
def same(a,b):
    for f in fields:
        x=a.get(f); y=b.get(f)
        if isinstance(x,(int,float)) and isinstance(y,(int,float)):
            if not math.isclose(float(x),float(y),rel_tol=1e-12,abs_tol=1e-12): return False
        elif x!=y:return False
    return True
changed=[k for k in common if not same(newm[k],oldm[k])]
only_new=sorted(ks_new-ks_old); only_old=sorted(ks_old-ks_new)
old_failed=[a for a in old if a['symbol'] in failed]
only_old_completed=[k for k in only_old if k[0] in completed]
only_new_completed=[k for k in only_new if k[0] in completed]
old_n=Counter(a['symbol'] for a in old); new_n=Counter(a['symbol'] for a in trades)
deltas=[]
for s in sorted(completed):
    if old_n[s]!=new_n[s]: deltas.append({'symbol':s,'old_n':old_n[s],'new_n':new_n[s],'delta':new_n[s]-old_n[s]})
report={
 'status':'STRICT_10M_REBUILD_COMPLETE' if not failures else 'STRICT_10M_REBUILD_WITH_INTEGRITY_FAILURES',
 'baseline':{'symbols':654,'trades':len(old)},
 'strict':{'symbols_completed':len(completed),'symbols_failed':len(failed),'trades':len(trades)},
 'comparison':{
   'common_trade_keys':len(common),'unchanged_common':len(common)-len(changed),'changed_common':len(changed),
   'only_old':len(only_old),'only_new':len(only_new),'only_old_from_failed_symbols':len(old_failed),
   'only_old_completed_symbols':len(only_old_completed),'only_new_completed_symbols':len(only_new_completed),
   'symbols_with_trade_count_delta':len(deltas)},
 'failed_symbols':failures,
 'trade_count_deltas_top100':sorted(deltas,key=lambda x:(-abs(x['delta']),x['symbol']))[:100],
 'changed_trade_samples':[{'key':k,'old':oldm[k],'new':newm[k]} for k in changed[:50]],
 'only_old_completed_samples':only_old_completed[:100],
 'only_new_completed_samples':only_new_completed[:100]
}
json.dump(sorted(summaries,key=lambda x:x['symbol']),open(OUT/'summary.json','w'),indent=2)
json.dump(failures,open(OUT/'failures.json','w'),indent=2)
json.dump(integrity,open(OUT/'integrity.json','w'),indent=2)
json.dump(sorted(completed),open(OUT/'universe.json','w'),indent=2)
json.dump(report,open(OUT/'strict_comparison.json','w'),indent=2)
with open(OUT/'trades.jsonl','w') as f:
    for a in trades:f.write(json.dumps(a,separators=(',',':'))+'\n')
print(json.dumps(report,indent=2))
