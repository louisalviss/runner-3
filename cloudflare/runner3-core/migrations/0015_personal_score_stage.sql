CREATE TABLE IF NOT EXISTS personal_score_stage (
  model_version TEXT NOT NULL,
  item_id TEXT NOT NULL,
  relevance_signal REAL NOT NULL DEFAULT 0,
  matched_features INTEGER NOT NULL DEFAULT 0,
  semantic_matches INTEGER NOT NULL DEFAULT 0,
  semantic_weight REAL NOT NULL DEFAULT 0,
  novel_semantic_weight REAL NOT NULL DEFAULT 0,
  profile_confidence REAL NOT NULL DEFAULT 0,
  matched_families INTEGER NOT NULL DEFAULT 0,
  freshness_bonus REAL NOT NULL DEFAULT 0,
  novelty_bonus REAL NOT NULL DEFAULT 0,
  base_score REAL NOT NULL DEFAULT 50,
  staged_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (model_version, item_id)
);

CREATE INDEX IF NOT EXISTS idx_personal_score_stage_model_base
  ON personal_score_stage(model_version, base_score);
