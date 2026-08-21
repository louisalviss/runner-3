#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, statistics, sys, time, types
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
OUT=Path(os.getenv('WR_OUT','/tmp/wr-duka-expanded')); OUT.mkdir(parents=True,exist_ok=True)
STATE_START=pd.Timestamp('2021-12-01T00:00:00Z')
START=pd.Timestamp('2022-01-01T00:00:00Z')
END=pd.Timestamp('2026-08-21T00:00:00Z')
COST_GRID=(0.0,0.5,1.0,1.5,2.0,3.0)

CORE={
'EURUSD':('FX',1e-5,'America/New_York','1700-1700'),'GBPUSD':('FX',1e-5,'America/New_York','1700-1700'),
'USDJPY':('FX',1e-3,'America/New_York','1700-1700'),'AUDUSD':('FX',1e-5,'America/New_York','1700-1700'),
'USDCAD':('FX',1e-5,'America/New_York','1700-1700'),'USDCHF':('FX',1e-5,'America/New_York','1700-1700'),
'NZDUSD':('FX',1e-5,'America/New_York','1700-1700'),'EURJPY':('FX',1e-3,'America/New_York','1700-1700'),
'GBPJPY':('FX',1e-3,'America/New_York','1700-1700'),'EURGBP':('FX',1e-5,'America/New_York','1700-1700'),
'XAUUSD':('METAL',1e-3,'America/New_York','1700-1700'),'XAGUSD':('METAL',1e-5,'America/New_York','1700-1700'),
'US500':('INDEX',0.01,'America/Chicago','1700-1559'),'NAS100':('INDEX',0.01,'America/Chicago','1700-1559'),
}
EXPLICIT={'XAUUSD':'INSTRUMENT_FX_METALS_XAU_USD','XAGUSD':'INSTRUMENT_FX_METALS_XAG_USD','US500':'INSTRUMENT_IDX_AMERICA_E_SANDP_500','NAS100':'INSTRUMENT_IDX_AMERICA_E_NQ_100'}
ALIASES={'META':['META.US/USD','FB.US/USD'],'GOOGL':['GOOGL.US/USD','GOOG.US/USD']}

# Public US-listed equities prioritized because they are currently represented on Hyperliquid/TradeXYZ
# or are common liquid stock-CFD underlyings. Availability is discovered against Dukascopy at runtime.
STOCKS=[
'AAPL','AMZN','GOOGL','META','MSFT','NVDA','TSLA','NFLX','ORCL','IBM','NOW',
'AMD','AMAT','ARM','ASML','AVGO','CRWV','INTC','LITE','MRVL','MU','QCOM','TSM','WDC','SNDK',
'COIN','MSTR','HOOD','CRCL','PLTR','BX','COST','DKNG','EBAY','GME','BABA','ZM','LLY','HIMS','RIVN','RKLB',
'UBER','DIS','HD','WMT','NVO','JPM','BAC','GS','V','MA','PYPL','SHOP','RBLX','SNAP','XOM','CVX','BA','CAT','PFE','JNJ']


def load_modules(tf):
    import importlib.util
    sp=importlib.util.spec_from_file_location(f'wr_tv_base_exp_{tf}',HERE/'wr_tv_parity.py')
    base=importlib.util.module_from_spec(sp);sys.modules[sp.name]=base;sp.loader.exec_module(base)
    path='/tmp/reference_verify.py';src=Path(path).read_text()
    ref=types.ModuleType(f'wrref_exp_{tf}');ref.__file__=path;sys.modules[ref.__name__]=ref;exec(compile(src,path,'exec'),ref.__dict__)
    def piv(v,left,right,high=True):
        out=[None]*len(v);ties=0
        for conf in range(left+right,len(v)):
            c=conf-right;x=v[c];L=v[c-left:c];R=v[c+1:c+right+1]
            ok=(all(x>=z for z in L) and all(x>z for z in R)) if high else (all(x<=z for z in L) and all(x<z for z in R))
            if ok:out[conf]=x
            elif x==(max(v[c-left:c+right+1]) if high else min(v[c-left:c+right+1])):ties+=1
        return [None]+out[:-1],ties
    ref.pivots=piv
    base.START=START.to_pydatetime();base.END=END.to_pydatetime();base.TF=str(tf);base.TF_MS=tf*60000
    return base,ref


def pick_const(names):
    import dukascopy_python as d
    for k in names:
        v=getattr(d,k,None)
        if v is not None:return v
    raise RuntimeError('missing constant '+str(names))


