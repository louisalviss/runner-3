// Existing content_items ingest is insert/upsert-only; updates do not change row count.
// Track the INTEGER PRIMARY KEY rowid high-water mark, not every content row on
// synthesis GET. Reconcile the count with a full scan once per UTC day so any
// off-contract direct deletes or repairs cannot leave a permanent stale count.
// This is derived cache state in existing workflow_state; no user event writes.
const KEY = "content-intelligence-synthesis-item-count";
const SCHEMA = "content-intelligence-synthesis-items-v1";

function utcDate(now) {
  const date = now instanceof Date ? now : new Date(now);
  if (!Number.isFinite(date.getTime())) throw new Error("invalid_synthesis_clock");
  return date.toISOString().slice(0,10);
}

function verifiedSnapshot(row, date) {
  let value;
  try {
    const raw = String(row?.detail || "");
    if (raw.length > 2000) return null;
    value = JSON.parse(raw);
  } catch { return null; }
  if (!value || value.schema !== SCHEMA || value.date_utc !== date
      || !Number.isSafeInteger(value.max_rowid) || value.max_rowid < 0
      || !Number.isSafeInteger(value.item_count) || value.item_count < 0
      || value.item_count > value.max_rowid) return null;
  return value;
}

async function highwater(db) {
  const row = await db.prepare("SELECT COALESCE(MAX(rowid),0) AS max_rowid FROM content_items").first();
  const n = Number(row?.max_rowid);
  if (!Number.isSafeInteger(n) || n < 0) throw new Error("invalid_D1_content_highwater");
  return n;
}

async function store(db, snapshot) {
  const sql = [
    "INSERT INTO workflow_state(source,status,detail,updated_at)",
    "VALUES(?,'clean',?,CURRENT_TIMESTAMP)",
    "ON CONFLICT(source) DO UPDATE SET status='clean',detail=excluded.detail,updated_at=CURRENT_TIMESTAMP",
    "WHERE (CASE WHEN json_valid(workflow_state.detail)",
    "            THEN COALESCE(json_extract(workflow_state.detail,'$.date_utc'),'')",
    "            ELSE '' END) < ?",
    "   OR ((CASE WHEN json_valid(workflow_state.detail)",
    "             THEN COALESCE(json_extract(workflow_state.detail,'$.date_utc'),'')",
    "             ELSE '' END) = ?",
    "       AND (CASE WHEN json_valid(workflow_state.detail)",
    "                 THEN COALESCE(CAST(json_extract(workflow_state.detail,'$.max_rowid') AS INTEGER),-1)",
    "                 ELSE -1 END) <= ?)",
  ].join("\n");
  try {
    await db.prepare(sql).bind(KEY,JSON.stringify(snapshot),
      snapshot.date_utc,snapshot.date_utc,snapshot.max_rowid).run();
  } catch(error) {
    console.warn("synthesis_item_count_cache_write_failed", String(error?.name || "unknown"));
  }
}

export async function readSynthesisItemCount(db, {now=new Date()}={}) {
  const day = utcDate(now);
  const [cachedRow, currentMax] = await Promise.all([
    db.prepare("SELECT detail FROM workflow_state WHERE source=?").bind(KEY).first(),
    highwater(db),
  ]);
  const cached = verifiedSnapshot(cachedRow, day);
  if (cached && cached.max_rowid === currentMax) return cached.item_count;

  let count = null;
  let cacheSafe = true;
  if (cached && cached.max_rowid < currentMax) {
    const delta = await db.prepare(
      "SELECT COUNT(*) AS n FROM content_items WHERE rowid>? AND rowid<=?"
    ).bind(cached.max_rowid,currentMax).first();
    const added = Number(delta?.n);
    if (Number.isSafeInteger(added) && added > 0
        && cached.item_count + added <= currentMax) count = cached.item_count + added;
  }
  if (count === null) {
    const full = await db.prepare("SELECT COUNT(*) AS n FROM content_items").first();
    count = Number(full?.n);
    if (!Number.isSafeInteger(count) || count < 0 || count > currentMax)
      throw new Error("invalid_D1_content_count");
    cacheSafe = (await highwater(db)) === currentMax;
  }
  if (cacheSafe) await store(db, {schema:SCHEMA,date_utc:day,max_rowid:currentMax,item_count:count});
  return count;
}
