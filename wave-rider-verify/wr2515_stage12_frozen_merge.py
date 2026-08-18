#!/usr/bin/env python3
from __future__ import annotations
import glob,json,math,os,statistics
from bisect import bisect_left,bisect_right
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(os.getenv('BASE_DIR','/tmp/base'))
IN=Path(os.getenv('IN_DIR','/tmp/all'))
OUT=Path(os.getenv('OUT_DIR','/tmp/final'));OUT.mkdir(parents=True,exist_ok=True)
START=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,15,tzinfo=timezone.utc)
START_MS=int(START.timestamp()*1000);END_MS=int(END.timestamp()*1000)
# Baseline structural ledger starts Jan 1. First fully covered 14d checkpoint is Jan 15 15:30 VN = 08:30Z.
READY=datetime(2025,1,15,8,30,tzinfo=timezone.utc);READY_MS=int(READY.timestamp()*1000)
VN=ZoneInfo('Asia/Ho_Chi_Minh');NY=ZoneInfo('America/New_York')
LOOK=14*86400_000;MINSET=5;TOPN=5


def checkpoints():
    z=[];d=date(2024,12,31)
    while d<=date(2026,8,15):
        cp=datetime(d.year,d.month,d.day,15,30,tzinfo=VN);ms=int(cp.timestamp()*1000)
        if START_MS<=ms<END_MS:z.append((ms,(cp-timedelta(hours=6)).date().isoformat(),'VN1530'))
        d+=timedelta(days=1)
    d=date(2024,12,31)
    while d<=date(2026,8,15):
        if d.weekday()<5:
            for h,m,l in ((10,0,'ET1000'),(12,45,'ET1245'),(15,45,'ET1545')):
                cp=datetime(d.year,d.month,d.day,h,m,tzinfo=NY);ms=int(cp.timestamp()*1000)
                if START_MS<=ms<END_MS:
                    v=cp.astimezone(VN);z.append((ms,(v-timedelta(hours=6)).date().isoformat(),l))
        d+=timedelta(days=1)
    return sorted({x[0]:x for x in z}.values())

CPS=checkpoints();CPMS=[x[0] for x in CPS]


def pct(vals,q):
    a=sorted(float(x) for x in vals);n=len(a)
    if not n:return None
    p=q*(n-1);lo=int(math.floor(p));hi=int(math.ceil(p))
    return a[lo] if lo==hi else a[lo]+(p-lo)*(a[hi]-a[lo])


def signal_ms(x):
    s=x['signal_time']
    return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000) if isinstance(s,str) else int(s)


def cost_r(t,bps=6):
    d=abs(float(t['entry'])-float(t['stop']))
    return 0.0 if d<=0 else abs(float(t['entry']))/d*(bps/10000.0)


def metrics(ts):
    n=len(ts);rs=[float(x['R']) for x in ts];gross=sum(rs);gp=sum(max(x,0) for x in rs);gl=sum(max(-x,0) for x in rs)
    net6=sum(float(x['R'])-cost_r(x,6) for x in ts)
    stops=[float(x['stop_pct']) for x in ts if x.get('stop_pct') is not None]
    req=[float(x['required_x']) for x in ts if x.get('required_x') is not None]
    return {
      'trades':n,'gross_r':gross,'avg_r':gross/n if n else None,
      'pf':gp/gl if gl>0 else (None if gp==0 else 999.0),
      'win_rate':sum(x>0 for x in rs)/n*100 if n else None,
      'net_r_6bps':net6,'avg_net_r_6bps':net6/n if n else None,
      'median_stop_pct':statistics.median(stops) if stops else None,
      'p90_required_x':pct(req,.9) if req else None
    }


