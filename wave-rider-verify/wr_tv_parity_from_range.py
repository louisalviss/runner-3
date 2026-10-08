#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys
from datetime import timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base_tv_parity',HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)

ROOT=HERE/'output'/'tv-range'
OUT=HERE/'output'/'tv-parity-range-client';OUT.mkdir(parents=True,exist_ok=True)
FILES={
 'OANDA:EURUSD':'OANDA-EURUSD.json',
 'OANDA:USDJPY':'OANDA-USDJPY.json',
 'OANDA:XAUUSD':'OANDA-XAUUSD.json',
 'ICMARKETS:US500':'ICMARKETS-US500.json',
 'NASDAQ:AAPL':'NASDAQ-AAPL.json',
}

def parse_history(h):
    bars=[]
    for x in h:
        # @ch99q/twc history items are arrays [ts,o,h,l,c,...].
        if isinstance(x,dict):
            v=x.get('v') or x.get('value') or x.get('data')
            if v is None and all(k in x for k in ('time','open','high','low','close')):
                v=[x['time'],x['open'],x['high'],x['low'],x['close']]
        else:v=x
        if not isinstance(v,(list,tuple)) or len(v)<5:continue
        try:
            ts=int(float(v[0]));
            if ts>10_000_000_000:ts//=1000
            bars.append(base.Bar(ts*1000,ts*1000+base.TF_MS,float(v[1]),float(v[2]),float(v[3]),float(v[4])))
        except Exception:continue
    ded={b.ot:b for b in bars};return [ded[k] for k in sorted(ded)]

def main():
    ref=base.load_ref();summary=[];detail={}
    for sym,fn in FILES.items():
        obj=json.loads((ROOT/fn).read_text());bars=parse_history(obj.get('history',[]));info=obj.get('symbol') or {}
        exp=base.ORACLES[sym];runs=[]
        for days in (7,14,30,60,120):
            for anchor in ('start','end'):
                tr,m=base.run_case(ref,bars,info,base.START-timedelta(days=days),anchor,True)
                m.update({'warmup_days':days,'anchor':anchor,'delta_n':m.get('n',0)-exp[0],'delta_R':m.get('R',0)-exp[1]});runs.append(m)
        tr,m=base.run_case(ref,bars,info,base.START-timedelta(days=120),'start',False);m.update({'warmup_days':120,'anchor':'NO_SESSION','delta_n':m.get('n',0)-exp[0],'delta_R':m.get('R',0)-exp[1]});runs.append(m)
        best=min(runs,key=lambda z:(abs(z.get('delta_n',99)),abs(z.get('delta_R',999))))
        exact=[z for z in runs if z.get('delta_n')==0 and abs(z.get('delta_R',999))<0.015]
        detail[sym]={'expected':{'n':exp[0],'R':exp[1]},'bars':len(bars),'first':bars[0].ot if bars else None,'last':bars[-1].ot if bars else None,'best':best,'exact':exact,'runs':runs}
        summary.append({'symbol':sym,'expected':{'n':exp[0],'R':exp[1]},'bars':len(bars),'exact_matches':len(exact),'best':best})
        print('PARITY',sym,'bars',len(bars),'expected',exp,'best',best,'exact',len(exact),flush=True)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str));(OUT/'detail.json').write_text(json.dumps(detail,indent=2,default=str))
    print(json.dumps(summary,indent=2,default=str))
if __name__=='__main__':main()
