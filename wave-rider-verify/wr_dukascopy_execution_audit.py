#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, statistics, sys, time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import wr_dukascopy_expanded_matrix as exp

OUT=Path(os.getenv('WR_OUT','/tmp/wr-exec-audit'));OUT.mkdir(parents=True,exist_ok=True)
STATE_START=pd.Timestamp('2021-12-01T00:00:00Z')
START=pd.Timestamp('2022-01-01T00:00:00Z')
END=pd.Timestamp('2026-08-21T00:00:00Z')
TP_R=2.3

@dataclass
class Plan:
    d:int;e:float;s:float;t:float;risk:float;qty:float;sig_i:int;sig_t:int;report:bool;features:dict


def load_quotes(symbol):
    instrument=exp.resolve_symbol(symbol)
    if not instrument:return None,None,[],None
    bidc=exp.pick_const(('OFFER_SIDE_BID','PRICE_TYPE_BID','BID'));askc=exp.pick_const(('OFFER_SIDE_ASK','PRICE_TYPE_ASK','ASK'))
    bids=[];asks=[];manifest=[]
    for a,b in exp.month_chunks(STATE_START,END):
        try:
            db=exp.fetch_side(instrument,bidc,a,b,1);da=exp.fetch_side(instrument,askc,a,b,1)
            idx=db.index.intersection(da.index)
            if len(idx):
                bids.append(db.loc[idx,['open','high','low','close']]);asks.append(da.loc[idx,['open','high','low','close']])
            manifest.append({'month':a.strftime('%Y-%m'),'bid_rows':int(len(db)),'ask_rows':int(len(da)),'common_rows':int(len(idx))})
        except Exception as e:
            manifest.append({'month':a.strftime('%Y-%m'),'error':repr(e)})
    if not bids:return None,None,manifest,instrument
    bid=pd.concat(bids).sort_index();ask=pd.concat(asks).sort_index()
    bid=bid[~bid.index.duplicated(keep='last')];ask=ask[~ask.index.duplicated(keep='last')]
    idx=bid.index.intersection(ask.index);bid=bid.loc[idx];ask=ask.loc[idx]
    bid=bid[(bid.index>=STATE_START)&(bid.index<END)];ask=ask.loc[bid.index]
    return bid,ask,manifest,instrument


def chart_quotes(bid1,ask1,tf):
    mid1=(bid1+ask1)/2.0
    mid,_=exp.aggregate(mid1,1,tf);bid,_=exp.aggregate(bid1,1,tf);ask,_=exp.aggregate(ask1,1,tf)
    idx=mid.index.intersection(bid.index).intersection(ask.index)
    return mid.loc[idx],bid.loc[idx],ask.loc[idx]


def bars_from(df,Bar,tf):
    span=tf*60000;out=[]
    for ts,r in df.iterrows():
        ot=int(ts.timestamp()*1000);out.append(Bar(ot,ot+span,float(r.open),float(r.high),float(r.low),float(r.close)))
    return out


def atr14(bars,ref):
    tr=[]
    for i,x in enumerate(bars):
        tr.append(x.h-x.l if i==0 else max(x.h-x.l,abs(x.h-bars[i-1].c),abs(x.l-bars[i-1].c)))
    return ref.rma(tr,14)


def close_spread_bps(bid,ask):
    m=(float(bid.close)+float(ask.close))/2
    return None if m<=0 else 10000*(float(ask.close)-float(bid.close))/m


def minute_slice(df,ot,ct):
    a=pd.Timestamp(ot,unit='ms',tz='UTC');b=pd.Timestamp(ct,unit='ms',tz='UTC')
    return df[(df.index>=a)&(df.index<b)]


