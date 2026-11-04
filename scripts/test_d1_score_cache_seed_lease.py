import sqlite3
from pathlib import Path

text = Path("cloudflare/runner3-core/src/content-personalization.js").read_text()
part = text.split("async function acquireScoreCacheSeedLease(",1)[1].split("async function assertScoreCacheSeedBounds(",1)[0]
sql = part.split("env.DB.prepare(`",1)[1].split("`).bind(",1)[0]
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE workflow_state(source TEXT PRIMARY KEY,status TEXT,run_id TEXT,detail TEXT,updated_at TEXT)")
key = "content-intelligence-profile"
clock = "content-intelligence-profile-last-recompute"
original = '{"model":"personal-v4"}'
args = ["seed-token",'{"reason":"score_cache_seed"}',key,original,clock,clock,"-21600 seconds"]
assert sql.count("?") == len(args), (sql.count("?"),len(args))
def trial(state,age,want,stored=original,expected=original):
    db.execute("DELETE FROM workflow_state")
    db.execute("INSERT INTO workflow_state VALUES(?,?,NULL,?,datetime('now','-1 hour'))",(key,state,stored))
    if age is not None:
        db.execute("INSERT INTO workflow_state VALUES(?,'clean',NULL,'{}',datetime('now',?))",(clock,age))
    before = db.total_changes
    db.execute(sql,[args[0],args[1],key,expected,clock,clock,args[-1]])
    got = db.total_changes-before
    assert got == want, (state,age,stored,expected,got,want)
trial("clean","-7 hours",1)
trial("clean","-1 hour",0)
trial("clean",None,1)
trial("dirty","-7 hours",0)
trial("recomputing","-7 hours",0)
trial("clean","-7 hours",0,stored='{"model":"other"}')
trial("clean","-7 hours",1,stored=None,expected=None)
db.execute("DELETE FROM workflow_state")
db.execute("INSERT INTO workflow_state VALUES(?,'clean',NULL,?,datetime('now','-1 hour'))",(key,original))
db.execute("INSERT INTO workflow_state VALUES(?,'clean',NULL,'{}',datetime('now','-7 hours'))",(clock,))
db.execute(sql,args)
before = db.total_changes
db.execute(sql,args)
assert db.total_changes == before, "racing seed acquired a second time"
print("D1_SCORE_CACHE_SEED_LEASE_PASS 8 cases")
