#!/usr/bin/env python3
import json,gzip,datetime,importlib.util,sys,math,csv
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
ROOT=Path('/opt/runner3-wr-tickfix-20260921');OUT=ROOT/'research/wr_finalized_fidelity_audit_20260921';CACHE=Path('/opt/wr-crossasset-cache')
PRE=json.load(open(OUT/'wr_m30_crossasset_preregister_20260922.json'));ST1=json.load(open(OUT/'wr_m30_crossasset_stage1_signals_20260922.json'))
UTC=datetime.timezone.utc;VN=ZoneInfo('Asia/Ho_Chi_Minh');TFMS=30*60*1000;TPR=2.3
START_MS=int(datetime.datetime(2021,1,1,tzinfo=UTC).timestamp()*1000);END_MS=int(datetime.datetime(2026,8,15,tzinfo=UTC).timestamp()*1000)
rp=ROOT/'.wave-rider-recheck-dropbox/code/reference_verify.py';spec=importlib.util.spec_from_file_location('wrref_crossfinal',rp);ref=importlib.util.module_from_spec(spec);sys.modules['wrref_crossfinal']=ref;spec.loader.exec_module(ref);Bar=ref.Bar
T0={datetime.date.fromisoformat(x) for x in ST1['calendar_T0']};labels={}
for y in range(2020,2027):
 d=datetime.date(y,1,1);last=datetime.date(y,12,31)
 while d<=last:
  labs=set();mp={-2:'T-2',-1:'T-1',0:'T0',1:'T+1',2:'T+2',3:'T+3'}
  for e in T0:
   off=(d-e).days
   if off in mp:labs.add(mp[off])
  labels[d]=labs;d+=datetime.timedelta(days=1)
def tclass(ms):
 dt=datetime.datetime.fromtimestamp(ms/1000,tz=UTC).astimezone(VN);d=dt.date()
 if d.weekday()>=5:return 'OFF_WEEKEND'
 labs=labels.get(d,set())
 if labs & {'T-2','T-1','T0','T+2','T+3'}:return 'OFF_CLUSTER'
 return 'T+1' if 'T+1' in labs else 'NORMAL'
def admitted(ms):
 tc=tclass(ms)
 if tc not in {'NORMAL','T+1'}:return False,tc
 dt=datetime.datetime.fromtimestamp(ms/1000,tz=UTC).astimezone(VN)
 return ((14<=dt.hour<=17) or (21<=dt.hour<=23)),tc
def load_bid(sym):
 rows=json.loads(gzip.decompress((CACHE/'bid'/(sym+'.json.gz')).read_bytes()));return rows,[Bar(int(r[0]),int(r[0])+TFMS-1,*map(float,r[1:5])) for r in rows]
def load_ask(sym):
 m={}
 for ym in ST1['ask_months'].get(sym,[]):
  f=CACHE/'ask'/sym/(ym+'.json.gz')
  if not f.exists():continue
  for r in json.loads(gzip.decompress(f.read_bytes())):m[int(r[0])]=Bar(int(r[0]),int(r[0])+TFMS-1,*map(float,r[1:5]))
 return m
def tick_from_rows(rows):
 md=0
 for r in rows[:min(20000,len(rows))]:
  for v in r[1:5]:
   s=(f'{float(v):.8f}').rstrip('0')
   if '.' in s:md=max(md,len(s.split('.')[1]))
 return 10**(-min(md,6))
def labels_path(b):return ['o','h','l','c'] if abs(b.o-b.h)<abs(b.o-b.l) else ['o','l','h','c']
def val(b,k):return getattr(b,k)
def first_exit_segment(a,z,s,t):
 cand=[]
 if min(a,z)<=s<=max(a,z) and abs(s-a)>1e-12:cand.append((abs(s-a),'SL',s))
 if min(a,z)<=t<=max(a,z) and abs(t-a)>1e-12:cand.append((abs(t-a),'TP',t))
 if not cand:return None,None
 _,r,p=min(cand);return r,p
def existing_exit(d,b,s,t):
 # use side-specific quote bar for a position that existed before bar open
 if d==1:
  if b.o<=s:return 'SL',b.o
  if b.o>=t:return 'TP',b.o
 else:
  if b.o>=s:return 'SL',b.o
  if b.o<=t:return 'TP',b.o
 labs=labels_path(b);cur=val(b,labs[0])
 for k in labs[1:]:
  z=val(b,k);r,p=first_exit_segment(cur,z,s,t)
  if r:return r,p
  cur=z
 return None,None
