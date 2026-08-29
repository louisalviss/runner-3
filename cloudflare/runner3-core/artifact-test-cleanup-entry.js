import app from "./artifact-library-pin-v2-entry.js";

const ROOT = "core/ebook/";
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const TEST_SCOPE_PREFIXES = [
  "core/ebook/ebook-resume-proof-",
  "core/ebook/ebook-runtime-smoke-",
  "core/ebook/ebook-runtime-codex-smoke-",
];
const EXACT_TEST_BASENAMES = new Set([
  "smoke-book.vi.epub",
  "smoke-book.codex.vi.epub",
  "mailbox-bookforge-codex-smoke.vi.epub",
]);
const RESUME_PROOF_BASENAME = /^resume-proof-v\d+\.vi\.epub$/;

function expectedToken(env) {
  return typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
}

function authorized(request, env) {
  const expected = expectedToken(env);
  if (!expected) return false;
  const auth = request.headers.get("Authorization") || "";
  return auth.startsWith("Bearer ") && auth.slice(7).trim() === expected;
}

function headers(base = {}) {
  const h = new Headers(base);
  h.set("X-Robots-Tag", ROBOTS);
  h.set("Cache-Control", "private, no-store, max-age=0");
  h.set("Pragma", "no-cache");
  h.set("Referrer-Policy", "no-referrer");
  return h;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: headers({ "Content-Type": "application/json; charset=utf-8" }),
  });
}

function classify(key) {
  if (!key.startsWith(ROOT)) return null;
  if (key.startsWith("core/ebook/dcc-")) return null;

  const scopePrefix = TEST_SCOPE_PREFIXES.find((prefix) => key.startsWith(prefix));
  if (scopePrefix) return { reason: "explicit_test_scope", scope_prefix: scopePrefix };

  const basename = key.slice(key.lastIndexOf("/") + 1);
  if (EXACT_TEST_BASENAMES.has(basename)) {
    return { reason: "exact_test_fixture_basename", basename };
  }
  if (RESUME_PROOF_BASENAME.test(basename)) {
    return { reason: "resume_proof_fixture_basename", basename };
  }
  return null;
}

async function listAll(env) {
  const objects = [];
  let cursor;
  for (;;) {
    const page = await env.ARTIFACTS.list({ prefix: ROOT, cursor, limit: 1000 });
    for (const object of page.objects || []) objects.push(object);
    if (!page.truncated || !page.cursor) break;
    cursor = page.cursor;
  }
  return objects;
}

async function cleanup(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!authorized(request, env)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (!env.ARTIFACTS) return json({ ok: false, error: "ARTIFACTS_BINDING_MISSING" }, 503);

  const url = new URL(request.url);
  const apply = url.searchParams.get("apply") === "1";
  const all = await listAll(env);
  const candidates = [];

  for (const object of all) {
    const rule = classify(object.key);
    if (!rule) continue;
    candidates.push({
      key: object.key,
      size: Number(object.size || 0),
      uploaded: object.uploaded ? new Date(object.uploaded).toISOString() : null,
      ...rule,
    });
  }

  const protectedDccCount = all.filter((object) => object.key.startsWith("core/ebook/dcc-")).length;
  if (candidates.some((item) => item.key.startsWith("core/ebook/dcc-"))) {
    return json({ ok: false, error: "DCC_SAFETY_GUARD_TRIPPED" }, 500);
  }

  const deleted = [];
  if (apply) {
    for (const item of candidates) {
      await env.ARTIFACTS.delete(item.key);
      deleted.push(item.key);
    }
  }

  return json({
    ok: true,
    mode: apply ? "apply" : "dry-run",
    root: ROOT,
    scanned_count: all.length,
    candidate_count: candidates.length,
    protected_dcc_object_count: protectedDccCount,
    candidates,
    deleted_count: deleted.length,
    deleted,
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/artifact-cleanup-tests") return cleanup(request, env);
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
