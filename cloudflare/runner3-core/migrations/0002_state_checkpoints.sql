CREATE TABLE IF NOT EXISTS workflow_state (
  source TEXT PRIMARY KEY,
  status TEXT,
  run_id TEXT,
  detail TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

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

CREATE INDEX IF NOT EXISTS idx_checkpoints_source ON checkpoints(source);
