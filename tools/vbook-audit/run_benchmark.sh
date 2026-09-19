#!/usr/bin/env bash
set -euo pipefail
IDS="${VBOOK_IDS:-5,7,8,10,11,12,15,16,17,18}"
mkdir -p out
START=$(date +%s)
cp tools/vbook-audit/vbook171_meta.json /tmp/vbook171_meta.json
cp tools/vbook-audit/vbook_batch_plain.py /tmp/vbook_batch_plain.py
python3 tools/vbook-audit/vbook_prepare.py
node tools/vbook-audit/decrypt_vbook_plugins.js
python3 tools/vbook-audit/vbook_root_server.py >/tmp/vbook_root_server.log 2>&1 &
ROOT_PID=$!
trap "kill $ROOT_PID 2>/dev/null || true" EXIT
adb install -r vbook.apk
adb root || true
adb wait-for-device
sleep 2
adb shell am force-stop com.vbook.app || true
adb shell am startservice -n com.vbook.app/.test.ExtensionTestService
adb forward tcp:28080 tcp:8080
python3 - <<"PY"
import base64,json,requests,time
p={"language":"javascript","script":"function execute(x){return Response.success(\"pong \"+x)}","ip":"http://10.0.2.2:18807","root":"5","input":["gh"]}
h={"data":base64.b64encode(json.dumps(p).encode()).decode()}
for i in range(30):
    try:
        r=requests.get("http://127.0.0.1:28080/test",headers=h,timeout=5)
        j=r.json()
        if j.get("status")==0:
            print("VBOOK_ENGINE_READY",j.get("result"));break
    except Exception as e:
        pass
    time.sleep(2)
else:
    raise SystemExit("VBook engine did not become ready")
PY
VBOOK_BATCH=/tmp/vbook_batch_plain.py python3 tools/vbook-audit/vbook_e2e_final.py "$IDS"
cp /tmp/vbook-audit/e2e-final.json out/e2e-benchmark.json
# Generic/manual search probe remains useful for explicitly supplied queries.
python3 /tmp/vbook_batch_plain.py "$IDS" || true
cp /tmp/vbook-audit/plain-results.json out/search-probe.json 2>/dev/null || true
# Required search identity gate: discover a real item, get its canonical title,
# then prove NFC and NFD search find that same item and can traverse
# search -> detail -> TOC -> chapter. Accentless/fuzzy support is recorded as
# a warning dimension, not a hard requirement for every upstream site.
SEARCH_IDENTITY_STATUS=0
VBOOK_BATCH=/tmp/vbook_batch_plain.py VBOOK_E2E_RESULTS=out/e2e-benchmark.json \
  python3 tools/vbook-audit/vbook_search_identity.py "$IDS" || SEARCH_IDENTITY_STATUS=$?
END=$(date +%s)
python3 - "$START" "$END" "$IDS" <<"PY"
import json,sys,os
s,e,ids=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
rows=json.load(open("out/e2e-benchmark.json"))
out={"wall_seconds":e-s,"ids":ids,"count":len(rows),"classes":{},"search_identity_classes":{}}
for r in rows: out["classes"][r["class"]]=out["classes"].get(r["class"],0)+1
if os.path.exists("out/search-identity.json"):
    for r in json.load(open("out/search-identity.json")):
        c=r.get("class","UNKNOWN"); out["search_identity_classes"][c]=out["search_identity_classes"].get(c,0)+1
json.dump(out,open("out/benchmark-summary.json","w"),indent=2,ensure_ascii=False)
print(json.dumps(out,ensure_ascii=False))
PY
exit "$SEARCH_IDENTITY_STATUS"
