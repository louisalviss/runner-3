-- RSS Library searchable catalog + deterministic R2 object keys.
-- Idempotent because deploy currently replays all migrations.

UPDATE rss_articles
SET
  original_object_key = COALESCE(original_object_key, 'rss/original/' || article_id || '.txt'),
  vi_object_key = CASE
    WHEN source_language = 'vi' THEN NULL
    ELSE COALESCE(vi_object_key, 'rss/vi/' || article_id || '.txt')
  END,
  updated_at = CURRENT_TIMESTAMP
WHERE article_id IN (
  'projectsyndicate-url-26a9686e21ebe4fa865d',
  'projectsyndicate-url-db223b141f372578df3c',
  'genk-165260824141950644',
  'fulcrum-url-a87e54dbda2e37fe40a7',
  'tinhte-4171630',
  'nghiencuuquocte-url-6cd04807aefc80d9be93'
);

CREATE VIRTUAL TABLE IF NOT EXISTS rss_articles_fts USING fts5(
  article_id UNINDEXED,
  title,
  source_name,
  source_key
);

INSERT INTO rss_articles_fts(rowid, article_id, title, source_name, source_key)
SELECT a.rowid, a.article_id, a.title, a.source_name, a.source_key
FROM rss_articles a
WHERE NOT EXISTS (
  SELECT 1 FROM rss_articles_fts f WHERE f.rowid = a.rowid
);

CREATE TRIGGER IF NOT EXISTS rss_articles_fts_ai
AFTER INSERT ON rss_articles BEGIN
  INSERT INTO rss_articles_fts(rowid, article_id, title, source_name, source_key)
  VALUES (new.rowid, new.article_id, new.title, new.source_name, new.source_key);
END;

CREATE TRIGGER IF NOT EXISTS rss_articles_fts_ad
AFTER DELETE ON rss_articles BEGIN
  DELETE FROM rss_articles_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS rss_articles_fts_au
AFTER UPDATE ON rss_articles BEGIN
  DELETE FROM rss_articles_fts WHERE rowid = old.rowid;
  INSERT INTO rss_articles_fts(rowid, article_id, title, source_name, source_key)
  VALUES (new.rowid, new.article_id, new.title, new.source_name, new.source_key);
END;
