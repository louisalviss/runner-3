const MAX_JSON_CHARS = 100000;
const MAX_KEY_CHARS = 200;
const ALLOWED_MACRO = new Set(["NORMAL", "WATCH", "ALERT"]);
const ALLOWED_FED = new Set(["GREEN", "AMBER", "AMBER HIGH", "RED", "CRITICAL"]);
const ALLOWED_RELATION = new Set([
  "HAWKISH_DAMAGE",
  "HAWKISH_ABSORBED",
  "DOVISH_RISK_ON",
  "DOVISH_RECESSION",
  "MIXED_OR_UNCONFIRMED",
]);
const ALLOWED_DIRECTION = new Set(["HAWKISH", "DOVISH", "NEUTRAL", "MIXED"]);
const ALLOWED_IMPACT = new Set(["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]);

function noStoreJson(value, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("cache-control", "no-store");
  headers.set("content-type", "application/json; charset=utf-8");
  return new Response(JSON.stringify(value), { ...init, headers });
}

function requireDb(env) {
  if (!env.DB) return noStoreJson({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  return null;
}

function requireWriteAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return noStoreJson({ ok: false, error: "WRITE_AUTH_NOT_CONFIGURED" }, { status: 503 });
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return noStoreJson({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  return null;
}

function text(value, max = MAX_KEY_CHARS) {
  if (value == null) return null;
  const out = String(value).trim();
  if (!out) return null;
  if (out.length > max) throw new Error(`text_too_large:${out.length}:${max}`);
  return out;
}

function key(value, name) {
  const out = text(value, MAX_KEY_CHARS);
  if (!out) throw new Error(`${name}_required`);
  if (!/^[A-Za-z0-9._:-]+$/.test(out)) throw new Error(`${name}_invalid`);
  return out;
}

function jsonText(value, name) {
  if (value == null) return null;
  const out = JSON.stringify(value);
  if (out.length > MAX_JSON_CHARS) throw new Error(`${name}_too_large`);
  return out;
}

function parseJson(value) {
  if (typeof value !== "string") return value ?? null;
  try { return JSON.parse(value); } catch { return value; }
}

function parseCurrent(row) {
  if (!row) return null;
  return {
    regime_key: row.regime_key,
    macro_state: row.macro_state,
    fed_state: row.fed_state,
    policy_market_state: row.policy_market_state,
    policy_direction: row.policy_direction,
    default_action: row.default_action,
    evidence: parseJson(row.evidence_json),
    confirmation_families: parseJson(row.confirmation_json),
    affected_exposures: parseJson(row.affected_exposures_json),
    source_session: row.source_session,
    evidence_asof: row.evidence_asof,
    last_checked_at: row.last_checked_at,
    state_changed_at: row.state_changed_at,
    version: Number(row.version || 0),
    updated_at: row.updated_at,
  };
}

function parseCandidate(row) {
  if (!row) return null;
  return {
    candidate_key: row.candidate_key,
    regime_key: row.regime_key,
    exposure: parseJson(row.exposure_json),
    regime_impact: row.regime_impact,
    impact_note: row.impact_note,
    checked_at: row.checked_at,
    regime_version: Number(row.regime_version || 0),
    source_row_ref: row.source_row_ref,
    updated_at: row.updated_at,
  };
}

function validateState(body) {
  const macro = text(body.macro_state, 30);
  const fed = text(body.fed_state, 30);
  const relation = text(body.policy_market_state, 50);
  const direction = text(body.policy_direction, 30);
  if (!ALLOWED_MACRO.has(macro)) throw new Error("macro_state_invalid");
  if (fed && !ALLOWED_FED.has(fed)) throw new Error("fed_state_invalid");
  if (!ALLOWED_RELATION.has(relation)) throw new Error("policy_market_state_invalid");
  if (direction && !ALLOWED_DIRECTION.has(direction)) throw new Error("policy_direction_invalid");
  const expectedVersion = Number.parseInt(body.expected_version, 10);
  if (!Number.isInteger(expectedVersion) || expectedVersion < 0) throw new Error("expected_version_invalid");
  const checkedAt = text(body.checked_at, 100) || new Date().toISOString();
  const evidenceAsof = text(body.evidence_asof, 100) || checkedAt;
  return {
    expectedVersion,
    macro,
    fed,
    relation,
    direction,
    defaultAction: text(body.default_action, 2000),
    evidenceJson: jsonText(body.evidence, "evidence"),
    confirmationJson: jsonText(body.confirmation_families, "confirmation_families"),
    exposuresJson: jsonText(body.affected_exposures, "affected_exposures"),
    sourceSession: text(body.source_session, 100),
    evidenceAsof,
    checkedAt,
    trigger: text(body.trigger, 2000),
    sourceRunId: text(body.source_run_id, 300),
  };
}

function decisionSnapshot(state) {
  if (!state) return null;
  return {
    macro_state: state.macro_state,
    fed_state: state.fed_state,
    policy_market_state: state.policy_market_state,
    policy_direction: state.policy_direction,
    default_action: state.default_action,
  };
}

function decisionChanged(current, next) {
  if (!current) return true;
  const oldValue = decisionSnapshot(current);
  const newValue = {
    macro_state: next.macro,
    fed_state: next.fed,
    policy_market_state: next.relation,
    policy_direction: next.direction,
    default_action: next.defaultAction,
  };
  return JSON.stringify(oldValue) !== JSON.stringify(newValue);
}

async function readCurrent(env, regimeKey) {
  const row = await env.DB.prepare(`SELECT * FROM opportunity_regime_current WHERE regime_key=?`).bind(regimeKey).first();
  return parseCurrent(row);
}

async function putCurrent(request, env, regimeKey) {
  const authError = requireWriteAuth(request, env);
  if (authError) return authError;
  let body;
  try { body = await request.json(); } catch { return noStoreJson({ ok: false, error: "invalid_json" }, { status: 400 }); }
  try {
    const next = validateState(body || {});
    const current = await readCurrent(env, regimeKey);
    const currentVersion = Number(current?.version || 0);
    if (currentVersion !== next.expectedVersion) {
      return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: next.expectedVersion, current }, { status: 409 });
    }

    const changed = decisionChanged(current, next);
    const toVersion = current ? (changed ? currentVersion + 1 : currentVersion) : 1;
    const stateChangedAt = current && !changed ? current.state_changed_at : next.checkedAt;

    if (!current) {
      const transitionId = `${regimeKey}:v1`;
      const newStateJson = jsonText({
        macro_state: next.macro,
        fed_state: next.fed,
        policy_market_state: next.relation,
        policy_direction: next.direction,
        default_action: next.defaultAction,
      }, "new_state");
      try {
        await env.DB.batch([
          env.DB.prepare(`INSERT INTO opportunity_regime_current
            (regime_key,macro_state,fed_state,policy_market_state,policy_direction,default_action,
             evidence_json,confirmation_json,affected_exposures_json,source_session,evidence_asof,
             last_checked_at,state_changed_at,version,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)`)
            .bind(regimeKey,next.macro,next.fed,next.relation,next.direction,next.defaultAction,
              next.evidenceJson,next.confirmationJson,next.exposuresJson,next.sourceSession,next.evidenceAsof,
              next.checkedAt,stateChangedAt),
          env.DB.prepare(`INSERT INTO opportunity_regime_history
            (transition_id,regime_key,from_version,to_version,old_state_json,new_state_json,trigger,evidence_json,source_run_id,changed_at)
            VALUES(?,?,0,1,NULL,?,?,?,?,?)`)
            .bind(transitionId,regimeKey,newStateJson,next.trigger,next.evidenceJson,next.sourceRunId,next.checkedAt),
        ]);
      } catch {
        const raced = await readCurrent(env, regimeKey);
        return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: 0, current: raced }, { status: 409 });
      }
    } else if (changed) {
      const transitionId = `${regimeKey}:v${toVersion}`;
      const oldStateJson = jsonText(decisionSnapshot(current), "old_state");
      const newStateJson = jsonText({
        macro_state: next.macro,
        fed_state: next.fed,
        policy_market_state: next.relation,
        policy_direction: next.direction,
        default_action: next.defaultAction,
      }, "new_state");
      try {
        const results = await env.DB.batch([
          env.DB.prepare(`UPDATE opportunity_regime_current SET
            macro_state=?,fed_state=?,policy_market_state=?,policy_direction=?,default_action=?,
            evidence_json=?,confirmation_json=?,affected_exposures_json=?,source_session=?,evidence_asof=?,
            last_checked_at=?,state_changed_at=?,version=?,updated_at=CURRENT_TIMESTAMP
            WHERE regime_key=? AND version=?`)
            .bind(next.macro,next.fed,next.relation,next.direction,next.defaultAction,
              next.evidenceJson,next.confirmationJson,next.exposuresJson,next.sourceSession,next.evidenceAsof,
              next.checkedAt,stateChangedAt,toVersion,regimeKey,currentVersion),
          env.DB.prepare(`INSERT INTO opportunity_regime_history
            (transition_id,regime_key,from_version,to_version,old_state_json,new_state_json,trigger,evidence_json,source_run_id,changed_at)
            SELECT ?,?,?,?,?,?,?,?,?,?
            WHERE EXISTS (SELECT 1 FROM opportunity_regime_current WHERE regime_key=? AND version=?)`)
            .bind(transitionId,regimeKey,currentVersion,toVersion,oldStateJson,newStateJson,next.trigger,
              next.evidenceJson,next.sourceRunId,next.checkedAt,regimeKey,toVersion),
        ]);
        if (Number(results?.[0]?.meta?.changes || 0) !== 1 || Number(results?.[1]?.meta?.changes || 0) !== 1) {
          const raced = await readCurrent(env, regimeKey);
          return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: currentVersion, current: raced }, { status: 409 });
        }
      } catch {
        const raced = await readCurrent(env, regimeKey);
        return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: currentVersion, current: raced }, { status: 409 });
      }
    } else {
      const result = await env.DB.prepare(`UPDATE opportunity_regime_current SET
        evidence_json=?,confirmation_json=?,affected_exposures_json=?,source_session=?,evidence_asof=?,
        last_checked_at=?,updated_at=CURRENT_TIMESTAMP
        WHERE regime_key=? AND version=?`)
        .bind(next.evidenceJson,next.confirmationJson,next.exposuresJson,next.sourceSession,next.evidenceAsof,
          next.checkedAt,regimeKey,currentVersion).run();
      if (Number(result?.meta?.changes || 0) !== 1) {
        const raced = await readCurrent(env, regimeKey);
        return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: currentVersion, current: raced }, { status: 409 });
      }
    }

    const saved = await readCurrent(env, regimeKey);
    return noStoreJson({ ok: true, changed, version_changed: Boolean(changed), current: saved });
  } catch (err) {
    return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 });
  }
}

