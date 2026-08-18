#!/usr/bin/env python3
from __future__ import annotations
import glob,json,math,os
from bisect import bisect_right
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(os.getenv('BASE_DIR','/tmp/base')); IN=Path(os.getenv('IN_DIR','/tmp/all')); OUT=Path(os.getenv('OUT_DIR','/tmp/final'));OUT.mkdir(parents=True,exist_ok=True)
START=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,15,tzinfo=timezone.utc);START_MS=int(START.timestamp()*1000);END_MS=int(END.timestamp()*1000)
VN=ZoneInfo('Asia/Ho_Chi_Minh');NY=ZoneInfo('America/New_York');LOOK=14*86400_000;MINSET=5;TOPN=5

def checkpoints():
    z=[];d=date(2024,12,31)
    while d<=date(2026,8,15):
        cp=datetime(d.year,d.month,d.day,15,30,tzinfo=VN);ms=int(cp.timestamp()*1000)
        if START_MS<=ms<END_MS:z.append((ms,(cp-timedelta(hours=6)).date().isoformat(),'VN1530'))
        d+=timedelta(days=1)
    d=date(2024,12,31)
    while d<=date(2026,8,15):
        for h,m,l in [(10,0,'ET1000'),(12,45,'ET1245'),(15,45,'ET1545')]:
            cp=datetime(d.year,d.month,d.day,h,m,tzinfo=NY);ms=int(cp.timestamp()*1000)
            if START_MS<=ms<END_MS:
                v=cp.astimezone(VN);z.append((ms,(v-timedelta(hours=6)).date().isoformat(),l))
        d+=timedelta(days=1)
    return sorted({x[0]:x for x in z}.values())
CPS=checkpoints();CPMS=[x[0] for x in CPS]

def p90(vals):
    a=sorted(float(x) for x in vals);n=len(a)
    if not n:return None
    p=.9*(n-1);lo=int(math.floor(p));hi=int(math.ceil(p))
    return a[lo] if lo==hi else a[lo]+(p-lo)*(a[hi]-a[lo])

def cost_r(t,bps=6):
    d=abs(float(t['entry'])-float(t['stop']))
    return 0.0 if d<=0 else abs(float(t['entry']))/d*(bps/10000.0)

def metrics(ts):
    n=len(ts);rs=[float(x['R']) for x in ts];gross=sum(rs);gp=sum(max(x,0) for x in rs);gl=sum(max(-x,0) for x in rs);net6=sum(float(x['R'])-cost_r(x,6) for x in ts)
    return {'trades':n,'gross_r':gross,'avg_r':gross/n if n else None,'pf':gp/gl if gl>0 else (None if gp==0 else 999.0),'win_rate':sum(x>0 for x in rs)/n*100 if n else None,'net_r_6bps':net6,'avg_net_r_6bps':net6/n if n else None}

