#!/usr/bin/env python3
from pathlib import Path

P=Path('cloudflare/runner3-core/src/content-personalization.js')
C=Path('scripts/content_intelligence_client.py')
R=Path('.github/workflows/content-intelligence-v2-test.yml')

p=P.read_text(encoding='utf-8')
old='''  const before = await profileState(env);\n  if (!before) return { ok: true, recomputed: false, status: "missing" };\n  if (before.status === "clean") return { ok: true, recomputed: false, status: "clean" };\n\n  const token = await acquireRecomputeLease(env, modelVersion);\n'''
new='''  const before = await profileState(env);\n  if (!before) return { ok: true, recomputed: false, status: "missing" };\n  if (before.status === "clean") {\n    const materialized = await env.DB.prepare(\n      "SELECT 1 AS ok FROM content_scores WHERE score_type='personal_relevance' AND model_version=? LIMIT 1"\n    ).bind(modelVersion).first();\n    if (materialized?.ok) return { ok: true, recomputed: false, status: "clean" };\n    await env.DB.prepare(`\n      UPDATE workflow_state\n      SET status='dirty', run_id=NULL, detail=?, updated_at=CURRENT_TIMESTAMP\n      WHERE source=? AND status='clean'\n    `).bind(JSON.stringify({ reason: "model_materialization_missing", model: modelVersion }), PROFILE_STATE_KEY).run();\n  }\n\n  const token = await acquireRecomputeLease(env, modelVersion);\n'''
if p.count(old)!=1: raise SystemExit('maybeRecompute clean marker mismatch')
p=p.replace(old,new,1)
P.write_text(p,encoding='utf-8')

c=C.read_text(encoding='utf-8')
old='DEFAULT_PERSONAL_MODEL = "personal-v2"'
new='DEFAULT_PERSONAL_MODEL = "personal-v3"'
if c.count(old)!=1: raise SystemExit('default personal model marker mismatch')
c=c.replace(old,new,1)
C.write_text(c,encoding='utf-8')

r=R.read_text(encoding='utf-8')
old="          grep -q 'result\\[\"materialization\"\\] = materialization' scripts/content_intelligence_client.py\n"
new=old+"          grep -q 'DEFAULT_PERSONAL_MODEL = \"personal-v3\"' scripts/content_intelligence_client.py\n          grep -q 'model_materialization_missing' cloudflare/runner3-core/src/content-personalization.js\n"
if r.count(old)!=1: raise SystemExit('regression marker mismatch')
r=r.replace(old,new,1)
R.write_text(r,encoding='utf-8')
print('INTEREST_V3_MODEL_BOOTSTRAP_PATCH_APPLIED')
