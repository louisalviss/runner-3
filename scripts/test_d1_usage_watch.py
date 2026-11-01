#!/usr/bin/env python3
"""Offline tests for D1 account usage watch read/write gates."""
import contextlib, io, json, os, tempfile, textwrap, urllib.request
from pathlib import Path

yaml=Path(".github/workflows/runner3-d1-usage-watch.yml").read_text()
script=textwrap.dedent(yaml.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0])
assert "readFreeTierHardLimit" in script
assert "READ PACE WARN" in script
class Reply:
    status=200
    def __init__(self, body): self.body=body
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.body).encode()

def trial(reads,writes):
    original=urllib.request.urlopen
    def fake(req,timeout=30):
        if req.full_url.endswith("/graphql"):
            return Reply({"data":{"viewer":{"accounts":[{
                "d1AnalyticsAdaptiveGroups":[{"dimensions":{"databaseId":"db1"},"sum":{
                    "rowsRead":reads,"rowsWritten":writes,"readQueries":25,"writeQueries":25
                }}]}]}}})
        return Reply({"result":[{"uuid":"db1","name":"test-content-intelligence"}]})
    values={
        "CF_TOKEN":"mock","CF_ACCOUNT":"mock","WARN_ROWS":"50000",
        "ALERT_ROWS":"70000","EMERGENCY_ROWS":"90000",
        "WARN_READ_ROWS":"3000000","ALERT_READ_ROWS":"3800000",
        "EMERGENCY_READ_ROWS":"4500000"
    }
    prior={k:os.environ.get(k) for k in values}
    os.environ.update(values)
    output=io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["GITHUB_STEP_SUMMARY"]=tmp+"/summary"
        urllib.request.urlopen=fake
        try:
            with contextlib.redirect_stdout(output):
                try: exec(compile(script,"watch.py","exec"),{"__name__":"__main__"})
                except SystemExit as e: code=int(e.code)
                else: code=0
        finally:
            urllib.request.urlopen=original
            os.environ.pop("GITHUB_STEP_SUMMARY",None)
            for k,v in prior.items():
                if v is None: os.environ.pop(k,None)
                else: os.environ[k]=v
        summary=Path(tmp,"summary").read_text()
    return code,output.getvalue(),summary

code,out,summary=trial(2000000,10000)
assert code==0 and "PASS" in out and "Rows read" in summary
code,out,_=trial(3200000,10000)
assert code==0 and "READ WARN" in out
code,out,_=trial(3900000,10000)
assert code==1 and "READ ALERT" in out
code,out,_=trial(4600000,10000)
assert code==2 and "READ EMERGENCY" in out
code,out,_=trial(2000000,91000)
assert code==2 and "D1 ACCOUNT EMERGENCY" in out
print("D1_USAGE_WATCH_PASS 5 cases")
