import json, math, sys, importlib.util
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
ROOT=Path('/opt/runner3-wr-tickfix-20260921'); REL=Path('/opt/wr-crossasset-release'); OUT=ROOT/'research/wr_finalized_fidelity_audit_20260921'
UTC=timezone.utc; VN=ZoneInfo('Asia/Ho_Chi_Minh'); TF=15; TFMS=TF*60000; TP=2.3; VARIANT=sys.argv[1].upper()
if VARIANT not in ('T','ALL'): raise SystemExit('variant must be T or ALL')
START=int(datetime(2022,1,1,tzinfo=UTC).timestamp()*1000); END=int(datetime(2026,8,15,tzinfo=UTC).timestamp()*1000)
# calendar authority
st=json.load(open(OUT/'wr_m30_crossasset_stage1_signals_20260922.json')); T0={datetime.fromisoformat(x).date() for x in st['calendar_T0']}
labels={}
for y in range(2021,2027):
 d=datetime(y,1,1).date(); e=datetime(y,12,31).date()
 while d<=e:
  labs=set()
  for x in T0:
   off=(d-x).days
   if off in (-2,-1,0,1,2,3): labs.add({-2:'T-2',-1:'T-1',0:'T0',1:'T+1',2:'T+2',3:'T+3'}[off])
  labels[d]=labs; d+=timedelta(days=1)
def tclass(ms):
 dt=datetime.fromtimestamp(ms/1000,tz=UTC).astimezone(VN); d=dt.date()
 if d.weekday()>=5:return 'OFF_WEEKEND'
 labs=labels.get(d,set())
 if labs & {'T-2','T-1','T0','T+2','T+3'}:return 'OFF_CLUSTER'
 return 'T+1' if 'T+1' in labs else 'NORMAL'
def filter_ok(ms):
 tc=tclass(ms)
 if tc=='OFF_WEEKEND': return False,tc
 if VARIANT=='T': return tc in ('NORMAL','T+1'),tc
 return True,tc
def tick_from(vals):
 md=0
 for v in vals[:5000]:
  s=f'{float(v):.8f}'.rstrip('0')
  if '.' in s: md=max(md,len(s.split('.')[1]))
 return 10**(-min(md,6))
def rma(x,n):
 out=np.full(len(x),np.nan); 
 if len(x)<n:return out
 p=float(np.mean(x[:n])); out[n-1]=p
 for i in range(n,len(x)):
  p=(p*(n-1)+x[i])/n; out[i]=p
 return out
