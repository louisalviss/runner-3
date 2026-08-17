#!/usr/bin/env python3
from __future__ import annotations
import csv,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GOLDEN=ROOT/'golden/tv_5m_window_report_2026-07-27T17_2026-08-15T17.json'
ENGINE=ROOT/'reference_verify_parity.py'
START='2026-07-27'; END='2026-08-17'
RS=datetime.fromisoformat('2026-07-27T17:00:00+00:00')
RE=datetime.fromisoformat('2026-08-15T17:00:00+00:00')
INIT=100000.0

def dt(s): return datetime.fromisoformat(s.replace('Z','+00:00'))
def rounded_display(v,n=2): return round(v,n)

def verify(sym,exp):
    env=os.environ.copy();env.update(WR_SYMBOL=sym,WR_START=START,WR_END=END)
    subprocess.run([sys.executable,str(ENGINE)],env=env,check=True,stdout=subprocess.DEVNULL)
    with (ROOT/'output'/f'{sym}_5m_trades.csv').open(newline='') as f: rows=list(csv.DictReader(f))
    eq=INIT; window=[]; w_eq=None; w_peak=None; maxdd=0.0; cur=maxls=0
    for r in rows:
        cr=float(r['canon_r']); risk=float(r['risk_cash']); sig=dt(r['signal_time'])
        eligible=RS<=sig<RE
        if eligible and w_eq is None:
            w_eq=eq; w_peak=eq
        if eligible:
            cash=cr*risk
            w_eq += cash; w_peak=max(w_peak,w_eq); maxdd=max(maxdd,100*(w_peak-w_eq)/w_peak)
            cur=cur+1 if cr<0 else 0; maxls=max(maxls,cur)
            window.append((r,cr,risk))
        eq += cr*risk
    trades=len(window); wins=sum(cr>0 for _,cr,_ in window); total=sum(cr for _,cr,_ in window); avg=total/trades
    gp=sum(max(cr*risk,0) for _,cr,risk in window); gl=sum(max(-cr*risk,0) for _,cr,risk in window); pf=gp/gl
    got={'trades':trades,'total_r':total,'win_rate_pct':100*wins/trades,'avg_r':avg,'profit_factor':pf,'max_closed_dd_pct':maxdd,'max_losing_streak':maxls}
    checks={
      'trades':got['trades']==exp['trades'],
      'total_r':round(got['total_r'],2)==round(exp['total_r'],2),
      'win_rate':round(got['win_rate_pct'],1)==round(exp['win_rate_pct'],1),
      'avg_r':round(got['avg_r'],2)==round(exp['avg_r'],2),
      'profit_factor':round(got['profit_factor'],2)==round(exp['profit_factor'],2),
      'max_dd':round(got['max_closed_dd_pct'],2)==round(exp['max_closed_dd_pct'],2),
      'max_losing_streak':got['max_losing_streak']==exp['max_losing_streak'],
    }
    return got,checks

def main():
    g=json.load(open(GOLDEN)); out={'exact_dashboard_parity':True,'symbols':{}}
    for sym,exp in g['symbols'].items():
        got,checks=verify(sym,exp); ok=all(checks.values()); out['exact_dashboard_parity'] &= ok
        out['symbols'][sym]={'got':got,'expected':{k:exp[k] for k in got},'checks':checks,'pass':ok}
        print(json.dumps({'symbol':sym,'pass':ok,'got':got,'checks':checks},indent=2))
    Path('/tmp/wr-tv-window-golden-result.json').write_text(json.dumps(out,indent=2)+'\n')
    if not out['exact_dashboard_parity']: sys.exit(9)
if __name__=='__main__': main()
