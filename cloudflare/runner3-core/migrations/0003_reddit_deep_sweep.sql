-- Reddit Deep Sweep operational/content index.
-- Raw source payloads stay in private R2; D1 keeps normalized searchable records.

CREATE TABLE IF NOT EXISTS reddit_scan_runs (
  run_id TEXT PRIMARY KEY,
  subreddit TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  posts_seen INTEGER NOT NULL DEFAULT 0,
  threads_fetched INTEGER NOT NULL DEFAULT 0,
  comments_seen INTEGER NOT NULL DEFAULT 0,
  raw_object_key TEXT,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_reddit_scan_runs_subreddit_started
  ON reddit_scan_runs(subreddit, started_at DESC);

CREATE TABLE IF NOT EXISTS reddit_posts (
  post_id TEXT PRIMARY KEY,
  subreddit TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT,
  author TEXT,
  created_utc INTEGER,
  score INTEGER,
  num_comments INTEGER,
  body_text TEXT,
  body_hash TEXT,
  quality_score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'indexed',
  source_sorts TEXT,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_thread_fetch_at TEXT,
  comments_snapshot_count INTEGER NOT NULL DEFAULT 0,
  raw_object_key TEXT
);

CREATE INDEX IF NOT EXISTS idx_reddit_posts_subreddit_quality
  ON reddit_posts(subreddit, quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_reddit_posts_subreddit_created
  ON reddit_posts(subreddit, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_reddit_posts_subreddit_seen
  ON reddit_posts(subreddit, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS reddit_comments (
  comment_id TEXT PRIMARY KEY,
  post_id TEXT NOT NULL,
  parent_id TEXT,
  author TEXT,
  depth INTEGER NOT NULL DEFAULT 0,
  body_text TEXT,
  body_hash TEXT,
  score INTEGER,
  created_utc INTEGER,
  quality_score REAL NOT NULL DEFAULT 0,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reddit_comments_post
  ON reddit_comments(post_id);
CREATE INDEX IF NOT EXISTS idx_reddit_comments_quality
  ON reddit_comments(post_id, quality_score DESC);

CREATE TABLE IF NOT EXISTS reddit_post_tags (
  post_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (post_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_reddit_post_tags_tag
  ON reddit_post_tags(tag, weight DESC);
