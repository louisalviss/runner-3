import app from "./rss-entry.js";

const MAX_BATCH_ROWS = 100;
const MAX_TEXT = 100000;

function requireDb(env) {
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  return null;
}

function requireAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return Response.json({ ok: false, error: "WRITE_AUTH_NOT_CONFIGURED" }, { status: 503 });
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) {
    return Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  }
  return null;
}

function text(value, max = MAX_TEXT) {
  if (value == null) return null;
  const out = typeof value === "string" ? value : String(value);
  if (out.length > max) throw new Error(`text_too_large:${out.length}:${max}`);
  return out;
}

function integer(value, fallback = 0) {
  const n = Number.parseInt(value ?? fallback, 10);
  return Number.isFinite(n) ? n : fallback;
}

function number(value, fallback = 0) {
  const n = Number(value ?? fallback);
  return Number.isFinite(n) ? n : fallback;
}

function rowsFrom(body) {
  if (!Array.isArray(body.rows)) throw new Error("rows_must_be_array");
  if (body.rows.length < 1 || body.rows.length > MAX_BATCH_ROWS) {
    throw new Error(`rows_must_contain_1_to_${MAX_BATCH_ROWS}`);
  }
  return body.rows;
}

function runShape(value) {
  const row = value && typeof value === "object" ? value : {};
  const runId = text(row.run_id, 200)?.trim();
  const subreddit = text(row.subreddit, 100)?.trim();
  const mode = text(row.mode, 30)?.trim();
  if (!runId || !subreddit || !mode) throw new Error("run_id_subreddit_mode_required");
  return {
    run_id: runId,
    subreddit,
    mode,
    started_at: text(row.started_at, 100) || new Date().toISOString(),
    finished_at: text(row.finished_at, 100),
    posts_seen: integer(row.posts_seen),
    threads_fetched: integer(row.threads_fetched),
    comments_seen: integer(row.comments_seen),
    raw_object_key: text(row.raw_object_key, 1000),
    error: row.error == null ? null : text(typeof row.error === "string" ? row.error : JSON.stringify(row.error), 100000),
  };
}

async function ingestStart(env, body) {
  const row = runShape(body.run);
  await env.DB.prepare(`
    INSERT INTO reddit_scan_runs
      (run_id, subreddit, mode, status, started_at, posts_seen, threads_fetched, comments_seen, raw_object_key, error)
    VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)
    ON CONFLICT(run_id) DO UPDATE SET
      subreddit=excluded.subreddit,
      mode=excluded.mode,
      status='running',
      started_at=excluded.started_at,
      finished_at=NULL,
      posts_seen=excluded.posts_seen,
      threads_fetched=excluded.threads_fetched,
      comments_seen=excluded.comments_seen,
      raw_object_key=excluded.raw_object_key,
      error=excluded.error
  `).bind(
    row.run_id, row.subreddit, row.mode, row.started_at, row.posts_seen,
    row.threads_fetched, row.comments_seen, row.raw_object_key, row.error
  ).run();
  return { ok: true, phase: "start", run_id: row.run_id };
}

function postStatement(env, row) {
  const postId = text(row.post_id, 100)?.trim();
  const subreddit = text(row.subreddit, 100)?.trim();
  const canonicalUrl = text(row.canonical_url, 4096)?.trim();
  if (!postId || !subreddit || !canonicalUrl) throw new Error("post_id_subreddit_canonical_url_required");
  const fetched = row.status === "thread_fetched" || row.fetched === true;
  const sourceSorts = Array.isArray(row.source_sorts)
    ? JSON.stringify(row.source_sorts)
    : text(row.source_sorts, 10000);
  const binds = [
    postId,
    subreddit,
    canonicalUrl,
    text(row.title, 2000),
    text(row.author, 300),
    integer(row.created_utc),
    integer(row.score),
    integer(row.num_comments),
    text(row.body_text),
    text(row.body_hash, 128),
    number(row.quality_score),
    fetched ? "thread_fetched" : "indexed",
    sourceSorts,
    fetched ? text(row.last_thread_fetch_at, 100) : null,
    fetched ? integer(row.comments_snapshot_count) : 0,
    fetched ? text(row.raw_object_key, 1200) : null,
  ];
  const update = fetched
    ? `subreddit=excluded.subreddit, canonical_url=excluded.canonical_url, title=excluded.title,
       author=excluded.author, created_utc=excluded.created_utc, score=excluded.score,
       num_comments=excluded.num_comments, body_text=excluded.body_text, body_hash=excluded.body_hash,
       quality_score=excluded.quality_score, status='thread_fetched', source_sorts=excluded.source_sorts,
       last_thread_fetch_at=excluded.last_thread_fetch_at,
       comments_snapshot_count=excluded.comments_snapshot_count,
       raw_object_key=excluded.raw_object_key, last_seen_at=CURRENT_TIMESTAMP`
    : `subreddit=excluded.subreddit, canonical_url=excluded.canonical_url, title=excluded.title,
       author=excluded.author, created_utc=excluded.created_utc, score=excluded.score,
       num_comments=excluded.num_comments, body_text=excluded.body_text, body_hash=excluded.body_hash,
       quality_score=excluded.quality_score, source_sorts=excluded.source_sorts,
       last_seen_at=CURRENT_TIMESTAMP`;
  return env.DB.prepare(`
    INSERT INTO reddit_posts (
      post_id, subreddit, canonical_url, title, author, created_utc, score, num_comments,
      body_text, body_hash, quality_score, status, source_sorts, last_thread_fetch_at,
      comments_snapshot_count, raw_object_key
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(post_id) DO UPDATE SET ${update}
  `).bind(...binds);
}

