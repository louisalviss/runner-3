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
