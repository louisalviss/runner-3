#!/usr/bin/env python3
import json,gzip,datetime,importlib.util,sys,math
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path('/opt/runner3-wr-tickfix-20260921')
OUT=ROOT/'research/wr_finalized_fidelity_audit_20260921'
PRE=json.load(open(OUT/'wr_m30_crossasset_preregister_20260922.json'))
CACHE=Path('/opt/wr-crossasset-cache/bid')
UTC=datetime.timezone.utc; VN=ZoneInfo('Asia/Ho_Chi_Minh'); TFMS=30*60*1000
START_MS=int(datetime.datetime(2021,1,1,tzinfo=UTC).timestamp()*1000); END_MS=int(datetime.datetime(2026,8,15,tzinfo=UTC).timestamp()*1000)
# verifier
rp=ROOT/'.wave-rider-recheck-dropbox/code/reference_verify.py'
spec=importlib.util.spec_from_file_location('wrref_cross',rp); ref=importlib.util.module_from_spec(spec);sys.modules['wrref_cross']=ref;spec.loader.exec_module(ref);Bar=ref.Bar
# unified T0 calendar: 2021 official artifact + 2022-24 frozen lists + 2025-26 pre-existing WR calendar
T0=set()
old=json.load(open(OUT/'wr_m30_backtest_2021_2022.json'))
for e in old.get('events',[]):
 d=datetime.date.fromisoformat(e['date'])
 if d.year==2021:T0.add(d)
def add(s):
 for x in s.split():T0.add(datetime.date.fromisoformat(x))
add('''2022-01-07 2022-01-12 2022-01-27 2022-02-04 2022-02-10 2022-03-04 2022-03-10 2022-03-17 2022-04-01 2022-04-12 2022-05-05 2022-05-06 2022-05-11 2022-06-03 2022-06-10 2022-06-16 2022-07-08 2022-07-13 2022-07-28 2022-08-05 2022-08-10 2022-09-02 2022-09-13 2022-09-22 2022-10-07 2022-10-13 2022-11-03 2022-11-04 2022-11-10 2022-12-02 2022-12-13 2022-12-15''')
add('''2023-01-06 2023-01-12 2023-02-02 2023-02-03 2023-02-14 2023-03-10 2023-03-14 2023-03-23 2023-04-07 2023-04-12 2023-05-04 2023-05-05 2023-05-10 2023-06-02 2023-06-13 2023-06-15 2023-07-07 2023-07-12 2023-07-27 2023-08-04 2023-08-10 2023-09-01 2023-09-13 2023-09-21 2023-10-06 2023-10-12 2023-11-02 2023-11-03 2023-11-14 2023-12-08 2023-12-12 2023-12-14''')
add('''2024-01-05 2024-01-11 2024-02-01 2024-02-02 2024-02-13 2024-03-08 2024-03-12 2024-03-21 2024-04-05 2024-04-10 2024-05-02 2024-05-03 2024-05-15 2024-06-07 2024-06-12 2024-06-13 2024-07-05 2024-07-11 2024-08-01 2024-08-02 2024-08-14 2024-09-06 2024-09-11 2024-09-19 2024-10-04 2024-10-10 2024-11-01 2024-11-08 2024-11-13 2024-12-06 2024-12-11 2024-12-19''')
oldcal=json.load(open(ROOT/'research/wr_tvol_audit_20260921/volume_candidates.json'))
for e in oldcal['T0_dates']:
 d=datetime.date.fromisoformat(e['date'])
 if datetime.date(2025,1,1)<=d<=datetime.date(2026,8,14):T0.add(d)
labels={}
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
def load(sym):
 f=CACHE/(sym+'.json.gz')
 rows=json.loads(gzip.decompress(f.read_bytes()))
 bars=[]
 for r in rows:
  ot=int(r[0]);
  # dukascopy row timestamp = bar open; close time = +30m-1ms
  bars.append(Bar(ot,ot+TFMS-1,float(r[1]),float(r[2]),float(r[3]),float(r[4])))
 return bars
def next_month(y,m):return (y+1,1) if m==12 else (y,m+1)
def main():
 symbols=PRE['universe']['fx']+PRE['universe']['metals']+PRE['universe']['indices']
 out={};needed={}
 for sym in symbols:
  f=CACHE/(sym+'.json.gz')
  if not f.exists():continue
  bars=load(sym);ind,_,_=ref.calc_ind(bars);sigs=[];months=set()
  for i,b in enumerate(bars):
   if not (START_MS<=b.ct<END_MS):continue
   z=ind[i];allowed_session,_=ref.session_flags(b.ct,TFMS)
   lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
   sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
   nl=allowed_session and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']
   ns=allowed_session and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
   if not(nl or ns):continue
   ok,tc=admitted(b.ct)
   if not ok:continue
   dt=datetime.datetime.fromtimestamp(b.ot/1000,tz=UTC);m=(dt.year,dt.month);months.add(m);months.add(next_month(*m))
   sigs.append({'i':i,'ot':b.ot,'ct':b.ct,'iso':dt.isoformat(),'side':'LONG' if nl else 'SHORT','tclass':tc})
  out[sym]={'bars':len(bars),'admitted_signal_count':len(sigs),'signals':sigs}
  needed[sym]=sorted(f'{y:04d}-{m:02d}' for y,m in months if 2021<=y<=2026)
  print(sym,'bars',len(bars),'admitted',len(sigs),'ask_months',len(needed[sym]),flush=True)
 json.dump({'symbols':out,'ask_months':needed,'calendar_T0':[str(x) for x in sorted(T0)]},open(OUT/'wr_m30_crossasset_stage1_signals_20260922.json','w'),indent=2)
 print('TOTAL_SIG',sum(v['admitted_signal_count'] for v in out.values()),'SYMS',len(out))
if __name__=='__main__':main()