async function getHistory(env, regimeKey, url) {
  const rawLimit = Number.parseInt(url.searchParams.get("limit") || "20", 10);
  const limit = Math.min(100, Math.max(1, Number.isFinite(rawLimit) ? rawLimit : 20));
  const result = await env.DB.prepare(`SELECT transition_id,regime_key,from_version,to_version,
    old_state_json,new_state_json,trigger,evidence_json,source_run_id,changed_at,created_at
    FROM opportunity_regime_history WHERE regime_key=? ORDER BY to_version DESC LIMIT ?`)
    .bind(regimeKey, limit).all();
  const rows = (result?.results || []).map((row) => ({
    ...row,
    old_state: parseJson(row.old_state_json),
    new_state: parseJson(row.new_state_json),
    evidence: parseJson(row.evidence_json),
    old_state_json: undefined,
    new_state_json: undefined,
    evidence_json: undefined,
  }));
  return noStoreJson({ ok: true, regime_key: regimeKey, history: rows });
}

async function putCandidate(request, env, candidateKey) {
  const authError = requireWriteAuth(request, env);
  if (authError) return authError;
  let body;
  try { body = await request.json(); } catch { return noStoreJson({ ok: false, error: "invalid_json" }, { status: 400 }); }
  try {
    const regimeKey = key(body?.regime_key || "global", "regime_key");
    const current = await readCurrent(env, regimeKey);
    if (!current) return noStoreJson({ ok: false, error: "REGIME_NOT_FOUND" }, { status: 409 });
    const regimeVersion = Number.parseInt(body?.regime_version, 10);
    if (!Number.isInteger(regimeVersion) || regimeVersion !== current.version) {
      return noStoreJson({ ok: false, error: "REGIME_VERSION_CONFLICT", current_version: current.version }, { status: 409 });
    }
    const impact = text(body?.regime_impact, 30);
    if (impact && !ALLOWED_IMPACT.has(impact)) throw new Error("regime_impact_invalid");
    const checkedAt = text(body?.checked_at, 100) || new Date().toISOString();
    const exposureJson = jsonText(body?.exposure, "exposure");
    const impactNote = text(body?.impact_note, 10000);
    const sourceRowRef = text(body?.source_row_ref, 300);
    await env.DB.prepare(`INSERT INTO opportunity_candidate_regime_state
      (candidate_key,regime_key,exposure_json,regime_impact,impact_note,checked_at,regime_version,source_row_ref,updated_at)
      VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
      ON CONFLICT(candidate_key,regime_key) DO UPDATE SET
        exposure_json=excluded.exposure_json,
        regime_impact=excluded.regime_impact,
        impact_note=excluded.impact_note,
        checked_at=excluded.checked_at,
        regime_version=excluded.regime_version,
        source_row_ref=excluded.source_row_ref,
        updated_at=CURRENT_TIMESTAMP`)
      .bind(candidateKey,regimeKey,exposureJson,impact,impactNote,checkedAt,regimeVersion,sourceRowRef).run();
    const row = await env.DB.prepare(`SELECT * FROM opportunity_candidate_regime_state
      WHERE candidate_key=? AND regime_key=?`).bind(candidateKey,regimeKey).first();
    return noStoreJson({ ok: true, candidate: parseCandidate(row) });
  } catch (err) {
    return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 });
  }
}