def main():
    setups=[];passes=[];errs=[];meta=[]
    for p in glob.glob(str(IN/'setups-*.json')):setups+=json.load(open(p))
    for p in glob.glob(str(IN/'passes-*.json')):passes+=json.load(open(p))
    for p in glob.glob(str(IN/'errors-*.json')):errs+=json.load(open(p))
    for p in glob.glob(str(IN/'meta-*.json')):meta+=json.load(open(p))
    tv=json.load(open(BASE/'tv_tick_map.json'));summary=json.load(open(BASE/'summary.json'));have={x['symbol'] for x in summary};universe=set(tv)&have
    if errs: raise SystemExit('shard errors '+json.dumps(errs[:20]))
    if len({x['symbol'] for x in meta})!=len(universe): raise SystemExit(f'meta universe mismatch meta={len({x["symbol"] for x in meta})} universe={len(universe)}')
    pass_by=defaultdict(set)
    for x in passes:
        if x['symbol'] in universe:pass_by[int(x['checkpoint'])].add(x['symbol'])
    setup_by=defaultdict(list)
    for x in setups:
        if x['symbol'] in universe:setup_by[x['symbol']].append((int(x['signal_time']),float(x['required_x'])))
    for s in setup_by:setup_by[s].sort()
    # Session-union reconstruction. A new session replaces the prior union at its first checkpoint; within-session checkpoints accumulate.
    union=set();prev_session=None;stage1_snap={};stage2_snap={};selection_rows=[]
    for cp,session_date,mode in CPS:
        now=pass_by.get(cp,set())
        if session_date!=prev_session:
            union=set(now);prev_session=session_date
        else:union|=now
        stage1_snap[cp]=set(union)
        ranked=[]
        lo=cp-LOOK
        for sym in union:
            vals=[v for t,v in setup_by.get(sym,[]) if lo<=t<cp]
            if len(vals)>=MINSET:
                q=p90(vals);ranked.append((q,sym,len(vals)))
        ranked.sort(key=lambda x:(x[0],x[1]));sel={x[1] for x in ranked[:TOPN]};stage2_snap[cp]=sel
        selection_rows.append({'checkpoint':cp,'session_date':session_date,'mode':mode,'stage1_pass_now':len(now),'stage1_union':len(union),'stage2_eligible':len(ranked),'selected':[{'symbol':s,'p90_required_x':q,'setup_n_14d':n} for q,s,n in ranked[:TOPN]]})
    trades=[]
    with open(BASE/'trades.jsonl') as f:
        for line in f:
            if not line.strip():continue
            x=json.loads(line)
            if x.get('symbol') not in universe:continue
            st=x['signal_time']
            if isinstance(st,str):
                ms=int(datetime.fromisoformat(st.replace('Z','+00:00')).timestamp()*1000)
            else:ms=int(st)
            if START_MS<=ms<END_MS:x['_signal_ms']=ms;trades.append(x)
    s1=[];s12=[]
    for t in trades:
        j=bisect_right(CPMS,t['_signal_ms'])-1
        if j<0:continue
        cp=CPMS[j];sym=t['symbol']
        if sym in stage1_snap.get(cp,set()):
            s1.append(t)
            if sym in stage2_snap.get(cp,set()):s12.append(t)
    # Calendar stability blocks; these are descriptive, not fresh OOS.
    def period(a,b,arr):
        aa=int(datetime.fromisoformat(a).replace(tzinfo=timezone.utc).timestamp()*1000);bb=int(datetime.fromisoformat(b).replace(tzinfo=timezone.utc).timestamp()*1000)
        return metrics([x for x in arr if aa<=x['_signal_ms']<bb])
    report={
      'status':'STAGE12_5M_RECONSTRUCTION_PASS',
      'engine':'Wave Rider v2.5.15 verified Pine semantics, 5m',
      'universe_policy':'current TradingView BINANCE USDT perpetual overlap only; historical/missing-current-TV contracts quarantined',
      'universe_symbols':len(universe),
      'period':'2025-01-01 to 2026-08-15 exclusive',
      'stage1_rule':{'qv24_gte':100000000,'avg_usd_volume_10d_gte':200000000,'vol7_gt':0.06,'adr14_gte':0.05,'checkpoint_modes':['15:30 VN','10:00 ET','12:45 ET','15:45 ET'],'semantics':'session union; previous session remains effective until next session first checkpoint'},
      'stage2_rule':{'lookback_calendar_days':14,'min_prior_setups':5,'rank':'lowest P90 Required-X','top_n':5,'uses_pnl':False,'timeframe_minutes':5},
      'checkpoints':len(CPS),'setup_rows':len(setups),'stage1_pass_rows':len(passes),
      'all_current_tv':metrics(trades),'stage1':metrics(s1),'stage1_stage2':metrics(s12),
      'stability':{
        '2025_all':{'raw':period('2025-01-01','2026-01-01',trades),'stage1':period('2025-01-01','2026-01-01',s1),'stage12':period('2025-01-01','2026-01-01',s12)},
        '2026_pre_aug15':{'raw':period('2026-01-01','2026-08-15',trades),'stage1':period('2026-01-01','2026-08-15',s1),'stage12':period('2026-01-01','2026-08-15',s12)}},
      'contamination_note':'W4 was already consumed before this reconstruction. No thresholds are changed from frozen Stage1/Stage2 rules based on W4; these results are research reconstruction, not fresh OOS.',
      'true_forward_start':'2026-08-15'
    }
    # Per-symbol Stage12 outcome for diagnosis only; never convert directly to a static whitelist.
    by=defaultdict(list)
    for x in s12:by[x['symbol']].append(x)
    symrows=[{'symbol':s,**metrics(v)} for s,v in by.items()];symrows.sort(key=lambda x:(-x['net_r_6bps'],x['symbol']))
    report['stage12_top20_by_net6']=symrows[:20]
    report['stage12_bottom20_by_net6']=symrows[-20:]
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    (OUT/'selections.json').write_text(json.dumps(selection_rows,indent=2))
    (OUT/'stage12_symbol_results.json').write_text(json.dumps(symrows,indent=2))
    with open(OUT/'stage1_trades.jsonl','w') as f:
        for x in s1:x.pop('_signal_ms',None);f.write(json.dumps(x,separators=(',',':'))+'\n')
    with open(OUT/'stage12_trades.jsonl','w') as f:
        for x in s12:x.pop('_signal_ms',None);f.write(json.dumps(x,separators=(',',':'))+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
