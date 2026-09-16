import {
  PERSONAL_MODEL_VERSION,
  CONTENT_INTELLIGENCE_CONTRACT_VERSION,
  PERSONAL_POLICY_VERSION,
  PROFILE_STATE_KEY,
  profileProjectionCte,
} from "./content-personalization.js";
import { INTEREST_ONTOLOGY_VERSION } from "./content-interest-ontology.js";

function bounded(value, fallback, max) {
  const parsed = Number.parseInt(String(value ?? fallback), 10);
  return Math.min(max, Math.max(1, Number.isFinite(parsed) ? parsed : fallback));
}

function signalReason(row) {
  if (Number(row.signal || 0) < 0) return "latest-explicit-disliked";
  if (row.liked_at) return "latest-explicit-liked";
  if (Number(row.interest_saved || 0) > 0) return "interest_saved";
  if (Number(row.saved || 0) > 0) return "saved";
  if (Number(row.deep_read || 0) > 0) return "deep_read";
  if (Number(row.selected || 0) > 0) return "selected";
  return "interaction";
}

function evidenceItem(row) {
  if (!row?.item_id) return null;
  return {
    item_id: String(row.item_id),
    canonical_url: row.canonical_url || null,
    title: row.title || null,
    source_type: row.source_type || null,
    source_name: row.source_name || null,
    signal: Number(row.signal || 0),
    signal_reason: signalReason(row),
    recency_factor: Number(row.recency_factor || 0),
    contribution: Number(row.contribution || 0),
    last_event_at: row.last_event_at || null,
    follow_up_count: Number(row.follow_up_count || 0),
    feature_weight: row.feature_weight == null ? null : Number(row.feature_weight),
    feature_confidence: row.feature_confidence == null ? null : Number(row.feature_confidence),
  };
}

function groupRows(rows, kind) {
  const output = [];
  const index = new Map();
  for (const row of rows || []) {
    const key = kind === "family"
      ? String(row.family_key || "")
      : `${row.feature_type}::${row.feature_key}`;
    if (!key) continue;
    let node = index.get(key);
    if (!node) {
      const base = {
        weight: Number(row.weight || 0),
        evidence_count: Number(row.evidence_count || 0),
        positive_count: Number(row.positive_count || 0),
        negative_count: Number(row.negative_count || 0),
        confidence: Number(row.confidence || 0),
        updated_at: row.updated_at || null,
        evidence: [],
      };
      node = kind === "family"
        ? { family_key: String(row.family_key), ...base }
        : { feature_type: String(row.feature_type), feature_key: String(row.feature_key), ...base };
      index.set(key, node);
      output.push(node);
    }
    const item = evidenceItem(row);
    if (item) node.evidence.push(item);
  }
  return output;
}