def resolve_symbol(symbol):
    from dukascopy_python import instruments as dq
    sym=symbol.upper()
    if sym in EXPLICIT:
        v=getattr(dq,EXPLICIT[sym],None)
        if v is not None:return v
    vals=[v for k,v in vars(dq).items() if k.startswith('INSTRUMENT_') and isinstance(v,str)]
    if sym in CORE and len(sym)==6:
        pair=sym[:3]+'/'+sym[3:]
        for v in vals:
            if v.replace('/','').upper()==sym:return v
        return pair
    candidates=ALIASES.get(sym,[f'{sym}.US/USD'])
    for cand in candidates:
        for v in vals:
            if v.upper()==cand.upper():return v
    for v in vals:
        norm=v.replace('/','').replace('.','').replace('-','').upper()
        if norm.startswith(sym+'US') and norm.endswith('USD'):return v
    return None


def month_chunks(start,end):
    cur=pd.Timestamp(year=start.year,month=start.month,day=1,tz='UTC')
    while cur<end:
        nxt=cur+pd.DateOffset(months=1);yield max(cur,start),min(nxt,end);cur=nxt


def normalize_df(df):
    if df is None or not len(df):return pd.DataFrame(columns=['open','high','low','close'])
    if 'timestamp' in df.columns:df=df.set_index('timestamp')
    df=df.copy();df.index=pd.to_datetime(df.index,utc=True)
    cols={str(c).lower():c for c in df.columns};need=['open','high','low','close']
    if any(k not in cols for k in need):raise RuntimeError('OHLC missing '+str(list(df.columns)))
    out=pd.DataFrame({k:pd.to_numeric(df[cols[k]],errors='coerce') for k in need},index=df.index).dropna()
    return out[~out.index.duplicated(keep='last')].sort_index()


def fetch_side(instrument,side,a,b,base_min):
    import dukascopy_python as d
    interval=pick_const(('INTERVAL_MIN_1','INTERVAL_MINUTE_1','INTERVAL_M1')) if base_min==1 else pick_const(('INTERVAL_MIN_5','INTERVAL_MINUTE_5','INTERVAL_M5'))
    last=None
    for attempt in range(4):
        try:return normalize_df(d.fetch(instrument,interval,side,a.to_pydatetime(),b.to_pydatetime()))
        except Exception as e:last=e;time.sleep(0.8*(attempt+1))
    raise RuntimeError(repr(last))


def load_mid(symbol,base_min):
    instrument=resolve_symbol(symbol)
    if not instrument:return None,[],None
    bid=pick_const(('OFFER_SIDE_BID','PRICE_TYPE_BID','BID'));ask=pick_const(('OFFER_SIDE_ASK','PRICE_TYPE_ASK','ASK'))
    frames=[];manifest=[]
    for a,b in month_chunks(STATE_START,END):
        try:
            db=fetch_side(instrument,bid,a,b,base_min);da=fetch_side(instrument,ask,a,b,base_min);idx=db.index.intersection(da.index)
        except Exception as e:
            manifest.append({'month':a.strftime('%Y-%m'),'error':repr(e)});continue
        if len(idx):frames.append((db.loc[idx,['open','high','low','close']]+da.loc[idx,['open','high','low','close']])/2.0)
        manifest.append({'month':a.strftime('%Y-%m'),'bid_rows':int(len(db)),'ask_rows':int(len(da)),'mid_rows':int(len(idx))})
    if not frames:return None,manifest,instrument
    df=pd.concat(frames).sort_index();df=df[~df.index.duplicated(keep='last')];df=df[(df.index>=STATE_START)&(df.index<END)]
    return df,manifest,instrument


