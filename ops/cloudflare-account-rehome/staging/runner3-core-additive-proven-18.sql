-- REVIEW CANDIDATE ONLY: DO NOT EXECUTE on Cloudflare without fresh target sqlite_master preflight, safety review, and authorization.
-- Authenticated source DDL+PK/column fingerprint matches: 18/18 (run 39826582807). SOURCE is production authority.
-- Covers 9 Core tables + 9 indexes. Does NOT cover typed_kv, r2_receipts or d1_migrations.
-- No rows, auth material, Worker, cron, R2 or deployment in this file.

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);

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

CREATE TABLE IF NOT EXISTS artifact_library_magic_links (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_artifact_library_magic_links_expires_at
  ON artifact_library_magic_links(expires_at);

CREATE TABLE IF NOT EXISTS vps_mailbox_jobs (
  request_id TEXT PRIMARY KEY,
  envelope_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','claimed','done','failed','cancelled')),
  attempts INTEGER NOT NULL DEFAULT 0,
  lease_owner TEXT,
  lease_until INTEGER,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vps_mailbox_jobs_claim
  ON vps_mailbox_jobs(status, lease_until, created_at);

CREATE TABLE IF NOT EXISTS artifact_library_auth (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  salt TEXT NOT NULL,
  pin_hash TEXT NOT NULL,
  iterations INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_library_pin_attempts (
  client_hash TEXT PRIMARY KEY,
  window_started_at INTEGER NOT NULL,
  failures INTEGER NOT NULL,
  blocked_until INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_library_pin_attempts_blocked_until
  ON artifact_library_pin_attempts(blocked_until);

CREATE TABLE IF NOT EXISTS delivery_permalinks (
  token_hash TEXT PRIMARY KEY,
  project TEXT NOT NULL,
  scope TEXT NOT NULL,
  name TEXT NOT NULL,
  object_key TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  revoked_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_delivery_permalinks_object_key
  ON delivery_permalinks(object_key);

CREATE INDEX IF NOT EXISTS idx_delivery_permalinks_active
  ON delivery_permalinks(revoked_at);

CREATE TABLE IF NOT EXISTS ebook_reader_trace_v113(
      trace_id TEXT NOT NULL,seq INTEGER NOT NULL,created_at INTEGER NOT NULL,
      scope TEXT NOT NULL DEFAULT '',mode TEXT NOT NULL DEFAULT '',event TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(trace_id,seq));

CREATE INDEX IF NOT EXISTS idx_ebook_reader_trace_v113_created ON ebook_reader_trace_v113(created_at DESC);
