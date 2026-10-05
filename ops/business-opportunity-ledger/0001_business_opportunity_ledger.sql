PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS business_opportunity_candidate (
  candidate_id TEXT PRIMARY KEY,
  normalized_problem TEXT NOT NULL,
  thesis_version TEXT,
  project_id TEXT,
  status TEXT NOT NULL CHECK (status IN (
    'DISCOVERED','RESEARCHING','WATCH','VALIDATED_CANDIDATE',
    'INVESTIGATE','TEST','PROJECT','WTP','PILOT','EXECUTE',
    'HOLD','DROP','KILL'
  )),
  score REAL,
  next_gate TEXT,
  decision_reason TEXT,
  source_lane TEXT,
  research_terminal INTEGER NOT NULL DEFAULT 0 CHECK (research_terminal IN (0,1)),
  research_terminal_at TEXT,
  last_material_delta_at TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bizopp_candidate_status
  ON business_opportunity_candidate(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_bizopp_candidate_project
  ON business_opportunity_candidate(project_id);
CREATE INDEX IF NOT EXISTS idx_bizopp_candidate_delta
  ON business_opportunity_candidate(last_material_delta_at);

CREATE TABLE IF NOT EXISTS business_opportunity_identity (
  identity_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  identity_type TEXT NOT NULL,
  identity_value TEXT NOT NULL,
  identity_sha256 TEXT NOT NULL,
  source_lane TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(candidate_id) REFERENCES business_opportunity_candidate(candidate_id) ON DELETE CASCADE,
  UNIQUE(identity_type, identity_sha256)
);

CREATE INDEX IF NOT EXISTS idx_bizopp_identity_candidate
  ON business_opportunity_identity(candidate_id);

CREATE TABLE IF NOT EXISTS business_opportunity_evidence (
  evidence_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  source_lane TEXT NOT NULL,
  source_ref TEXT,
  source_ref_sha256 TEXT,
  evidence_type TEXT NOT NULL,
  independence_group TEXT,
  hard_signal INTEGER NOT NULL DEFAULT 0 CHECK (hard_signal IN (0,1)),
  direction TEXT NOT NULL CHECK (direction IN ('SUPPORT','COUNTER','NEUTRAL')),
  observed_at TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(candidate_id) REFERENCES business_opportunity_candidate(candidate_id) ON DELETE CASCADE,
  UNIQUE(candidate_id, evidence_hash)
);

CREATE INDEX IF NOT EXISTS idx_bizopp_evidence_candidate
  ON business_opportunity_evidence(candidate_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_bizopp_evidence_independence
  ON business_opportunity_evidence(candidate_id, independence_group);
CREATE INDEX IF NOT EXISTS idx_bizopp_evidence_hard
  ON business_opportunity_evidence(candidate_id, hard_signal, direction);

CREATE TABLE IF NOT EXISTS business_opportunity_transition (
  transition_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  from_version INTEGER NOT NULL,
  to_version INTEGER NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  old_next_gate TEXT,
  new_next_gate TEXT,
  reason TEXT,
  evidence_snapshot_hash TEXT,
  changed_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(candidate_id) REFERENCES business_opportunity_candidate(candidate_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bizopp_transition_candidate
  ON business_opportunity_transition(candidate_id, to_version DESC);

CREATE TABLE IF NOT EXISTS business_opportunity_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO business_opportunity_meta(key,value,updated_at)
VALUES('schema_version','1',CURRENT_TIMESTAMP)
ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP;
