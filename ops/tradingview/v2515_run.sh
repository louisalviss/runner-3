#!/usr/bin/env bash
set -euo pipefail
echo "::add-mask::$AUTOMATION_KEY"
git fetch --no-tags --depth=1 origin d2b7b8febb4735b06c45638447df1eb70cfd3bf3
git show d2b7b8febb4735b06c45638447df1eb70cfd3bf3:ops/tradingview/wr-window-report.pine.aes >/tmp/wr.aes
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:AUTOMATION_KEY -in /tmp/wr.aes -out /tmp/wr2513.pine
test "$(sha256sum /tmp/wr2513.pine|awk '{print $1}')" = 9156e8c49b9a5e36007620f3e17fcab26c06714a3e32a252be52437ae23d6026
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:AUTOMATION_KEY -in ops/tradingview/session-state.json.aes -out /tmp/tv-state.json
curl -fL "$VERIFIER_URL" -o /tmp/reference_verify.py
python3 ops/tradingview/v2515_builder.py | tee /tmp/build.log
python3 -m py_compile /tmp/reference_verify_v2.5.15.py
mkdir -p /tmp/pyproof
case1(){ sym="$1"; s="$2"; e="$3"; tag="$4"; rm -rf wave-rider-verify/output; WR_SYMBOL="$sym" WR_TF=5 WR_QTY_STEP=1 WR_STATE_START='2026-07-28T00:00:00+07:00' WR_REPORT_START="$s" WR_REPORT_END="$e" python3 /tmp/reference_verify_v2.5.15.py >"/tmp/pyproof/${tag}_${sym}.json"; }
case1 BNBUSDT 2026-08-05T00:00:00+07:00 2026-08-10T00:00:00+07:00 W1
case1 TRXUSDT 2026-08-05T00:00:00+07:00 2026-08-10T00:00:00+07:00 W1
case1 BNBUSDT 2026-08-10T00:00:00+07:00 2026-08-16T00:00:00+07:00 W2
case1 TRXUSDT 2026-08-10T00:00:00+07:00 2026-08-16T00:00:00+07:00 W2
python3 - <<'PY' | tee /tmp/python-summary.txt
import glob,json,os
for f in sorted(glob.glob('/tmp/pyproof/*.json')):
 d=json.load(open(f)); q=d['summary'][0]; print(os.path.basename(f),f"TRADES={q['trades']}",f"TOTAL_R={q['total_r']}",f"WR={q['win_rate']}")
PY
npm install --no-save playwright-core@1.58.2 >/dev/null
node ops/tradingview/v2515_tv.js | tee /tmp/tv.log