def bracket_touch(plan, q, existing=True):
    # q is executable-side 1m quote: BID for longs, ASK for shorts.
    o,h,l=float(q.open),float(q.high),float(q.low)
    if plan.d==1:
        if existing and o<=plan.s:return 'SL',o
        if existing and o>=plan.t:return 'TP',o
        sl=l<=plan.s;tp=h>=plan.t
    else:
        if existing and o>=plan.s:return 'SL',o
        if existing and o<=plan.t:return 'TP',o
        sl=h>=plan.s;tp=l<=plan.t
    if sl and tp:return 'AMBIG->SL',plan.s
    if sl:return 'SL',plan.s
    if tp:return 'TP',plan.t
    return None,None


def run_exec(symbol,tf,bid1,ask1):
    base,ref=exp.load_modules(tf)
    mid,bidc,askc=chart_quotes(bid1,ask1,tf)
    mbars=bars_from(mid,base.Bar,tf)
    if len(mbars)<100:return {'status':'TOO_FEW_BARS'},[]
    ind,_,_=ref.calc_ind(mbars);a14=atr14(mbars,ref);tick=exp.cfg(symbol)[1];info=exp.provider_info(symbol);sc=base.SessionClock(info,'start')
    start_ms=int(START.timestamp()*1000);end_ms=int(END.timestamp()*1000);chart_ms=tf*60000
    ny=ZoneInfo('America/New_York')
    news=[datetime(2025,11,20,8,30,tzinfo=ny),datetime(2025,12,10,14,0,tzinfo=ny),datetime(2025,12,16,8,30,tzinfo=ny),datetime(2025,12,18,8,30,tzinfo=ny)]
    news=[int(x.timestamp()*1000) for x in news]
    def news_locked(t):return any(e-15*60000<=t<e+15*60000 for e in news)
    def news_exit(tc):return any((tc<e-15*60000 and tc+chart_ms>=e-15*60000) or (tc>=e-15*60000 and tc<e) for e in news)
    def sess_flags(b):
        market,rdc=sc.state(b)
        if not market or rdc is None:return False,False
        tc=b.ct;ne=rdc-40*60000;ex=rdc-15*60000
        noentry=tc<=rdc and (tc>=ne or tc+chart_ms>=ne)
        lastbar=tc>=rdc or tc+chart_ms>rdc
        sexit=(tc<ex and tc+chart_ms>=ex) or (tc>=ex and tc<=rdc) or lastbar
        return not noentry,sexit
    eq=100000.0;pending=None;active=None;trades=[];entry_px=None;entry_t=None;entry_spread=None
    above=below=0
    diag={'signals':0,'fills':0,'pending_expired':0,'tp':0,'sl':0,'ema':0,'session':0,'news':0,'ambig':0}
    for i,b in enumerate(mbars):
        z=ind[i]
        above=above+1 if b.c>z['ema'] else 0;below=below+1 if b.c<z['ema'] else 0
        # Brackets are simulated on 1m executable-side quotes before close-based exits.
        mins_bid=minute_slice(bid1,b.ot,b.ct);mins_ask=minute_slice(ask1,b.ot,b.ct);mins_idx=mins_bid.index.intersection(mins_ask.index)
        closed=False
        if active is not None:
            for ts in mins_idx:
                q=mins_bid.loc[ts] if active.d==1 else mins_ask.loc[ts]
                r,px=bracket_touch(active,q,True)
                if r:
                    exit_px=px;exit_t=int((ts+pd.Timedelta(minutes=1)).timestamp()*1000);reason=r
                    diag['ambig' if r=='AMBIG->SL' else r.lower()]+=1;closed=True;break
            if closed:
                planned=abs(active.e-active.s);pnl=(exit_px-entry_px)*(1 if active.d==1 else -1);rr=pnl/planned if planned>0 else 0.0
                eq+=rr*active.risk
                if active.report:
                    row={'signal':active.sig_t,'entry':entry_t,'exit':exit_t,'side':'L' if active.d==1 else 'S','R_exec':rr,'reason':reason,'planned_entry':active.e,'actual_entry':entry_px,'stop':active.s,'target':active.t,'actual_exit':exit_px,'entry_spread_bps':entry_spread,'exit_spread_bps':close_spread_bps(mins_bid.loc[ts],mins_ask.loc[ts]),**active.features}
                    trades.append(row)
                active=None;entry_px=entry_t=entry_spread=None
        # Next-chart-bar-only stop entry, simulated on 1m ASK for long / BID for short.
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            for ts in mins_idx:
                qb=mins_bid.loc[ts];qa=mins_ask.loc[ts]
                if pending.d==1:
                    fill=float(qa.open)>=pending.e or float(qa.high)>=pending.e
                    px=float(qa.open) if float(qa.open)>=pending.e else pending.e
                else:
                    fill=float(qb.open)<=pending.e or float(qb.low)<=pending.e
                    px=float(qb.open) if float(qb.open)<=pending.e else pending.e
                if not fill:continue
                active=pending;pending=None;entry_px=px;entry_t=int(ts.timestamp()*1000);entry_spread=close_spread_bps(qb,qa);diag['fills']+=1
                q=qb if active.d==1 else qa
                r,xp=bracket_touch(active,q,False)
                if r:
                    exit_px=xp;exit_t=int((ts+pd.Timedelta(minutes=1)).timestamp()*1000);reason=r;diag['ambig' if r=='AMBIG->SL' else r.lower()]+=1
                    planned=abs(active.e-active.s);pnl=(exit_px-entry_px)*(1 if active.d==1 else -1);rr=pnl/planned if planned>0 else 0.0;eq+=rr*active.risk
                    if active.report:trades.append({'signal':active.sig_t,'entry':entry_t,'exit':exit_t,'side':'L' if active.d==1 else 'S','R_exec':rr,'reason':reason,'planned_entry':active.e,'actual_entry':entry_px,'stop':active.s,'target':active.t,'actual_exit':exit_px,'entry_spread_bps':entry_spread,'exit_spread_bps':close_spread_bps(qb,qa),**active.features})
                    active=None;entry_px=entry_t=entry_spread=None;closed=True
                break
        allowed,sexit=sess_flags(b)
        if active is not None and not closed:
            le=active.d==1 and b.c<z['ema'] and not z['ha'] and not z['ema_up'];se=active.d==-1 and b.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            reason=None
            if sexit:reason='SESSION';diag['session']+=1
            elif news_exit(b.ct):reason='NEWS';diag['news']+=1
            elif le or se:reason='EMA';diag['ema']+=1
            if reason:
                cb=bidc.iloc[i];ca=askc.iloc[i];exit_px=float(cb.close) if active.d==1 else float(ca.close);exit_t=b.ct
                planned=abs(active.e-active.s);pnl=(exit_px-entry_px)*(1 if active.d==1 else -1);rr=pnl/planned if planned>0 else 0.0;eq+=rr*active.risk
                if active.report:trades.append({'signal':active.sig_t,'entry':entry_t,'exit':exit_t,'side':'L' if active.d==1 else 'S','R_exec':rr,'reason':reason,'planned_entry':active.e,'actual_entry':entry_px,'stop':active.s,'target':active.t,'actual_exit':exit_px,'entry_spread_bps':entry_spread,'exit_spread_bps':close_spread_bps(cb,ca),**active.features})
                active=None;entry_px=entry_t=entry_spread=None;closed=True
        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None;diag['pending_expired']+=1
        if active is None and pending is None and not closed:
            lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None;sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            safe=not news_locked(b.ct) and not news_locked(b.ct+chart_ms)
            nl=allowed and safe and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res'];ns=allowed and safe and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
            if nl or ns:
                if nl:d=1;e=b.h+tick;s=b.l-tick;t=e+TP_R*(e-s);level=z['res']
                else:d=-1;e=b.l-tick;s=b.h+tick;t=e-TP_R*(s-e);level=z['sup']
                dist=abs(e-s);q=math.floor((max(eq,0)*0.01)/dist);risk=dist*q
                if q>0 and risk>0:
                    aa=a14[i]
                    local=datetime.fromtimestamp(b.ct/1000,tz=timezone.utc).astimezone(sc.tz)
                    features={'signal_hour_local':local.hour,'signal_year':local.year,'signal_range_atr':None if aa in (None,0) else (b.h-b.l)/aa,'breakout_atr':None if aa in (None,0) else ((b.c-level)/aa if d==1 else (level-b.c)/aa),'retest_atr':None if aa in (None,0) else ((level-b.l)/aa if d==1 else (b.h-level)/aa),'ema_dist_atr':None if aa in (None,0) else abs(b.c-z['ema'])/aa,'trend_age':above if d==1 else below}
                    pending=Plan(d,e,s,t,risk,q,i,b.ct,start_ms<=b.ct<end_ms,features);diag['signals']+=1
    vals=[x['R_exec'] for x in trades];gp=sum(max(x,0) for x in vals);gl=sum(max(-x,0) for x in vals)
    canonical,_raw=base.run_case(ref,mbars,info,STATE_START.to_pydatetime(),anchor='start',use_session=True)
    summary={'symbol':symbol,'tf':f'{tf}m','status':'OK','n_exec':len(trades),'R_exec':sum(vals),'avg_R_exec':statistics.mean(vals) if vals else None,'PF_exec':gp/gl if gl else None,'n_mid':len(canonical),'R_mid':sum(x['R'] for x in canonical),'trade_count_delta':len(trades)-len(canonical),'median_entry_spread_bps':statistics.median([x['entry_spread_bps'] for x in trades if x['entry_spread_bps'] is not None]) if trades else None,'median_exit_spread_bps':statistics.median([x['exit_spread_bps'] for x in trades if x['exit_spread_bps'] is not None]) if trades else None,'diag':diag}
    return summary,trades