def aggregate(df,base_min,target_min):
    if target_min==base_min:return df.copy(),0
    step=target_min*60000;base=base_min*60000;need=target_min//base_min
    buckets={}
    for ts,r in df.iterrows():
        ms=int(ts.timestamp()*1000);ot=(ms//step)*step;buckets.setdefault(ot,[]).append((ms,r))
    rows=[];idx=[];reject=0
    for ot,xs in sorted(buckets.items()):
        xs=sorted(xs,key=lambda z:z[0])
        if len(xs)!=need or any(xs[i][0]!=ot+i*base for i in range(need)):
            reject+=1;continue
        idx.append(pd.Timestamp(ot,unit='ms',tz='UTC'));rows.append({'open':float(xs[0][1].open),'high':max(float(z[1].high) for z in xs),'low':min(float(z[1].low) for z in xs),'close':float(xs[-1][1].close)})
    return pd.DataFrame(rows,index=idx),reject


def cfg(symbol):
    if symbol in CORE:
        group,tick,tz,session=CORE[symbol];return group,tick,tz,session
    return 'STOCK',0.01,'America/New_York','0930-1600'


def provider_info(symbol):
    group,tick,tz,session=cfg(symbol)
    return {'timezone':tz,'exchange_timezone':tz,'session':session,'subsessions':[{'id':'regular','session':session}],'minmov':1,'pricescale':int(round(1/tick)),'_tick':tick}


def to_bars(df,Bar,tf):
    span=tf*60000;out=[]
    for ts,r in df.iterrows():
        ot=int(ts.timestamp()*1000);out.append(Bar(ot,ot+span,float(r.open),float(r.high),float(r.low),float(r.close)))
    return out


def cost_r(t,bps):
    dist=abs(float(t['e'])-float(t['s']))
    return 0.0 if dist<=0 else (float(t['e'])/dist)*(bps/10000.0)


def metrics(trades,bps):
    vals=[float(t['R'])-cost_r(t,bps) for t in trades];n=len(vals)
    if not n:return {'n':0,'net_R':0.0,'avg_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0}
    gp=sum(max(x,0) for x in vals);gl=sum(max(-x,0) for x in vals);eq=peak=mdd=0.0
    for x in vals:eq+=x;peak=max(peak,eq);mdd=min(mdd,eq-peak)
    return {'n':n,'net_R':sum(vals),'avg_R':statistics.mean(vals),'PF':gp/gl if gl else None,'win_rate':100*sum(x>0 for x in vals)/n,'max_DD_R':mdd}


def by_year(trades,bps):
    out={}
    for y in (2022,2023,2024,2025,2026):
        yy=[t for t in trades if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y];out[str(y)]=metrics(yy,bps)
    return out


def save_unavailable(symbol,tf,reason,instrument=None,manifest=None):
    group,_,_,_=cfg(symbol);o={'symbol':symbol,'group':group,'tf':f'{tf}m','status':'UNAVAILABLE','reason':reason,'instrument':instrument,'manifest':manifest or []}
    (OUT/f'summary-{symbol}-{tf}m.json').write_text(json.dumps(o,indent=2));print('UNAVAILABLE',symbol,tf,reason,flush=True)


def run_one(symbol,tf,raw_df,base_min,instrument,manifest):
    if raw_df is None or raw_df.empty:return save_unavailable(symbol,tf,'no historical midpoint data',instrument,manifest)
    df,reject=aggregate(raw_df,base_min,tf)
    if df.empty:return save_unavailable(symbol,tf,'no complete bars after aggregation',instrument,manifest)
    base,ref=load_modules(tf);group,tick,tz,session=cfg(symbol);base.tv_tick=lambda _i,_v:tick
    bars=to_bars(df,base.Bar,tf);trades,raw=base.run_case(ref,bars,provider_info(symbol),STATE_START.to_pydatetime(),anchor='start',use_session=True)
    coverage_start=df.index.min().isoformat();coverage_end=df.index.max().isoformat();years=max(0.0,(df.index.max()-df.index.min()).total_seconds()/(365.25*86400))
    status='OK' if years>=3.0 else 'SHORT_HISTORY'
    summary={'symbol':symbol,'group':group,'tf':f'{tf}m','status':status,'source':f'Dukascopy BID+ASK midpoint from M{base_min}','instrument':instrument,'coverage_start':coverage_start,'coverage_end':coverage_end,'coverage_years':years,'bars':len(bars),'rejected_buckets':reject,'target_session_tz':tz,'target_session':session,'tick':tick,'raw':raw,'gross':metrics(trades,0.0),'cost_grid':{str(b):metrics(trades,b) for b in COST_GRID},'years_gross':by_year(trades,0.0),'years_1bps':by_year(trades,1.0),'years_2bps':by_year(trades,2.0),'manifest':manifest}
    (OUT/f'summary-{symbol}-{tf}m.json').write_text(json.dumps(summary,indent=2,default=str))
    with (OUT/f'trades-{symbol}-{tf}m.jsonl').open('w') as f:
        for t in trades:f.write(json.dumps({'symbol':symbol,'group':group,'tf':tf,**t})+'\n')
    print('RESULT',symbol,tf,status,json.dumps({'n':summary['gross']['n'],'gross_R':summary['gross']['net_R'],'avg_R':summary['gross']['avg_R'],'PF':summary['gross']['PF'],'net_1bps':summary['cost_grid']['1.0']['net_R'],'coverage_years':years}),flush=True)


def run_core3(symbol):
    df,manifest,instrument=load_mid(symbol,1)
    if instrument is None:return save_unavailable(symbol,3,'instrument not found')
    run_one(symbol,3,df,1,instrument,manifest)


def run_stockbundle(symbol):
    if symbol not in STOCKS:raise RuntimeError('unknown stock '+symbol)
    instrument=resolve_symbol(symbol)
    if not instrument:
        for tf in (3,5,10):save_unavailable(symbol,tf,'instrument not found')
        return
    df1,m1,_=load_mid(symbol,1);df5,m5,_=load_mid(symbol,5)
    run_one(symbol,3,df1,1,instrument,m1);run_one(symbol,5,df5,5,instrument,m5);run_one(symbol,10,df5,5,instrument,m5)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['core3','stockbundle']);ap.add_argument('--symbol');a=ap.parse_args();sym=a.symbol or os.environ['SYMBOL']
    run_core3(sym) if a.mode=='core3' else run_stockbundle(sym)

if __name__=='__main__':main()
