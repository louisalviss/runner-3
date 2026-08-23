#!/usr/bin/env python3
from __future__ import annotations
import json, os, statistics, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from close_confirm import run_case, assert_canonical_parity

BASE_DIR=Path(os.getenv('WR_BASE_DIR','/tmp/wrbase'))
sys.path.insert(0,str(BASE_DIR))
import wr_dukascopy_expanded_matrix as exp

OUT=Path(os.getenv('WR_OUT','/tmp/wr-stock10-close')); OUT.mkdir(parents=True,exist_ok=True)
SYMBOL=os.environ.get('SYMBOL') or (sys.argv[1] if len(sys.argv)>1 else None)
if not SYMBOL: raise SystemExit('SYMBOL required')


def cost_r(t,bps):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)

def metric(trades,bps=0.0):
    vals=[float(t['R'])-cost_r(t,bps) for t in trades]; n=len(vals)
    gp=sum(max(x,0.0) for x in vals); gl=sum(max(-x,0.0) for x in vals)
    eq=peak=0.0; mdd=0.0
    for x in vals:
        eq+=x; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {'n':n,'R':sum(vals),'avg_R':sum(vals)/n if n else None,'PF':gp/gl if gl else None,'max_DD_R':mdd,'win_rate':100*sum(x>0 for x in vals)/n if n else None}

def year_of(t): return datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year

def subset(trades,years=None,side=None):
    out=[]
    for t in trades:
        if years is not None and year_of(t) not in years: continue
        if side is not None and t['side']!=side: continue
        out.append(t)
    return out

def geometry(trades):
    xs=[]
    for t in trades:
        e=float(t['e']); s=float(t['s']); d=abs(e-s)
        if e<=0 or d<=0: continue
        risk_bps=d/e*10000.0
        xs.append((risk_bps,1.0/risk_bps if risk_bps>0 else None,float(t['R'])))
    if not xs:return {'n':0}
    r=sorted(x[0] for x in xs)
    def q(p):
        k=(len(r)-1)*p; a=int(k); b=min(a+1,len(r)-1); w=k-a; return r[a]*(1-w)+r[b]*w
    return {'n':len(xs),'risk_bps_median':statistics.median(r),'risk_bps_q20':q(.2),'risk_bps_q80':q(.8),'median_R_loss_per_1bps':statistics.median(1/x[0] for x in xs)}

def report_variant(name,trades,raw):
    train=subset(trades,{2022,2023}); oos=subset(trades,{2024,2025,2026})
    return {
      'variant':name,'raw_engine':raw,
      'train_2022_2023':{'gross':metric(train,0),'net_1bps':metric(train,1),'net_2bps':metric(train,2),'long_1bps':metric(subset(train,side='L'),1),'short_1bps':metric(subset(train,side='S'),1),'geometry':geometry(train)},
      'oos_2024_2026':{'gross':metric(oos,0),'net_1bps':metric(oos,1),'net_2bps':metric(oos,2),'long_1bps':metric(subset(oos,side='L'),1),'short_1bps':metric(subset(oos,side='S'),1),'geometry':geometry(oos),
                       'by_year':{str(y):{'net_1bps':metric(subset(oos,{y}),1),'net_2bps':metric(subset(oos,{y}),2)} for y in (2024,2025,2026)}}
    }

def main():
    symbol=SYMBOL.upper(); instrument=exp.resolve_symbol(symbol)
    if not instrument:
        (OUT/f'{symbol}.json').write_text(json.dumps({'symbol':symbol,'status':'UNAVAILABLE','reason':'instrument_not_found'},indent=2)); return
    raw,manifest,_=exp.load_mid(symbol,5)
    if raw is None or raw.empty:
        (OUT/f'{symbol}.json').write_text(json.dumps({'symbol':symbol,'status':'UNAVAILABLE','reason':'no_mid_data','manifest':manifest},indent=2)); return
    df,reject=exp.aggregate(raw,5,10)
    base,ref=exp.load_modules(10); _,tick,tz,session=exp.cfg(symbol); base.tv_tick=lambda _i,_v:tick
    bars=exp.to_bars(df,base.Bar,10); info=exp.provider_info(symbol)
    parity_n=assert_canonical_parity(base,ref,bars,info,exp.STATE_START.to_pydatetime(),exp.START.to_pydatetime(),exp.END.to_pydatetime(),anchor='start',use_session=True)
    baseline,braw=run_case(base,ref,bars,info,exp.STATE_START.to_pydatetime(),exp.START.to_pydatetime(),exp.END.to_pydatetime(),variant='canonical',anchor='start',use_session=True)
    close,craw=run_case(base,ref,bars,info,exp.STATE_START.to_pydatetime(),exp.START.to_pydatetime(),exp.END.to_pydatetime(),variant='close_confirmed',anchor='start',use_session=True)
    payload={'status':'OK','symbol':symbol,'tf':'10m','test':'single-change close-confirmed entry A/B','close_confirm_semantics':'signal at T; next 10m bar must close beyond canonical stop-entry trigger; entry at following bar open; original signal-candle stop side retained; TP reset to 2.3R from actual entry','source':'Dukascopy M5 BID/ASK-side midpoint bars aggregated to 10m; structural comparison only, not final executable proof','cost_units':'modeled round-trip-equivalent bps sensitivity','parity_all_eligible_n':parity_n,'bars':len(bars),'rejected_10m_buckets':reject,'instrument':instrument,'tick':tick,'manifest':manifest,
             'baseline':report_variant('canonical',baseline,braw),'close_confirmed':report_variant('close_confirmed',close,craw)}
    a=payload['baseline']['oos_2024_2026']['net_1bps']; b=payload['close_confirmed']['oos_2024_2026']['net_1bps']
    payload['oos_delta_close_minus_baseline_1bps']={'R':b['R']-a['R'],'n':b['n']-a['n'],'avg_R':(b['avg_R']-a['avg_R']) if a['avg_R'] is not None and b['avg_R'] is not None else None}
    (OUT/f'{symbol}.json').write_text(json.dumps(payload,indent=2,default=str))
    with (OUT/f'{symbol}-trades.jsonl').open('w') as f:
        for name,trs in [('baseline',baseline),('close_confirmed',close)]:
            for t in trs:
                f.write(json.dumps({'symbol':symbol,'tf':10,'variant':name,'year':year_of(t),'risk_bps':abs(float(t['e'])-float(t['s']))/float(t['e'])*10000.0,**t})+'\n')
    print('RESULT',symbol,'parity',parity_n,'base_oos_1bps',a,'close_oos_1bps',b,'deltaR',b['R']-a['R'],flush=True)

if __name__=='__main__': main()
