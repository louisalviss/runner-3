// Synthetic-only contract; no Cloudflare token, network, or Worker deployment.
import assert from "node:assert/strict";
import { fencedContentEnvForPrototype, readOnlyD1Facade } from
  "../cloudflare_d1_content_write_fence_prototype.mjs";

let passes = 0;
function test(name, fn) {
  fn();
  passes++;
  process.stdout.write("PASS " + name + "\n");
}
function fakeDb() {
  const executed = [];
  function stmt(sql, binds = []) {
    return {
      bind(...args) { return stmt(sql, args); },
      first() { executed.push(["first",sql,binds]); return {ok:1}; },
      all() { executed.push(["all",sql,binds]); return {results:[{ok:1}]}; },
      raw() { executed.push(["raw",sql,binds]); return [[1]]; },
      run() { executed.push(["run",sql,binds]); return {success:true}; }
    };
  }
  return {
    executed,
    prepare(sql) { executed.push(["prepare",sql]); return stmt(sql); },
    batch(stmts) {
      executed.push(["batch",stmts.length]);
      return stmts.map(x => x.all());
    },
    withSession() { return this; },
    exec(sql) { executed.push(["exec",sql]); return {success:true}; },
    dump() { executed.push(["dump"]); return new Uint8Array(); }
  };
}

test("reads and binds preserved", () => {
  const raw=fakeDb(), fenced=readOnlyD1Facade(raw);
  assert.deepEqual(fenced.prepare(" \n SELECT * FROM content_features WHERE item_id=?").bind("a").first(),{ok:1});
  assert.deepEqual(fenced.prepare("SELECT 1").all(),{results:[{ok:1}]});
  assert.deepEqual(fenced.prepare("SELECT 1").raw(),[[1]]);
  assert.equal(fenced.prepare("SELECT 1").run().success,true);
  assert.equal(raw.executed.filter(x=>x[0]==="prepare").length,4);
});

test("insert/update/delete and CTE statements fail before raw prepare", () => {
  const raw=fakeDb(), fenced=readOnlyD1Facade(raw);
  for (const sql of [
    "INSERT INTO content_features VALUES(1)",
    "UPDATE content_features SET weight=1",
    "DELETE FROM content_features",
    "REPLACE INTO content_features VALUES(1)",
    "CREATE TRIGGER t AFTER INSERT ON x BEGIN SELECT 1; END",
    "DROP TABLE content_items",
    "PRAGMA journal_mode = WAL",
    "WITH x AS (SELECT 1) DELETE FROM content_features",
    "SELECT 1; DELETE FROM content_features",
    "SELECT 1 -- injected",
    "SELECT /* comment */ 1",
    ""
  ]) {
    assert.throws(()=>fenced.prepare(sql), /D1_CONTENT_WRITE_FENCE_BLOCKED/);
  }
  assert.equal(raw.executed.length,0);
});

test("read-only batch rejects raw and unknown statements", () => {
  const raw=fakeDb(), fenced=readOnlyD1Facade(raw);
  assert.deepEqual(fenced.batch([fenced.prepare("SELECT 1"),fenced.prepare("SELECT 2").bind("b")]).map(x=>x.success||false),[false,false]);
  assert.equal(raw.executed.filter(x=>x[0]==="batch").length,1);
  assert.throws(()=>fenced.batch([raw.prepare("INSERT INTO x VALUES(1)")]),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
  assert.throws(()=>fenced.batch([{}]),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
  assert.throws(()=>fenced.batch(Array.from({length:251},()=>fenced.prepare("SELECT 1"))),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
});

test("cross-binding statement reuse is blocked", () => {
  const db1=fakeDb(), db2=fakeDb();
  const left=readOnlyD1Facade(db1), right=readOnlyD1Facade(db2);
  const foreign=right.prepare("SELECT 1");
  assert.throws(()=>left.batch([foreign]),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
  assert.equal(db1.executed.length,0);
});

test("exec/dump cannot be used through fenced interface", () => {
  const db=fakeDb(), fenced=readOnlyD1Facade(db);
  assert.equal(typeof fenced.exec,"undefined");
  assert.equal(typeof fenced.dump,"undefined");
  assert.throws(()=>fenced.exec("DELETE FROM x"),TypeError);
  assert.throws(()=>fenced.dump(),TypeError);
  assert.equal(db.executed.length,0);
});

test("session remains fenced", () => {
  const db=fakeDb(), fenced=readOnlyD1Facade(db).withSession("first-primary");
  assert.deepEqual(fenced.prepare("SELECT 1").first(),{ok:1});
  assert.throws(()=>fenced.prepare("DELETE FROM user_content_events"),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
});

test("Content DB alias wrapped; RSS DB and unrelated DB untouched", () => {
  const content=fakeDb(), rss=fakeDb();
  const original={ DB:rss, RSS_DB:rss, CONTENT_DB:content, ARTIFACTS:{ok:true} };
  const env=fencedContentEnvForPrototype(original);
  assert.equal(env.DB,rss);
  assert.equal(env.RSS_DB,rss);
  assert.equal(env.ARTIFACTS,original.ARTIFACTS);
  assert.notEqual(env.CONTENT_DB,content);
  assert.equal(original.CONTENT_DB,content);
  assert.throws(()=>env.CONTENT_DB.prepare("INSERT INTO content_items VALUES (1)"),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
  const alias=fencedContentEnvForPrototype({DB:content,CONTENT_DB:content});
  assert.equal(alias.DB,alias.CONTENT_DB);
  assert.throws(()=>alias.DB.prepare("DELETE FROM user_content_events"),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
});

test("missing Content binding fails closed", () => {
  assert.throws(()=>fencedContentEnvForPrototype({DB:fakeDb()}),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
  assert.throws(()=>readOnlyD1Facade({}),/D1_CONTENT_WRITE_FENCE_BLOCKED/);
});

test("no raw bindings exposed through facade", () => {
  const content=fakeDb(), fenced=fencedContentEnvForPrototype({CONTENT_DB:content}).CONTENT_DB;
  assert.equal(Object.isFrozen(fenced),true);
  assert.equal(fenced.inner,undefined);
  assert.equal(fenced._db,undefined);
  assert.equal(fenced.prepare("SELECT 1").inner,undefined);
  assert.equal(Object.getOwnPropertySymbols(fenced.prepare("SELECT 1")).length,0);
});

process.stdout.write("D1_CONTENT_FENCE_OFFLINE_TESTS " + passes + " PASS NO_NETWORK NO_DEPLOY\n");
