-- Personal Library durable catalog. Separate from runner3-core operational D1.
CREATE TABLE IF NOT EXISTS library_file_index_v1 (
  library_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  title TEXT,
  creator TEXT,
  series TEXT,
  volume INTEGER,
  format TEXT,
  file_name TEXT,
  size INTEGER,
  chat_id TEXT NOT NULL,
  topic_id INTEGER,
  message_id INTEGER NOT NULL,
  telegram_link TEXT,
  source TEXT,
  source_message_id INTEGER,
  tags TEXT,
  search_text TEXT,
  indexed_at TEXT,
  row_hash TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_library_file_index_category ON library_file_index_v1(category);
CREATE INDEX IF NOT EXISTS idx_library_file_index_title ON library_file_index_v1(title);
CREATE INDEX IF NOT EXISTS idx_library_file_index_creator ON library_file_index_v1(creator);
CREATE INDEX IF NOT EXISTS idx_library_file_index_series ON library_file_index_v1(series);
CREATE INDEX IF NOT EXISTS idx_library_file_index_updated ON library_file_index_v1(updated_at DESC);

CREATE TABLE IF NOT EXISTS library_index_meta_v1 (
  k TEXT PRIMARY KEY,
  v TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO library_index_meta_v1(k,v,updated_at)
VALUES('schema_version','1',CURRENT_TIMESTAMP)
ON CONFLICT(k) DO UPDATE SET v=excluded.v,updated_at=CURRENT_TIMESTAMP;
