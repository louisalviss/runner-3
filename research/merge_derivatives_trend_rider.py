#!/usr/bin/env python3
import glob,sys
import numpy as np,pandas as pd
out=sys.argv[1]; fs=glob.glob('artifacts/**/trades.csv',recursive=True); xs=[]
for f in fs:
 try:
  x=pd.read_csv(f)
  if len(x):xs.append(x)
 except:pass
if not xs:
 open(out,'w').write('NO VALID DERIVATIVES TRADES\n');sys.exit()
x=pd.concat(xs,ignore_index=True); x['time']=pd.to_datetime(x.time,utc=True); x['episode']=x.time.dt.floor('30min')
rows=[]
for keys,g in x.groupby(['year','tf','family','tp']):
 # ex-ante: strongest absolute derivatives score, max 3; episode risk split to total 1R
 picks=[]
 for ep,q in g.groupby('episode'):
  q=q.sort_values('score',key=lambda s:s.abs(),ascending=False).head(3).copy(); q['w']=1/len(q); picks.append(q)
 p=pd.concat(picks) if picks else g.iloc[:0]
 r=dict(zip(['year','tf','family','tp'],keys));r['trades']=len(p);r['episodes']=p.episode.nunique()
 for c in [4,6,8,10,12]:r[f'portfolio_net{c}']=float((p[f'net{c}']*p.w).sum())
 r['avg_net6']=float(p.net6.mean()) if len(p) else np.nan; rows.append(r)
s=pd.DataFrame(rows).sort_values(['tf','family','tp','year']);s.to_csv(out,index=False)
# Frozen criterion: development aggregate >0, then 2025 >0 and untouched 2026 >0 @6bps; >=100 episodes each eval year.
print(s.to_string(index=False));print('\nPASS:')
for k,g in s.groupby(['tf','family','tp']):
 d=g[g.year.isin([2022,2023,2024])].portfolio_net6.sum();v=g[g.year==2025];o=g[g.year==2026]
 if len(v) and len(o) and d>0 and v.iloc[0].portfolio_net6>0 and o.iloc[0].portfolio_net6>0 and v.iloc[0].episodes>=100 and o.iloc[0].episodes>=100:print(k,'DEV',d,'VAL',v.iloc[0].portfolio_net6,'OOS',o.iloc[0].portfolio_net6)
