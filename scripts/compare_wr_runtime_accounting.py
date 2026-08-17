#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,os,re,subprocess,sys
from pathlib import Path
SYMS=['BNBUSDT','TRXUSDT']; INIT=100000.0; RISK_PCT=1.0; TP_R=2.3
STEP_CANDIDATES=[1.0,0.1,0.01,0.001,0.0001,0.00001]

def parse_meta(frames,sym):
    text='\n'.join(frames); chunks=[x for x in re.split(r'~m~\d+~m~',text) if sym in x]; pool='\n'.join(chunks) if chunks else text
    def num(key):
        m=re.search(r'"'+re.escape(key)+r'"\s*:\s*(-?\d+(?:\.\d+)?)',pool); return float(m.group(1)) if m else None
    ps=num('pricescale'); mm=num('minmov'); pv=num('pointvalue')
    if not ps or mm is None or pv is None: raise RuntimeError(f'{sym}: missing symbol metadata')
    return {'pricescale':ps,'minmov':mm,'mintick':mm/ps,'pointvalue':pv}

def parse_num(s): return float(s.replace('−','-').replace('+','').replace(',','').strip())
def parse_tv_row(r):
    cells=r['cells']; times=re.findall(r'(?:Jul|Aug) \d{1,2}, 2026, \d{2}:\d{2}',cells[3]); prices=[float(x) for x in re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?(?= USDT)',cells[4])]; pnl_m=re.search(r'([+−-][\d,]+(?:\.\d+)?) USD',cells[6])
    if len(times)!=2 or len(prices)!=2 or not pnl_m: raise RuntimeError(f'unparsed TV row: {r["text"]}')
    from datetime import datetime,timezone
    def iso(x): return datetime.strptime(x,'%b %d, %Y, %H:%M').replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:00Z')
    return {'n':r['n'],'side':r['side'],'exit_time':iso(times[0]),'entry_time':iso(times[1]),'exit':prices[0],'entry':prices[1],'native_pnl':parse_num(pnl_m.group(1)),'size_text':cells[5]}
def run_engine(sym):
    env=os.environ.copy();env.update(WR_SYMBOL=sym,WR_START='2026-07-27',WR_END='2026-08-17'); subprocess.run([sys.executable,'wave-rider-verify/reference_verify_parity.py'],env=env,check=True,stdout=subprocess.DEVNULL)
    with open(f'wave-rider-verify/output/{sym}_5m_trades.csv',newline='') as f:return list(csv.DictReader(f))
def floor_step(v,step): return math.floor(v/step+1e-12)*step

def simulate(tv,py,meta,step):
    pmap={r['entry_time']:r for r in py}; eq=INIT; diffs=[]; rows=[]; sqerr=0.0; compared=0
    for t in tv:
        p=pmap.get(t['entry_time'])
        if not p: diffs.append({'trade':t['n'],'field':'entry_time','tv':t['entry_time'],'py':None}); continue
        entry=float(p['entry']); stop=float(p['stop']); ex=float(p['exit_price']); side=p['side']; reason=p['exit_reason']; pv=meta['pointvalue']; risk_budget=max(eq,0.0)*RISK_PCT/100.0
        rpu=abs(entry-stop)*pv; raw=risk_budget/rpu if rpu>0 else 0.0; qty=floor_step(raw,step); risk=abs(entry-stop)*qty*pv; direction=1 if side=='LONG' else -1; native=(ex-entry)*direction*qty*pv
        canon=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG→SL','AMBIG->SL') else (native/risk if risk else 0.0)); eq_before=eq; eq += canon*risk; err=native-t['native_pnl']; sqerr+=err*err; compared+=1
        rows.append({'n':t['n'],'entry_time':t['entry_time'],'qty':qty,'risk':risk,'eq_before':eq_before,'canon_r':canon,'exit_reason':reason,'calc_native_pnl':native,'tv_native_pnl':t['native_pnl'],'entry':entry,'stop':stop,'exit':ex,'pnl_error':err})
        if abs(err)>0.02: diffs.append({'trade':t['n'],'field':'native_pnl','tv':t['native_pnl'],'calc':native,'qty':qty,'step':step,'entry':entry,'exit':ex,'reason':reason})
        if abs(entry-t['entry'])>meta['mintick']*0.51: diffs.append({'trade':t['n'],'field':'entry_price','tv':t['entry'],'py':entry})
        if abs(ex-t['exit'])>meta['mintick']*0.51: diffs.append({'trade':t['n'],'field':'exit_price','tv':t['exit'],'py':ex})
    return {'step':step,'rows':rows,'diffs':diffs,'rmse_native_pnl':math.sqrt(sqerr/max(compared,1)),'final_canonical_equity':eq,'compared':compared}

def main():
    result={'symbols':{},'exact':True}
    for sym in SYMS:
        tvj=json.load(open(f'/tmp/tv-runtime-{sym}.json')); meta=parse_meta(tvj['metaFrames'],sym); tv=[parse_tv_row(r) for r in tvj['rows']]; py=run_engine(sym)
        sims=[simulate(tv,py,meta,s) for s in STEP_CANDIDATES]; sims.sort(key=lambda x:(len(x['diffs']),x['rmse_native_pnl'])); best=sims[0]; meta['inferred_mincontract']=best['step']; exact=not best['diffs']
        result['symbols'][sym]={'meta':meta,'tv_rows':len(tv),'engine_rows':len(py),'candidate_scores':[{'step':x['step'],'diffs':len(x['diffs']),'rmse_native_pnl':x['rmse_native_pnl']} for x in sims],'rows':best['rows'],'diffs':best['diffs'],'exact_native_accounting':exact,'final_canonical_equity':best['final_canonical_equity']}; result['exact'] &= exact
        print(json.dumps({'symbol':sym,'meta':meta,'tv_rows':len(tv),'engine_rows':len(py),'candidate_scores':result['symbols'][sym]['candidate_scores'],'exact_native_accounting':exact,'first_divergence':best['diffs'][0] if best['diffs'] else None,'final_canonical_equity':best['final_canonical_equity']},indent=2))
    Path('/tmp/wr-runtime-accounting-result.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['exact']: sys.exit(7)
if __name__=='__main__': main()
