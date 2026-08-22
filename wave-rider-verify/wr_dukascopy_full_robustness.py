#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, statistics, sys, time, types
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
OUT=Path(os.getenv('WR_OUT','/tmp/wr-duka-full')); OUT.mkdir(parents=True,exist_ok=True)
STATE_START=pd.Timestamp('2021-12-01T00:00:00Z')
START=pd.Timestamp('2022-01-01T00:00:00Z')
END=pd.Timestamp('2026-08-21T00:00:00Z')
TF_MIN=int(os.getenv('TF_MIN','5'))
COST_GRID=(0.0,0.5,1.0,1.5,2.0,3.0)

ASSETS={
    'EURUSD': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'GBPUSD': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'USDJPY': {'group':'FX','tick':1e-3,'tz':'America/New_York','session':'1700-1700'},
    'AUDUSD': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'USDCAD': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'USDCHF': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'NZDUSD': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'EURJPY': {'group':'FX','tick':1e-3,'tz':'America/New_York','session':'1700-1700'},
    'GBPJPY': {'group':'FX','tick':1e-3,'tz':'America/New_York','session':'1700-1700'},
    'EURGBP': {'group':'FX','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'XAUUSD': {'group':'METAL','tick':1e-3,'tz':'America/New_York','session':'1700-1700'},
    'XAGUSD': {'group':'METAL','tick':1e-5,'tz':'America/New_York','session':'1700-1700'},
    'US500': {'group':'INDEX','tick':0.01,'tz':'America/Chicago','session':'1700-1559'},
    'NAS100': {'group':'INDEX','tick':0.01,'tz':'America/Chicago','session':'1700-1559'},
    'AAPL': {'group':'STOCK','tick':0.01,'tz':'America/New_York','session':'0930-1600'},
    'MSFT': {'group':'STOCK','tick':0.01,'tz':'America/New_York','session':'0930-1600'},
    'NVDA': {'group':'STOCK','tick':0.01,'tz':'America/New_York','session':'0930-1600'},
    'AMZN': {'group':'STOCK','tick':0.01,'tz':'America/New_York','session':'0930-1600'},
    'META': {'group':'STOCK','tick':0.01,'tz':'America/New_York','session':'0930-1600'},
    'TSLA': {'group':'STOCK','tick':0.01,'tz':'America/New_York','session':'0930-1600'},
}
EXPLICIT={
    'XAUUSD':'INSTRUMENT_FX_METALS_XAU_USD',
    'XAGUSD':'INSTRUMENT_FX_METALS_XAG_USD',
    'US500':'INSTRUMENT_IDX_AMERICA_E_SANDP_500',
    'NAS100':'INSTRUMENT_IDX_AMERICA_E_NQ_100',
}


def load_modules():
    import importlib.util
    bs=importlib.util.spec_from_file_location('wr_tv_base_full',HERE/'wr_tv_parity.py')
    base=importlib.util.module_from_spec(bs);sys.modules[bs.name]=base;bs.loader.exec_module(base)
    path='/tmp/reference_verify.py'; src=Path(path).read_text()
    ref=types.ModuleType('wrref_duka_full'); ref.__file__=path; sys.modules[ref.__name__]=ref; exec(compile(src,path,'exec'),ref.__dict__)
    def pine_rightmost_pivots(v,left,right,high=True):
        out=[None]*len(v); ties=0
        for conf in range(left+right,len(v)):
            c=conf-right; x=v[c]; L=v[c-left:c]; R=v[c+1:c+right+1]
            if high: ok=all(x>=z for z in L) and all(x>z for z in R)
            else: ok=all(x<=z for z in L) and all(x<z for z in R)
            if ok: out[conf]=x
            elif x==(max(v[c-left:c+right+1]) if high else min(v[c-left:c+right+1])): ties+=1
        return [None]+out[:-1],ties
    ref.pivots=pine_rightmost_pivots
    base.START=START.to_pydatetime(); base.END=END.to_pydatetime(); base.TF=str(TF_MIN); base.TF_MS=TF_MIN*60000
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
    stock=None
    for name,value in vars(dq).items():
        if not name.startswith('INSTRUMENT_') or not isinstance(value,str):continue
        norm=value.replace('/','').replace('.','').upper()
        if value.replace('/','').upper()==sym:return value
        if value.upper()==sym+'.US/USD':stock=value
        if ASSETS[sym]['group']=='STOCK' and norm.startswith(sym+'US') and norm.endswith('USD'):stock=value
    if stock:return stock
    if len(sym)==6:return sym[:3]+'/'+sym[3:]
    raise RuntimeError('cannot resolve '+sym)


def month_chunks(start,end):
    cur=pd.Timestamp(year=start.year,month=start.month,day=1,tz='UTC')
    while cur<end:
        nxt=cur+pd.DateOffset(months=1); yield max(cur,start),min(nxt,end); cur=nxt


def normalize_df(df):
    if df is None or not len(df):return pd.DataFrame(columns=['open','high','low','close'])
    if 'timestamp' in df.columns:df=df.set_index('timestamp')
    df=df.copy();df.index=pd.to_datetime(df.index,utc=True)
    cols={str(c).lower():c for c in df.columns};need=['open','high','low','close']
    if any(k not in cols for k in need):raise RuntimeError('OHLC missing '+str(list(df.columns)))
    out=pd.DataFrame({k:pd.to_numeric(df[cols[k]],errors='coerce') for k in need},index=df.index).dropna()
    return out[~out.index.duplicated(keep='last')].sort_index()


def fetch_side(instrument,side,a,b):
    import dukascopy_python as d
    interval=pick_const(('INTERVAL_MIN_5','INTERVAL_MINUTE_5','INTERVAL_M5'));last=None
    for attempt in range(4):
        try:return normalize_df(d.fetch(instrument,interval,side,a.to_pydatetime(),b.to_pydatetime()))
        except Exception as e:last=e;time.sleep(0.8*(attempt+1))
    raise RuntimeError(repr(last))


def load_mid(symbol):
    instrument=resolve_symbol(symbol);bid=pick_const(('OFFER_SIDE_BID','PRICE_TYPE_BID','BID'));ask=pick_const(('OFFER_SIDE_ASK','PRICE_TYPE_ASK','ASK'))
    frames=[];manifest=[]
    for a,b in month_chunks(STATE_START,END):
        label=a.strftime('%Y-%m');db=fetch_side(instrument,bid,a,b);da=fetch_side(instrument,ask,a,b);idx=db.index.intersection(da.index)
        if len(idx):frames.append((db.loc[idx,['open','high','low','close']]+da.loc[idx,['open','high','low','close']])/2.0)
        manifest.append({'month':label,'bid_rows':int(len(db)),'ask_rows':int(len(da)),'mid_rows':int(len(idx))})
        print(symbol,label,len(db),len(da),len(idx),flush=True)
    if not frames:raise RuntimeError(symbol+': no midpoint data')
    df=pd.concat(frames).sort_index();df=df[~df.index.duplicated(keep='last')];df=df[(df.index>=STATE_START)&(df.index<END)]
    return df,manifest,instrument


def aggregate_10m(df):
    buckets={};rejected=0
    for ts,r in df.iterrows():
        ms=int(ts.timestamp()*1000);ot=(ms//600000)*600000;buckets.setdefault(ot,[]).append((ms,r))
    rows=[];idx=[]
    for ot,xs in sorted(buckets.items()):
        xs=sorted(xs,key=lambda z:z[0])
        if len(xs)!=2 or xs[0][0]!=ot or xs[1][0]!=ot+300000:rejected+=1;continue
        idx.append(pd.Timestamp(ot,unit='ms',tz='UTC'))
        rows.append({'open':float(xs[0][1].open),'high':max(float(z[1].high) for z in xs),'low':min(float(z[1].low) for z in xs),'close':float(xs[-1][1].close)})
    return pd.DataFrame(rows,index=idx),rejected


def to_bars(df,Bar):
    out=[];span=TF_MIN*60000
    for ts,r in df.iterrows():
        ot=int(ts.timestamp()*1000);out.append(Bar(ot,ot+span,float(r.open),float(r.high),float(r.low),float(r.close)))
    return out


def provider_info(symbol):
    cfg=ASSETS[symbol];tick=cfg['tick']
    return {'timezone':cfg['tz'],'exchange_timezone':cfg['tz'],'session':cfg['session'],'subsessions':[{'id':'regular','session':cfg['session']}],'minmov':1,'pricescale':int(round(1/tick)),'_tick':tick}


def trade_cost_r(t,bps):
    dist=abs(float(t['e'])-float(t['s']))
    return 0.0 if dist<=0 else (float(t['e'])/dist)*(bps/10000.0)


def metrics(trades,bps):
    vals=[float(t['R'])-trade_cost_r(t,bps) for t in trades];n=len(vals)
    if not n:return {'n':0,'net_R':0.0,'avg_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0}
    gp=sum(max(x,0) for x in vals);gl=sum(max(-x,0) for x in vals);eq=peak=mdd=0.0
    for x in vals:eq+=x;peak=max(peak,eq);mdd=min(mdd,eq-peak)
    return {'n':n,'net_R':sum(vals),'avg_R':statistics.mean(vals),'PF':(gp/gl if gl else None),'win_rate':100*sum(x>0 for x in vals)/n,'max_DD_R':mdd}


def by_year(trades,bps):
    out={}
    for y in (2022,2023,2024,2025,2026):
        yy=[t for t in trades if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y];out[str(y)]=metrics(yy,bps)
    return out


def run_symbol(symbol):
    if symbol not in ASSETS:raise RuntimeError('unknown symbol '+symbol)
    base,ref=load_modules();df,manifest,instrument=load_mid(symbol);reject10=0
    if TF_MIN==10:df,reject10=aggregate_10m(df)
    elif TF_MIN!=5:raise RuntimeError('TF must be 5 or 10')
    bars=to_bars(df,base.Bar);base.tv_tick=lambda _info,_vals:ASSETS[symbol]['tick']
    trades,raw=base.run_case(ref,bars,provider_info(symbol),STATE_START.to_pydatetime(),anchor='start',use_session=True)
    summary={'symbol':symbol,'group':ASSETS[symbol]['group'],'source':'Dukascopy BID+ASK midpoint built from M5','instrument':instrument,'tf':f'{TF_MIN}m','state_start_utc':STATE_START.isoformat(),'start_utc':START.isoformat(),'end_utc_exclusive':END.isoformat(),'bars':len(bars),'rejected_10m_buckets':reject10,'target_session_tz':ASSETS[symbol]['tz'],'target_session':ASSETS[symbol]['session'],'tick':ASSETS[symbol]['tick'],'raw':raw,'gross':metrics(trades,0.0),'cost_grid':{str(b):metrics(trades,b) for b in COST_GRID},'years_gross':by_year(trades,0.0),'years_1bps':by_year(trades,1.0),'years_2bps':by_year(trades,2.0),'manifest':manifest}
    (OUT/f'summary-{symbol}-{TF_MIN}m.json').write_text(json.dumps(summary,indent=2,default=str))
    with (OUT/f'trades-{symbol}-{TF_MIN}m.jsonl').open('w') as f:
        for t in trades:f.write(json.dumps({'symbol':symbol,'group':ASSETS[symbol]['group'],'tf':TF_MIN,**t})+'\n')
    print('RESULT',symbol,TF_MIN,json.dumps({'group':summary['group'],'n':summary['gross']['n'],'gross_R':summary['gross']['net_R'],'avg_R':summary['gross']['avg_R'],'PF':summary['gross']['PF'],'net_1bps':summary['cost_grid']['1.0']['net_R'],'net_2bps':summary['cost_grid']['2.0']['net_R'],'years_1bps':summary['years_1bps']},default=str),flush=True)


def merge(root,final):
    root=Path(root);final=Path(final);final.mkdir(parents=True,exist_ok=True);rows=[]
    for p in root.rglob('summary-*.json'):
        try:rows.append(json.loads(p.read_text()))
        except Exception:pass
    rows.sort(key=lambda r:(r['group'],r['symbol'],r['tf']))
    compact=[]
    for r in rows:
        compact.append({'symbol':r['symbol'],'group':r['group'],'tf':r['tf'],'n':r['gross']['n'],'gross_R':r['gross']['net_R'],'gross_avg_R':r['gross']['avg_R'],'gross_PF':r['gross']['PF'],'net_1bps_R':r['cost_grid']['1.0']['net_R'],'net_2bps_R':r['cost_grid']['2.0']['net_R'],'years_1bps':{y:r['years_1bps'][y]['net_R'] for y in ('2022','2023','2024','2025','2026')}})
    report={'strategy':'WR 2.5.13 exact rules + Pine rightmost-tie pivots','purpose':'full independent cross-asset robustness matrix; no interim stopping and NOT TradingView trade parity','dataset':'Dukascopy BID+ASK midpoint; 10m strictly aggregated from complete M5 pairs','window':'2022-01-01 to 2026-08-21 UTC exclusive','results':compact,'count':len(compact)}
    (final/'full-crossasset-robustness.json').write_text(json.dumps(report,indent=2));(final/'full-crossasset-all-summaries.json').write_text(json.dumps(rows,indent=2))
    print('FINAL_COUNT',len(compact),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['symbol','merge']);ap.add_argument('--symbol');ap.add_argument('--root',default='/tmp/all');ap.add_argument('--final',default='/tmp/final');a=ap.parse_args()
    if a.mode=='symbol':run_symbol(a.symbol or os.environ['SYMBOL'])
    else:merge(a.root,a.final)

if __name__=='__main__':main()
