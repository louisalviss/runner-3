#!/usr/bin/env python3
from __future__ import annotations
import bisect, csv, io, json, os, sys, time, zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from close_confirm import run_case, assert_canonical_parity

BASE_DIR=Path(os.getenv('WR_BASE_DIR','/tmp/wrbase'))
sys.path.insert(0,str(BASE_DIR))
import wr_tv_parity as base
base.TF='5'; base.TF_MS=300000
ref=base.load_ref()

OUT=Path(os.getenv('WR_OUT','/tmp/wr-crypto-stage1-close')); OUT.mkdir(parents=True,exist_ok=True)
SHARD=int(os.getenv('SHARD','0')); SHARDS=int(os.getenv('SHARDS','32'))
REPORT_START=datetime(2025,1,1,tzinfo=timezone.utc)
REPORT_END=datetime(2026,8,15,tzinfo=timezone.utc)
HISTORY_START=datetime(2024,12,1,tzinfo=timezone.utc)
LOAD_END=datetime(2026,8,19,tzinfo=timezone.utc)
BINANCE_S3='https://data.binance.vision'; LIST_ENDPOINT='https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'; PREFIX='data/futures/um/monthly/klines/'
VN=ZoneInfo('Asia/Ho_Chi_Minh'); NY=ZoneInfo('America/New_York')
COSTS=(4.0,6.0,8.0)

@dataclass
class K:
    ot:int; ct:int; o:float; h:float; l:float; c:float; v:float; qv:float


def sess():
    s=requests.Session(); s.headers['User-Agent']='runner3-wr-stage1-close-ab/1.0'; return s

def list_symbols(http):
    params={'list-type':'2','delimiter':'/','prefix':PREFIX,'max-keys':'1000'}; out=[]; ns={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}
    import xml.etree.ElementTree as ET
    while True:
        r=http.get(LIST_ENDPOINT,params=params,timeout=60); r.raise_for_status(); root=ET.fromstring(r.content)
        for p in root.findall('s:CommonPrefixes/s:Prefix',ns):
            x=p.text or ''
            if x.startswith(PREFIX):
                sym=x[len(PREFIX):].strip('/')
                if sym.endswith('USDT') and '_' not in sym: out.append(sym)
        trunc=root.findtext('s:IsTruncated',default='false',namespaces=ns)=='true'; token=root.findtext('s:NextContinuationToken',default='',namespaces=ns)
        if not trunc or not token: break
        params['continuation-token']=token
    return sorted(set(out))

def current_tradifi(http):
    urls=['https://www.binance.com/fapi/v1/exchangeInfo','https://fapi.binance.com/fapi/v1/exchangeInfo']
    for u in urls:
        try:
            r=http.get(u,timeout=30)
            if r.ok:
                x=r.json(); return {s.get('symbol') for s in x.get('symbols',[]) if s.get('contractType')=='TRADIFI_PERPETUAL'}
        except Exception: pass
    return set()

def get_zip(http,url):
    for k in range(3):
        try:
            r=http.get(url,timeout=45)
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if k==2: raise
            time.sleep(.4*(k+1))

def read_zip(data):
    out=[]
    if not data:return out
    with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit(): continue
        out.append(K(int(row[0]),int(row[6]),float(row[1]),float(row[2]),float(row[3]),float(row[4]),float(row[5]),float(row[7])))
    return out

def months():
    d=date(2024,12,1); end=date(2026,8,1)
    while d<=end:
        yield d.year,d.month
        d=(d.replace(day=28)+timedelta(days=4)).replace(day=1)

def load_symbol(http,sym):
    bars=[]
    for y,m in months():
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip'; url=f'{BINANCE_S3}/data/futures/um/monthly/klines/{sym}/5m/{fn}'
        try: bars.extend(read_zip(get_zip(http,url)))
        except Exception as e: print('MONTH_ERR',sym,y,m,repr(e),flush=True)
    for d in range(1,19):
        fn=f'{sym}-5m-2026-08-{d:02d}.zip'; url=f'{BINANCE_S3}/data/futures/um/daily/klines/{sym}/5m/{fn}'
        try: bars.extend(read_zip(get_zip(http,url)))
        except Exception as e: print('DAY_ERR',sym,d,repr(e),flush=True)
    lo=int(HISTORY_START.timestamp()*1000); hi=int(LOAD_END.timestamp()*1000)
    ded={b.ot:b for b in bars if lo<=b.ot<hi}; return [ded[k] for k in sorted(ded)]

