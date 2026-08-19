import json, random, statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
import sys

# Reuse the exact frozen definitions/enrichment used by the successful TF×session×T matrix.
sys.path.insert(0,'wave-rider-verify')
import wr_tf_session_t_matrix as m

OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
T=m.T; C=m.C; net=m.net; utc_dt=m.utc_dt; session=m.session; t_on=m.t_on; ET=m.ET
COSTS=(4,6,8,10,12,15,20)
TON=(-2,-1,0,2,3)

# Event-type labels for the already-frozen event dates from the matrix. No dates or T offsets are changed here.
CPI={
'2025-01-15','2025-02-12','2025-03-12','2025-04-10','2025-05-13','2025-06-11','2025-07-15','2025-08-12','2025-09-11','2025-10-24','2025-12-18',
'2026-01-13','2026-02-13','2026-03-11','2026-04-10','2026-05-12','2026-06-10','2026-07-14','2026-08-12'}
NFP={
'2025-01-10','2025-02-07','2025-03-07','2025-04-04','2025-05-02','2025-06-06','2025-07-03','2025-08-01','2025-09-05','2025-11-20','2025-12-16',
'2026-01-09','2026-02-11','2026-03-06','2026-04-03','2026-05-08','2026-06-05','2026-07-02','2026-08-07'}
FOMC={
'2025-01-29','2025-03-19','2025-05-07','2025-06-18','2025-07-30','2025-09-17','2025-10-29','2025-12-10',
'2026-01-28','2026-03-18','2026-04-29','2026-06-17','2026-07-29'}
LABEL={date.fromisoformat(x):'CPI' for x in CPI}
LABEL.update({date.fromisoformat(x):'NFP' for x in NFP})
LABEL.update({date.fromisoformat(x):'FOMC' for x in FOMC})
assert set(LABEL)==set(m.EVENT_DATES), (len(LABEL),len(m.EVENT_DATES),set(m.EVENT_DATES)-set(LABEL),set(LABEL)-set(m.EVENT_DATES))

def event_matches(a):
    d=utc_dt(a).astimezone(ET).date(); out=[]
    for e in m.EVENT_DATES:
        off=(d-e).days
        if off in TON:
            out.append({'date':e.isoformat(),'type':LABEL[e],'offset':off,'distance':abs(off)})
    return sorted(out,key=lambda z:(z['distance'],z['date'],z['type']))

def assigned_event(a):
    x=event_matches(a)
    return x[0] if x else None

def maxdd(xs,bps=6):
    eq=peak=mdd=0.0
    for a in sorted(xs,key=lambda z:(z['signal_time'],z['symbol'])):
        eq+=net(a,bps); peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return mdd

def metrics(xs,bps=6):
    vals=[net(a,bps) for a in xs]
    return {'n':len(xs),'net':sum(vals),'avg':statistics.mean(vals) if vals else None,'max_dd':maxdd(xs,bps),'symbols':len(set(a['symbol'] for a in xs))}

def by_month(xs,bps=6):
    z=defaultdict(float)
    for a in xs:z[utc_dt(a).strftime('%Y-%m')]+=net(a,bps)
    return dict(sorted(z.items()))

def bootstrap_trade(xs,n=10000,seed=251503):
    vals=[net(a,6) for a in xs]
    if not vals:return [None,None]
    r=random.Random(seed); draws=[]
    for _ in range(n):draws.append(sum(r.choice(vals) for _ in vals)/len(vals))
    draws.sort();return [draws[int(.025*n)],draws[int(.975*n)-1]]

def block_bootstrap(totals,n=10000,seed=251504):
    vals=list(totals)
    if not vals:return [None,None]
    r=random.Random(seed); draws=[]
    for _ in range(n):draws.append(sum(r.choice(vals) for _ in vals)/len(vals))
    draws.sort();return [draws[int(.025*n)],draws[int(.975*n)-1]]

def symbol_concentration(xs):
    z=defaultdict(float)
    for a in xs:z[a['symbol']]+=net(a,6)
    ranked=sorted(z.items(),key=lambda kv:kv[1],reverse=True)
    total=sum(net(a,6) for a in xs)
    return {'top10':ranked[:10],**{f'drop_top_{k}':total-sum(v for _,v in ranked[:k]) for k in (1,5,10)}}