def breakdown(trades):
    def met(xs):
        v=[x['R_exec'] for x in xs];gp=sum(max(a,0) for a in v);gl=sum(max(-a,0) for a in v)
        return {'n':len(v),'R':sum(v),'avg_R':statistics.mean(v) if v else None,'PF':gp/gl if gl else None}
    out={}
    for key,fn in [('year',lambda x:str(x['signal_year'])),('side',lambda x:x['side']),('hour',lambda x:str(x['signal_hour_local'])),('reason',lambda x:x['reason'])]:
        d={}
        for x in trades:d.setdefault(fn(x),[]).append(x)
        out[key]={k:met(v) for k,v in sorted(d.items())}
    return out


def run(symbol,tf):
    bid1,ask1,manifest,instrument=load_quotes(symbol)
    if bid1 is None:
        result={'symbol':symbol,'tf':f'{tf}m','status':'UNAVAILABLE','instrument':instrument,'manifest':manifest};(OUT/f'audit-{symbol}-{tf}m.json').write_text(json.dumps(result,indent=2));print('UNAVAILABLE',symbol,tf);return
    summary,trades=run_exec(symbol,tf,bid1,ask1);summary.update({'instrument':instrument,'source':'Dukascopy 1m BID/ASK; midpoint signals; 1m executable-side quote simulation','breakdown':breakdown(trades),'manifest':manifest})
    (OUT/f'audit-{symbol}-{tf}m.json').write_text(json.dumps(summary,indent=2,default=str))
    with (OUT/f'trades-{symbol}-{tf}m.jsonl').open('w') as f:
        for x in trades:f.write(json.dumps(x)+'\n')
    print('AUDIT_RESULT',symbol,tf,json.dumps({k:summary.get(k) for k in ('n_mid','R_mid','n_exec','R_exec','avg_R_exec','PF_exec','trade_count_delta','median_entry_spread_bps')},default=str),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--symbol',default=os.getenv('SYMBOL'));ap.add_argument('--tf',type=int,default=int(os.getenv('TF_MIN','3')));a=ap.parse_args();run(a.symbol,a.tf)
if __name__=='__main__':main()
