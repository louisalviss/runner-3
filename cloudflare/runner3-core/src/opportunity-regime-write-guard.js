const MAX_REGIME_WRITE_AGE_MS = 20 * 60 * 1000;
const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;

function noStoreJson(value, status) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function parseTimestamp(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

export async function guardOpportunityRegimeWrite(request, url) {
  if (request.method !== "PUT") return null;
  if (!/^\/opportunity-radar\/regime\/current\/[^/]+$/.test(url.pathname)) return null;

  let body;
  try {
    body = await request.clone().json();
  } catch {
    return null; // Let the canonical handler return invalid_json.
  }

  const checkedAtMs = parseTimestamp(body?.checked_at);
  if (checkedAtMs == null) {
    return noStoreJson({
      ok: false,
      error: "REGIME_WRITE_CHECKED_AT_REQUIRED",
      max_age_seconds: MAX_REGIME_WRITE_AGE_MS / 1000,
    }, 400);
  }

  const nowMs = Date.now();
  const ageMs = nowMs - checkedAtMs;
  if (ageMs < -MAX_FUTURE_SKEW_MS) {
    return noStoreJson({
      ok: false,
      error: "REGIME_WRITE_FROM_FUTURE",
      max_future_skew_seconds: MAX_FUTURE_SKEW_MS / 1000,
    }, 409);
  }
  if (ageMs > MAX_REGIME_WRITE_AGE_MS) {
    return noStoreJson({
      ok: false,
      error: "STALE_REGIME_WRITE",
      age_seconds: Math.floor(ageMs / 1000),
      max_age_seconds: MAX_REGIME_WRITE_AGE_MS / 1000,
    }, 409);
  }

  if (body?.expires_at != null) {
    const expiresAtMs = parseTimestamp(body.expires_at);
    if (expiresAtMs == null) {
      return noStoreJson({ ok: false, error: "REGIME_WRITE_EXPIRES_AT_INVALID" }, 400);
    }
    if (expiresAtMs <= checkedAtMs || expiresAtMs - checkedAtMs > MAX_REGIME_WRITE_AGE_MS) {
      return noStoreJson({
        ok: false,
        error: "REGIME_WRITE_TTL_INVALID",
        max_ttl_seconds: MAX_REGIME_WRITE_AGE_MS / 1000,
      }, 400);
    }
    if (nowMs > expiresAtMs) {
      return noStoreJson({ ok: false, error: "EXPIRED_REGIME_WRITE" }, 409);
    }
  }

  return null;
}
