CREATE TABLE IF NOT EXISTS artifact_library_magic_links (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_artifact_library_magic_links_expires_at
  ON artifact_library_magic_links(expires_at);
