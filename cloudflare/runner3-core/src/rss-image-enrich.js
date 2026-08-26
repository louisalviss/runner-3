const RESTRICTED_DIRECT_ONLY = new Set(["projectsyndicate", "economist", "theatlantic"]);
const ESSENTIAL_KINDS = new Set(["chart", "diagram", "screenshot"]);
const MAX_SELECTED_IMAGES = 6;
const MAX_NORMAL_PHOTOS = 2;
const MAX_CACHE_BYTES = 6 * 1024 * 1024;
const MEDIA_PREFIX = "rss-media/";
const NORMAL_RETENTION_MS = 180 * 24 * 60 * 60 * 1000;
const DELETED_RETENTION_MS = 30 * 24 * 60 * 60 * 1000;

function text(value, max = 2000) {
  return String(value ?? "").trim().slice(0, max);
}

function looksLikeAdOrChrome(value) {
  const s = String(value || "").toLowerCase();
  if (/(?:doubleclick\.net|googlesyndication\.com|googleadservices\.com|adnxs\.com|criteo\.|taboola\.|outbrain\.)/.test(s)) return true;
  return /(?:^|[\s/_\-.])(ads?|advert|advertisement|banner|sponsor|sponsored|promo|promoted|tracking|pixel|beacon|spacer|favicon|logo|avatar|author-photo|sprite|badge|icon|emoji)(?:[\s/_\-.]|$)/i.test(s);
}

function classifyImage(value) {
  const s = String(value || "").toLowerCase();
  if (/\b(chart|graph|plot|histogram|candlestick|heatmap|scatter|timeseries|time series)\b/.test(s)) return "chart";
  if (/\b(screenshot|screen shot|dashboard|interface|app screen|terminal output|console output)\b/.test(s)) return "screenshot";
  if (/\b(diagram|architecture|schematic|flowchart|workflow|topology|infographic)\b/.test(s)) return "diagram";
  return "photo";
}

function remoteSource(item) {
  return text(item?.source_url || item?.url, 6000);
}

function normalizeCandidate(item, index) {
  const sourceUrl = remoteSource(item);
  if (!/^https?:\/\//i.test(sourceUrl)) return null;
  const currentUrl = text(item?.url, 6000);
  const isCached = item?.cache_status === "cached" && /^https?:\/\//i.test(currentUrl);
  const alt = text(item?.alt, 1000);
  const caption = text(item?.caption, 2000);
  if (looksLikeAdOrChrome(`${sourceUrl} ${alt} ${caption}`)) return null;

  const width = Math.max(0, Number.parseInt(item?.width || 0, 10) || 0);
  const height = Math.max(0, Number.parseInt(item?.height || 0, 10) || 0);
  if ((width && width < 120) || (height && height < 120)) return null;
  if (width && height) {
    const ratio = width / height;
    if ((ratio > 4.5 && height < 500) || (ratio < 0.18 && width < 500)) return null;
  }

  const declaredKind = String(item?.kind || "").toLowerCase();
  const kind = ESSENTIAL_KINDS.has(declaredKind) || declaredKind === "photo"
    ? declaredKind
    : classifyImage(`${sourceUrl} ${alt} ${caption}`);
  let score = Number(item?.score || 0);
  if (!Number.isFinite(score)) score = 0;
  if (ESSENTIAL_KINDS.has(kind)) score = Math.max(score, 8);
  if (caption.length >= 12) score += 3;
  if (alt.length >= 12) score += 1;
  if (item?.inFigure) score += 2;
  if (width >= 500 || height >= 500) score += 1;

  return {
    index,
    url: isCached ? currentUrl : sourceUrl,
    source_url: sourceUrl,
    alt,
    caption,
    width,
    height,
    kind,
    score,
    inFigure: Boolean(item?.inFigure),
    cache_status: isCached ? "cached" : "remote",
    cache_token: text(item?.cache_token, 80) || null,
    cached_at: text(item?.cached_at, 80) || null,
  };
}

export function selectContentImages(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const candidates = [];
  for (let i = 0; i < value.length; i++) {
    const candidate = normalizeCandidate(value[i], i);
    if (!candidate || seen.has(candidate.source_url)) continue;
    seen.add(candidate.source_url);
    candidates.push(candidate);
  }

  const essential = candidates
    .filter((x) => ESSENTIAL_KINDS.has(x.kind))
    .sort((a, b) => b.score - a.score || a.index - b.index);
  const photos = candidates
    .filter((x) => x.kind === "photo")
    .sort((a, b) => b.score - a.score || a.index - b.index);

  const selected = essential.slice(0, MAX_SELECTED_IMAGES);
  let normalPhotos = 0;
  for (const photo of photos) {
    if (selected.length >= MAX_SELECTED_IMAGES || normalPhotos >= MAX_NORMAL_PHOTOS) break;
    if (photo.score < 2 && selected.length) continue;
    selected.push(photo);
    normalPhotos++;
  }
  if (!selected.length && photos.length) selected.push(photos[0]);

  return selected
    .slice(0, MAX_SELECTED_IMAGES)
    .sort((a, b) => a.index - b.index)
    .map(({ index, ...item }) => item);
}

function signedOrExpiringUrl(value) {
  try {
    const url = new URL(value);
    for (const key of url.searchParams.keys()) {
      if (/^(?:token|sig|signature|expires?|expiry|auth|x-amz-|x-goog-)/i.test(key)) return true;
    }
  } catch {}
  return false;
}

function safePublicImageUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (host === "localhost" || host.endsWith(".local") || host === "::1") return null;
    if (/^(?:127\.|0\.|10\.|192\.168\.|169\.254\.)/.test(host)) return null;
    const m = host.match(/^172\.(\d+)\./);
    if (m && Number(m[1]) >= 16 && Number(m[1]) <= 31) return null;
    if (/^(?:fc|fd|fe80):/i.test(host)) return null;
    return url.toString();
  } catch {
    return null;
  }
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(value)));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function articleSegment(articleId) {
  return encodeURIComponent(String(articleId));
}

