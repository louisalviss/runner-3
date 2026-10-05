const VERSION = "business-opportunity-ledger-v1";
const MAX_KEY_CHARS = 200;
const MAX_TEXT_CHARS = 4000;
const ALLOWED_STATUS = new Set([
  "DISCOVERED","RESEARCHING","WATCH","VALIDATED_CANDIDATE",
  "INVESTIGATE","TEST","PROJECT","WTP","PILOT","EXECUTE",
  "HOLD","DROP","KILL",
]);
const ALLOWED_DIRECTION = new Set(["SUPPORT","COUNTER","NEUTRAL"]);

function noStoreJson(value, status = 200) {
  return Response.json(value, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "x-r3-business-opportunity-ledger": VERSION,
    },
  });
}

function db(env) {
  return env.BUSINESS_OPPORTUNITY_DB || null;
}

function requireDb(env) {
  if (!db(env)) return noStoreJson({ ok: false, error: "BUSINESS_OPPORTUNITY_D1_NOT_BOUND", version: VERSION }, 503);
  return null;
}

function requireAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return noStoreJson({ ok: false, error: "WRITE_AUTH_NOT_CONFIGURED" }, 503);
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return noStoreJson({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function text(value, max = MAX_TEXT_CHARS) {
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

function timestamp(value, name) {
  const out = text(value, 100);
  if (!out) return null;
  if (!Number.isFinite(Date.parse(out))) throw new Error(`${name}_invalid`);
  return out;
}

function bool(value, fallback = false) {
  if (value == null) return fallback;
  if (value === true || value === 1 || value === "1" || value === "true") return true;
  if (value === false || value === 0 || value === "0" || value === "false") return false;
  throw new Error("boolean_invalid");
}

function score(value, fallback = null) {
  if (value == null || value === "") return fallback;
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0 || n > 10) throw new Error("score_invalid");
  return n;
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value ?? ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function normalizeIdentity(type, value) {
  const raw = text(value, 2000);
  if (!raw) throw new Error("identity_value_required");
  const kind = text(type, 60)?.toLowerCase();
  if (!kind) throw new Error("identity_type_required");
  if (kind === "domain") return raw.toLowerCase().replace(/^www\./, "").replace(/\.$/, "");
  if (kind === "url") {
    try {
      const u = new URL(raw);
      u.protocol = u.protocol.toLowerCase();
      u.hostname = u.hostname.toLowerCase();
      u.hash = "";
      if ((u.protocol === "https:" && u.port === "443") || (u.protocol === "http:" && u.port === "80")) u.port = "";
      if (u.pathname.length > 1) u.pathname = u.pathname.replace(/\/+$/, "");
      return u.toString();
    } catch {
      throw new Error("identity_url_invalid");
    }
  }
  return raw.replace(/\s+/g, " ").toLowerCase();
}

function parseCandidate(row) {
  if (!row) return null;
  return {
    candidate_id: row.candidate_id,
    normalized_problem: row.normalized_problem,
    thesis_version: row.thesis_version,
    project_id: row.project_id,
    status: row.status,
    score: row.score == null ? null : Number(row.score),
    next_gate: row.next_gate,
    decision_reason: row.decision_reason,
    source_lane: row.source_lane,
    research_terminal: Number(row.research_terminal || 0) === 1,
    research_terminal_at: row.research_terminal_at,
    last_material_delta_at: row.last_material_delta_at,
    version: Number(row.version || 0),
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function parseIdentity(row) {
  if (!row) return null;
  return {
    identity_id: row.identity_id,
    candidate_id: row.candidate_id,
    identity_type: row.identity_type,
    identity_value: row.identity_value,
    identity_sha256: row.identity_sha256,
    source_lane: row.source_lane,
    created_at: row.created_at,
  };
}

function parseEvidence(row) {
  if (!row) return null;
  return {
    evidence_id: row.evidence_id,
    candidate_id: row.candidate_id,
    source_lane: row.source_lane,
    source_ref: row.source_ref,
    source_ref_sha256: row.source_ref_sha256,
    evidence_type: row.evidence_type,
    independence_group: row.independence_group,
    hard_signal: Number(row.hard_signal || 0) === 1,
    direction: row.direction,
    observed_at: row.observed_at,
    evidence_hash: row.evidence_hash,
    note: row.note,
    created_at: row.created_at,
  };
}

async function readCandidate(env, candidateId) {
  const row = await db(env).prepare(
    "SELECT * FROM business_opportunity_candidate WHERE candidate_id=?"
  ).bind(candidateId).first();
  return parseCandidate(row);
}

function candidateSnapshot(candidate) {
  return {
    normalized_problem: candidate.normalized_problem,
    thesis_version: candidate.thesis_version,
    project_id: candidate.project_id,
    status: candidate.status,
    score: candidate.score,
    next_gate: candidate.next_gate,
    decision_reason: candidate.decision_reason,
    source_lane: candidate.source_lane,
    research_terminal: Boolean(candidate.research_terminal),
    research_terminal_at: candidate.research_terminal_at,
    last_material_delta_at: candidate.last_material_delta_at,
  };
}

function candidateEquivalent(a, b) {
  return JSON.stringify(candidateSnapshot(a)) === JSON.stringify(candidateSnapshot(b));
}

function decisionChanged(a, b) {
  if (!a) return true;
  return a.status !== b.status ||
    a.next_gate !== b.next_gate ||
    a.thesis_version !== b.thesis_version ||
    Boolean(a.research_terminal) !== Boolean(b.research_terminal);
}

function validateCandidate(body, current = null) {
  const checkedAt = timestamp(body?.checked_at, "checked_at") || new Date().toISOString();
  const normalizedProblem = text(body?.normalized_problem, 2000) || current?.normalized_problem;
  if (!normalizedProblem) throw new Error("normalized_problem_required");
  const status = text(body?.status, 40) || current?.status || "DISCOVERED";
  if (!ALLOWED_STATUS.has(status)) throw new Error("status_invalid");
  const researchTerminal = bool(body?.research_terminal, current?.research_terminal || false);
  let researchTerminalAt;
  if (researchTerminal) {
    researchTerminalAt = timestamp(body?.research_terminal_at, "research_terminal_at") ||
      current?.research_terminal_at || checkedAt;
  } else {
    researchTerminalAt = body && Object.prototype.hasOwnProperty.call(body, "research_terminal_at")
      ? timestamp(body.research_terminal_at, "research_terminal_at")
      : current?.research_terminal_at || null;
  }
  return {
    normalized_problem: normalizedProblem,
    thesis_version: body && Object.prototype.hasOwnProperty.call(body, "thesis_version")
      ? text(body.thesis_version, 300) : current?.thesis_version || null,
    project_id: body && Object.prototype.hasOwnProperty.call(body, "project_id")
      ? text(body.project_id, 300) : current?.project_id || null,
    status,
    score: body && Object.prototype.hasOwnProperty.call(body, "score")
      ? score(body.score, null) : current?.score ?? null,
    next_gate: body && Object.prototype.hasOwnProperty.call(body, "next_gate")
      ? text(body.next_gate, MAX_TEXT_CHARS) : current?.next_gate || null,
    decision_reason: body && Object.prototype.hasOwnProperty.call(body, "decision_reason")
      ? text(body.decision_reason, MAX_TEXT_CHARS) : current?.decision_reason || null,
    source_lane: body && Object.prototype.hasOwnProperty.call(body, "source_lane")
      ? text(body.source_lane, 200) : current?.source_lane || null,
    research_terminal: researchTerminal,
    research_terminal_at: researchTerminalAt,
    last_material_delta_at: body && Object.prototype.hasOwnProperty.call(body, "last_material_delta_at")
      ? timestamp(body.last_material_delta_at, "last_material_delta_at")
      : current?.last_material_delta_at || null,
    checked_at: checkedAt,
    transition_reason: text(body?.transition_reason, MAX_TEXT_CHARS),
    evidence_snapshot_hash: text(body?.evidence_snapshot_hash, 128),
  };
}

async function putCandidate(request, env, candidateId) {
  let body;
  try { body = await request.json(); }
  catch { return noStoreJson({ ok: false, error: "invalid_json" }, 400); }

  try {
    const current = await readCandidate(env, candidateId);
    const expectedVersion = Number.parseInt(body?.expected_version, 10);
    if (!Number.isInteger(expectedVersion) || expectedVersion < 0) throw new Error("expected_version_invalid");
    const currentVersion = Number(current?.version || 0);
    if (currentVersion !== expectedVersion) {
      return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: expectedVersion, current }, 409);
    }

    const next = validateCandidate(body || {}, current);
    const nextCandidate = {
      candidate_id: candidateId,
      ...next,
      version: current ? currentVersion + 1 : 1,
    };

    if (current && candidateEquivalent(current, nextCandidate)) {
      return noStoreJson({ ok: true, changed: false, transition: false, current });
    }

    const changedDecision = decisionChanged(current, nextCandidate);
    if (!current) {
      const transitionId = `${candidateId}:v1`;
      await db(env).batch([
        db(env).prepare(`INSERT INTO business_opportunity_candidate
          (candidate_id,normalized_problem,thesis_version,project_id,status,score,next_gate,decision_reason,
           source_lane,research_terminal,research_terminal_at,last_material_delta_at,version,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)`)
          .bind(candidateId,next.normalized_problem,next.thesis_version,next.project_id,next.status,next.score,
            next.next_gate,next.decision_reason,next.source_lane,next.research_terminal ? 1 : 0,
            next.research_terminal_at,next.last_material_delta_at),
        db(env).prepare(`INSERT INTO business_opportunity_transition
          (transition_id,candidate_id,from_version,to_version,from_status,to_status,old_next_gate,new_next_gate,
           reason,evidence_snapshot_hash,changed_at)
          VALUES(?,?,0,1,NULL,?,NULL,?,?,?,?)`)
          .bind(transitionId,candidateId,next.status,next.next_gate,next.transition_reason || "candidate_created",
            next.evidence_snapshot_hash,next.checked_at),
      ]);
    } else {
      const toVersion = currentVersion + 1;
      const statements = [
        db(env).prepare(`UPDATE business_opportunity_candidate SET
          normalized_problem=?,thesis_version=?,project_id=?,status=?,score=?,next_gate=?,decision_reason=?,
          source_lane=?,research_terminal=?,research_terminal_at=?,last_material_delta_at=?,version=?,
          updated_at=CURRENT_TIMESTAMP
          WHERE candidate_id=? AND version=?`)
          .bind(next.normalized_problem,next.thesis_version,next.project_id,next.status,next.score,next.next_gate,
            next.decision_reason,next.source_lane,next.research_terminal ? 1 : 0,next.research_terminal_at,
            next.last_material_delta_at,toVersion,candidateId,currentVersion),
      ];
      if (changedDecision) {
        statements.push(
          db(env).prepare(`INSERT INTO business_opportunity_transition
            (transition_id,candidate_id,from_version,to_version,from_status,to_status,old_next_gate,new_next_gate,
             reason,evidence_snapshot_hash,changed_at)
            SELECT ?,?,?,?,?,?,?,?,?,?,?
            WHERE EXISTS (
              SELECT 1 FROM business_opportunity_candidate WHERE candidate_id=? AND version=?
            )`)
            .bind(`${candidateId}:v${toVersion}`,candidateId,currentVersion,toVersion,current.status,next.status,
              current.next_gate,next.next_gate,next.transition_reason || "candidate_updated",
              next.evidence_snapshot_hash,next.checked_at,candidateId,toVersion)
        );
      }
      const results = await db(env).batch(statements);
      if (Number(results?.[0]?.meta?.changes || 0) !== 1) {
        return noStoreJson({ ok: false, error: "VERSION_CONFLICT", expected_version: currentVersion, current: await readCandidate(env, candidateId) }, 409);
      }
    }
    const saved = await readCandidate(env, candidateId);
    return noStoreJson({ ok: true, changed: true, transition: changedDecision, current: saved });
  } catch (error) {
    return noStoreJson({ ok: false, error: String(error?.message || error) }, 400);
  }
}

async function getCandidateDetail(env, candidateId, url) {
  const candidate = await readCandidate(env, candidateId);
  if (!candidate) return noStoreJson({ ok: false, error: "CANDIDATE_NOT_FOUND" }, 404);
  const rawLimit = Number.parseInt(url.searchParams.get("limit") || "50", 10);
  const limit = Math.min(100, Math.max(1, Number.isFinite(rawLimit) ? rawLimit : 50));
  const [identities, evidence, transitions] = await db(env).batch([
    db(env).prepare(`SELECT * FROM business_opportunity_identity
      WHERE candidate_id=? ORDER BY created_at ASC LIMIT ?`).bind(candidateId, limit),
    db(env).prepare(`SELECT * FROM business_opportunity_evidence
      WHERE candidate_id=? ORDER BY observed_at DESC, created_at DESC LIMIT ?`).bind(candidateId, limit),
    db(env).prepare(`SELECT * FROM business_opportunity_transition
      WHERE candidate_id=? ORDER BY to_version DESC LIMIT ?`).bind(candidateId, limit),
  ]);
  return noStoreJson({
    ok: true,
    candidate,
    identities: (identities?.results || []).map(parseIdentity),
    evidence: (evidence?.results || []).map(parseEvidence),
    transitions: transitions?.results || [],
  });
}

async function listCandidates(env, url) {
  const rawLimit = Number.parseInt(url.searchParams.get("limit") || "50", 10);
  const limit = Math.min(200, Math.max(1, Number.isFinite(rawLimit) ? rawLimit : 50));
  const status = text(url.searchParams.get("status"), 40);
  if (status && !ALLOWED_STATUS.has(status)) return noStoreJson({ ok: false, error: "status_invalid" }, 400);
  const projectId = text(url.searchParams.get("project_id"), 300);
  let sql = "SELECT * FROM business_opportunity_candidate";
  const where = [];
  const binds = [];
  if (status) { where.push("status=?"); binds.push(status); }
  if (projectId) { where.push("project_id=?"); binds.push(projectId); }
  if (where.length) sql += " WHERE " + where.join(" AND ");
  sql += " ORDER BY updated_at DESC LIMIT ?";
  binds.push(limit);
  const result = await db(env).prepare(sql).bind(...binds).all();
  return noStoreJson({ ok: true, candidates: (result?.results || []).map(parseCandidate) });
}

async function addIdentity(request, env) {
  let body;
  try { body = await request.json(); }
  catch { return noStoreJson({ ok: false, error: "invalid_json" }, 400); }
  try {
    const candidateId = key(body?.candidate_id, "candidate_id");
    const candidate = await readCandidate(env, candidateId);
    if (!candidate) return noStoreJson({ ok: false, error: "CANDIDATE_NOT_FOUND" }, 404);
    const identityType = text(body?.identity_type, 60)?.toLowerCase();
    if (!identityType || !/^[a-z0-9._:-]+$/.test(identityType)) throw new Error("identity_type_invalid");
    const normalized = normalizeIdentity(identityType, body?.identity_value);
    const digest = await sha256Hex(normalized);
    const identityId = `${identityType}:${digest}`;
    const existing = await db(env).prepare(`SELECT * FROM business_opportunity_identity
      WHERE identity_type=? AND identity_sha256=?`).bind(identityType,digest).first();
    if (existing) {
      if (existing.candidate_id !== candidateId) {
        return noStoreJson({ ok: false, error: "IDENTITY_CONFLICT", identity: parseIdentity(existing) }, 409);
      }
      return noStoreJson({ ok: true, changed: false, identity: parseIdentity(existing) });
    }
    await db(env).prepare(`INSERT INTO business_opportunity_identity
      (identity_id,candidate_id,identity_type,identity_value,identity_sha256,source_lane)
      VALUES(?,?,?,?,?,?)`)
      .bind(identityId,candidateId,identityType,normalized,digest,text(body?.source_lane,200)).run();
    const saved = await db(env).prepare(`SELECT * FROM business_opportunity_identity
      WHERE identity_id=?`).bind(identityId).first();
    return noStoreJson({ ok: true, changed: true, identity: parseIdentity(saved) });
  } catch (error) {
    return noStoreJson({ ok: false, error: String(error?.message || error) }, 400);
  }
}

async function putEvidence(request, env, evidenceId) {
  let body;
  try { body = await request.json(); }
  catch { return noStoreJson({ ok: false, error: "invalid_json" }, 400); }
  try {
    const candidateId = key(body?.candidate_id, "candidate_id");
    if (!(await readCandidate(env, candidateId))) return noStoreJson({ ok: false, error: "CANDIDATE_NOT_FOUND" }, 404);
    const sourceLane = text(body?.source_lane, 200);
    if (!sourceLane) throw new Error("source_lane_required");
    const evidenceType = text(body?.evidence_type, 200);
    if (!evidenceType) throw new Error("evidence_type_required");
    const direction = (text(body?.direction, 20) || "NEUTRAL").toUpperCase();
    if (!ALLOWED_DIRECTION.has(direction)) throw new Error("direction_invalid");
    const observedAt = timestamp(body?.observed_at, "observed_at") || new Date().toISOString();
    const sourceRef = text(body?.source_ref, 2000);
    const sourceRefSha = sourceRef ? await sha256Hex(sourceRef) : null;
    const note = text(body?.note, 2000);
    const suppliedHash = text(body?.evidence_hash, 128);
    const evidenceHash = suppliedHash || await sha256Hex(JSON.stringify({
      candidate_id: candidateId,
      source_lane: sourceLane,
      source_ref: sourceRef,
      evidence_type: evidenceType,
      independence_group: text(body?.independence_group, 300),
      direction,
      observed_at: observedAt,
      note,
    }));
    const duplicate = await db(env).prepare(`SELECT * FROM business_opportunity_evidence
      WHERE candidate_id=? AND evidence_hash=?`).bind(candidateId,evidenceHash).first();
    if (duplicate && duplicate.evidence_id !== evidenceId) {
      return noStoreJson({ ok: true, changed: false, deduped: true, evidence: parseEvidence(duplicate) });
    }
    const existing = await db(env).prepare(`SELECT * FROM business_opportunity_evidence
      WHERE evidence_id=?`).bind(evidenceId).first();
    if (existing && existing.candidate_id !== candidateId) {
      return noStoreJson({ ok: false, error: "EVIDENCE_ID_CONFLICT", evidence: parseEvidence(existing) }, 409);
    }
    await db(env).prepare(`INSERT INTO business_opportunity_evidence
      (evidence_id,candidate_id,source_lane,source_ref,source_ref_sha256,evidence_type,independence_group,
       hard_signal,direction,observed_at,evidence_hash,note)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(evidence_id) DO UPDATE SET
        source_lane=excluded.source_lane,
        source_ref=excluded.source_ref,
        source_ref_sha256=excluded.source_ref_sha256,
        evidence_type=excluded.evidence_type,
        independence_group=excluded.independence_group,
        hard_signal=excluded.hard_signal,
        direction=excluded.direction,
        observed_at=excluded.observed_at,
        evidence_hash=excluded.evidence_hash,
        note=excluded.note`)
      .bind(evidenceId,candidateId,sourceLane,sourceRef,sourceRefSha,evidenceType,
        text(body?.independence_group,300),bool(body?.hard_signal,false) ? 1 : 0,
        direction,observedAt,evidenceHash,note).run();
    const saved = await db(env).prepare(`SELECT * FROM business_opportunity_evidence
      WHERE evidence_id=?`).bind(evidenceId).first();
    return noStoreJson({ ok: true, changed: true, evidence: parseEvidence(saved) });
  } catch (error) {
    return noStoreJson({ ok: false, error: String(error?.message || error) }, 400);
  }
}

async function resolveIdentity(env, identityType, identityValue) {
  const kind = text(identityType, 60)?.toLowerCase();
  if (!kind || !/^[a-z0-9._:-]+$/.test(kind)) throw new Error("identity_type_invalid");
  const normalized = normalizeIdentity(kind, identityValue);
  const digest = await sha256Hex(normalized);
  const row = await db(env).prepare(`SELECT c.*
    FROM business_opportunity_identity i
    JOIN business_opportunity_candidate c ON c.candidate_id=i.candidate_id
    WHERE i.identity_type=? AND i.identity_sha256=?`)
    .bind(kind,digest).first();
  return parseCandidate(row);
}

async function reconcile(request, env) {
  let body;
  try { body = await request.json(); }
  catch { return noStoreJson({ ok: false, error: "invalid_json" }, 400); }
  try {
    let candidate = null;
    if (body?.candidate_id) {
      candidate = await readCandidate(env, key(body.candidate_id, "candidate_id"));
    } else if (body?.identity_type && body?.identity_value) {
      candidate = await resolveIdentity(env, body.identity_type, body.identity_value);
    } else {
      throw new Error("candidate_or_identity_required");
    }

    if (!candidate) {
      return noStoreJson({
        ok: true,
        decision: "NEW_CANDIDATE",
        research_allowed: true,
        reason: "NO_EXISTING_IDENTITY",
        candidate: null,
      });
    }

    const incomingThesis = text(body?.thesis_version, 300);
    if (incomingThesis && candidate.thesis_version && incomingThesis !== candidate.thesis_version) {
      return noStoreJson({
        ok: true,
        decision: "RESEARCH_ALLOWED",
        research_allowed: true,
        reason: "THESIS_CHANGED",
        candidate,
      });
    }

    if (!candidate.research_terminal) {
      return noStoreJson({
        ok: true,
        decision: "RESEARCH_ALLOWED",
        research_allowed: true,
        reason: "RESEARCH_NOT_TERMINAL",
        candidate,
      });
    }

    const terminalMs = candidate.research_terminal_at ? Date.parse(candidate.research_terminal_at) : NaN;
    const deltaMs = candidate.last_material_delta_at ? Date.parse(candidate.last_material_delta_at) : NaN;
    if (Number.isFinite(deltaMs) && (!Number.isFinite(terminalMs) || deltaMs > terminalMs)) {
      return noStoreJson({
        ok: true,
        decision: "RESEARCH_ALLOWED",
        research_allowed: true,
        reason: "MATERIAL_DELTA_AFTER_TERMINAL",
        candidate,
      });
    }

    return noStoreJson({
      ok: true,
      decision: "NO_RECHECK",
      research_allowed: false,
      reason: "UNCHANGED_TERMINAL_THESIS",
      next_gate: candidate.next_gate,
      candidate,
    });
  } catch (error) {
    return noStoreJson({ ok: false, error: String(error?.message || error) }, 400);
  }
}

async function health(env) {
  const meta = await db(env).prepare(
    "SELECT value FROM business_opportunity_meta WHERE key='schema_version'"
  ).first();
  const [candidates, identities, evidence] = await db(env).batch([
    db(env).prepare("SELECT COUNT(*) AS n FROM business_opportunity_candidate"),
    db(env).prepare("SELECT COUNT(*) AS n FROM business_opportunity_identity"),
    db(env).prepare("SELECT COUNT(*) AS n FROM business_opportunity_evidence"),
  ]);
  return noStoreJson({
    ok: true,
    version: VERSION,
    schema_version: meta?.value || null,
    counts: {
      candidates: Number(candidates?.results?.[0]?.n || 0),
      identities: Number(identities?.results?.[0]?.n || 0),
      evidence: Number(evidence?.results?.[0]?.n || 0),
    },
  });
}

export async function handleBusinessOpportunityLedger(request, env, url) {
  if (!url.pathname.startsWith("/business-opportunity/")) return null;
  const dbError = requireDb(env);
  if (dbError) return dbError;
  const authError = requireAuth(request, env);
  if (authError) return authError;

  if (url.pathname === "/business-opportunity/health") {
    if (request.method !== "GET") return noStoreJson({ ok: false, error: "method_not_allowed" }, 405);
    return health(env);
  }

  if (url.pathname === "/business-opportunity/reconcile") {
    if (request.method !== "POST") return noStoreJson({ ok: false, error: "method_not_allowed" }, 405);
    return reconcile(request, env);
  }

  if (url.pathname === "/business-opportunity/identities") {
    if (request.method !== "POST") return noStoreJson({ ok: false, error: "method_not_allowed" }, 405);
    return addIdentity(request, env);
  }

  if (url.pathname === "/business-opportunity/candidates") {
    if (request.method !== "GET") return noStoreJson({ ok: false, error: "method_not_allowed" }, 405);
    return listCandidates(env, url);
  }

  let match = url.pathname.match(/^\/business-opportunity\/candidates\/([^/]+)$/);
  if (match) {
    let candidateId;
    try { candidateId = key(decodeURIComponent(match[1]), "candidate_id"); }
    catch (error) { return noStoreJson({ ok: false, error: String(error?.message || error) }, 400); }
    if (request.method === "GET") return getCandidateDetail(env, candidateId, url);
    if (request.method === "PUT") return putCandidate(request, env, candidateId);
    return noStoreJson({ ok: false, error: "method_not_allowed" }, 405);
  }

  match = url.pathname.match(/^\/business-opportunity\/evidence\/([^/]+)$/);
  if (match) {
    let evidenceId;
    try { evidenceId = key(decodeURIComponent(match[1]), "evidence_id"); }
    catch (error) { return noStoreJson({ ok: false, error: String(error?.message || error) }, 400); }
    if (request.method === "PUT") return putEvidence(request, env, evidenceId);
    return noStoreJson({ ok: false, error: "method_not_allowed" }, 405);
  }

  return noStoreJson({ ok: false, error: "not_found" }, 404);
}
