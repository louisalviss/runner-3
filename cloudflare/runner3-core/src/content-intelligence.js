const MAX_ROWS = 100;
const MAX_JSON = 200000;

function requireDb(env) {
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  return null;
}

function requireAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return Response.json({ ok: false, error: "WRITE_AUTH_NOT_CONFIGURED" }, { status: 503 });
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  return null;
}

function text(value, max = 4096) {
  if (value == null) return null;
  const out = typeof value === "string" ? value : String(value);
  if (out.length > max) throw new Error(`text_too_large:${out.length}:${max}`);
  return out;
}

function jsonText(value) {
  if (value == null) return null;
  const out = JSON.stringify(value);
  if (out.length > MAX_JSON) throw new Error(`json_too_large:${out.length}:${MAX_JSON}`);
  return out;
}

function rows(body) {
  if (!Array.isArray(body?.rows)) throw new Error("rows_must_be_array");
  if (body.rows.length < 1 || body.rows.length > MAX_ROWS) throw new Error(`rows_must_contain_1_to_${MAX_ROWS}`);
  return body.rows;
}

function itemStatement(env, row) {
  const itemId = text(row.item_id, 4096)?.trim();
  const canonicalUrl = text(row.canonical_url, 4096)?.trim();
  const sourceType = text(row.source_type, 100)?.trim();
  if (!itemId || !canonicalUrl || !sourceType) throw new Error("item_id_canonical_url_source_type_required");
  return env.DB.prepare(`
    INSERT INTO content_items (
      item_id, canonical_url, source_type, source_name, source_key, title,
      published_at, captured_at, language, raw_ref, content_hash, metadata_json,
      first_seen_at, last_seen_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(item_id) DO UPDATE SET
      canonical_url=excluded.canonical_url,
      source_type=excluded.source_type,
      source_name=excluded.source_name,
      source_key=excluded.source_key,
      title=excluded.title,
      published_at=excluded.published_at,
      language=COALESCE(excluded.language, content_items.language),
      raw_ref=COALESCE(excluded.raw_ref, content_items.raw_ref),
      content_hash=COALESCE(excluded.content_hash, content_items.content_hash),
      metadata_json=COALESCE(excluded.metadata_json, content_items.metadata_json),
      last_seen_at=CURRENT_TIMESTAMP
  `).bind(
    itemId, canonicalUrl, sourceType,
    text(row.source_name, 300), text(row.source_key, 200), text(row.title, 4000),
    text(row.published_at, 100), text(row.language, 50), text(row.raw_ref, 2000),
    text(row.content_hash, 200), jsonText(row.metadata)
  );
}

async function handleItems(request, env) {
  const dbError = requireDb(env); if (dbError) return dbError;
  const authError = requireAuth(request, env); if (authError) return authError;
  if (request.method !== "POST") return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  try {
    const body = await request.json();
    const list = rows(body);
    await env.DB.batch(list.map((row) => itemStatement(env, row)));
    return Response.json({ ok: true, applied: list.length });
  } catch (err) {
    return Response.json({ ok: false, error: String(err?.message || err) }, { status: 400 });
  }
}

async function handleEvent(request, env) {
  const dbError = requireDb(env); if (dbError) return dbError;
  const authError = requireAuth(request, env); if (authError) return authError;
  if (request.method !== "POST") return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  try {
    const body = await request.json();
    const itemId = text(body.item_id, 4096)?.trim();
    const eventType = text(body.event_type, 100)?.trim();
    if (!itemId || !eventType) throw new Error("item_id_event_type_required");
    const exists = await env.DB.prepare("SELECT 1 AS ok FROM content_items WHERE item_id = ? LIMIT 1").bind(itemId).first();
    if (!exists) return Response.json({ ok: false, error: "CONTENT_ITEM_NOT_FOUND" }, { status: 404 });
    const result = await env.DB.prepare(`
      INSERT INTO user_content_events (
        item_id, render_id, event_type, assistant_recommended, assistant_rank,
        explicit_feedback, context_json, event_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    `).bind(
      itemId,
      text(body.render_id, 300),
      eventType,
      body.assistant_recommended ? 1 : 0,
      Number.isFinite(Number(body.assistant_rank)) ? Number(body.assistant_rank) : null,
      text(body.explicit_feedback, 1000),
      jsonText(body.context)
    ).run();
    return Response.json({ ok: true, id: result.meta?.last_row_id ?? null });
  } catch (err) {
    return Response.json({ ok: false, error: String(err?.message || err) }, { status: 400 });
  }
}

async function handleProfile(request, env, url) {
  const dbError = requireDb(env); if (dbError) return dbError;
  const authError = requireAuth(request, env); if (authError) return authError;
  if (request.method !== "GET") return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  const limit = Math.min(500, Math.max(1, Number.parseInt(url.searchParams.get("limit") || "100", 10) || 100));
  const result = await env.DB.prepare(`
    SELECT feature_type, feature_key, weight, evidence_count, positive_count,
           negative_count, confidence, updated_at
    FROM interest_profile
    ORDER BY ABS(weight) DESC, confidence DESC, evidence_count DESC
    LIMIT ?
  `).bind(limit).all();
  return Response.json({ ok: true, rows: result.results || [] });
}

export async function handleContentIntelligence(request, env, url) {
  if (url.pathname === "/content-intelligence/items") return handleItems(request, env);
  if (url.pathname === "/content-intelligence/events") return handleEvent(request, env);
  if (url.pathname === "/content-intelligence/profile") return handleProfile(request, env, url);
  return null;
}
