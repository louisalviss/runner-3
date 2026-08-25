const RESTRICTED_DIRECT_ONLY = new Set(["projectsyndicate", "economist", "theatlantic"]);
const MAX_IMAGES = 24;

function safeImages(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  const seen = new Set();
  for (const item of value) {
    if (out.length >= MAX_IMAGES) break;
    const url = String(item?.url || "").trim();
    if (!/^https?:\/\//i.test(url) || seen.has(url)) continue;
    seen.add(url);
    out.push({
      url,
      alt: String(item?.alt || "").trim().slice(0, 1000),
      caption: String(item?.caption || "").trim().slice(0, 2000),
    });
  }
  return out;
}

export async function enrichFetchedArticleImages(env, articleId) {
  if (!env?.DB || !env?.ARTIFACTS || !env?.RSS_FASTLANE) return { ok: false, error: "IMAGE_ENRICH_BINDING_MISSING" };
  const article = await env.DB.prepare(`
    SELECT article_id, canonical_url, source_key, title, original_object_key, source_checksum
    FROM rss_articles WHERE article_id = ?
  `).bind(articleId).first();
  if (!article?.original_object_key) return { ok: false, error: "ORIGINAL_NOT_FETCHED" };

  const target = new URL("https://rss-fastlane/v1/rss/fetch");
  target.searchParams.set("sourceKey", article.source_key);
  target.searchParams.set("url", article.canonical_url);
  target.searchParams.set("title", article.title || article.canonical_url);
  if (RESTRICTED_DIRECT_ONLY.has(article.source_key)) target.searchParams.set("accessMode", "direct_only");

  const response = await env.RSS_FASTLANE.fetch(new Request(target.toString(), { method: "GET" }));
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.fetched?.[0]) {
    return { ok: false, error: payload?.error || `FASTLANE_HTTP_${response.status}` };
  }
  const images = safeImages(payload.fetched[0].images);

  const object = await env.ARTIFACTS.get(article.original_object_key);
  if (!object) return { ok: false, error: "ORIGINAL_ARTIFACT_MISSING" };
  const artifact = JSON.parse(await object.text());
  artifact.images = images;
  artifact.imageCount = images.length;

  await env.ARTIFACTS.put(article.original_object_key, JSON.stringify(artifact), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: {
      articleId: String(article.article_id).slice(0, 160),
      sourceKey: String(article.source_key).slice(0, 80),
      checksum: String(article.source_checksum || "").slice(0, 64),
      kind: "rss-original",
      imageCount: String(images.length),
    },
  });

  return { ok: true, articleId, imageCount: images.length };
}
