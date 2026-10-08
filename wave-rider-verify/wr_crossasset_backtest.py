import argparse
import json
import math
import statistics
import sys
import time
import types
from pathlib import Path
import pandas as pd

START=pd.Timestamp('2022-01-01T00:00:00Z')
STATE_START=pd.Timestamp('2021-12-01T00:00:00Z')
END=pd.Timestamp('2026-08-21T00:00:00Z')
COST_GRID=(0,2,4,6,10)
ASSETS={
'EURUSD':{'group':'FX','tick':0.00001,'base_cost_bps':1.2},'GBPUSD':{'group':'FX','tick':0.00001,'base_cost_bps':1.8},'USDJPY':{'group':'FX','tick':0.001,'base_cost_bps':1.5},'AUDUSD':{'group':'FX','tick':0.00001,'base_cost_bps':1.8},'USDCAD':{'group':'FX','tick':0.00001,'base_cost_bps':1.8},'USDCHF':{'group':'FX','tick':0.00001,'base_cost_bps':2.0},'NZDUSD':{'group':'FX','tick':0.00001,'base_cost_bps':2.0},'EURJPY':{'group':'FX','tick':0.001,'base_cost_bps':2.0},'GBPJPY':{'group':'FX','tick':0.001,'base_cost_bps':2.5},'EURGBP':{'group':'FX','tick':0.00001,'base_cost_bps':1.5},'XAUUSD':{'group':'METAL','tick':0.01,'base_cost_bps':2.0},'US500':{'group':'INDEX_CFD','tick':0.1,'base_cost_bps':1.5},'NAS100':{'group':'INDEX_CFD','tick':0.1,'base_cost_bps':1.5},'AAPL':{'group':'US_STOCK_CFD','tick':0.01,'base_cost_bps':3.0},'MSFT':{'group':'US_STOCK_CFD','tick':0.01,'base_cost_bps':3.0},'NVDA':{'group':'US_STOCK_CFD','tick':0.01,'base_cost_bps':3.0},'AMZN':{'group':'US_STOCK_CFD','tick':0.01,'base_cost_bps':3.0},'META':{'group':'US_STOCK_CFD','tick':0.01,'base_cost_bps':3.0},'TSLA':{'group':'US_STOCK_CFD','tick':0.01,'base_cost_bps':3.0}}
EXPLICIT={'XAUUSD':'INSTRUMENT_FX_METALS_XAU_USD','US500':'INSTRUMENT_IDX_AMERICA_E_SANDP_500','NAS100':'INSTRUMENT_IDX_AMERICA_E_NQ_100'}

def load_reference(path='/tmp/reference_verify.py'):
    src=Path(path).read_text().replace('sra<=SIGNAL_RANGE_MAX','sra<SIGNAL_RANGE_MAX')
    old="""        if v[c]==ext:\n            if sum(x==ext for x in w)==1: base[conf]=v[c]\n            else: ties+=1\n"""; new="""        if v[c]==ext:\n            if all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]\n            else: ties+=1\n"""
    if old in src: src=src.replace(old,new,1)
    mod=types.ModuleType('wrref_crossasset'); mod.__file__=path; sys.modules[mod.__name__]=mod; exec(compile(src,path,'exec'),mod.__dict__); return mod

def resolve_symbol(symbol):
    from dukascopy_python import instruments as dq
    sym=symbol.upper()
    if sym in EXPLICIT:
        v=getattr(dq,EXPLICIT[sym],None)
        if v is None: raise RuntimeError('missing '+EXPLICIT[sym])
        return v
    stock=None
    for name,value in vars(dq).items():
        if not name.startswith('INSTRUMENT_') or not isinstance(value,str): continue
        if value.replace('/','').upper()==sym:return value
        if value.upper()==sym+'.US/USD':stock=value
    if stock:return stock
    raise RuntimeError('cannot resolve '+sym)

