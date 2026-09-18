#!/usr/bin/env bash
set -euo pipefail
mkdir -p out
cp tools/vbook-audit/vbook171_meta.json /tmp/vbook171_meta.json
cp tools/vbook-audit/vbook_batch_plain.py /tmp/vbook_batch_plain.py
python3 tools/vbook-audit/vbook_prepare.py
node tools/vbook-audit/decrypt_vbook_plugins.js
python3 tools/vbook-audit/vbook_root_server.py >/tmp/vbook_root_server.log 2>&1 &
ROOT_PID=
trap "kill  2>/dev/null || true" EXIT
adb install -r vbook.apk
adb root || true
adb wait-for-device
sleep 2
adb shell am force-stop com.vbook.app || true
adb shell am startservice -n com.vbook.app/.test.ExtensionTestService
adb forward tcp:28080 tcp:8080
python3 - <<"PY"
import base64,json,requests,time
p={"language":"javascript","script":"function execute(x){return Response.success('pong '+x)}","ip":"http://10.0.2.2:18807","root":"5","input":["special"]}
h={"data":base64.b64encode(json.dumps(p).encode()).decode()}
for i in range(30):
    try:
        r=requests.get("http://127.0.0.1:28080/test",headers=h,timeout=5); j=r.json()
        if j.get("status")==0: print("VBOOK_ENGINE_READY",j.get("result")); break
    except Exception: pass
    time.sleep(2)
else: raise SystemExit("VBook engine did not become ready")
PY
VBOOK_BATCH=/tmp/vbook_batch_plain.py python3 tools/vbook-audit/vbook_special_audit.py
cp /tmp/vbook-audit/special-results.json out/special-results.json
