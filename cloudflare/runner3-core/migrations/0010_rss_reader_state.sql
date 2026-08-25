-- Reader interaction state and explicit preference signals.
-- Source/article artifacts remain immutable in R2; delete is soft-delete only.

CREATE TABLE IF NOT EXISTS rss_reader_state (
  article_id TEXT PRIMARY KEY,
  lifecycle TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle IN ('active','archived','deleted')),
  featured INTEGER NOT NULL DEFAULT 0 CHECK (featured IN (0,1)),
  category TEXT,
  preference TEXT CHECK (preference IS NULL OR preference IN ('like','dislike')),
  last_opened_at TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (article_id) REFERENCES rss_articles(article_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rss_reader_state_lifecycle
  ON rss_reader_state(lifecycle, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_reader_state_featured
  ON rss_reader_state(featured, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_reader_state_category
  ON rss_reader_state(category, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_reader_state_preference
  ON rss_reader_state(preference, updated_at DESC);

CREATE TABLE IF NOT EXISTS rss_preference_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id TEXT NOT NULL,
  action TEXT NOT NULL,
  value TEXT,
  source_key TEXT,
  category TEXT,
  title_snapshot TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (article_id) REFERENCES rss_articles(article_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rss_preference_events_created
  ON rss_preference_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_preference_events_article
  ON rss_preference_events(article_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_preference_events_action
  ON rss_preference_events(action, created_at DESC);