async function getCandidate(request, env, candidateKey, url) {
  const authError = requireWriteAuth(request, env);
  if (authError) return authError;
  let regimeKey;
  try { regimeKey = key(url.searchParams.get("regime_key") || "global", "regime_key"); }
  catch (err) { return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 }); }
  const row = await env.DB.prepare(`SELECT * FROM opportunity_candidate_regime_state
    WHERE candidate_key=? AND regime_key=?`).bind(candidateKey,regimeKey).first();
  return noStoreJson({ ok: true, candidate: parseCandidate(row) });
}

async function getStaleCandidates(request, env, regimeKey, url) {
  const authError = requireWriteAuth(request, env);
  if (authError) return authError;
  const current = await readCurrent(env, regimeKey);
  if (!current) return noStoreJson({ ok: true, regime_key: regimeKey, current_version: null, candidates: [] });
  const rawLimit = Number.parseInt(url.searchParams.get("limit") || "100", 10);
  const limit = Math.min(500, Math.max(1, Number.isFinite(rawLimit) ? rawLimit : 100));
  const result = await env.DB.prepare(`SELECT * FROM opportunity_candidate_regime_state
    WHERE regime_key=? AND regime_version < ? ORDER BY regime_version ASC, checked_at ASC LIMIT ?`)
    .bind(regimeKey,current.version,limit).all();
  return noStoreJson({
    ok: true,
    regime_key: regimeKey,
    current_version: current.version,
    candidates: (result?.results || []).map(parseCandidate),
  });
}

