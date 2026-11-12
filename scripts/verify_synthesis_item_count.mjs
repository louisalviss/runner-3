import assert from "node:assert/strict";
import {readSynthesisItemCount} from "../cloudflare/runner3-core/src/content-synthesis-item-count.js";

function makeDb(rowids = []) {
  const state={rowids:[...rowids],snapshot:null,calls:[],writes:0,race:false,rejectWrites:false};
  const db={prepare(sql) {
    state.calls.push(sql.trim());
    return {args:[],bind(...args){this.args=args;return this;},
      async first() {
        if (sql.includes("SELECT detail FROM workflow_state WHERE source=?"))
          return state.snapshot?{detail:state.snapshot}:null;
        if (sql.includes("SELECT COALESCE(MAX(rowid),0)"))
          return {max_rowid:Math.max(0,...state.rowids)};
        if (sql.includes("SELECT COUNT(*) AS n FROM content_items WHERE rowid>?")) {
          const [lo,hi]=this.args;
          return {n:state.rowids.filter(id=>id>lo&&id<=hi).length};
        }
        if (sql.includes("SELECT COUNT(*) AS n FROM content_items")) {
          const n=state.rowids.length;
          if (state.race) {state.race=false;state.rowids.push(Math.max(0,...state.rowids)+1);}
          return {n};
        }
        throw new Error("unknown SELECT:"+sql);
      },
      async run() {
        assert(sql.includes("INSERT INTO workflow_state"));
        if(state.rejectWrites)throw Error("read-only degrade");
        const value=JSON.parse(this.args[1]);
        let old=null;
        try { old=state.snapshot?JSON.parse(state.snapshot):null; } catch {}
        if(!old||value.date_utc>old.date_utc
           ||value.date_utc===old.date_utc&&value.max_rowid>=old.max_rowid) {
          state.snapshot=JSON.stringify(value);state.writes++;
        }
        return {meta:{changes:1}};
      },
    };
  }};
  return {db,state};
}
function n(s,part){return s.calls.filter(q=>q.includes(part)).length;}
const time=new Date("2026-11-13T12:00:00Z");
const a=makeDb([1,2,4,8]);
assert.equal(await readSynthesisItemCount(a.db,{now:time}),4);
assert.equal(a.state.writes,1);
assert.equal(n(a.state,"SELECT COUNT(*) AS n FROM content_items"),1);
assert.equal(await readSynthesisItemCount(a.db,{now:time}),4);
assert.equal(a.state.writes,1);
assert.equal(n(a.state,"SELECT COUNT(*) AS n FROM content_items"),1);

a.state.rowids.push(10,12);
assert.equal(await readSynthesisItemCount(a.db,{now:time}),6);
assert.equal(a.state.writes,2);
assert.equal(n(a.state,"WHERE rowid>?"),1);
assert.equal(n(a.state,"SELECT COUNT(*) AS n FROM content_items"),2);
assert.equal(JSON.parse(a.state.snapshot).max_rowid,12);

// Existing ingest never deletes; if direct administrative repair does,
// a new UTC-day full scan restores the canonical count.
a.state.rowids.splice(0,1);
assert.equal(await readSynthesisItemCount(a.db,{now:new Date("2026-11-14T00:01:00Z")}),5);
assert.equal(JSON.parse(a.state.snapshot).date_utc,"2026-11-14");
assert.equal(JSON.parse(a.state.snapshot).item_count,5);

a.state.snapshot="{bad";
assert.equal(await readSynthesisItemCount(a.db,{now:new Date("2026-11-14T00:02:00Z")}),5);
assert.equal(JSON.parse(a.state.snapshot).item_count,5);

// A concurrent insertion while rebuilding invalidates snapshot commit.
const race=makeDb([1,3]);race.state.race=true;
assert.equal(await readSynthesisItemCount(race.db,{now:time}),2);
assert.equal(race.state.snapshot,null);
assert.equal(await readSynthesisItemCount(race.db,{now:time}),3);

// If derived cache writes fail, user gets fresh authoritative count instead.
const fail=makeDb([1,2,3]);fail.state.rejectWrites=true;
const warn=console.warn;console.warn=()=>{};
try{assert.equal(await readSynthesisItemCount(fail.db,{now:time}),3);}
finally{console.warn=warn;}
assert.equal(fail.state.writes,0);

// Sparse rowid sequences are valid: count only newly inserted rows, not gaps.
const missing=makeDb([1,2]);
await readSynthesisItemCount(missing.db,{now:time});
missing.state.rowids=[1,2,4];
assert.equal(await readSynthesisItemCount(missing.db,{now:time}),3);
console.log("SYNTHESIS_ITEM_COUNT_PASS (stable, append, day repair, corrupt, race, write failure)");
