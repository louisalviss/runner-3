import assert from "node:assert/strict";
import { readSynthesisEventAggregate } from "../cloudflare/runner3-core/src/content-synthesis-event-aggregate.js";

function makeDb(events = []) {
  const state = {events:[...events], snapshot:null, calls:[], writes:0, rejectWrites:false, raceAfterFull:false};
  function full() {
    const by = new Map();
    for (const e of state.events) {
      const row = by.get(e.event_type) || {event_type:e.event_type,count:0,last_event_at:null};
      row.count++;
      if (e.event_at && (!row.last_event_at || e.event_at>row.last_event_at))
        row.last_event_at = e.event_at;
      by.set(e.event_type,row);
    }
    return [...by.values()].sort((a,b)=>b.count-a.count||a.event_type.localeCompare(b.event_type));
  }
  const db = {
    prepare(sql) {
      state.calls.push(sql.trim());
      const bound = {args:[],bind(...args){this.args=args;return this;},
        async first() {
          if (sql.includes("SELECT detail FROM workflow_state WHERE source=?"))
            return state.snapshot ? {detail:state.snapshot} : null;
          if (sql.includes("SELECT COALESCE(MAX(id),0) AS max_id"))
            return {max_id:Math.max(0,...state.events.map(e=>e.id))};
          throw new Error("Unexpected first query: "+sql);
        },
        async all() {
          if (sql.includes("SELECT id,event_type,event_at FROM user_content_events")) {
            const [from,to,cap]=this.args;
            return {results:state.events.filter(e=>e.id>from && e.id<=to)
              .sort((a,b)=>a.id-b.id).slice(0,cap)};
          }
          if (sql.includes("SELECT event_type,COUNT(*) AS count")) {
            const rows=full();
            if (state.raceAfterFull) {
              state.raceAfterFull=false;
              state.events.push({id:Math.max(0,...state.events.map(e=>e.id))+1,
                event_type:"shown",event_at:"2026-11-13 04:00:00"});
            }
            return {results:rows};
          }
          throw new Error("Unexpected all query: "+sql);
        },
        async run() {
          if (!sql.includes("INSERT INTO workflow_state(source,status,detail,updated_at)"))
            throw new Error("Unexpected write: "+sql);
          if (state.rejectWrites) throw new Error("quota_exhausted");
          const next=JSON.parse(this.args[1]);
          let curr=null;
          try { curr=state.snapshot?JSON.parse(state.snapshot):null; } catch {}
          if (!curr || curr.date_utc<next.date_utc
              || curr.date_utc===next.date_utc && curr.max_id<=next.max_id) {
            state.snapshot=JSON.stringify(next);
            state.writes++;
          }
          return {meta:{changes:1}};
        },
      };
      return bound;
    },
  };
  return {db,state};
}
function calls(s,term){return s.calls.filter(q=>q.includes(term)).length;}

const a=makeDb([
  {id:1,event_type:"shown",event_at:"2026-11-13 01:00:00"},
  {id:2,event_type:"liked",event_at:"2026-11-13 01:05:00"},
  {id:4,event_type:"shown",event_at:"2026-11-13 01:08:00"},
]);
const now=new Date("2026-11-13T02:00:00Z");
let r=await readSynthesisEventAggregate(a.db,{now});
assert.deepEqual(r,[
  {event_type:"shown",count:2,last_event_at:"2026-11-13 01:08:00"},
  {event_type:"liked",count:1,last_event_at:"2026-11-13 01:05:00"},
]);
assert.equal(a.state.writes,1);
assert.equal(calls(a.state,"SELECT event_type,COUNT(*)"),1);
r=await readSynthesisEventAggregate(a.db,{now});
assert.equal(calls(a.state,"SELECT event_type,COUNT(*)"),1);
assert.equal(calls(a.state,"SELECT id,event_type,event_at"),0);
assert.equal(a.state.writes,1);
a.state.events.push({id:7,event_type:"interest_saved",event_at:"2026-11-13 02:01:00"});
a.state.events.push({id:8,event_type:"shown",event_at:"2026-11-13 02:02:00"});
r=await readSynthesisEventAggregate(a.db,{now:new Date("2026-11-13T02:03:00Z")});
assert.equal(calls(a.state,"SELECT event_type,COUNT(*)"),1,"do not reread all event history");
assert.equal(calls(a.state,"SELECT id,event_type,event_at"),1,"bounded delta only");
assert.equal(a.state.writes,2);
assert.deepEqual(r,[
  {event_type:"shown",count:3,last_event_at:"2026-11-13 02:02:00"},
  {event_type:"interest_saved",count:1,last_event_at:"2026-11-13 02:01:00"},
  {event_type:"liked",count:1,last_event_at:"2026-11-13 01:05:00"},
]);
assert.equal(JSON.parse(a.state.snapshot).max_id,8);
r=await readSynthesisEventAggregate(a.db,{now:new Date("2026-11-14T00:01:00Z")});
assert.equal(calls(a.state,"SELECT event_type,COUNT(*)"),2,"UTC day repair");
assert.equal(JSON.parse(a.state.snapshot).date_utc,"2026-11-14");

a.state.snapshot="{malformed";
r=await readSynthesisEventAggregate(a.db,{now:new Date("2026-11-14T00:02:00Z")});
assert.equal(calls(a.state,"SELECT event_type,COUNT(*)"),3,"invalid cache fail closed");
assert.equal(r.reduce((n,x)=>n+x.count,0),5);

// An insertion during the initial full scan must never be cached under the old watermark.
const race=makeDb([{id:10,event_type:"liked",event_at:"2026-11-13 01:00:00"}]);
race.state.raceAfterFull=true;
r=await readSynthesisEventAggregate(race.db,{now});
assert.equal(r.length,1);
assert.equal(race.state.snapshot,null);
assert.equal(race.state.writes,0);
r=await readSynthesisEventAggregate(race.db,{now});
assert.equal(r.reduce((n,x)=>n+x.count,0),2);
assert.equal(race.state.writes,1);

// A derived-cache write failure must not block exact D1 source reads.
const fail=makeDb([{id:1,event_type:"liked",event_at:"2026-11-13 01:00:00"}]);
fail.state.rejectWrites=true;
const warning=console.warn;
console.warn=()=>{};
try { r=await readSynthesisEventAggregate(fail.db,{now}); }
finally { console.warn=warning; }
assert.equal(r[0].count,1);
assert.equal(fail.state.writes,0);

// A bounded delta is not allowed to silently truncate. Rebuild on 2001 new events.
const big=makeDb([{id:1,event_type:"shown",event_at:"2026-11-13 00:00:00"}]);
await readSynthesisEventAggregate(big.db,{now});
for (let i=2;i<=2002;i++)
  big.state.events.push({id:i,event_type:"shown",event_at:"2026-11-13 00:01:00"});
r=await readSynthesisEventAggregate(big.db,{now});
assert.equal(r[0].count,2002);
assert.equal(calls(big.state,"SELECT event_type,COUNT(*)"),2);
console.log("SYNTHESIS_EVENT_INCREMENTAL_PASS (fresh, stable, delta, rollover, invalid, race, write fallback, bounded)");
