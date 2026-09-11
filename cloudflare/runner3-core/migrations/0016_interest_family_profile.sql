-- Keep durable semantic interests and derived family aggregation physically separate.
CREATE TABLE IF NOT EXISTS interest_family_profile (
  family_key TEXT PRIMARY KEY,
  weight REAL NOT NULL DEFAULT 0,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  positive_count INTEGER NOT NULL DEFAULT 0,
  negative_count INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- v7 previously materialized family rows into interest_profile. They are
-- derived and will be rebuilt from immutable events/features after deploy.
DELETE FROM interest_profile WHERE feature_type='family';