function mediaKey(articleId, token) {
  return `${MEDIA_PREFIX}${articleSegment(articleId)}/${token}`;
}

function publicOrigin(env) {
  const configured = String(env?.RSS_READER_PUBLIC_ORIGIN || "").trim().replace(/\/$/, "");
  return configured || "https://runner3-core.ducduy2411.workers.dev";
}

function mediaUrl(env, articleId, token) {
  return `${publicOrigin(env)}/rss/media/${articleSegment(articleId)}/${token}`;
}

async function readLimited(response, maxBytes = MAX_CACHE_BYTES) {
  if (!response.body) return null;
  const declared = Number(response.headers.get("content-length") || 0);
  if (declared && declared > maxBytes) return null;
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      try { await reader.cancel(); } catch {}
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}

async function cacheOneImage(env, article, item, reason) {
  const sourceUrl = safePublicImageUrl(remoteSource(item));
  if (!sourceUrl) return { ...item, cache_status: "remote", cache_error: "UNSAFE_URL" };
  const token = (await sha256Hex(sourceUrl)).slice(0, 32);
  const key = mediaKey(article.article_id, token);
  const existing = await env.ARTIFACTS.head(key);
  if (!existing) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    let response;
    try {
      const headers = new Headers({
        accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "user-agent": "Mozilla/5.0 (compatible; Runner3RSS/1.0; +https://runner3-core.ducduy2411.workers.dev)",
      });
      if (/^https?:\/\//i.test(article.canonical_url || "")) headers.set("referer", article.canonical_url);
      response = await fetch(sourceUrl, { headers, redirect: "follow", signal: controller.signal });
    } catch (error) {
      clearTimeout(timer);
      return { ...item, cache_status: "remote", cache_error: String(error?.name || "FETCH_FAILED") };
    }
    clearTimeout(timer);
    const contentType = String(response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
    if (!response.ok || !contentType.startsWith("image/") || contentType === "image/svg+xml") {
      return { ...item, cache_status: "remote", cache_error: `HTTP_${response.status}_${contentType || "unknown"}` };
    }
    const bytes = await readLimited(response);
    if (!bytes || !bytes.byteLength) return { ...item, cache_status: "remote", cache_error: "IMAGE_TOO_LARGE_OR_EMPTY" };
    await env.ARTIFACTS.put(key, bytes, {
      httpMetadata: { contentType, cacheControl: "public, max-age=31536000, immutable" },
      customMetadata: {
        articleId: String(article.article_id).slice(0, 160),
        sourceKey: String(article.source_key || "").slice(0, 80),
        imageKind: String(item.kind || "photo").slice(0, 30),
        cacheReason: String(reason || "reader").slice(0, 30),
        sourceHash: token,
      },
    });
  }

  return {
    ...item,
    source_url: sourceUrl,
    url: mediaUrl(env, article.article_id, token),
    cache_status: "cached",
    cache_token: token,
    cached_at: new Date().toISOString(),
    cache_error: undefined,
  };
}

async function putArtifact(env, article, artifact, objectMetadata = {}) {
  const images = Array.isArray(artifact.images) ? artifact.images : [];
  await env.ARTIFACTS.put(article.original_object_key, JSON.stringify(artifact), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: {
      ...objectMetadata,
      articleId: String(article.article_id).slice(0, 160),
      sourceKey: String(article.source_key || "").slice(0, 80),
      checksum: String(article.source_checksum || "").slice(0, 64),
      kind: "rss-original",
      imageCount: String(images.length),
      cachedImageCount: String(images.filter((x) => x.cache_status === "cached").length),
    },
  });
}

