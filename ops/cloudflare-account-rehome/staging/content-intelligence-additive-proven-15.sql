-- REVIEW ONLY: DO NOT AUTO-APPLY TO D1. Exact source schema metadata, run #39826582807.
-- 2 TABLE + 12 INDEX + 1 TRIGGER objects missing on target in historical source/target snapshot.
-- Depends on nine shared source/target schema objects; re-check target DDL and existing data before any SQL.
-- D1 rows transferred=0; worker deploys=0; R2 requests=0; cutover=false.

CREATE TABLE IF NOT EXISTS checkpoints (
  project TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'default',
  source TEXT NOT NULL,
  status TEXT,
  position TEXT,
  dropbox_path TEXT,
  last_error TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(project, scope)
);

CREATE TABLE IF NOT EXISTS workflow_state (
  source TEXT PRIMARY KEY,
  status TEXT,
  run_id TEXT,
  detail TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_source ON checkpoints(source);

CREATE INDEX IF NOT EXISTS idx_content_features_lookup ON content_features(feature_type, feature_key);

CREATE INDEX IF NOT EXISTS idx_content_items_published_at ON content_items(published_at);

CREATE INDEX IF NOT EXISTS idx_content_items_source_key ON content_items(source_key);

CREATE INDEX IF NOT EXISTS idx_content_items_source_type ON content_items(source_type);

CREATE INDEX IF NOT EXISTS idx_content_scores_type_score ON content_scores(score_type, score DESC);

CREATE INDEX IF NOT EXISTS idx_personal_score_stage_model_base
  ON personal_score_stage(model_version, base_score);

CREATE INDEX IF NOT EXISTS idx_user_content_events_at ON user_content_events(event_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_content_events_identity
ON user_content_events(item_id, event_type, render_id)
WHERE render_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_content_events_item ON user_content_events(item_id);

CREATE INDEX IF NOT EXISTS idx_user_content_events_render ON user_content_events(render_id);

CREATE INDEX IF NOT EXISTS idx_user_content_events_type ON user_content_events(event_type);

CREATE TRIGGER IF NOT EXISTS trg_user_content_events_render_dedupe
BEFORE INSERT ON user_content_events
WHEN NEW.render_id IS NOT NULL
 AND EXISTS (
   SELECT 1 FROM user_content_events
   WHERE item_id = NEW.item_id
     AND event_type = NEW.event_type
     AND render_id = NEW.render_id
 )
BEGIN
  SELECT RAISE(IGNORE);
END;
