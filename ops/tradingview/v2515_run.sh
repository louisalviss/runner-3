#!/usr/bin/env bash
set -euo pipefail
cp ops/tradingview/reference_verify_v2515_tmp.py /tmp/reference_verify_v2.5.15.py
python3 - <<'PY'
from pathlib import Path
import hashlib
p=Path('/tmp/reference_verify_v2.5.15.py').read_text()
old="fill=(pending.d==1 and x.h>=pending.e) or (pending.d==-1 and x.l<=pending.e)"
new="eps=tick*1e-6; fill=(pending.d==1 and x.h+eps>=pending.e) or (pending.d==-1 and x.l-eps<=pending.e)"
assert p.count(old)==1
p=p.replace(old,new,1)
Path('/tmp/reference_verify_v2.5.15.py').write_text(p)
print('VERIFIER_TICK_TOL_SHA256='+hashlib.sha256(p.encode()).hexdigest())
PY
mkdir -p /tmp/pyproof
case1(){ sym="$1"; s="$2"; e="$3"; tag="$4"; step=1; [ "$sym" = BNBUSDT ] && step=0.01; rm -rf wave-rider-verify/output; WR_SYMBOL="$sym" WR_TF=5 WR_QTY_STEP="$step" WR_STATE_START='2026-07-28T00:00:00+07:00' WR_REPORT_START="$s" WR_REPORT_END="$e" python3 /tmp/reference_verify_v2.5.15.py >"/tmp/pyproof/${tag}_${sym}.json"; cp "wave-rider-verify/output/${sym}_5m_trades.csv" "/tmp/pyproof/${tag}_${sym}_trades.csv"; }
case1 BNBUSDT 2026-08-05T00:00:00+07:00 2026-08-10T00:00:00+07:00 W1
case1 TRXUSDT 2026-08-05T00:00:00+07:00 2026-08-10T00:00:00+07:00 W1
case1 BNBUSDT 2026-08-10T00:00:00+07:00 2026-08-16T00:00:00+07:00 W2
case1 TRXUSDT 2026-08-10T00:00:00+07:00 2026-08-16T00:00:00+07:00 W2
python3 - <<'PY' | tee /tmp/python-summary.txt
import glob,json,os,math
expect={
'W1_BNBUSDT.json':(5,3.420895522388211),
'W1_TRXUSDT.json':(4,2.6),
'W2_BNBUSDT.json':(3,6.9),
'W2_TRXUSDT.json':(2,-2.0),
}
allpass=True
for f in sorted(glob.glob('/tmp/pyproof/*.json')):
 d=json.load(open(f));q=d['summary'][0]; name=os.path.basename(f); exp=expect[name]; ok=q['trades']==exp[0] and math.isclose(q['total_r'],exp[1],abs_tol=1e-9); allpass &= ok
 print(name,f"TRADES={q['trades']}",f"TOTAL_R={q['total_r']}",f"EXPECTED={exp}",f"PASS={ok}")
print('PARITY_4_WINDOWS='+('PASS' if allpass else 'FAIL'))
print('\nW2_TRX_TRADES')
print(open('/tmp/pyproof/W2_TRXUSDT_trades.csv').read())
if not allpass: raise SystemExit(9)
PY
sha256sum /tmp/reference_verify_v2.5.15.py > /tmp/pyproof/SHA256.txt
