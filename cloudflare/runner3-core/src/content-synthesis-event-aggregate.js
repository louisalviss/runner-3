// Derived read-only event history projection, stored in the EXISTING workflow_state.
// All real Interest and engagement events remain append-only in user_content_events.
// The high-water ID is checked from D1 on every GET; only new rows are aggregated.
// Rebuild once per UTC day to reconcile off-contract corrections. No new table/timer.
const KEY = "content-intelligence-synthesis-event-aggregate";
const SCHEMA = "content-intelligence-synthesis-events-v1";
const MAX_DELTA = 2000;

function normalizeDate(now) {
  const value = now instanceof Date ? now : new Date(now);
  if (!Number.isFinite(value.getTime())) throw new Error("invalid_synthesis_clock");
  return value.toISOString().slice(0, 10);
}

function readSnapshot(row, date) {
  let snapshot;
  try {
    const raw = String(row?.detail || "");
    if (raw.length > 32000) return null;
    snapshot = JSON.parse(raw);
  } catch { return null; }
  if (!snapshot || snapshot.schema !== SCHEMA || snapshot.date_utc !== date
      || !Number.isSafeInteger(snapshot.max_id) || snapshot.max_id < 0
      || !Array.isArray(snapshot.rows) || snapshot.rows.length > 64) return null;
  const seen = new Set();
  let sum = 0;
  for (const r of snapshot.rows) {
    if (!r || typeof r.event_type !== "string" || !r.event_type || r.event_type.length > 100
        || seen.has(r.event_type) || !Number.isSafeInteger(r.count) || r.count < 1
        || !(r.last_event_at === null || typeof r.last_event_at === "string"
             && r.last_event_at.length <= 80)) return null;
    seen.add(r.event_type);
    sum += r.count;
  }
  if (!Number.isSafeInteger(sum) || !Number.isSafeInteger(snapshot.total_events)
      || snapshot.total_events !== sum || sum > snapshot.max_id) return null;
  return snapshot;
}

function orderedRows(rows) {
  return [...rows].sort((a, b) => b.count - a.count || a.event_type.localeCompare(b.event_type));
}
function fromDelta(oldRows, delta) {
  const counts = new Map(oldRows.map(r => [r.event_type, {...r}]));
  for (const row of delta) {
    const type = row.event_type;
    if (typeof type !== "string" || !type || type.length > 100)
      throw new Error("invalid_D1_event_type");
    const old = counts.get(type) || {event_type:type, count:0, last_event_at:null};
    const at = row.event_at === null || row.event_at === undefined ? null : String(row.event_at);
    old.count += 1;
    if (at !== null && (old.last_event_at === null || String(at) > old.last_event_at))
      old.last_event_at = String(at);
    counts.set(type, old);
  }
  return orderedRows([...counts.values()]);
}
function fromFull(rows) {
  if (!Array.isArray(rows) || rows.length > 64) throw new Error("invalid_D1_event_aggregate");
  const normalized = rows.map(r => ({
    event_type:String(r.event_type),
    count:Number(r.count),
    last_event_at:r.last_event_at ?? null,
  }));
  if (normalized.some(r => !r.event_type || !Number.isSafeInteger(r.count) || r.count < 1))
    throw new Error("invalid_D1_event_aggregate");
  return orderedRows(normalized);
}

async function readMaxId(db) {
  const r = await db.prepare("SELECT COALESCE(MAX(id),0) AS max_id FROM user_content_events").first();
  const id = Number(r?.max_id);
  if (!Number.isSafeInteger(id) || id < 0) throw new Error("invalid_D1_event_highwater");
  return id;
}

async function storeSnapshot(db, snapshot) {
  const data = JSON.stringify(snapshot);
  try {
    // Concurrent readers must not overwrite a newer snapshot with an older one.
    await db.prepare(`
      INSERT INTO workflow_state(source,status,detail,updated_at)
      VALUES(?,'clean',?,CURRENT_TIMESTAMP)
      ON CONFLICT(source) DO UPDATE SET status='clean',detail=excluded.detail,updated_at=CURRENT_TIMESTAMP
      WHERE (CASE WHEN json_valid(workflow_state.detail)
                  THEN COALESCE(json_extract(workflow_state.detail,'$.date_utc'),'')
                  ELSE '' END) < ?
         OR ((CASE WHEN json_valid(workflow_state.detail)
                   THEN COALESCE(json_extract(workflow_state.detail,'$.date_utc'),'')
                   ELSE '' END) = ?
             AND (CASE WHEN json_valid(workflow_state.detail)
                       THEN COALESCE(CAST(json_extract(workflow_state.detail,'$.max_id') AS INTEGER),-1)
                       ELSE -1 END) <= ?)
    `).bind(KEY, data, snapshot.date_utc, snapshot.date_utc, snapshot.max_id).run();
  } catch (error) {
    // A cache write failure cannot turn a successful authenticated read into a failure.
    console.warn("synthesis_event_aggregate_cache_write_failed", String(error?.name || "unknown"));
  }
}

// Returns identical public event_type/count/last_event_at fields to the old full scan.
export async function readSynthesisEventAggregate(db, {now=new Date()}={}) {
  const date = normalizeDate(now);
  const [row, maxId] = await Promise.all([
    db.prepare("SELECT detail FROM workflow_state WHERE source=?").bind(KEY).first(),
    readMaxId(db),
  ]);
  const cached = readSnapshot(row, date);
  if (cached && cached.max_id === maxId) return cached.rows;

  let nextRows;
  let canCommit = true;
  if (cached && cached.max_id < maxId) {
    const delta = await db.prepare(`
      SELECT id,event_type,event_at FROM user_content_events
      WHERE id>? AND id<=? ORDER BY id ASC LIMIT ?
    `).bind(cached.max_id, maxId, MAX_DELTA + 1).all();
    const newRows = delta.results || [];
    if (newRows.length <= MAX_DELTA && newRows.length > 0
        && Number(newRows[newRows.length - 1].id) === maxId
        && newRows.every((r, i) => Number.isSafeInteger(Number(r.id))
             && Number(r.id) > cached.max_id && Number(r.id) <= maxId
             && (i === 0 || Number(r.id) > Number(newRows[i-1].id)))) {
      nextRows = fromDelta(cached.rows, newRows);
    }
  }
  if (!nextRows) {
    const full = await db.prepare(
      "SELECT event_type,COUNT(*) AS count,MAX(event_at) AS last_event_at FROM user_content_events GROUP BY event_type ORDER BY count DESC"
    ).all();
    nextRows = fromFull(full.results || []);
    // Never attach a full-scan snapshot to an earlier high-water mark.
    canCommit = (await readMaxId(db)) === maxId;
  }
  if (canCommit) await storeSnapshot(db, {schema:SCHEMA,date_utc:date,max_id:maxId,
    total_events:nextRows.reduce((n, row) => n + row.count, 0), rows:nextRows});
  return nextRows;
}