def pick_const(names):
    import dukascopy_python as d
    for k in names:
        v=getattr(d,k,None)
        if v is not None:return v
    raise RuntimeError('missing constant '+str(names))

def month_chunks(start,end):
    cur=pd.Timestamp(year=start.year,month=start.month,day=1,tz='UTC')
    while cur<end:
        nxt=cur+pd.DateOffset(months=1); yield max(cur,start),min(nxt,end); cur=nxt

def download_m5(symbol):
    import dukascopy_python as d
    instrument=resolve_symbol(symbol); interval=pick_const(('INTERVAL_MIN_5','INTERVAL_MINUTE_5','INTERVAL_M5')); side=pick_const(('OFFER_SIDE_BID','PRICE_TYPE_BID','BID'))
    frames=[]; manifest=[]
    for a,b in month_chunks(STATE_START,END):
        label=a.strftime('%Y-%m'); last=None
        for attempt in range(4):
            try:
                df=d.fetch(instrument,interval,side,a.to_pydatetime(),b.to_pydatetime())
                if df is None:df=pd.DataFrame()
                if 'timestamp' in df.columns:df=df.set_index('timestamp')
                if len(df):df=df.copy();df.index=pd.to_datetime(df.index,utc=True);frames.append(df)
                manifest.append({'month':label,'rows':int(len(df)),'status':'ok'});last=None;break
            except Exception as e:last=repr(e);time.sleep(.6*(attempt+1))
        if last is not None:manifest.append({'month':label,'rows':0,'status':'error','error':last});raise RuntimeError(f'{symbol} {label} fetch failed: {last}')
    if not frames:raise RuntimeError(symbol+': no data')
    df=pd.concat(frames).sort_index();df=df[~df.index.duplicated(keep='last')];cols={c.lower():c for c in df.columns};need=['open','high','low','close']
    if any(k not in cols for k in need):raise RuntimeError(f'{symbol}: OHLC missing {list(df.columns)}')
    out=pd.DataFrame({k:pd.to_numeric(df[cols[k]],errors='coerce') for k in need},index=df.index).dropna();out=out[(out.index>=STATE_START)&(out.index<END)]
    return out,manifest,instrument

def to_bars(df,Bar):
    out=[]
    for ts,r in df.iterrows():
        ot=int(ts.timestamp()*1000);out.append(Bar(ot,ot+300000-1,float(r.open),float(r.high),float(r.low),float(r.close)))
    return out

