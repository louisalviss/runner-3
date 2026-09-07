#!/usr/bin/env python3
from pathlib import Path

P=Path('cloudflare/runner3-core/src/content-personalization.js')
C=Path('scripts/content_intelligence_client.py')

p=P.read_text(encoding='utf-8')
old='export const PROFILE_STATE_KEY = "content-intelligence-profile";\n'
new=old+'export const PROFILE_RECOMPUTE_CLOCK_KEY = "content-intelligence-profile-last-recompute";\n'
if p.count(old)!=1: raise SystemExit('PROFILE_STATE_KEY marker mismatch')
p=p.replace(old,new,1)

old='''  const result = await env.DB.prepare(`
    UPDATE workflow_state
    SET status='recomputing', run_id=?, detail=?, updated_at=CURRENT_TIMESTAMP
    WHERE source=? AND (
      (status='dirty' AND updated_at <= datetime('now',?))
      OR (status='recomputing' AND updated_at <= datetime('now',?))
    )
  `).bind(token, detail, PROFILE_STATE_KEY, agoModifier(RECOMPUTE_DEBOUNCE_MS), agoModifier(RECOMPUTE_LEASE_MS)).run();
'''
new='''  const result = await env.DB.prepare(`
    UPDATE workflow_state
    SET status='recomputing', run_id=?, detail=?, updated_at=CURRENT_TIMESTAMP
    WHERE source=? AND (
      (status='dirty' AND (
        NOT EXISTS(SELECT 1 FROM workflow_state WHERE source=?)
        OR EXISTS(SELECT 1 FROM workflow_state WHERE source=? AND updated_at <= datetime('now',?))
        OR NOT EXISTS(SELECT 1 FROM content_scores WHERE score_type='personal_relevance' AND model_version=?)
      ))
      OR (status='recomputing' AND updated_at <= datetime('now',?))
    )
  `).bind(
    token, detail, PROFILE_STATE_KEY,
    PROFILE_RECOMPUTE_CLOCK_KEY, PROFILE_RECOMPUTE_CLOCK_KEY, agoModifier(RECOMPUTE_DEBOUNCE_MS), modelVersion,
    agoModifier(RECOMPUTE_LEASE_MS),
  ).run();
'''
if p.count(old)!=1: raise SystemExit('acquire lease marker mismatch')
p=p.replace(old,new,1)

old='''  const result = await env.DB.prepare(`
    UPDATE workflow_state
    SET status='clean', run_id=NULL, detail=?, updated_at=CURRENT_TIMESTAMP
    WHERE source=? AND status='recomputing' AND run_id=?
  `).bind(JSON.stringify({ recomputed_at: new Date().toISOString(), model: modelVersion }), PROFILE_STATE_KEY, token).run();
  return Number(result.meta?.changes || 0) === 1;
'''
new='''  const recomputedAt = new Date().toISOString();
  const detail = JSON.stringify({ recomputed_at: recomputedAt, model: modelVersion });
  const result = await env.DB.prepare(`
    UPDATE workflow_state
    SET status='clean', run_id=NULL, detail=?, updated_at=CURRENT_TIMESTAMP
    WHERE source=? AND status='recomputing' AND run_id=?
  `).bind(detail, PROFILE_STATE_KEY, token).run();
  const committed = Number(result.meta?.changes || 0) === 1;
  if (committed) {
    await env.DB.prepare(`
      INSERT INTO workflow_state(source,status,run_id,detail,updated_at)
      VALUES(?, 'clean', NULL, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(source) DO UPDATE SET status='clean',run_id=NULL,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP
    `).bind(PROFILE_RECOMPUTE_CLOCK_KEY, detail).run();
  }
  return committed;
'''
if p.count(old)!=1: raise SystemExit('finish lease marker mismatch')
p=p.replace(old,new,1)
P.write_text(p,encoding='utf-8')

c=C.read_text(encoding='utf-8')
old='''def cmd_recommendation_snapshot(args: argparse.Namespace) -> int:
    payload = {"render_id": args.render_id, "snapshot_id": args.snapshot_id, "top_k": args.top_k}
    result = request_json("POST", "/content-intelligence/recommendations/snapshot", payload, core_url=args.core_url)
    text = json.dumps(result, ensure_ascii=False, sort_keys=True)
'''
new='''def cmd_recommendation_snapshot(args: argparse.Namespace) -> int:
    materialization: dict[str, Any]
    try:
        materialization = request_json(
            "POST", "/content-intelligence/profile/recompute",
            {"model_version": DEFAULT_PERSONAL_MODEL}, core_url=args.core_url,
        )
    except Exception as exc:
        materialization = {"ok": False, "error": str(exc), "guarded": True}
    payload = {"render_id": args.render_id, "snapshot_id": args.snapshot_id, "top_k": args.top_k}
    result = request_json("POST", "/content-intelligence/recommendations/snapshot", payload, core_url=args.core_url)
    result["materialization"] = materialization
    text = json.dumps(result, ensure_ascii=False, sort_keys=True)
'''
if c.count(old)!=1: raise SystemExit('snapshot client marker mismatch')
c=c.replace(old,new,1)
C.write_text(c,encoding='utf-8')
print('INTEREST_V3_RECOMPUTE_CLOCK_PATCH_APPLIED')