def main():
    passes=[];errs=[];meta=[]
    for p in glob.glob(str(IN/'passes-*.json')):passes+=json.load(open(p))
    for p in glob.glob(str(IN/'errors-*.json')):errs+=json.load(open(p))
    for p in glob.glob(str(IN/'meta-*.json')):meta+=json.load(open(p))
    if errs:raise SystemExit('Stage1 shard errors '+json.dumps(errs[:20]))

    tv=json.load(open(BASE/'tv_tick_map.json'));summary=json.load(open(BASE/'summary.json'));have={x['symbol'] for x in summary};universe=set(tv)&have
    got={x['symbol'] for x in meta}
    if got!=universe:raise SystemExit(f'Stage1 universe mismatch got={len(got)} expected={len(universe)} missing={sorted(universe-got)[:20]}')

    pass_by=defaultdict(set)
    for x in passes:
        if x['symbol'] in universe:pass_by[int(x['checkpoint'])].add(x['symbol'])

    # Exact frozen Stage2 structural sample: filled standalone v2.5.15 trades, keyed by signal_time.
    trades=[];sample_by=defaultdict(list)
    with open(BASE/'trades.jsonl') as f:
        for line in f:
            if not line.strip():continue
            x=json.loads(line);sym=x.get('symbol')
            if sym not in universe:continue
            ms=signal_ms(x);x['_signal_ms']=ms
            if START_MS<=ms<END_MS:
                trades.append(x)
                if x.get('required_x') is not None:sample_by[sym].append((ms,float(x['required_x'])))
    sample_times={}
    for s in sample_by:
        sample_by[s].sort();sample_times[s]=[x[0] for x in sample_by[s]]

    union=set();prev_session=None;stage1_snap={};stage2_snap={};selection_rows=[]
    for cp,session_date,mode in CPS:
        now=pass_by.get(cp,set())
        if session_date!=prev_session:
            union=set(now);prev_session=session_date
        else:union|=now
        stage1_snap[cp]=set(union)
        ranked=[];lo=cp-LOOK
        for sym in union:
            arr=sample_by.get(sym,[]);tt=sample_times.get(sym,[])
            a=bisect_left(tt,lo);b=bisect_left(tt,cp);vals=[v for _,v in arr[a:b]]
            if len(vals)>=MINSET:
                ranked.append((pct(vals,.9),pct(vals,.5),sym,len(vals)))
        ranked.sort(key=lambda x:(x[0],x[1],x[2]));selected=ranked[:TOPN]
        stage2_snap[cp]={x[2] for x in selected}
        selection_rows.append({
          'checkpoint':cp,'checkpoint_utc':datetime.fromtimestamp(cp/1000,tz=timezone.utc).isoformat(),
          'session_date':session_date,'mode':mode,'fully_covered_14d':cp>=READY_MS,
          'stage1_pass_now':len(now),'stage1_union':len(union),'stage2_eligible':len(ranked),
          'selected':[{'symbol':s,'p90_required_x':p90,'p50_required_x':p50,'filled_trade_n_14d':n} for p90,p50,s,n in selected]
        })

    # Common comparison window begins only once a full 14d structural sample is available from the tick-clean baseline ledger.
    raw=[];s1=[];s12=[]
    for t in trades:
        if t['_signal_ms']<READY_MS:continue
        raw.append(t);j=bisect_right(CPMS,t['_signal_ms'])-1
        if j<0:continue
        cp=CPMS[j];sym=t['symbol']
        if sym in stage1_snap.get(cp,set()):
            s1.append(t)
            if sym in stage2_snap.get(cp,set()):s12.append(t)

    def period(a,b,arr):
        aa=int(datetime.fromisoformat(a).replace(tzinfo=timezone.utc).timestamp()*1000);bb=int(datetime.fromisoformat(b).replace(tzinfo=timezone.utc).timestamp()*1000)
        return metrics([x for x in arr if aa<=x['_signal_ms']<bb])

    by=defaultdict(list)
    for x in s12:by[x['symbol']].append(x)
    symrows=[{'symbol':s,**metrics(v)} for s,v in by.items()];symrows.sort(key=lambda x:(-x['net_r_6bps'],x['symbol']))
    selected_symbols=sorted({y['symbol'] for r in selection_rows if r['fully_covered_14d'] for y in r['selected']})

    report={
      'status':'STAGE12_5M_FROZEN_RULE_RECONSTRUCTION_PASS',
      'engine':'Wave Rider v2.5.15 verified Pine semantics, 5m; TradingView-tick-clean baseline',
      'baseline_artifact':'wr2515-5m-tv-tick-final / run 32158961561',
      'universe_policy':'current TradingView BINANCE USDT perpetual overlap only for this pass',
      'universe_symbols':len(universe),
      'survivorship_warning':'134 historical baseline symbols are absent from current TradingView and are not in this pass. Because Stage2 is cross-sectional Top-5, this pass is diagnostic until historical-universe impact is audited.',
      'stage1_reconstruction':'past-only historical candle reconstruction; 15:30 VN daily and 10:00/12:45/15:45 ET weekdays; session rollover 06:00 VN; session union',
      'stage2_rule':{
        'structural_sample':'filled standalone v2.5.15 trades with signal_time in [checkpoint-14d, checkpoint)',
        'lookback_calendar_days':14,'minimum_prior_filled_trades':5,
        'rank':'lowest P90 Required-X','tie_break':'P50 Required-X then ticker','top_n':5,'uses_pnl':False,
        'effective_period':'checkpoint until next checkpoint','timeframe_minutes':5
      },
      'common_evaluation_start_utc':READY.isoformat(),'common_evaluation_end_utc':END.isoformat(),
      'warmup_reason':'tick-clean filled-trade ledger begins 2025-01-01; first fully covered 14d Stage2 checkpoint is 2025-01-15 08:30Z',
      'checkpoints_total':len(CPS),'checkpoints_fully_covered':sum(cp>=READY_MS for cp,_,_ in CPS),
      'stage1_pass_rows':len(passes),'unique_stage2_selected_symbols':len(selected_symbols),'selected_symbols':selected_symbols,
      'raw_current_tv':metrics(raw),'stage1':metrics(s1),'stage1_stage2':metrics(s12),
      'stability':{
        '2025_after_warmup':{'raw':period('2025-01-15','2026-01-01',raw),'stage1':period('2025-01-15','2026-01-01',s1),'stage12':period('2025-01-15','2026-01-01',s12)},
        '2026_pre_aug15':{'raw':period('2026-01-01','2026-08-15',raw),'stage1':period('2026-01-01','2026-08-15',s1),'stage12':period('2026-01-01','2026-08-15',s12)}
      },
      'stage12_top20_by_net6':symrows[:20],'stage12_bottom20_by_net6':symrows[-20:],
      'w4_contamination':'W4 was already consumed. No Stage1/Stage2 threshold is changed using W4. This reconstruction is not a fresh W4 holdout.',
      'true_forward_start':'2026-08-15'
    }

    for x in trades:x.pop('_signal_ms',None)
    (OUT/'report.json').write_text(json.dumps(report,indent=2));(OUT/'selections.json').write_text(json.dumps(selection_rows,indent=2));(OUT/'stage12_symbol_results.json').write_text(json.dumps(symrows,indent=2))
    with open(OUT/'stage1_trades.jsonl','w') as f:
        for x in s1:
            y={k:v for k,v in x.items() if k!='_signal_ms'};f.write(json.dumps(y,separators=(',',':'))+'\n')
    with open(OUT/'stage12_trades.jsonl','w') as f:
        for x in s12:
            y={k:v for k,v in x.items() if k!='_signal_ms'};f.write(json.dumps(y,separators=(',',':'))+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
