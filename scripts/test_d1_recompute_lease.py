import re, sqlite3
from pathlib import Path

text=Path("cloudflare/runner3-core/src/content-personalization.js").read_text()
part=text.split("async function acquireRecomputeLease(",1)[1].split("async function finishRecomputeLease(",1)[0]
sql=part.split("env.DB.prepare(`",1)[1].split("`).bind(",1)[0]
db=sqlite3.connect(":memory:")
db.execute("CREATE TABLE workflow_state(source TEXT PRIMARY KEY,status TEXT,run_id TEXT,detail TEXT,updated_at TEXT)")
key="content-intelligence-profile"; clock="content-intelligence-profile-last-recompute"
args=["run","{}",key,"-3600 seconds",clock,clock,"-21600 seconds","-900 seconds",clock,clock,"-21600 seconds"]
assert sql.count("?")==len(args), (sql.count("?"),len(args))
def trial(state,age,expected,detail="{}",last_age="-1 hour"):
    db.execute("DELETE FROM workflow_state")
    db.execute("INSERT INTO workflow_state VALUES(?,?,NULL,?,datetime('now',?))",(key,state,detail,last_age))
    if age:
        db.execute("INSERT INTO workflow_state VALUES(?,'clean',NULL,'{}',datetime('now',?))",(clock,age))
    before=db.total_changes
    db.execute(sql,args)
    assert db.total_changes-before==expected,(state,age,expected)
trial("dirty","-2 hours",0)
trial("dirty","-7 hours",1)
trial("dirty",None,1)
trial("clean","-8 hours",0)
trial("dirty","-8 hours",0,'{"retryable_error":"retry"}',"-10 minutes")
trial("dirty","-8 hours",1,'{"retryable_error":"retry"}',"-2 hours")
trial("recomputing","-2 hours",0,"{}","-20 minutes")
trial("recomputing","-7 hours",1,"{}","-20 minutes")
print("D1_RECOMPUTE_LEASE_PASS 8 cases")
