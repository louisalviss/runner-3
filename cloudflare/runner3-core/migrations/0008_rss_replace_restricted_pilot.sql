-- Replace the two Project Syndicate pilot rows that cannot provide complete bodies
-- through the authorized direct route. Keep the pilot at exactly six articles.

DELETE FROM rss_articles
WHERE article_id IN (
  'projectsyndicate-url-26a9686e21ebe4fa865d',
  'projectsyndicate-url-db223b141f372578df3c'
);

INSERT INTO rss_articles (
  article_id, stable_key, canonical_url, source_key, source_name,
  source_language, item_type, title, published_at, fetch_status,
  translation_status
) VALUES
  (
    'huggingface-url-d556a48bace2bfaa6a70',
    'huggingface:url:d556a48bace2bfaa6a70',
    'https://huggingface.co/blog/state-of-open-models-summer-2026',
    'huggingface', 'Hugging Face', 'en', 'article',
    'State of Open Models: Summer 2026 Observations',
    '2026-08-14T00:00:00Z', 'pending', 'pending'
  ),
  (
    'cloudflare-url-781ba125e818919ba95e',
    'cloudflare:url:781ba125e818919ba95e',
    'https://blog.cloudflare.com/cloudflare-computer/',
    'cloudflare', 'Cloudflare Blog', 'en', 'article',
    'Your agent needs a computer, not a container — introducing @cloudflare/computer',
    '2026-08-03T00:00:00Z', 'pending', 'pending'
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