def fill_and_samebar(d,e,s,t,bid,ask):
 # trigger side path determines chronology; map fractional trigger location to exit-side quote path.
 trig=ask if d==1 else bid; exq=bid if d==1 else ask
 if trig is None or exq is None:return False,None,None,None
 labs=labels_path(trig);tv=[val(trig,k) for k in labs];ev=[val(exq,k) for k in labs]
 gap=(d==1 and tv[0]>=e) or (d==-1 and tv[0]<=e)
 if gap:
  exec_e=tv[0];start_ev=ev[0];start_seg=0
  r,p=first_exit_segment(start_ev,ev[1],s,t)
  if r:return True,exec_e,r,p
  cur=ev[1];j0=2
 else:
  hit=None
  for j in range(1,len(tv)):
   a,z=tv[j-1],tv[j]
   ok=(d==1 and a<e<=z) or (d==-1 and a>e>=z)
   if ok:
    frac=(e-a)/(z-a) if z!=a else 0.0
    start_ev=ev[j-1]+frac*(ev[j]-ev[j-1]);hit=j;break
  if hit is None:return False,None,None,None
  exec_e=e
  r,p=first_exit_segment(start_ev,ev[hit],s,t)
  if r:return True,exec_e,r,p
  cur=ev[hit];j0=hit+1
 for j in range(j0,len(ev)):
  r,p=first_exit_segment(cur,ev[j],s,t)
  if r:return True,exec_e,r,p
  cur=ev[j]
 return True,exec_e,None,None
def commission_rate(sym):
 return 35.0 if sym in PRE['universe']['fx'] else 52.5
def metrics(rows,key='net_R'):
 vals=[r[key] for r in rows];gp=sum(max(x,0) for x in vals);gl=sum(max(-x,0) for x in vals);eq=0;peak=0;dd=0;ls=mxls=0
 for x in sorted(rows,key=lambda r:r['exit_ms']):
  v=x[key];eq+=v;peak=max(peak,eq);dd=max(dd,peak-eq)
  if v<0:ls+=1;mxls=max(mxls,ls)
  else:ls=0
 return {'n':len(vals),'R':sum(vals),'E':sum(vals)/len(vals) if vals else None,'PF':gp/gl if gl else None,'maxDD_R':dd,'max_losing_streak':mxls}
def run(sym):
 raw,bars=load_bid(sym);askmap=load_ask(sym);tick=tick_from_rows(raw);ind,_,_=ref.calc_ind(bars);pending=None;active=None;tr=[];diag={'signals':0,'admitted':0,'filled':0,'expired':0,'missing_ask':0,'tp':0,'sl':0,'ema':0,'session':0}
 def close(i,reason,px):
  nonlocal active
  p=active; b=bars[i];gross=((px-p['exec_e'])*(1 if p['d']==1 else -1))/p['planned_risk'];rate=commission_rate(sym);comm=(abs(p['exec_e'])+abs(px))*rate/1e6/p['planned_risk'];net=gross-comm
  tr.append({'symbol':sym,'asset_class':('fx' if sym in PRE['universe']['fx'] else ('metal' if sym in PRE['universe']['metals'] else 'index')),'signal_ms':p['sig_t'],'signal_iso':datetime.datetime.fromtimestamp(p['sig_t']/1000,tz=UTC).isoformat(),'entry_ms':p['entry_t'],'exit_ms':b.ct,'side':'LONG' if p['d']==1 else 'SHORT','tclass':tclass(p['sig_t']),'plan_entry':p['plan_e'],'exec_entry':p['exec_e'],'stop':p['s'],'target':p['t'],'exit_price':px,'exit_reason':reason,'planned_risk':p['planned_risk'],'spread_execution_R':gross,'commission_R':comm,'net_R':net})
  active=None
 for i,b in enumerate(bars):
  if b.ct<START_MS:continue
  if b.ct>=END_MS:break
  ask=askmap.get(b.ot);closed=False
  if active is not None:
   qb=b if active['d']==1 else ask
   if qb is None:diag['missing_ask']+=1
   else:
    r,px=existing_exit(active['d'],qb,active['s'],active['t'])
    if r:diag['tp' if r=='TP' else 'sl']+=1;close(i,r,px);closed=True
  if active is None and pending is not None and not closed:
   if i==pending['sig_i']+1:
    if ask is None and pending['d']==1:diag['missing_ask']+=1;pending=None
    elif ask is None and pending['d']==-1:diag['missing_ask']+=1;pending=None
    else:
     fill,ee,r,px=fill_and_samebar(pending['d'],pending['plan_e'],pending['s'],pending['t'],b,ask)
     if fill:
      active=pending;pending=None;active['exec_e']=ee;active['entry_t']=b.ot;diag['filled']+=1
      if r:diag['tp' if r=='TP' else 'sl']+=1;close(i,r,px);closed=True
     else:diag['expired']+=1;pending=None
  allowed_session,sexit=ref.session_flags(b.ct,TFMS)
  if active is not None and not closed:
   z=ind[i];le=active['d']==1 and b.c<z['ema'] and not z['ha'] and not z['ema_up'];se=active['d']==-1 and b.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
   if sexit:
    px=b.c if active['d']==1 else (ask.c if ask else b.c);diag['session']+=1;close(i,'SESSION',px);closed=True
   elif le or se:
    px=b.c if active['d']==1 else (ask.c if ask else b.c);diag['ema']+=1;close(i,'EMA',px);closed=True
  if pending is not None and active is None and i>=pending['sig_i']+1:pending=None
  if active is None and pending is None and not closed:
   z=ind[i];lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None;sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
   nl=allowed_session and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res'];ns=allowed_session and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
   if nl or ns:
    diag['signals']+=1;ok,tc=admitted(b.ct)
    if not ok:continue
    diag['admitted']+=1
    if nl:d=1;e=round(b.h/tick)*tick+tick;s=round(b.l/tick)*tick-tick;t=e+TPR*(e-s)
    else:d=-1;e=round(b.l/tick)*tick-tick;s=round(b.h/tick)*tick+tick;t=e-TPR*(s-e)
    risk=abs(e-s)
    if risk>0:pending={'d':d,'plan_e':e,'s':s,'t':t,'sig_i':i,'sig_t':b.ct,'planned_risk':risk}
 return tr,diag,tick

