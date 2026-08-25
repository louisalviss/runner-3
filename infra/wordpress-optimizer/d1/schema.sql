PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_meta (key, value, updated_at)
VALUES ('schema_version', '1', CURRENT_TIMESTAMP)
ON CONFLICT(key) DO UPDATE SET
  value = excluded.value,
  updated_at = CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS sites (
  site_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  public_url TEXT NOT NULL,
  origin_url TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  current_deployment TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candidates (
  candidate_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  parameters_json TEXT NOT NULL DEFAULT '{}',
  commit_sha TEXT,
  artifact_prefix TEXT,
  status TEXT NOT NULL DEFAULT 'proposed',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(site_id) REFERENCES sites(site_id)
);

CREATE TABLE IF NOT EXISTS optimization_runs (
  run_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  baseline_run_id TEXT,
  candidate_id TEXT,
  workflow_name TEXT,
  workflow_run_id TEXT,
  workflow_job_id TEXT,
  status TEXT NOT NULL,
  verdict TEXT,
  commit_sha TEXT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(site_id) REFERENCES sites(site_id),
  FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
);

CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  sample_no INTEGER NOT NULL,
  valid INTEGER NOT NULL DEFAULT 1 CHECK(valid IN (0,1)),
  performance REAL,
  accessibility REAL,
  best_practices REAL,
  seo REAL,
  fcp_ms REAL,
  lcp_ms REAL,
  tbt_ms REAL,
  cls REAL,
  collector TEXT,
  result_url TEXT,
  failure_reason TEXT,
  raw_artifact_key TEXT,
  measured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  raw_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(run_id) REFERENCES optimization_runs(run_id),
  UNIQUE(run_id, phase, sample_no)
);

CREATE TABLE IF NOT EXISTS gates (
  run_id TEXT NOT NULL,
  gate_name TEXT NOT NULL,
  status TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(run_id, gate_name),
  FOREIGN KEY(run_id) REFERENCES optimization_runs(run_id)
);

CREATE TABLE IF NOT EXISTS decisions (
  run_id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL CHECK(verdict IN ('KEEP_CANDIDATE','ROLLBACK','INCONCLUSIVE')),
  baseline_median_lcp_ms REAL,
  candidate_median_lcp_ms REAL,
  tolerance_ms REAL,
  reason TEXT,
  decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  details_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(run_id) REFERENCES optimization_runs(run_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  r2_key TEXT,
  url TEXT,
  sha256 TEXT,
  bytes INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES optimization_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_site_started
  ON optimization_runs(site_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_run_phase
  ON measurements(run_id, phase, sample_no);
CREATE INDEX IF NOT EXISTS idx_candidates_site_created
  ON candidates(site_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_kind
  ON artifacts(run_id, kind);