def checkpoint_times():
    out=[]; d=date(2025,1,1); last=date(2026,8,14)
    while d<=last:
        for label,hh,mm,tz in [('refresh',15,30,VN),('main',10,0,NY),('final',12,45,NY),('preclose',15,45,NY)]:
            dt=datetime(d.year,d.month,d.day,hh,mm,tzinfo=tz).astimezone(timezone.utc)
            if REPORT_START<=dt<REPORT_END: out.append((d.isoformat(),label,int(dt.timestamp()*1000)))
        d+=timedelta(days=1)
    return sorted(out,key=lambda x:x[2])
CHECKPOINTS=checkpoint_times()

def daily_agg(bars):
    by=defaultdict(list)
    for b in bars: by[datetime.fromtimestamp(b.ot/1000,tz=timezone.utc).date()].append(b)
    out={}
    for d,x in by.items():
        x=sorted(x,key=lambda b:b.ot)
        if len(x)<280: continue
        out[d]={'open':x[0].o,'high':max(z.h for z in x),'low':min(z.l for z in x),'close':x[-1].c,'base_volume':sum(z.v for z in x),'usd_volume_proxy':x[-1].c*sum(z.v for z in x)}
    return out

def reconstruct_stage1(bars,is_tradifi=False):
    if not bars:return {},[]
    cts=[b.ct for b in bars]; qv_prefix=[0.0]
    for b in bars:qv_prefix.append(qv_prefix[-1]+b.qv)
    da=daily_agg(bars); days=sorted(da)
    firstq={}; rows=[]
    for session_date,label,ms in CHECKPOINTS:
        j=bisect.bisect_right(cts,ms)-1
        if j<0: continue
        lo=bisect.bisect_left(cts,ms-24*3600*1000)
        qv24=qv_prefix[j+1]-qv_prefix[lo]
        cur=bars[j].c; utc_day=datetime.fromtimestamp(ms/1000,tz=timezone.utc).date()
        prior=[d for d in days if d<utc_day]
        if len(prior)<14: continue
        last14=prior[-14:]; last10=prior[-10:]; last7=prior[-7:]
        avg10=sum(da[d]['usd_volume_proxy'] for d in last10)/10.0
        vol7=sum((da[d]['high']-da[d]['low'])/abs(da[d]['low']) for d in last7 if da[d]['low']!=0)/7.0
        adr14=(sum(da[d]['high'] for d in last14)/14.0-sum(da[d]['low'] for d in last14)/14.0)/cur if cur else 0.0
        data_alive=(ms-bars[j].ct)<=10*60*1000
        qualified=bool(data_alive and not is_tradifi and qv24>=100_000_000 and avg10>200_000_000 and vol7>0.06 and adr14>=0.05)
        rows.append({'session_date':session_date,'checkpoint':label,'ts':ms,'qv24':qv24,'avg_usd_volume_10d':avg10,'volatility_7d':vol7,'adr14':adr14,'current_close':cur,'data_alive':data_alive,'current_tradifi':is_tradifi,'qualified':qualified})
        if qualified and session_date not in firstq: firstq[session_date]=ms
    return firstq,rows

def eligible_fn(firstq):
    def f(ms):
        dt=datetime.fromtimestamp(ms/1000,tz=timezone.utc).astimezone(VN)-timedelta(hours=6)
        sd=dt.date().isoformat(); q=firstq.get(sd)
        return q is not None and ms>=q
    return f

def info(tick): return {'timezone':'Etc/UTC','exchange_timezone':'Etc/UTC','session':'0000-0000:1234567','subsessions':[{'id':'regular','session':'0000-0000:1234567'}],'_tick':tick}
def cost_r(t,bps):
    d=abs(float(t['e'])-float(t['s'])); return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)
