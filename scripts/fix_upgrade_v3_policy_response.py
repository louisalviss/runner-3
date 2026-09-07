#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/upgrade_content_intelligence_v3.py')
s = p.read_text(encoding='utf-8')
old = '''i = replace_once(
    i,
    'return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,rows:result.results||[]}); }',
    'return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,policy_version:PERSONAL_POLICY_VERSION,rows:result.results||[]}); }',
    "profile response policy",
)'''
new = '''old_policy_response = 'return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,rows:result.results||[]}); }'
new_policy_response = 'return Response.json({ok:true,model_version:PERSONAL_MODEL_VERSION,policy_version:PERSONAL_POLICY_VERSION,rows:result.results||[]}); }'
if i.count(old_policy_response) != 2:
    raise SystemExit(f"profile/scores policy response: expected 2 matches, got {i.count(old_policy_response)}")
i = i.replace(old_policy_response, new_policy_response, 2)'''
if old not in s:
    raise SystemExit('target patch block not found')
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('UPGRADE_V3_POLICY_RESPONSE_FIX_APPLIED')
