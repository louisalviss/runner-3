-- Content Intelligence schema
-- Global structured store for RSS + X + Facebook + Reddit + web + YouTube.
-- Raw copyrighted/source bodies stay in R2; D1 stores identity, features, events and scores.

CREATE TABLE IF NOT EXISTS content_items (
  item_id TEXT PRIMARY KEY,
  canonical_url TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,
  source_name TEXT,
  source_key TEXT,
  title TEXT,
  published_at TEXT,
  captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
  language TEXT,
  raw_ref TEXT,
  content_hash TEXT,
  metadata_json TEXT,
  first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_content_items_source_type ON content_items(source_type);
CREATE INDEX IF NOT EXISTS idx_content_items_source_key ON content_items(source_key);
CREATE INDEX IF NOT EXISTS idx_content_items_published_at ON content_items(published_at);
CREATE INDEX IF NOT EXISTS idx_content_items_last_seen_at ON content_items(last_seen_at);

CREATE TABLE IF NOT EXISTS content_features (
  item_id TEXT NOT NULL,
  feature_type TEXT NOT NULL,
  feature_key TEXT NOT NULL,
  feature_value TEXT,
  weight REAL DEFAULT 1,
  confidence REAL DEFAULT 1,
  model_version TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (item_id, feature_type, feature_key),
  FOREIGN KEY (item_id) REFERENCES content_items(item_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_content_features_lookup ON content_features(feature_type, feature_key);

CREATE TABLE IF NOT EXISTS user_content_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL,
  render_id TEXT,
  event_type TEXT NOT NULL,
  assistant_recommended INTEGER DEFAULT 0,
  assistant_rank INTEGER,
  explicit_feedback TEXT,
  context_json TEXT,
  event_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (item_id) REFERENCES content_items(item_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_content_events_item ON user_content_events(item_id);
CREATE INDEX IF NOT EXISTS idx_user_content_events_type ON user_content_events(event_type);
CREATE INDEX IF NOT EXISTS idx_user_content_events_at ON user_content_events(event_at);
CREATE INDEX IF NOT EXISTS idx_user_content_events_render ON user_content_events(render_id);

CREATE TABLE IF NOT EXISTS content_scores (
  item_id TEXT NOT NULL,
  score_type TEXT NOT NULL,
  score REAL NOT NULL,
  confidence REAL DEFAULT 1,
  reason_json TEXT,
  model_version TEXT NOT NULL,
  scored_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (item_id, score_type, model_version),
  FOREIGN KEY (item_id) REFERENCES content_items(item_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_content_scores_type_score ON content_scores(score_type, score DESC);

CREATE TABLE IF NOT EXISTS interest_profile (
  feature_type TEXT NOT NULL,
  feature_key TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 0,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  positive_count INTEGER NOT NULL DEFAULT 0,
  negative_count INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (feature_type, feature_key)
);

CREATE TABLE IF NOT EXISTS recommendation_runs (
  render_id TEXT PRIMARY KEY,
  source_scope TEXT,
  item_count INTEGER DEFAULT 0,
  recommended_count INTEGER DEFAULT 0,
  exploration_ratio REAL,
  model_version TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  metadata_json TEXT
);