def strict_10m(bars,Bar):
    g={}
    for b in bars:g.setdefault((b.ot//600000)*600000,[]).append(b)
    out=[];reject=0
    for ot,xs in sorted(g.items()):
        xs=sorted(xs,key=lambda z:z.ot)
        if len(xs)!=2 or xs[0].ot!=ot or xs[1].ot!=ot+300000:reject+=1;continue
        out.append(Bar(ot,ot+600000-1,xs[0].o,max(x.h for x in xs),min(x.l for x in xs),xs[-1].c))
    return out,reject

def net_r(t,bps):
    d=abs(t['entry']-t['stop']);return t['R'] if d<=0 else t['R']-(t['entry']/d)*bps/10000

def metrics(trades,bps):
    v=[net_r(t,bps) for t in trades]
    if not v:return {'n':0,'net_R':0.0,'avg_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0,'max_L_streak':0}
    gp=sum(max(x,0) for x in v);gl=sum(max(-x,0) for x in v);eq=peak=0.;mdd=0.;ls=mls=0
    for x in v:
        eq+=x;peak=max(peak,eq);mdd=min(mdd,eq-peak)
        if x<0:ls+=1;mls=max(mls,ls)
        else:ls=0
    return {'n':len(v),'net_R':sum(v),'avg_R':statistics.mean(v),'PF':gp/gl if gl else None,'win_rate':100*sum(x>0 for x in v)/len(v),'max_DD_R':mdd,'max_L_streak':mls}

def run_bt(symbol,bars,tf,tick,mode,ref):
    calc=ref.calc_ind;nextb=ref.next_bracket;sf=ref.session_flags;Plan=ref.Plan;TP=ref.TP_R;RP=ref.RISK_PCT;INIT=ref.INIT;chart_ms=tf*60000;ind,_,_=calc(bars);eq=INIT;pending=active=None;tr=[]
    def close(i,reason,px):
        nonlocal active,eq
        p=active;both=bars[i].h>=max(p.s,p.t) and bars[i].l<=min(p.s,p.t) and reason in ('TP','SL')
        if both:reason='AMBIG->SL'
        cr=TP if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)*p.qty/p.risk));eq+=cr*p.risk
        if int(START.timestamp()*1000)<=p.sig_t<int(END.timestamp()*1000):tr.append({'symbol':symbol,'tf':tf,'mode':mode,'signal_time':p.sig_t,'side':'LONG' if p.d==1 else 'SHORT','entry':p.e,'stop':p.s,'target':p.t,'exit_time':bars[i].ct,'exit_reason':reason,'R':cr})
        active=None
    for i,x in enumerate(bars):
        closed=False
        if active is not None:
            r,px=nextb(active,x,None)
            if r:close(i,r,px);closed=True
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))
            if fill:
                gap=(pending.d==1 and round(x.o/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.o/tick)<=round(pending.e/tick));active=pending;pending=None;r,px=nextb(active,x,None if gap else active.e)
                if r:close(i,r,px);closed=True
        allowed,sexit=sf(x.ct+1,chart_ms) if mode=='CANONICAL_SESSION' else (True,False)
        if active is not None and not closed:
            z=ind[i];le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up'];se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit:close(i,'SESSION',x.c);closed=True
            elif le or se:close(i,'EMA',x.c);closed=True
        if pending is not None and i>=pending.sig_i+1 and active is None:pending=None
        if active is None and pending is None and not closed:
            z=ind[i];lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None;sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res'];sh=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or sh:
                if nl:d=1;e=x.h+tick;s=x.l-tick;t=e+TP*(e-s)
                else:d=-1;e=x.l-tick;s=x.h+tick;t=e-TP*(s-e)
                q=math.floor((eq*RP/100)/abs(e-s));risk=abs(e-s)*q
                if q>0 and risk>0:pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l)
    return tr

def summarize(symbol,b5,b10,reject,manifest,instrument,ref):
    cfg=ASSETS[symbol];rows=[];alltr=[]
    for tf,bars in ((5,b5),(10,b10)):
      for mode in ('CORE_NO_CRYPTO_SESSION','CANONICAL_SESSION'):
        tr=run_bt(symbol,bars,tf,cfg['tick'],mode,ref);alltr+=tr
        for yr in ('ALL',2022,2023,2024,2025,2026):
            yy=tr if yr=='ALL' else [t for t in tr if pd.Timestamp(t['signal_time'],unit='ms',tz='UTC').year==yr]
            rows.append({'symbol':symbol,'group':cfg['group'],'dukascopy_instrument':instrument,'tf':tf,'mode':mode,'year':yr,'bars':len(bars),'rejected_10m_buckets':reject if tf==10 else 0,'base_cost_bps':cfg['base_cost_bps'],'gross':metrics(yy,0),'base_cost':metrics(yy,cfg['base_cost_bps']),'cost_grid':{str(b):metrics(yy,b) for b in COST_GRID},'long_base':metrics([t for t in yy if t['side']=='LONG'],cfg['base_cost_bps']),'short_base':metrics([t for t in yy if t['side']=='SHORT'],cfg['base_cost_bps'])})
    q={'symbol':symbol,'instrument':instrument,'m5_rows':len(b5),'m10_rows':len(b10),'m10_rejected_incomplete_buckets':reject,'first_utc':pd.Timestamp(b5[0].ot,unit='ms',tz='UTC').isoformat() if b5 else None,'last_utc':pd.Timestamp(b5[-1].ot,unit='ms',tz='UTC').isoformat() if b5 else None,'month_manifest':manifest};return rows,alltr,q