def main():
 syms=PRE['universe']['fx']+PRE['universe']['metals']+PRE['universe']['indices'];alltr=[];by={};errs={}
 for sym in syms:
  try:
   tr,diag,tick=run(sym);alltr+=tr;yr={}
   for y in range(2021,2027):yr[str(y)]=metrics([r for r in tr if datetime.datetime.fromtimestamp(r['signal_ms']/1000,tz=UTC).year==y])
   early=metrics([r for r in tr if datetime.datetime.fromtimestamp(r['signal_ms']/1000,tz=UTC).year<=2023]);late=metrics([r for r in tr if datetime.datetime.fromtimestamp(r['signal_ms']/1000,tz=UTC).year>=2024]);m=metrics(tr);pos=sum(1 for v in yr.values() if v['n'] and v['R']>0)
   by[sym]={**m,'tick':tick,'diag':diag,'years':yr,'early_2021_2023':early,'late_2024_2026':late,'positive_years':pos};print('DONE',sym,m,'early',early['R'],'late',late['R'],flush=True)
  except Exception as e:errs[sym]=repr(e);print('ERR',sym,repr(e),flush=True)
 stable=[s for s,v in by.items() if v['n']>=30 and v['R']>0 and v['early_2021_2023']['R']>0 and v['late_2024_2026']['R']>0 and v['positive_years']>=4]
 rank=sorted(by.items(),key=lambda kv:kv[1]['R'],reverse=True)
 summary={'methodology':PRE,'all':metrics(alltr),'by_asset_class':{},'by_symbol':by,'errors':errs,'stable_gate':stable,'ranking':[{'symbol':s,**{k:v[k] for k in ['n','R','E','PF','maxDD_R','positive_years']},'early_R':v['early_2021_2023']['R'],'late_R':v['late_2024_2026']['R']} for s,v in rank]}
 for ac in ['fx','metal','index']:summary['by_asset_class'][ac]=metrics([r for r in alltr if r['asset_class']==ac])
 json.dump(summary,open(OUT/'wr_m30_crossasset_results_2021_20260814.json','w'),indent=2)
 fields=list(alltr[0].keys()) if alltr else []
 if fields:
  with open(OUT/'wr_m30_crossasset_trades_2021_20260814.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(alltr)
 print('STABLE',stable);print('ALL',summary['all']);print('CLASS',summary['by_asset_class']);print('TOP15');
 for x in summary['ranking'][:15]:print(x)
if __name__=='__main__':main()