def metrics(trades,bps):
    vals=[float(t['R'])-cost_r(t,bps) for t in trades]; n=len(vals); gp=sum(max(x,0) for x in vals); gl=sum(max(-x,0) for x in vals); eq=peak=0.;mdd=0.
    for x in vals:eq+=x;peak=max(peak,eq);mdd=min(mdd,eq-peak)
    return {'n':n,'R':sum(vals),'avg_R':sum(vals)/n if n else None,'PF':gp/gl if gl else None,'max_DD_R':mdd}
def summarize(trades):
    return {'gross':metrics(trades,0),**{f'net_{int(b)}bps':metrics(trades,b) for b in COSTS},'long_6bps':metrics([t for t in trades if t['side']=='L'],6),'short_6bps':metrics([t for t in trades if t['side']=='S'],6),
            'by_year':{str(y):metrics([t for t in trades if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y],6) for y in (2025,2026)}}
def infer_tick(bars):
    vals=[]
    for b in bars[:3000]: vals += [b.o,b.h,b.l,b.c]
    return float(ref.infer_tick(vals)) if vals else None

def one_symbol(sym,bars,is_tradifi,verify_parity=False):
    firstq,cp=reconstruct_stage1(bars,is_tradifi)
    if not firstq:
        return {'symbol':sym,'status':'NO_STAGE1','qualified_sessions':0,'checkpoints':cp},[]
    tick=infer_tick(bars)
    if not tick:return {'symbol':sym,'status':'NO_TICK'},[]
    wrbars=[base.Bar(b.ot,b.ct,b.o,b.h,b.l,b.c) for b in bars]; inf=info(tick); elig=eligible_fn(firstq)
    if verify_parity:
        n=assert_canonical_parity(base,ref,wrbars,inf,HISTORY_START,REPORT_START,REPORT_END,anchor='start',use_session=True)
    else:n=None
    a,ar=run_case(base,ref,wrbars,inf,HISTORY_START,REPORT_START,REPORT_END,variant='canonical',anchor='start',use_session=True,eligible_signal=elig)
    b,br=run_case(base,ref,wrbars,inf,HISTORY_START,REPORT_START,REPORT_END,variant='close_confirmed',anchor='start',use_session=True,eligible_signal=elig)
    payload={'symbol':sym,'status':'OK','tick':tick,'qualified_sessions':len(firstq),'first_qualified_by_session':firstq,'stage1_reconstruction':{'method':'point-in-time causal reconstruction from Binance 5m archive; 24h quote volume exact from 5m qv; 10D/7D/ADR14 use prior completed UTC daily aggregates; current TRADIFI contracts excluded','thresholds':{'qv24_gte':100_000_000,'avg_usd_volume_10d_gt':200_000_000,'volatility_7d_gt':0.06,'adr14_gte':0.05}},'parity_all_eligible_n':n,'baseline':summarize(a),'close_confirmed':summarize(b),'baseline_raw':ar,'close_raw':br,'checkpoints':cp}
    trades=[]
    for name,xx in [('baseline',a),('close_confirmed',b)]:
        for t in xx: trades.append({'symbol':sym,'variant':name,'cost6_R':float(t['R'])-cost_r(t,6),**t})
    return payload,trades

def shard():
    http=sess(); syms=list_symbols(http); tradifi=current_tradifi(http); mine=[s for i,s in enumerate(syms) if i%SHARDS==SHARD]
    summaries=[]; alltr=[]; parity_done=False
    for j,sym in enumerate(mine,1):
        print('LOAD',SHARD,j,len(mine),sym,flush=True)
        try:
            bars=load_symbol(http,sym)
            if len(bars)<1000:
                summaries.append({'symbol':sym,'status':'INSUFFICIENT','bars':len(bars)}); continue
            p,tr=one_symbol(sym,bars,sym in tradifi,verify_parity=not parity_done)
            if p.get('status')=='OK' and not parity_done: parity_done=True
            p['bars']=len(bars); summaries.append(p); alltr.extend(tr)
            print('RESULT',sym,p.get('status'),'sessions',p.get('qualified_sessions'), 'base',p.get('baseline',{}).get('net_6bps'), 'close',p.get('close_confirmed',{}).get('net_6bps'),flush=True)
        except Exception as e:
            summaries.append({'symbol':sym,'status':'ERROR','error':repr(e)}); print('ERROR',sym,repr(e),flush=True)
    (OUT/f'summary-{SHARD}.json').write_text(json.dumps({'shard':SHARD,'shards':SHARDS,'symbols_total':len(syms),'assigned':len(mine),'parity_done':parity_done,'results':summaries},indent=2,default=str))
    with (OUT/f'trades-{SHARD}.jsonl').open('w') as f:
        for t in alltr:f.write(json.dumps(t,separators=(',',':'))+'\n')
