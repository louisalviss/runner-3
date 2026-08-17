#!/usr/bin/env python3
"""Production Wave Rider v2.5.13 parity runner.

Execution dataset and report window are independent:
- WR_DATA_START / WR_DATA_END: UTC calendar dates fetched/executed.
- WR_REPORT_START / WR_REPORT_END: ISO-8601 UTC timestamps; end is exclusive.

The frozen historical reference remains untouched. All repaired semantics live in
reference_verify_parity.py and this runner only supplies the correct boundaries.
"""
from __future__ import annotations

import csv,json,os,sys
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path


def ms(s: str) -> int:
    d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
    return int(d.timestamp()*1000)


def main():
    symbol=os.getenv('WR_SYMBOL','BNBUSDT')
    data_start=os.getenv('WR_DATA_START')
    data_end=os.getenv('WR_DATA_END')
    report_start=os.getenv('WR_REPORT_START')
    report_end=os.getenv('WR_REPORT_END')
    tf=int(os.getenv('WR_TF','5'))
    if not all((data_start,data_end,report_start,report_end)):
        raise SystemExit('Require WR_DATA_START, WR_DATA_END, WR_REPORT_START, WR_REPORT_END')

    # reference_verify_parity resolves symbol/data metadata at import time.
    os.environ['WR_SYMBOL']=symbol
    os.environ['WR_START']=data_start
    os.environ['WR_END']=data_end
    os.environ['WR_DATA_START']=data_start
    os.environ['WR_DATA_END']=data_end

    import reference_verify_parity as parity
    r=parity.ref

    one,tick,missing=r.fetch_1m()
    bars=r.agg(one,tf)
    rs=ms(report_start)
    re_excl=ms(report_end)
    if re_excl<=rs: raise SystemExit('WR_REPORT_END must be after WR_REPORT_START')
    trades,summary=r.run(tf,bars,tick,rs,re_excl-1)

    out=Path(os.getenv('WR_OUT','wave-rider-verify/output-parity'))
    out.mkdir(parents=True,exist_ok=True)
    with (out/f'{symbol}_{tf}m_trades.csv').open('w',newline='') as f:
        fields=list(r.Trade.__dataclass_fields__)
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for t in trades:w.writerow(asdict(t))

    result={
        'strategy':'Wave Rider v2.5.13 TradingView parity runner',
        'symbol':symbol,'tf':tf,'data_start':data_start,'data_end':data_end,
        'report_start':report_start,'report_end_exclusive':report_end,
        'tick':tick,'missing':missing,'summary':summary,
    }
    (out/f'{symbol}_{tf}m_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