async function articleForImages(env, articleId) {
  return env.DB.prepare(`
    SELECT article_id, canonical_url, source_key, title, original_object_key, source_checksum
    FROM rss_articles WHERE article_id = ?
  `).bind(articleId).first();
}

export async function enrichFetchedArticleImages(env, articleId) {
  if (!env?.DB || !env?.ARTIFACTS || !env?.RSS_FASTLANE) return { ok: false, error: "IMAGE_ENRICH_BINDING_MISSING" };
  const article = await articleForImages(env, articleId);
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

  const object = await env.ARTIFACTS.get(article.original_object_key);
  if (!object) return { ok: false, error: "ORIGINAL_ARTIFACT_MISSING" };
  const artifact = JSON.parse(await object.text());
  const extracted = selectContentImages(payload.fetched[0].images);
  const existing = selectContentImages(artifact.images);
  let images = extracted.length ? extracted : existing;

  const cached = [];
  for (const image of images) {
    const cacheNow = ESSENTIAL_KINDS.has(image.kind) || signedOrExpiringUrl(image.source_url || image.url);
    cached.push(cacheNow ? await cacheOneImage(env, article, image, ESSENTIAL_KINDS.has(image.kind) ? "essential" : "expiring") : image);
  }
  images = cached;
  artifact.images = images;
  artifact.imageCount = images.length;
  artifact.imagePolicy = "content-only-v1";
  await putArtifact(env, article, artifact, object.customMetadata || {});

  return {
    ok: true,
    articleId,
    imageCount: images.length,
    cachedImageCount: images.filter((x) => x.cache_status === "cached").length,
    kinds: images.reduce((acc, x) => ({ ...acc, [x.kind]: (acc[x.kind] || 0) + 1 }), {}),
  };
}

export async function preserveArticleImages(env, articleId) {
  if (!env?.DB || !env?.ARTIFACTS) return { ok: false, error: "IMAGE_PRESERVE_BINDING_MISSING" };
  const article = await articleForImages(env, articleId);
  if (!article?.original_object_key) return { ok: false, error: "ORIGINAL_NOT_FETCHED" };
  const object = await env.ARTIFACTS.get(article.original_object_key);
  if (!object) return { ok: false, error: "ORIGINAL_ARTIFACT_MISSING" };
  const artifact = JSON.parse(await object.text());
  const images = selectContentImages(artifact.images);
  if (!images.length) return { ok: true, articleId, imageCount: 0, cachedImageCount: 0 };

  const preserved = [];
  for (const image of images) preserved.push(await cacheOneImage(env, article, image, "preserved"));
  artifact.images = preserved;
  artifact.imageCount = preserved.length;
  artifact.imagePolicy = "content-only-v1";
  await putArtifact(env, article, artifact, object.customMetadata || {});
  return {
    ok: true,
    articleId,
    imageCount: preserved.length,
    cachedImageCount: preserved.filter((x) => x.cache_status === "cached").length,
  };
}

