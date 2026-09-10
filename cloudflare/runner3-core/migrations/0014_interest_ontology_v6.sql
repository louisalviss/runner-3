-- Interest ontology v6 cleanup. Raw content_items and user_content_events are intentionally untouched.

-- Remove title-derived feature noise emitted only by semantic-bridge-v3.
DELETE FROM content_features
WHERE model_version='semantic-bridge-v3'
  AND (
    feature_type='keyword'
    OR (feature_type='concept' AND confidence BETWEEN 0.6199 AND 0.6201)
  );

-- Canonical semantic namespace: lowercase kebab-case for legacy underscore keys.
-- OR IGNORE preserves an already-existing canonical row on a per-item collision;
-- the second DELETE removes only the redundant legacy spelling left by that collision.
UPDATE OR IGNORE content_features
SET feature_key=lower(replace(feature_key,'_','-')), updated_at=CURRENT_TIMESTAMP
WHERE feature_type IN ('topic','concept','mechanism','story_attribute','method','workflow','trend','product')
  AND instr(feature_key,'_')>0;
DELETE FROM content_features
WHERE feature_type IN ('topic','concept','mechanism','story_attribute','method','workflow','trend','product')
  AND instr(feature_key,'_')>0;

UPDATE OR IGNORE content_features
SET feature_key=lower(feature_key), updated_at=CURRENT_TIMESTAMP
WHERE feature_type IN ('topic','concept','mechanism','story_attribute','method','workflow','trend','product')
  AND feature_key<>lower(feature_key);
DELETE FROM content_features
WHERE feature_type IN ('topic','concept','mechanism','story_attribute','method','workflow','trend','product')
  AND feature_key<>lower(feature_key);

-- Force the canonical Core materializer to rebuild the derived profile once v6 is live.
INSERT INTO workflow_state(source,status,run_id,detail,updated_at)
VALUES('content-intelligence-profile','dirty',NULL,'{"reason":"interest_ontology_v6_cleanup"}',datetime('now','-5 hours'))
ON CONFLICT(source) DO UPDATE SET
  status='dirty', run_id=NULL, detail=excluded.detail, updated_at=excluded.updated_at;
DELETE FROM workflow_state WHERE source='content-intelligence-profile-last-recompute';