def aggregate_metric(trades,key='cost6_R'):
    vals=[float(t[key]) for t in trades];n=len(vals);gp=sum(max(x,0) for x in vals);gl=sum(max(-x,0) for x in vals);return {'n':n,'R':sum(vals),'avg_R':sum(vals)/n if n else None,'PF':gp/gl if gl else None}
def episode_metrics(trades):
    by=defaultdict(list); byd=defaultdict(list)
    for t in trades:
        by[int(t['signal'])].append(float(t['cost6_R']))
        d=datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).date().isoformat();byd[d].append(float(t['cost6_R']))
    eps=[sum(v)/len(v) for v in by.values()]; days=[sum(v)/len(v) for v in byd.values()]
    return {'episode_count':len(eps),'episode_normalized_R':sum(eps),'daily_count':len(days),'daily_normalized_R':sum(days),'peak_same_signal':max((len(v) for v in by.values()),default=0)}
def merge():
    root=Path(os.getenv('MERGE_ROOT','/tmp/all')); final=Path(os.getenv('FINAL_OUT','/tmp/final'));final.mkdir(parents=True,exist_ok=True)
    summaries=[];tr=[]
    for p in root.rglob('summary-*.json'):
        x=json.loads(p.read_text());summaries.extend(x.get('results',[]))
    for p in root.rglob('trades-*.jsonl'):
        for ln in p.read_text().splitlines():
            if ln.strip():tr.append(json.loads(ln))
    report={'status':'COMPLETE','research_question':'On causally reconstructed historical Crypto Stage1 membership, does next-bar close confirmation improve WR 5m versus canonical intrabar stop-entry?','symbols_scanned':len(summaries),'symbols_stage1_ok':sum(x.get('status')=='OK' for x in summaries),'symbols_error':sum(x.get('status')=='ERROR' for x in summaries),'variants':{}}
    for v in ('baseline','close_confirmed'):
        xs=[t for t in tr if t['variant']==v];report['variants'][v]={'net_6bps':aggregate_metric(xs),'long_6bps':aggregate_metric([t for t in xs if t['side']=='L']),'short_6bps':aggregate_metric([t for t in xs if t['side']=='S']),'episode':episode_metrics(xs),'by_year':{str(y):aggregate_metric([t for t in xs if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y]) for y in (2025,2026)}}
    a=report['variants']['baseline']['net_6bps'];b=report['variants']['close_confirmed']['net_6bps'];report['delta_close_minus_baseline_6bps']={'R':b['R']-a['R'],'n':b['n']-a['n'],'avg_R':(b['avg_R']-a['avg_R']) if a['avg_R'] is not None and b['avg_R'] is not None else None}
    report['guardrails']=['No EMA/RS threshold tuning in this run','Stage1 thresholds frozen from operating methodology','Close-confirm is the only WR entry-structure change','6bps is a sensitivity model, not true executable replay','Episode-normalized R reported because simultaneous altcoin trades are correlated']
    (final/'report.json').write_text(json.dumps(report,indent=2));(final/'symbol-summaries.json').write_text(json.dumps(summaries,indent=2,default=str))
    with (final/'trades.jsonl').open('w') as f:
        for t in tr:f.write(json.dumps(t,separators=(',',':'))+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'shard'
    shard() if mode=='shard' else merge()
