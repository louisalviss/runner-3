-- Ebook reader state belongs to the Personal Library domain.
-- Schema mirrors the live runner3-core reader tables; data is copied separately with INSERT OR IGNORE.

CREATE TABLE IF NOT EXISTS ebook_reader_progress_v65 (
  book_key TEXT PRIMARY KEY,
  cfi TEXT NOT NULL DEFAULT '',
  percent INTEGER,
  last_open_at INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ebook_reader_progress_v65_updated
  ON ebook_reader_progress_v65(updated_at DESC);

CREATE TABLE IF NOT EXISTS ebook_reader_state_v72 (
  scope TEXT PRIMARY KEY,
  book_key TEXT NOT NULL,
  cfi TEXT NOT NULL DEFAULT '',
  percent INTEGER,
  last_open_at INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0,
  source_client TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ebook_reader_state_v72_updated
  ON ebook_reader_state_v72(updated_at DESC);

CREATE TABLE IF NOT EXISTS ebook_reader_trace_v113 (
  trace_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  scope TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT '',
  event TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(trace_id,seq)
);
CREATE INDEX IF NOT EXISTS idx_ebook_reader_trace_v113_created
  ON ebook_reader_trace_v113(created_at DESC);
