-- RSS Library catalog/state. Full article and translation bodies live in R2.

CREATE TABLE IF NOT EXISTS rss_articles (
  article_id TEXT PRIMARY KEY,
  stable_key TEXT NOT NULL UNIQUE,
  canonical_url TEXT NOT NULL UNIQUE,
  source_key TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_language TEXT NOT NULL DEFAULT 'en',
  item_type TEXT NOT NULL DEFAULT 'article',
  title TEXT NOT NULL,
  published_at TEXT,
  fetch_status TEXT NOT NULL DEFAULT 'pending',
  translation_status TEXT NOT NULL DEFAULT 'pending',
  current_version_id TEXT,
  original_object_key TEXT,
  vi_object_key TEXT,
  source_checksum TEXT,
  translation_checksum TEXT,
  translation_version TEXT,
  qa_state TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rss_articles_published
  ON rss_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_articles_source_published
  ON rss_articles(source_key, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_articles_fetch_status
  ON rss_articles(fetch_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rss_articles_translation_status
  ON rss_articles(translation_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS rss_article_versions (
  version_id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  source_checksum TEXT NOT NULL,
  object_key TEXT NOT NULL,
  fetch_route TEXT,
  resolved_url TEXT,
  content_chars INTEGER,
  truncated INTEGER NOT NULL DEFAULT 0,
  coverage TEXT,
  metadata TEXT,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (article_id) REFERENCES rss_articles(article_id) ON DELETE CASCADE,
  UNIQUE(article_id, source_checksum)
);

CREATE INDEX IF NOT EXISTS idx_rss_article_versions_article_fetched
  ON rss_article_versions(article_id, fetched_at DESC);

CREATE TABLE IF NOT EXISTS rss_translations (
  translation_id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  target_language TEXT NOT NULL DEFAULT 'vi',
  source_checksum TEXT NOT NULL,
  translation_checksum TEXT,
  object_key TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  translation_version TEXT,
  glossary_version TEXT,
  source_section_count INTEGER,
  translated_section_count INTEGER,
  coverage_ratio REAL,
  coverage_qa TEXT,
  consistency_qa TEXT,
  qa_state TEXT,
  metadata TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (article_id) REFERENCES rss_articles(article_id) ON DELETE CASCADE,
  FOREIGN KEY (version_id) REFERENCES rss_article_versions(version_id) ON DELETE CASCADE,
  UNIQUE(version_id, target_language)
);

CREATE INDEX IF NOT EXISTS idx_rss_translations_article_status
  ON rss_translations(article_id, target_language, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS rss_processing_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (article_id) REFERENCES rss_articles(article_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rss_processing_events_article_created
  ON rss_processing_events(article_id, created_at DESC);
