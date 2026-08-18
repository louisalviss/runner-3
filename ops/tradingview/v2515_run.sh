#!/usr/bin/env bash
set -euo pipefail
echo "::add-mask::$AUTOMATION_KEY"
git fetch --no-tags --depth=1 origin d2b7b8febb4735b06c45638447df1eb70cfd3bf3
git show d2b7b8febb4735b06c45638447df1eb70cfd3bf3:ops/tradingview/wr-window-report.pine.aes >/tmp/wr.aes
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:AUTOMATION_KEY -in /tmp/wr.aes -out /tmp/wr2513.pine
test "$(sha256sum /tmp/wr2513.pine|awk '{print $1}')" = 9156e8c49b9a5e36007620f3e17fcab26c06714a3e32a252be52437ae23d6026
curl -fL "$VERIFIER_URL" -o /tmp/reference_verify.py
python3 ops/tradingview/v2515_builder.py | tee /tmp/build.log
python3 -m py_compile /tmp/reference_verify_v2.5.15.py
mkdir -p /tmp/pyproof
case1(){
  sym="$1"; s="$2"; e="$3"; tag="$4"; step=1; [ "$sym" = BNBUSDT ] && step=0.01
  rm -rf wave-rider-verify/output
  WR_SYMBOL="$sym" WR_TF=5 WR_QTY_STEP="$step" WR_STATE_START='2026-07-28T00:00:00+07:00' WR_REPORT_START="$s" WR_REPORT_END="$e" python3 /tmp/reference_verify_v2.5.15.py >"/tmp/pyproof/${tag}_${sym}.json"
  cp "wave-rider-verify/output/${sym}_5m_trades.csv" "/tmp/pyproof/${tag}_${sym}_trades.csv"
}
case1 BNBUSDT 2026-08-05T00:00:00+07:00 2026-08-10T00:00:00+07:00 W1
case1 TRXUSDT 2026-08-05T00:00:00+07:00 2026-08-10T00:00:00+07:00 W1
case1 BNBUSDT 2026-08-10T00:00:00+07:00 2026-08-16T00:00:00+07:00 W2
case1 TRXUSDT 2026-08-10T00:00:00+07:00 2026-08-16T00:00:00+07:00 W2
python3 - <<'PY' | tee /tmp/python-summary.txt
import glob,json,os
for f in sorted(glob.glob('/tmp/pyproof/*.json')):
 d=json.load(open(f));q=d['summary'][0];print(os.path.basename(f),f"TRADES={q['trades']}",f"TOTAL_R={q['total_r']}",f"WR={q['win_rate']}")
print('\nW2_TRX_TRADES')
print(open('/tmp/pyproof/W2_TRXUSDT_trades.csv').read())
PY
# Diagnostic snapshots around the two known TradingView W2 TRX entries.
WR_SYMBOL=TRXUSDT WR_TF=5 WR_QTY_STEP=1 WR_STATE_START='2026-07-28T00:00:00+07:00' WR_REPORT_START='2026-08-10T00:00:00+07:00' WR_REPORT_END='2026-08-16T00:00:00+07:00' python3 - <<'PY' > /tmp/pyproof/W2_TRX_condition_diag.json
import importlib.util,json
from datetime import datetime,timezone
spec=importlib.util.spec_from_file_location('wr','/tmp/reference_verify_v2.5.15.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
one,tick,missing=m.fetch_1m(); bars=m.agg(one,5)
state_ms=int(datetime.fromisoformat(m.STATE_START).timestamp()*1000); bars=[x for x in bars if x.ot>=state_ms]
ind,_,_=m.calc_ind(bars)
windows=[('T1','2026-08-10T12:30:00+00:00','2026-08-10T13:35:00+00:00'),('T2','2026-08-14T18:55:00+00:00','2026-08-14T20:00:00+00:00')]
out=[]
for tag,a,b in windows:
 lo=int(datetime.fromisoformat(a).timestamp()*1000); hi=int(datetime.fromisoformat(b).timestamp()*1000)
 for i,x in enumerate(bars):
  if not (lo<=x.ct<=hi): continue
  z=ind[i]; allowed,sexit=m.session_flags(x.ct,5*60000)
  lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
  sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
  nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
  ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
  out.append(dict(tag=tag,ot=m.iso(x.ot),ct=m.iso(x.ct),o=x.o,h=x.h,l=x.l,c=x.c,ema=z['ema'],ha=z['ha'],hb=z['hb'],ag=z['ag'],ar=z['ar'],chop_ok=z['chop_ok'],sra_ok=z['sra_ok'],res=z['res'],sup=z['sup'],allowed=allowed,sexit=sexit,nl=nl,ns=ns))
print(json.dumps(out,indent=2))
PY
# No TradingView re-run needed here: the existing oracle for W2 TRX is 2 trades / -2R.