export async function handleOpportunityRegime(request, env, url) {
  if (!url.pathname.startsWith("/opportunity-radar/regime/")) return null;
  const dbError = requireDb(env);
  if (dbError) return dbError;

  let match = url.pathname.match(/^\/opportunity-radar\/regime\/current\/([^/]+)$/);
  if (match) {
    let regimeKey;
    try { regimeKey = key(decodeURIComponent(match[1]), "regime_key"); }
    catch (err) { return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 }); }
    if (request.method === "GET") return noStoreJson({ ok: true, current: await readCurrent(env, regimeKey) });
    if (request.method === "PUT") return putCurrent(request, env, regimeKey);
    return noStoreJson({ ok: false, error: "method_not_allowed" }, { status: 405 });
  }

  match = url.pathname.match(/^\/opportunity-radar\/regime\/history\/([^/]+)$/);
  if (match) {
    if (request.method !== "GET") return noStoreJson({ ok: false, error: "method_not_allowed" }, { status: 405 });
    let regimeKey;
    try { regimeKey = key(decodeURIComponent(match[1]), "regime_key"); }
    catch (err) { return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 }); }
    return getHistory(env, regimeKey, url);
  }

  match = url.pathname.match(/^\/opportunity-radar\/regime\/candidates\/([^/]+)$/);
  if (match) {
    let candidateKey;
    try { candidateKey = key(decodeURIComponent(match[1]), "candidate_key"); }
    catch (err) { return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 }); }
    if (request.method === "PUT") return putCandidate(request, env, candidateKey);
    if (request.method === "GET") return getCandidate(request, env, candidateKey, url);
    return noStoreJson({ ok: false, error: "method_not_allowed" }, { status: 405 });
  }

  match = url.pathname.match(/^\/opportunity-radar\/regime\/stale\/([^/]+)$/);
  if (match) {
    if (request.method !== "GET") return noStoreJson({ ok: false, error: "method_not_allowed" }, { status: 405 });
    let regimeKey;
    try { regimeKey = key(decodeURIComponent(match[1]), "regime_key"); }
    catch (err) { return noStoreJson({ ok: false, error: String(err?.message || err) }, { status: 400 }); }
    return getStaleCandidates(request, env, regimeKey, url);
  }

  return noStoreJson({ ok: false, error: "not_found" }, { status: 404 });
}
