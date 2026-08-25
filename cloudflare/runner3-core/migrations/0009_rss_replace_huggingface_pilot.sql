-- Hugging Face serves a thin JS shell to the direct fetch path in this environment.
-- Replace that temporary pilot row with a direct-readable public English source.

DELETE FROM rss_articles
WHERE article_id = 'huggingface-url-d556a48bace2bfaa6a70';

INSERT INTO rss_articles (
  article_id, stable_key, canonical_url, source_key, source_name,
  source_language, item_type, title, published_at, fetch_status,
  translation_status
) VALUES (
  'rasa-url-71191f21386ea1a88a22',
  'rasa:url:71191f21386ea1a88a22',
  'https://rasa.com/blog/agent-orchestration-tools',
  'rasa', 'Rasa', 'en', 'article',
  '10 Best AI Agent Orchestration Tools in 2026',
  '2026-05-18T00:00:00Z', 'pending', 'pending'
)
ON CONFLICT(canonical_url) DO UPDATE SET
  stable_key = excluded.stable_key,
  source_key = excluded.source_key,
  source_name = excluded.source_name,
  source_language = excluded.source_language,
  item_type = excluded.item_type,
  title = excluded.title,
  published_at = excluded.published_at,
  updated_at = CURRENT_TIMESTAMP;
