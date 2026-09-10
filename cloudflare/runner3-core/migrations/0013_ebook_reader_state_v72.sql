-- Ebook Library unified single-owner progress state (v72)
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

WITH legacy AS (
  SELECT
    substr(
      book_key,
      length('core/ebook/') + 1,
      instr(substr(book_key, length('core/ebook/') + 1), '/') - 1
    ) AS scope,
    book_key, cfi, percent, last_open_at, updated_at,
    row_number() OVER (
      PARTITION BY substr(
        book_key,
        length('core/ebook/') + 1,
        instr(substr(book_key, length('core/ebook/') + 1), '/') - 1
      )
      ORDER BY updated_at DESC, last_open_at DESC
    ) AS rn
  FROM ebook_reader_progress_v65
  WHERE book_key LIKE 'core/ebook/%/final/%'
)
INSERT OR IGNORE INTO ebook_reader_state_v72(
  scope, book_key, cfi, percent, last_open_at, updated_at, source_client
)
SELECT scope, book_key, cfi, percent, last_open_at, updated_at, 'v65-migration'
FROM legacy
WHERE rn = 1 AND scope <> '';