export async function buildInterestEvidenceSnapshot(env, options = {}) {
  if (!env?.DB) return { ok: false, error: "D1_NOT_BOUND" };
  const profileLimit = bounded(options.profileLimit, 30, 100);
  const familyLimit = bounded(options.familyLimit, 20, 50);
  const evidencePerNode = bounded(options.evidencePerNode, 6, 12);
  const projection = profileProjectionCte();
  const signalColumns = [
    "s.signal", "s.recency_factor", "s.last_event_at", "s.liked_at", "s.disliked_at",
    "s.interest_saved", "s.saved", "s.deep_read", "s.selected", "s.follow_up_count",
  ].join(",");

  const leafResult = await env.DB.prepare(`${projection},
    leaf_nodes AS (
      SELECT feature_type,feature_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at
      FROM interest_profile
      ORDER BY ABS(weight) DESC,confidence DESC,evidence_count DESC LIMIT ?
    ),
    leaf_evidence AS (
      SELECT p.feature_type,p.feature_key,f.item_id,${signalColumns},
        f.weight AS feature_weight,f.confidence AS feature_confidence,
        (s.signal*s.recency_factor*f.weight*f.confidence) AS contribution,
        i.canonical_url,i.title,i.source_type,i.source_name,
        ROW_NUMBER() OVER (
          PARTITION BY p.feature_type,p.feature_key
          ORDER BY ABS(s.signal*s.recency_factor*f.weight*f.confidence) DESC,
                   s.last_event_at DESC,f.item_id
        ) AS evidence_rank
      FROM leaf_nodes p
      JOIN normalized_features f
        ON f.feature_type=p.feature_type AND f.feature_key=p.feature_key
      JOIN item_signal s ON s.item_id=f.item_id AND s.signal<>0
      JOIN content_items i ON i.item_id=f.item_id
    )
    SELECT p.feature_type,p.feature_key,p.weight,p.evidence_count,p.positive_count,
      p.negative_count,p.confidence,p.updated_at,
      e.item_id,e.signal,e.recency_factor,e.last_event_at,e.liked_at,e.disliked_at,
      e.interest_saved,e.saved,e.deep_read,e.selected,e.follow_up_count,
      e.feature_weight,e.feature_confidence,e.contribution,
      e.canonical_url,e.title,e.source_type,e.source_name
    FROM leaf_nodes p
    LEFT JOIN leaf_evidence e
      ON e.feature_type=p.feature_type AND e.feature_key=p.feature_key
     AND e.evidence_rank<=?
    ORDER BY ABS(p.weight) DESC,p.confidence DESC,p.evidence_count DESC,e.evidence_rank
  `).bind(profileLimit,evidencePerNode).all();

  const familyResult = await env.DB.prepare(`${projection},
    family_nodes AS (
      SELECT family_key,weight,evidence_count,positive_count,negative_count,confidence,updated_at
      FROM interest_family_profile
      ORDER BY ABS(weight) DESC,confidence DESC,evidence_count DESC LIMIT ?
    ),
    family_evidence AS (
      SELECT p.family_key,fi.item_id,${signalColumns},
        fi.item_raw_weight AS contribution,
        fi.family_confidence AS feature_confidence,
        i.canonical_url,i.title,i.source_type,i.source_name,
        ROW_NUMBER() OVER (
          PARTITION BY p.family_key
          ORDER BY ABS(fi.item_raw_weight) DESC,s.last_event_at DESC,fi.item_id
        ) AS evidence_rank
      FROM family_nodes p
      JOIN family_item fi ON fi.family_key=p.family_key
      JOIN item_signal s ON s.item_id=fi.item_id
      JOIN content_items i ON i.item_id=fi.item_id
    )
    SELECT p.family_key,p.weight,p.evidence_count,p.positive_count,p.negative_count,
      p.confidence,p.updated_at,
      e.item_id,e.signal,e.recency_factor,e.last_event_at,e.liked_at,e.disliked_at,
      e.interest_saved,e.saved,e.deep_read,e.selected,e.follow_up_count,
      NULL AS feature_weight,e.feature_confidence,e.contribution,
      e.canonical_url,e.title,e.source_type,e.source_name
    FROM family_nodes p
    LEFT JOIN family_evidence e ON e.family_key=p.family_key AND e.evidence_rank<=?
    ORDER BY ABS(p.weight) DESC,p.confidence DESC,p.evidence_count DESC,e.evidence_rank
  `).bind(familyLimit,evidencePerNode).all();

  const state = await env.DB.prepare(
    "SELECT status,updated_at FROM workflow_state WHERE source=?"
  ).bind(PROFILE_STATE_KEY).first();
  const profile = groupRows(leafResult?.results || [], "leaf");
  const families = groupRows(familyResult?.results || [], "family");
  return {
    ok: true,
    schema: "content-intelligence-interest-evidence-v1",
    generated_at: new Date().toISOString(),
    derived: true,
    source_of_truth: "cloudflare-d1:user_content_events",
    model_version: PERSONAL_MODEL_VERSION,
    contract_version: CONTENT_INTELLIGENCE_CONTRACT_VERSION,
    policy_version: PERSONAL_POLICY_VERSION,
    ontology_version: INTEREST_ONTOLOGY_VERSION,
    signal_policy: "latest-explicit-wins + interaction-recency-decay",
    minimum_independent_signaled_items: 2,
    projection_state: state?.status || "missing",
    projection_state_updated_at: state?.updated_at || null,
    projection_consistent: state?.status === "clean",
    limits: {
      profile: profileLimit,
      families: familyLimit,
      evidence_per_node: evidencePerNode,
    },
    counts: {
      profile_nodes: profile.length,
      family_nodes: families.length,
      evidence_links: profile.reduce((n, x) => n + x.evidence.length, 0)
        + families.reduce((n, x) => n + x.evidence.length, 0),
    },
    profile,
    families,
  };
}