def summary(xs):
    bm=by_month(xs); total=sum(net(a,6) for a in xs)
    loo={k:total-v for k,v in bm.items()}
    return {
      'costs':{str(b):metrics(xs,b) for b in COSTS},
      'by_year':{str(y):{str(b):metrics([a for a in xs if utc_dt(a).year==y],b) for b in (6,8,10,12)} for y in (2025,2026)},
      'months':bm,'positive_months':sum(v>0 for v in bm.values()),'active_months':len(bm),
      'leave_one_month_out':{'min':min(loo.values()) if loo else None,'all_positive':all(v>0 for v in loo.values()) if loo else False},
      'bootstrap_trade_mean95':bootstrap_trade(xs),
      'bootstrap_month_mean95':block_bootstrap(bm.values()),
      'side':{s:metrics([a for a in xs if str(a.get('side','')).upper()==s],6) for s in ('LONG','SHORT')},
      'symbol_concentration':symbol_concentration(xs)
    }

zonec_all=[a for a in T if session(a)=='ZONE_C']
zonec_t=[a for a in zonec_all if t_on(a)]
zonec_c3=[a for a in C if session(a)=='ZONE_C']
X=[a for a in zonec_c3 if t_on(a)]
assert X

# Unique deterministic attribution for concentration tests; raw overlap counts are also reported.
assigned=[]; overlap=0
for a in X:
    ms=event_matches(a)
    if len(ms)>1:overlap+=1
    e=ms[0]
    b=dict(a); b['_event']=e; assigned.append(b)

ev=defaultdict(list); etype=defaultdict(list); eoff=defaultdict(list)
for a in assigned:
    e=a['_event']; ev[e['date']].append(a); etype[e['type']].append(a); eoff[str(e['offset'])].append(a)
ev_sum={k:metrics(v,6) for k,v in sorted(ev.items())}
total6=sum(net(a,6) for a in assigned)
loo_event={k:total6-v['net'] for k,v in ev_sum.items()}
rank_events=sorted(((k,v['net'],v['n']) for k,v in ev_sum.items()),key=lambda z:z[1],reverse=True)

def drop_top_events(k):return total6-sum(x[1] for x in rank_events[:k])

comparison={
 'zonec_baseline_all':summary(zonec_all),
 'zonec_baseline_t_on':summary(zonec_t),
 'zonec_candidate3_all_days':summary(zonec_c3),
 'frozen_zonec_candidate3_t_on':summary(X),
 'retention_vs_c3_all':{'trade_pct':100*len(X)/len(zonec_c3) if zonec_c3 else None,'net6_pct':100*total6/sum(net(a,6) for a in zonec_c3) if zonec_c3 and sum(net(a,6) for a in zonec_c3)!=0 else None}
}

report={
 'status':'WR_FROZEN_C3_T_ROBUSTNESS_COMPLETE',
 'frozen_rule':'WR 10m + Zone C 23:00-00:59 VN + BTC30<0 + BTC RV20>RV60 + breadth<=50% + funding3<=0 + T_ON {-2,-1,0,+2,+3}',
 'warning':'Retrospective composition robustness only. Candidate3 and T were discovered historically; this is not pristine OOS and no subset from event/type/offset decomposition may be promoted from this run.',
 'source':{'tf':10,'base_run':32237685245,'artifact':'wr2515-phase1-10m-final','common_universe_symbols':len(m.U)},
 'comparison':comparison,
 'event_diagnostic':{
   'unique_assignment_rule':'Among qualifying frozen T_ON events, assign trade to smallest absolute T offset; ties by event date then type. This is diagnostic only.',
   'trades_with_multiple_matching_event_windows':overlap,
   'by_event':ev_sum,
   'by_event_type':{k:summary(v) for k,v in sorted(etype.items())},
   'by_t_offset':{k:summary(v) for k,v in sorted(eoff.items(),key=lambda kv:int(kv[0]))},
   'positive_events':sum(v['net']>0 for v in ev_sum.values()),'active_events':len(ev_sum),
   'leave_one_event_out':{'min':min(loo_event.values()) if loo_event else None,'all_positive':all(v>0 for v in loo_event.values()) if loo_event else False,'values':loo_event},
   'event_block_bootstrap_mean95':block_bootstrap([v['net'] for v in ev_sum.values()],seed=251505),
   'event_concentration':{'ranked':rank_events,'drop_top_1':drop_top_events(1),'drop_top_3':drop_top_events(3),'drop_top_5':drop_top_events(5)}
 }
}
json.dump(report,open(OUT/'c3_t_robustness.json','w'),indent=2)
with open(OUT/'candidate_trades.jsonl','w') as f:
    for a in assigned:f.write(json.dumps(a,separators=(',',':'))+'\n')
print(json.dumps({'status':report['status'],'n':len(X),'net6':total6,'events':len(ev_sum),'overlap_trades':overlap,'costs':comparison['frozen_zonec_candidate3_t_on']['costs']},indent=2))
