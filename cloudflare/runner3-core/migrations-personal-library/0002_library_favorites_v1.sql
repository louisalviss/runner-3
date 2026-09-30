CREATE TABLE IF NOT EXISTS library_favorites_v1 (
  source TEXT NOT NULL,
  ref TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(source, ref)
);

CREATE INDEX IF NOT EXISTS idx_library_favorites_created_v1
ON library_favorites_v1(created_at DESC);

CREATE TABLE IF NOT EXISTS library_favorite_meta_v1 (
  k TEXT PRIMARY KEY,
  v TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