function commentStatement(env, row) {
  const commentId = text(row.comment_id, 100)?.trim();
  const postId = text(row.post_id, 100)?.trim();
  if (!commentId || !postId) throw new Error("comment_id_post_id_required");
  return env.DB.prepare(`
    INSERT INTO reddit_comments (
      comment_id, post_id, parent_id, author, depth, body_text, body_hash, score, created_utc, quality_score
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(comment_id) DO UPDATE SET
      post_id=excluded.post_id, parent_id=excluded.parent_id, author=excluded.author,
      depth=excluded.depth, body_text=excluded.body_text, body_hash=excluded.body_hash,
      score=excluded.score, created_utc=excluded.created_utc,
      quality_score=excluded.quality_score, last_seen_at=CURRENT_TIMESTAMP
  `).bind(
    commentId,
    postId,
    text(row.parent_id, 120),
    text(row.author, 300),
    integer(row.depth),
    text(row.body_text),
    text(row.body_hash, 128),
    integer(row.score),
    integer(row.created_utc),
    number(row.quality_score),
  );
}

function tagStatement(env, row) {
  const postId = text(row.post_id, 100)?.trim();
  const tag = text(row.tag, 200)?.trim();
  if (!postId || !tag) throw new Error("post_id_tag_required");
  return env.DB.prepare(`
    INSERT INTO reddit_post_tags (post_id, tag, weight) VALUES (?, ?, ?)
    ON CONFLICT(post_id, tag) DO UPDATE SET weight=excluded.weight, updated_at=CURRENT_TIMESTAMP
  `).bind(postId, tag, number(row.weight, 1));
}

async function ingestRows(env, phase, body) {
  const rows = rowsFrom(body);
  let statements;
  if (phase === "posts") statements = rows.map((row) => postStatement(env, row));
  else if (phase === "comments") statements = rows.map((row) => commentStatement(env, row));
  else if (phase === "tags") statements = rows.map((row) => tagStatement(env, row));
  else throw new Error("unsupported_rows_phase");
  await env.DB.batch(statements);
  return { ok: true, phase, applied: rows.length };
}

async function ingestFinish(env, body) {
  const row = runShape(body.run);
  await env.DB.prepare(`
    UPDATE reddit_scan_runs SET
      status='success', finished_at=?, posts_seen=?, threads_fetched=?, comments_seen=?,
      raw_object_key=?, error=?
    WHERE run_id=?
  `).bind(
    row.finished_at || new Date().toISOString(), row.posts_seen, row.threads_fetched,
    row.comments_seen, row.raw_object_key, row.error, row.run_id
  ).run();
  const stored = await env.DB.prepare("SELECT * FROM reddit_scan_runs WHERE run_id = ?").bind(row.run_id).first();
  if (!stored || stored.status !== "success") throw new Error("run_finish_verification_failed");
  return { ok: true, phase: "finish", run: stored };
}

async function handleIngest(request, env) {
  const dbError = requireDb(env);
  if (dbError) return dbError;
  const authError = requireAuth(request, env);
  if (authError) return authError;
  if (request.method !== "POST") {
    return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  }
  try {
    const body = await request.json();
    const phase = text(body?.phase, 30)?.trim().toLowerCase();
    let result;
    if (phase === "start") result = await ingestStart(env, body);
    else if (phase === "posts" || phase === "comments" || phase === "tags") result = await ingestRows(env, phase, body);
    else if (phase === "finish") result = await ingestFinish(env, body);
    else throw new Error("phase_must_be_start_posts_comments_tags_or_finish");
    return Response.json(result);
  } catch (err) {
    return Response.json({ ok: false, error: String(err?.message || err) }, { status: 400 });
  }
}

async function handleRunRead(request, env, runId) {
  const dbError = requireDb(env);
  if (dbError) return dbError;
  const authError = requireAuth(request, env);
  if (authError) return authError;
  if (request.method !== "GET") {
    return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  }
  const row = await env.DB.prepare("SELECT * FROM reddit_scan_runs WHERE run_id = ?").bind(runId).first();
  return Response.json({ ok: true, run: row || null });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/reddit/deep-sweep/ingest") {
      return handleIngest(request, env);
    }
    const match = url.pathname.match(/^\/reddit\/deep-sweep\/runs\/([^/]+)$/);
    if (match) {
      let runId;
      try { runId = decodeURIComponent(match[1]); } catch { return Response.json({ ok: false, error: "invalid_run_id" }, { status: 400 }); }
      if (!runId || runId.length > 200) return Response.json({ ok: false, error: "invalid_run_id" }, { status: 400 });
      return handleRunRead(request, env, runId);
    }
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