def indicators(o,h,l,c):
 n=len(c)
 # exact recursive EMA seed first close
 e=np.empty(n); a=2/22; e[0]=c[0]
 for i in range(1,n): e[i]=a*c[i]+(1-a)*e[i-1]
 pc=np.r_[c[0],c[:-1]]; tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc)))
 a10=rma(tr,10); a14=rma(tr,14)
 rh=np.full(n,np.nan); rl=np.full(n,np.nan); tsum=np.full(n,np.nan)
 w14h=np.lib.stride_tricks.sliding_window_view(h,14); w14l=np.lib.stride_tricks.sliding_window_view(l,14); w14t=np.lib.stride_tricks.sliding_window_view(tr,14)
 rh[13:]=w14h.max(axis=1); rl[13:]=w14l.min(axis=1); tsum[13:]=w14t.sum(axis=1)
 # unique 10/10 pivot at center; confirm + right + Pine [1] => +11
 wh=np.lib.stride_tricks.sliding_window_view(h,10); wl=np.lib.stride_tricks.sliding_window_view(l,10)
 left_h=np.full(n,np.nan); right_h=np.full(n,np.nan); left_l=np.full(n,np.nan); right_l=np.full(n,np.nan)
 left_h[10:]=wh[:-1].max(axis=1); right_h[:n-10]=wh[1:].max(axis=1)
 left_l[10:]=wl[:-1].min(axis=1); right_l[:n-10]=wl[1:].min(axis=1)
 phcand=(h>left_h)&(h>right_h); plcand=(l<left_l)&(l<right_l)
 ph=np.full(n,np.nan); pl=np.full(n,np.nan)
 src=np.where(phcand)[0]; idx=src+11; m=idx<n; ph[idx[m]]=h[src[m]]
 src=np.where(plcand)[0]; idx=src+11; m=idx<n; pl[idx[m]]=l[src[m]]
 ridx=np.maximum.accumulate(np.where(np.isfinite(ph),np.arange(n),-1)); sidx=np.maximum.accumulate(np.where(np.isfinite(pl),np.arange(n),-1))
 res=np.full(n,np.nan); sup=np.full(n,np.nan); mr=ridx>=0; ms=sidx>=0; res[mr]=ph[ridx[mr]]; sup[ms]=pl[sidx[ms]]
 above=(c>e).astype(np.int32); below=(c<e).astype(np.int32)
 ha=np.zeros(n,dtype=bool); hb=np.zeros(n,dtype=bool)
 ca=np.r_[0,np.cumsum(above,dtype=np.int64)]; cb=np.r_[0,np.cumsum(below,dtype=np.int64)]
 ha[11:]=(ca[12:]-ca[:-12])==12; hb[11:]=(cb[12:]-cb[:-12])==12
 eup=np.zeros(n,dtype=bool); eup[2:]=e[2:]>=e[:-2]
 ang=np.full(n,np.nan); valid=np.arange(n)>=4; ids=np.where(valid & np.isfinite(a10) & (a10!=0))[0]; ang[ids]=np.degrees(np.arctan((e[ids]-e[ids-4])/a10[ids]/4))
 prev=np.r_[np.nan,ang[:-1]]; outside=(ang>5)|(ang<-5); ag=outside&(ang>prev); ar=outside&(ang<prev)
 chop=np.full(n,np.nan); good=np.isfinite(tsum)&np.isfinite(rh)&(rh>rl)&(tsum>0); chop[good]=100*np.log10(tsum[good]/(rh[good]-rl[good]))/np.log10(14)
 chopok=chop<50; sra=(h-l)/a14; sraok=sra<=1.5
 return dict(ema=e,res=res,sup=sup,ha=ha,hb=hb,eup=eup,ag=ag,ar=ar,chop=chopok,sra=sraok)
def path_bracket(oo,hh,ll,cc,d,e,s,t,start_active=False):
 pts=[oo,hh,ll,cc] if abs(oo-hh)<abs(oo-ll) else [oo,ll,hh,cc]
 active=start_active; cur=pts[0]
 if active:
  if d==1 and oo<=s:return 'SL',oo
  if d==1 and oo>=t:return 'TP',oo
  if d==-1 and oo>=s:return 'SL',oo
  if d==-1 and oo<=t:return 'TP',oo
 for z in pts[1:]:
  pos=cur
  while True:
   if not active:
    enter=(d==1 and pos<e<=z) or (d==-1 and pos>e>=z)
    if not enter:break
    pos=e; active=True; continue
   cand=[]
   if min(pos,z)<=s<=max(pos,z) and abs(s-pos)>1e-12:cand.append((abs(s-pos),'SL',s))
   if min(pos,z)<=t<=max(pos,z) and abs(t-pos)>1e-12:cand.append((abs(t-pos),'TP',t))
   if not cand:break
   _,r,p=min(cand);return r,p
  cur=z
 return None,None
def metric(tr):
 vals=[x['R'] for x in tr];gp=sum(max(x,0) for x in vals);gl=sum(max(-x,0) for x in vals);eq=peak=dd=0;ls=ml=0
 for x in sorted(tr,key=lambda z:z['exit_ms']):
  v=x['R'];eq+=v;peak=max(peak,eq);dd=max(dd,peak-eq);ls=ls+1 if v<0 else 0;ml=max(ml,ls)
 return dict(n=len(vals),R=sum(vals),E=sum(vals)/len(vals) if vals else None,PF=gp/gl if gl else None,maxDD_R=dd,maxLS=ml)
