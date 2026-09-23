const TABLE = "library_file_index_v1";
const MAX_BATCH = 100;
const MAX_LIMIT = 200;
const FIELDS = [
  "library_id","category","title","creator","series","volume","format","file_name","size",
  "chat_id","topic_id","message_id","telegram_link","source","source_message_id","tags","search_text","indexed_at"
];

function reply(value, status = 200) {
  return Response.json(value, { status, headers: { "cache-control": "private, no-store" } });
}

function requireAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return reply({ ok: false, error: "LIBRARY_INDEX_AUTH_NOT_CONFIGURED" }, 503);
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return reply({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function text(value, max = 4096) {
  if (value == null) return null;
  const s = String(value).trim();
  return s ? s.slice(0, max) : null;
}

function integer(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isSafeInteger(n) ? n : null;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/đ/g, "d").replace(/[^a-z0-9]+/g, " ").trim();
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function cleanItem(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("item must be object");
  const item = {
    library_id: text(raw.library_id, 240),
    category: text(raw.category, 40),
    title: text(raw.title, 1000),
    creator: text(raw.creator, 500),
    series: text(raw.series, 500),
    volume: integer(raw.volume),
    format: text(raw.format, 40),
    file_name: text(raw.file_name, 1200),
    size: integer(raw.size),
    chat_id: text(raw.chat_id, 80),
    topic_id: integer(raw.topic_id),
    message_id: integer(raw.message_id),
    telegram_link: text(raw.telegram_link, 1200),
    source: text(raw.source, 120),
    source_message_id: integer(raw.source_message_id),
    tags: text(raw.tags, 4000),
    search_text: text(raw.search_text, 12000),
    indexed_at: text(raw.indexed_at, 100),
  };
  if (!item.library_id || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$/.test(item.library_id)) throw new Error("invalid library_id");
  if (!item.category || !/^[a-z][a-z0-9_-]{0,39}$/.test(item.category)) throw new Error("invalid category");
  if (!item.chat_id || item.message_id == null || item.message_id <= 0) throw new Error("telegram identity required");
  if (!item.search_text) item.search_text = normalize([item.title,item.creator,item.series,item.file_name,item.tags].filter(Boolean).join(" "));
  return item;
}

async function hashItem(item) {
  return sha256Hex(JSON.stringify(FIELDS.map((k) => item[k] ?? null)));
}

function page(url) {
  const limit = Math.max(1, Math.min(MAX_LIMIT, Number(url.searchParams.get("limit") || 100) || 100));
  const offset = Math.max(0, Math.min(100000, Number(url.searchParams.get("offset") || 0) || 0));
  return { limit, offset };
}

async function meta(env) {
  const count = await env.DB.prepare(`SELECT COUNT(*) AS n FROM ${TABLE}`).first();
  const cats = await env.DB.prepare(`SELECT category,COUNT(*) AS n FROM ${TABLE} GROUP BY category ORDER BY category`).all();
  const updated = await env.DB.prepare(`SELECT MAX(updated_at) AS latest FROM ${TABLE}`).first();
  return { ok: true, schema_version: 1, count: Number(count?.n || 0), categories: cats.results || [], latest_updated_at: updated?.latest || null };
}

async function batchUpsert(request, env) {
  let body;
  try { body = await request.json(); } catch { return reply({ ok: false, error: "INVALID_JSON" }, 400); }
  if (!Array.isArray(body?.items) || !body.items.length || body.items.length > MAX_BATCH) {
    return reply({ ok: false, error: `items must contain 1-${MAX_BATCH} records` }, 400);
  }
  let items;
  try { items = body.items.map(cleanItem); } catch (err) { return reply({ ok: false, error: String(err?.message || err) }, 400); }
  const hashed = [];
  for (const item of items) hashed.push({ item, row_hash: await hashItem(item) });
  const cols = [...FIELDS, "row_hash"];
  const assignments = cols.slice(1).map((c) => `${c}=excluded.${c}`).join(",");
  const sql = `INSERT INTO ${TABLE}(${cols.join(",")},updated_at) VALUES(${cols.map(() => "?").join(",")},CURRENT_TIMESTAMP) ON CONFLICT(library_id) DO UPDATE SET ${assignments},updated_at=CURRENT_TIMESTAMP`;
  const statements = hashed.map(({ item, row_hash }) => env.DB.prepare(sql).bind(...FIELDS.map((k) => item[k] ?? null), row_hash));
  await env.DB.batch(statements);
  const ids = items.map((x) => x.library_id);
  const readback = await env.DB.prepare(`SELECT library_id,row_hash FROM ${TABLE} WHERE library_id IN (${ids.map(() => "?").join(",")})`).bind(...ids).all();
  const got = new Map((readback.results || []).map((r) => [r.library_id, r.row_hash]));
  const verified = hashed.every((x) => got.get(x.item.library_id) === x.row_hash);
  const m = await meta(env);
  await env.DB.prepare("INSERT INTO library_index_meta_v1(k,v,updated_at) VALUES('record_count',?,CURRENT_TIMESTAMP) ON CONFLICT(k) DO UPDATE SET v=excluded.v,updated_at=CURRENT_TIMESTAMP").bind(String(m.count)).run();
  await env.DB.prepare("INSERT INTO library_index_meta_v1(k,v,updated_at) VALUES('last_write',?,CURRENT_TIMESTAMP) ON CONFLICT(k) DO UPDATE SET v=excluded.v,updated_at=CURRENT_TIMESTAMP").bind(new Date().toISOString()).run();
  return reply({ ok: verified, durable: verified, d1_readback: verified, accepted: items.length, count: m.count }, verified ? 200 : 500);
}

async function search(env, url) {
  const q = normalize(url.searchParams.get("q") || "");
  if (!q) return reply({ ok: false, error: "q required" }, 400);
  const { limit, offset } = page(url);
  const category = text(url.searchParams.get("category"), 40);
  const terms = q.split(/\s+/).filter(Boolean).slice(0, 12);
  const where = terms.map(() => "search_text LIKE ?");
  const params = terms.map((t) => `%${t}%`);
  if (category) { where.push("category=?"); params.push(category); }
  const rows = await env.DB.prepare(`SELECT ${FIELDS.join(",")} FROM ${TABLE} WHERE ${where.join(" AND ")} ORDER BY category,title,volume,library_id LIMIT ? OFFSET ?`).bind(...params, limit, offset).all();
  return reply({ ok: true, query: q, count: (rows.results || []).length, items: rows.results || [], limit, offset });
}

export async function handleLibraryIndex(request, env, url) {
  if (!url.pathname.startsWith("/library-index")) return null;
  if (!env.DB) return reply({ ok: false, error: "D1_NOT_BOUND" }, 503);
  const authError = requireAuth(request, env); if (authError) return authError;
  if (request.method === "POST" && url.pathname === "/library-index/batch") return batchUpsert(request, env);
  if (request.method !== "GET") return reply({ ok: false, error: "method_not_allowed" }, 405);
  if (url.pathname === "/library-index/meta") return reply(await meta(env));
  if (url.pathname === "/library-index/search") return search(env, url);
  const { limit, offset } = page(url);
  if (url.pathname === "/library-index/hashes") {
    const rows = await env.DB.prepare(`SELECT library_id,row_hash,updated_at FROM ${TABLE} ORDER BY library_id LIMIT ? OFFSET ?`).bind(limit, offset).all();
    return reply({ ok: true, items: rows.results || [], limit, offset });
  }
  if (url.pathname === "/library-index") {
    const rows = await env.DB.prepare(`SELECT ${FIELDS.join(",")} FROM ${TABLE} ORDER BY category,title,volume,library_id LIMIT ? OFFSET ?`).bind(limit, offset).all();
    return reply({ ok: true, items: rows.results || [], limit, offset });
  }
  return reply({ ok: false, error: "NOT_FOUND" }, 404);
}
