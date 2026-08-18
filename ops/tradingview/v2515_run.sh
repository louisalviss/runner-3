#!/usr/bin/env bash
set -euo pipefail
cp ops/tradingview/reference_verify_v2515_tmp.py /tmp/reference_verify_v2.5.15.py
export WR_SYMBOL=TRXUSDT WR_TF=5 WR_QTY_STEP=1 WR_STATE_START='2026-07-28T00:00:00+07:00' WR_REPORT_START='2026-08-10T00:00:00+07:00' WR_REPORT_END='2026-08-16T00:00:00+07:00'
mkdir -p /tmp/pyproof
python3 - <<'PY' | tee /tmp/python-summary.txt
import importlib.util,sys,json
from datetime import datetime
spec=importlib.util.spec_from_file_location('wrdiag','/tmp/reference_verify_v2.5.15.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
one,tick,missing=m.fetch_1m(); bars=m.agg(one,5)
st=int(datetime.fromisoformat(m.REPORT_START).timestamp()*1000); en=int(datetime.fromisoformat(m.REPORT_END).timestamp()*1000)
tr,s=m.run(5,bars,tick,st,en)
print('SUMMARY',json.dumps(s,sort_keys=True))
print('TRADES')
for t in tr: print(json.dumps(t.__dict__,sort_keys=True))
state_ms=int(datetime.fromisoformat(m.STATE_START).timestamp()*1000); bars=[x for x in bars if x.ot>=state_ms]; ind,pht,plt=m.calc_ind(bars)
lo=int(datetime.fromisoformat('2026-08-14T18:30:00+00:00').timestamp()*1000); hi=int(datetime.fromisoformat('2026-08-14T20:10:00+00:00').timestamp()*1000)
rows=[]
for i,x in enumerate(bars):
    if not (lo<=x.ct<=hi): continue
    z=ind[i]; allowed,sexit=m.session_flags(x.ct,5*60000)
    lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
    sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
    nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
    ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
    row=dict(ot=m.iso(x.ot),ct=m.iso(x.ct),o=x.o,h=x.h,l=x.l,c=x.c,ema=z['ema'],ha=z['ha'],hb=z['hb'],ag=z['ag'],ar=z['ar'],chop_ok=z['chop_ok'],sra_ok=z['sra_ok'],res=z['res'],sup=z['sup'],allowed=allowed,sexit=sexit,longReady=lr,shortReady=sr,nl=nl,ns=ns)
    rows.append(row); print('BAR',json.dumps(row,sort_keys=True))
open('/tmp/pyproof/W2_TRX_condition_diag.json','w').write(json.dumps(rows,indent=2))
PY
sha256sum /tmp/reference_verify_v2.5.15.py > /tmp/pyproof/SHA256.txt