def run(sym,group,ms,o,h,l,c,tick):
 z=indicators(o,h,l,c); n=len(c); tr=[]; pending=None; active=None; diag=dict(signals=0,admitted=0,fills=0,expired=0,tp=0,sl=0,ema=0,session=0)
 stock_close={}
 if group=='US_STOCK_CFD':
  days=ms//86400000
  for d in np.unique(days):
   idx=np.where(days==d)[0]
   stock_close[int(d)]=int(ms[idx[-1]]+TFMS-1)
 for i in range(n):
  ct=int(ms[i]+TFMS-1)
  if ct<START:continue
  if ct>=END:break
  closed=False
  if active is not None:
   r,px=path_bracket(o[i],h[i],l[i],c[i],active['d'],active['e'],active['s'],active['t'],True)
   if r:
    rr=TP if r=='TP' else -1.0; tr.append({**active,'exit_ms':ct,'exit_reason':r,'exit_price':px,'R':rr});diag['tp' if r=='TP' else 'sl']+=1;active=None;closed=True
  if active is None and pending is not None and i==pending['sig_i']+1 and not closed:
   fill=(pending['d']==1 and h[i]>=pending['e']) or (pending['d']==-1 and l[i]<=pending['e'])
   if fill:
    active=pending; pending=None; active['entry_ms']=int(ms[i]);diag['fills']+=1
    r,px=path_bracket(o[i],h[i],l[i],c[i],active['d'],active['e'],active['s'],active['t'],False)
    if r:
     rr=TP if r=='TP' else -1.0;tr.append({**active,'exit_ms':ct,'exit_reason':r,'exit_price':px,'R':rr});diag['tp' if r=='TP' else 'sl']+=1;active=None;closed=True
   else:diag['expired']+=1;pending=None
  # Preregistered native-session lifecycle.
  if group=='US_STOCK_CFD':
   close_ct=stock_close.get(int(ms[i]//86400000),ct)
   ne=close_ct-40*60000; ex=close_ct-15*60000
   allowed=not (ct>=ne or ct+TFMS>=ne)
   sexit=(ct<ex and ct+TFMS>=ex) or (ct>=ex and ct<=close_ct)
  else:
   tod=ct%86400000
   sexit=(tod<85500000 and tod+TFMS>=85500000) or tod>=85500000
   allowed=not (tod>=84000000 or tod+TFMS>=84000000)
  if active is not None and not closed:
   le=active['d']==1 and c[i]<z['ema'][i] and not z['ha'][i] and not z['eup'][i]
   se=active['d']==-1 and c[i]>z['ema'][i] and not z['hb'][i] and z['eup'][i]
   if sexit or le or se:
    rr=(c[i]-active['e'])*(1 if active['d']==1 else -1)/abs(active['e']-active['s']); tr.append({**active,'exit_ms':ct,'exit_reason':'SESSION' if sexit else 'EMA','exit_price':float(c[i]),'R':float(rr)});diag['session' if sexit else 'ema']+=1;active=None;closed=True
  if pending is not None and active is None and i>=pending['sig_i']+1:diag['expired']+=1;pending=None
  if active is None and pending is None and not closed:
   lr=z['ha'][i] and c[i]>z['ema'][i] and z['ag'][i] and z['chop'][i] and np.isfinite(z['res'][i])
   sr=z['hb'][i] and c[i]<z['ema'][i] and z['ar'][i] and z['chop'][i] and np.isfinite(z['sup'][i])
   nl=allowed and z['sra'][i] and c[i]>o[i] and lr and c[i]>z['res'][i] and l[i]<=z['res'][i]
   ns=allowed and z['sra'][i] and c[i]<o[i] and sr and c[i]<z['sup'][i] and h[i]>=z['sup'][i]
   if nl or ns:
    diag['signals']+=1; ok,tc=filter_ok(ct)
    if not ok:continue
    diag['admitted']+=1; d=1 if nl else -1
    if d==1:e=round(h[i]/tick)*tick+tick;s=round(l[i]/tick)*tick-tick;t=e+TP*(e-s)
    else:e=round(l[i]/tick)*tick-tick;s=round(h[i]/tick)*tick+tick;t=e-TP*(s-e)
    if abs(e-s)>0:pending=dict(symbol=sym,group=group,sig_i=i,signal_ms=ct,tclass=tc,d=d,e=float(e),s=float(s),t=float(t),entry_ms=None)
 return tr,diag

def load(f):
 t=pq.read_table(f,columns=['open','high','low','close','timestamp_utc']).to_pydict(); ms=np.array([int(x.timestamp()*1000) for x in t['timestamp_utc']],dtype=np.int64);o=np.array(t['open'],float);h=np.array(t['high'],float);l=np.array(t['low'],float);c=np.array(t['close'],float)
 if TF==5:return ms,o,h,l,c
 step=TF//5; buckets=(ms//TFMS)*TFMS; change=np.r_[True,buckets[1:]!=buckets[:-1]]; starts=np.where(change)[0]; ends=np.r_[starts[1:],len(ms)]
 oms=[];oo=[];hh=[];ll=[];cc=[]
 for a,b in zip(starts,ends):
  if b-a!=step:continue
  exp=buckets[a]+np.arange(step)*300000
  if not np.array_equal(ms[a:b],exp):continue
  oms.append(int(buckets[a]));oo.append(float(o[a]));hh.append(float(h[a:b].max()));ll.append(float(l[a:b].min()));cc.append(float(c[b-1]))
 return np.array(oms,dtype=np.int64),np.array(oo),np.array(hh),np.array(ll),np.array(cc)
manifest=json.load(open(REL/'manifest.json'));meta={x['symbol']:x for x in manifest['assets']};out={};alltr=[]
want=set(sys.argv[2:]) if len(sys.argv)>2 else set(meta)
for sym,a in sorted(meta.items()):
 if sym not in want: continue
 ms,o,h,l,c=load(REL/a['file']);tick=tick_from(np.r_[o[:2000],h[:2000],l[:2000],c[:2000]]);tr,diag=run(sym,a['group'],ms,o,h,l,c,tick);alltr+=tr
 yrs={str(y):metric([r for r in tr if datetime.fromtimestamp(r['signal_ms']/1000,tz=UTC).year==y]) for y in range(2022,2027)};early=metric([r for r in tr if datetime.fromtimestamp(r['signal_ms']/1000,tz=UTC).year<=2023]);late=metric([r for r in tr if datetime.fromtimestamp(r['signal_ms']/1000,tz=UTC).year>=2024]);m=metric(tr);pos=sum(1 for x in yrs.values() if x['n'] and x['R']>0)
 out[sym]={**m,'group':a['group'],'diag':diag,'years':yrs,'early':early,'late':late,'positive_years':pos,'tick':tick};print(sym,out[sym],flush=True)
classes={g:metric([r for r in alltr if r['group']==g]) for g in sorted(set(r['group'] for r in alltr))}; stable=[s for s,v in out.items() if v['n']>=30 and v['R']>0 and v['early']['R']>0 and v['late']['R']>0 and v['positive_years']>=3]
rank=sorted(out.items(),key=lambda kv:kv[1]['R'],reverse=True);res={'tf':f'M{TF}','source':'market-data-crossasset-m5-20260821 BID','period':['2022-01-01','2026-08-14'],'all':metric(alltr),'classes':classes,'by_symbol':out,'gross_stable_prefilter':stable,'ranking':[{'symbol':s,'group':v['group'],'n':v['n'],'R':v['R'],'E':v['E'],'PF':v['PF'],'early_R':v['early']['R'],'late_R':v['late']['R'],'positive_years':v['positive_years']} for s,v in rank]}
tag=(sorted(want)[0] if want else 'ALL19'); res['variant']=VARIANT; res['session_policy']='native'; json.dump(res,open(OUT/f'wr_m15_native_{VARIANT}_{tag}_gross_2022_20260814.json','w'),indent=2)
print('FINAL',json.dumps({'all':res['all'],'classes':classes,'stable':stable,'top':res['ranking'][:10]},indent=2))
