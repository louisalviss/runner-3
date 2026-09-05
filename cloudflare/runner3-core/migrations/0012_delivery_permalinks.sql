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
