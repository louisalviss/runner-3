-- The two Project Syndicate pilot fetches resolved only short direct-access excerpts
-- (697 / 932 chars in production proof), not full article bodies. Do not present
-- those snapshots as full originals and never translate them as if complete.

UPDATE rss_articles
SET
  fetch_status = 'blocked',
  translation_status = 'blocked_source',
  current_version_id = NULL,
  original_object_key = NULL,
  vi_object_key = NULL,
  source_checksum = NULL,
  translation_checksum = NULL,
  translation_version = NULL,
  qa_state = 'source_incomplete',
  last_error = 'INCOMPLETE_RESTRICTED_SOURCE_DIRECT_ONLY',
  updated_at = CURRENT_TIMESTAMP
WHERE article_id IN (
  'projectsyndicate-url-26a9686e21ebe4fa865d',
  'projectsyndicate-url-db223b141f372578df3c'
);