def merge_results(root,out):
    p=Path(root);o=Path(out);o.mkdir(parents=True,exist_ok=True);rows=[];quality=[];trades=[]
    for f in p.rglob('summary-*.json'):rows+=json.load(open(f))
    for f in p.rglob('quality-*.json'):quality.append(json.load(open(f)))
    for f in p.rglob('trades-*.jsonl'):
        for line in open(f):
            if line.strip():trades.append(json.loads(line))
    key={(r['symbol'],r['tf'],r['mode'],str(r['year'])):r for r in rows};passes=[]
    for sym in ASSETS:
      for tf in (5,10):
       for mode in ('CORE_NO_CRYPTO_SESSION','CANONICAL_SESSION'):
        a=key.get((sym,tf,mode,'2025'));b=key.get((sym,tf,mode,'2026'))
        if a and b:passes.append({'symbol':sym,'group':ASSETS[sym]['group'],'tf':tf,'mode':mode,'net2025':a['base_cost']['net_R'],'n2025':a['base_cost']['n'],'net2026':b['base_cost']['net_R'],'n2026':b['base_cost']['n'],'PASS_2025_2026':a['base_cost']['net_R']>0 and b['base_cost']['net_R']>0 and a['base_cost']['n']>=20 and b['base_cost']['n']>=10})
    groups=[]
    for g in sorted({x['group'] for x in ASSETS.values()}):
      for tf in (5,10):
       for mode in ('CORE_NO_CRYPTO_SESSION','CANONICAL_SESSION'):
        z=[x for x in passes if x['group']==g and x['tf']==tf and x['mode']==mode];groups.append({'group':g,'tf':tf,'mode':mode,'assets':len(z),'passes':sum(x['PASS_2025_2026'] for x in z),'pass_symbols':[x['symbol'] for x in z if x['PASS_2025_2026']]})
    report={'status':'COMPLETE','source':'Dukascopy public historical M5 BID','evaluation':'2022-01-01 through 2026-08-20 UTC','development':'2022-2024','validation':'2025','final_oos':'2026 through 2026-08-20','important':'US500/NAS100 are Dukascopy index CFDs (ES/NQ proxies); US equities are Dukascopy stock CFDs, not exchange prints.','pass_rule':'base-cost net >0 in both 2025 and 2026 with >=20 validation and >=10 OOS trades','passes':passes,'group_summary':groups,'quality':quality};json.dump(report,open(o/'report.json','w'),indent=2);json.dump(rows,open(o/'all_summaries.json','w'),indent=2)
    with open(o/'all_trades.jsonl','w') as f:
      for t in trades:f.write(json.dumps(t,separators=(',',':'))+'\n')
    print(json.dumps(report,indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--symbol');ap.add_argument('--out',default='/tmp/out');ap.add_argument('--merge-dir');a=ap.parse_args()
    if a.merge_dir:merge_results(a.merge_dir,a.out);return
    sym=a.symbol.upper();ref=load_reference();df,manifest,instrument=download_m5(sym);b5=to_bars(df,ref.Bar);b10,reject=strict_10m(b5,ref.Bar);rows,tr,q=summarize(sym,b5,b10,reject,manifest,instrument,ref);o=Path(a.out);o.mkdir(parents=True,exist_ok=True);json.dump(rows,open(o/f'summary-{sym}.json','w'),indent=2);json.dump(q,open(o/f'quality-{sym}.json','w'),indent=2)
    with open(o/f'trades-{sym}.jsonl','w') as f:
      for t in tr:f.write(json.dumps(t,separators=(',',':'))+'\n')
    print(json.dumps({'symbol':sym,'m5':len(b5),'m10':len(b10),'rejected10':reject,'trades':len(tr)}))
if __name__=='__main__':main()
