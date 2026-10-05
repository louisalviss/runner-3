import fs from "node:fs";

const core = (process.env.CORE_URL || "https://runner3-core.ducduy2411.workers.dev").replace(/\/$/, "");
const token = String(process.env.RUNNER3_CORE_TOKEN || "").trim();
const seedPath = process.argv[2] || "ops/business-opportunity-ledger/canonical-seed.json";
if (!token) throw new Error("RUNNER3_CORE_TOKEN_REQUIRED");

const seed = JSON.parse(fs.readFileSync(seedPath, "utf8"));
const headers = { authorization: `Bearer ${token}`, "content-type": "application/json" };

async function api(path, init = {}) {
  const response = await fetch(core + path, { ...init, headers: { ...headers, ...(init.headers || {}) } });
  const text = await response.text();
  let body = null;
  try { body = JSON.parse(text); } catch {}
  if (!response.ok) {
    const err = new Error(`HTTP_${response.status}:${path}:${text.slice(0, 500)}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }
  return body;
}

async function currentCandidate(id) {
  const response = await fetch(core + "/business-opportunity/candidates/" + encodeURIComponent(id), {
    headers: { authorization: `Bearer ${token}` },
  });
  if (response.status === 404) return null;
  const text = await response.text();
  if (!response.ok) throw new Error(`HTTP_${response.status}:candidate_get:${text.slice(0,500)}`);
  return JSON.parse(text).candidate;
}

async function upsertCandidate(item) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const current = await currentCandidate(item.candidate_id);
    const payload = {
      expected_version: current?.version || 0,
      normalized_problem: item.normalized_problem,
      thesis_version: item.thesis_version,
      project_id: item.project_id,
      status: item.status,
      score: item.score ?? null,
      next_gate: item.next_gate ?? null,
      decision_reason: item.decision_reason,
      source_lane: item.source_lane || "PROJECTS_MAP",
      research_terminal: Boolean(item.research_terminal),
      research_terminal_at: item.research_terminal_at,
      last_material_delta_at: item.last_material_delta_at,
      checked_at: new Date().toISOString(),
      transition_reason: "canonical_portfolio_seed",
    };
    try {
      return await api("/business-opportunity/candidates/" + encodeURIComponent(item.candidate_id), {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } catch (error) {
      if (error.status !== 409 || attempt === 2) throw error;
    }
  }
  throw new Error("candidate_upsert_retry_exhausted");
}

for (const item of seed.candidates || []) {
  const saved = await upsertCandidate(item);
  for (const [identityType, identityValue] of item.identities || []) {
    await api("/business-opportunity/identities", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: item.candidate_id,
        identity_type: identityType,
        identity_value: identityValue,
        source_lane: item.source_lane || "PROJECTS_MAP",
      }),
    });
  }
  if (item.research_terminal) {
    const reconciled = await api("/business-opportunity/reconcile", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: item.candidate_id,
        thesis_version: item.thesis_version,
      }),
    });
    if (reconciled.decision !== "NO_RECHECK" || reconciled.research_allowed !== false) {
      throw new Error(`NO_RECHECK_ASSERTION_FAILED:${item.candidate_id}:${JSON.stringify(reconciled)}`);
    }
  }
  process.stdout.write(JSON.stringify({
    candidate_id: item.candidate_id,
    changed: Boolean(saved?.changed),
    version: saved?.current?.version ?? null,
    status: saved?.current?.status ?? item.status,
  }) + "\n");
}
