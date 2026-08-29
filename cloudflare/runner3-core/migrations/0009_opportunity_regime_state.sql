-- Opportunity Radar macro/regime machine-state authority.
-- D1 owns runtime state/version/history; Google Sheet is a human-readable projection.

CREATE TABLE IF NOT EXISTS opportunity_regime_current (
  regime_key TEXT PRIMARY KEY,
  macro_state TEXT NOT NULL,
  fed_state TEXT,
  policy_market_state TEXT NOT NULL,
  policy_direction TEXT,
  default_action TEXT,
  evidence_json TEXT,
  confirmation_json TEXT,
  affected_exposures_json TEXT,
  source_session TEXT,
  evidence_asof TEXT,
  last_checked_at TEXT NOT NULL,
  state_changed_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_opportunity_regime_current_version
  ON opportunity_regime_current(regime_key, version);

CREATE TABLE IF NOT EXISTS opportunity_regime_history (
  transition_id TEXT PRIMARY KEY,
  regime_key TEXT NOT NULL,
  from_version INTEGER NOT NULL,
  to_version INTEGER NOT NULL,
  old_state_json TEXT,
  new_state_json TEXT NOT NULL,
  trigger TEXT,
  evidence_json TEXT,
  source_run_id TEXT,
  changed_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(regime_key, to_version)
);
CREATE INDEX IF NOT EXISTS idx_opportunity_regime_history_key_version
  ON opportunity_regime_history(regime_key, to_version DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_regime_history_changed_at
  ON opportunity_regime_history(changed_at DESC);

CREATE TABLE IF NOT EXISTS opportunity_candidate_regime_state (
  candidate_key TEXT NOT NULL,
  regime_key TEXT NOT NULL DEFAULT 'global',
  exposure_json TEXT,
  regime_impact TEXT,
  impact_note TEXT,
  checked_at TEXT NOT NULL,
  regime_version INTEGER NOT NULL,
  source_row_ref TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(candidate_key, regime_key)
);
CREATE INDEX IF NOT EXISTS idx_opportunity_candidate_regime_stale
  ON opportunity_candidate_regime_state(regime_key, regime_version, checked_at);