async function fallbackSourceForMissingMedia(env, articleId, token) {
  if (!env?.DB || !env?.ARTIFACTS) return null;
  const article = await articleForImages(env, articleId);
  if (!article?.original_object_key) return null;
  const object = await env.ARTIFACTS.get(article.original_object_key);
  if (!object) return null;
  let artifact;
  try { artifact = JSON.parse(await object.text()); } catch { return null; }
  const image = (artifact.images || []).find((x) => x?.cache_token === token);
  const source = safePublicImageUrl(image?.source_url);
  return source || null;
}

export async function serveCachedReaderImage(request, env, url) {
  const match = url.pathname.match(/^\/rss\/media\/([^/]+)\/([a-f0-9]{16,64})$/i);
  if (!match) return null;
  if (request.method !== "GET" && request.method !== "HEAD") return new Response("Method Not Allowed", { status: 405 });
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return new Response("Bad Request", { status: 400 }); }
  const token = match[2].toLowerCase();
  const key = mediaKey(articleId, token);
  const object = request.method === "HEAD" ? await env.ARTIFACTS.head(key) : await env.ARTIFACTS.get(key);
  if (!object) {
    const source = await fallbackSourceForMissingMedia(env, articleId, token);
    if (source) return Response.redirect(source, 302);
    return new Response("Not Found", { status: 404, headers: { "cache-control": "no-store" } });
  }
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  headers.set("cache-control", "public, max-age=31536000, immutable");
  headers.set("x-content-type-options", "nosniff");
  return new Response(request.method === "HEAD" ? null : object.body, { headers });
}

function articleIdFromMediaKey(key) {
  const rest = String(key || "").slice(MEDIA_PREFIX.length);
  const slash = rest.indexOf("/");
  if (slash <= 0) return null;
  try { return decodeURIComponent(rest.slice(0, slash)); } catch { return null; }
}

async function readerStates(env, articleIds) {
  const map = new Map();
  const unique = [...new Set(articleIds.filter(Boolean))];
  for (let i = 0; i < unique.length; i += 50) {
    const batch = unique.slice(i, i + 50);
    const marks = batch.map(() => "?").join(",");
    const result = await env.DB.prepare(`
      SELECT article_id, lifecycle, featured, preference
      FROM rss_reader_state WHERE article_id IN (${marks})
    `).bind(...batch).all();
    for (const row of result.results || []) map.set(row.article_id, row);
  }
  return map;
}

export async function pruneExpiredReaderImages(env) {
  if (!env?.DB || !env?.ARTIFACTS) return { ok: false, error: "IMAGE_PRUNE_BINDING_MISSING" };
  const objects = [];
  let cursor;
  for (let page = 0; page < 4; page++) {
    const listed = await env.ARTIFACTS.list({ prefix: MEDIA_PREFIX, limit: 250, cursor });
    objects.push(...(listed.objects || []));
    if (!listed.truncated || !listed.cursor) break;
    cursor = listed.cursor;
  }
  const ids = objects.map((x) => articleIdFromMediaKey(x.key));
  const states = await readerStates(env, ids);
  const now = Date.now();
  const deletions = [];

  for (const object of objects) {
    const articleId = articleIdFromMediaKey(object.key);
    if (!articleId) continue;
    const uploaded = new Date(object.uploaded || 0).getTime();
    if (!Number.isFinite(uploaded) || uploaded <= 0) continue;
    const state = states.get(articleId);
    const deleted = state?.lifecycle === "deleted";
    const preserved = !deleted && (Number(state?.featured || 0) === 1 || state?.preference === "like" || state?.lifecycle === "archived");
    if (preserved) continue;
    const retention = deleted ? DELETED_RETENTION_MS : NORMAL_RETENTION_MS;
    if (now - uploaded >= retention) deletions.push(object.key);
    if (deletions.length >= 250) break;
  }

  if (deletions.length) await env.ARTIFACTS.delete(deletions);
  return { ok: true, scanned: objects.length, deleted: deletions.length };
}
