const MAX_LIST = 100;
const MAX_TRANSLATION_SECTIONS = 600;
const MAX_TRANSLATION_CHARS = 180000;
const RESTRICTED_PROXY_SOURCES = new Set(["projectsyndicate", "economist", "theatlantic"]);

function json(value, status = 200) {
  return Response.json(value, {
    status,
    headers: { "cache-control": "private, no-store" },
  });
}

function requireBindings(env) {
  if (!env.DB) return json({ ok: false, error: "D1_NOT_BOUND" }, 503);
  if (!env.ARTIFACTS) return json({ ok: false, error: "R2_NOT_BOUND" }, 503);
  return null;
}

function requireAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return json({ ok: false, error: "RSS_LIBRARY_AUTH_NOT_CONFIGURED" }, 503);
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function parseJson(text, fallback = null) {
  if (typeof text !== "string") return fallback;
  try { return JSON.parse(text); } catch { return fallback; }
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(text ?? "")));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function semanticSections(text) {
  const source = String(text ?? "").replace(/\r/g, "").trim();
  if (!source) return [];
  let parts = source.split(/\n{2,}/).map((x) => x.trim()).filter(Boolean);
  if (parts.length === 1 && source.length > 3500) {
    parts = source.match(/[\s\S]{1,2800}(?:\s+|$)/g)?.map((x) => x.trim()).filter(Boolean) || [source];
  }
  return parts.map((textValue, index) => ({ id: `s${String(index + 1).padStart(4, "0")}`, text: textValue }));
}

function normalizeNumberToken(value) {
  return String(value).replace(/,/g, ".");
}

function extractTokens(text) {
  const raw = String(text ?? "");
  const urls = [...new Set(raw.match(/https?:\/\/[^\s)\]}>,]+/g) || [])];
  const numbers = [...new Set((raw.match(/\b\d+(?:[.,]\d+)?%?\b/g) || []).map(normalizeNumberToken))];
  return { urls, numbers };
}

function cleanRow(row) {
  if (!row) return null;
  return {
    article_id: row.article_id,
    stable_key: row.stable_key,
    canonical_url: row.canonical_url,
    source_key: row.source_key,
    source_name: row.source_name,
    source_language: row.source_language,
    item_type: row.item_type,
    title: row.title,
    published_at: row.published_at,
    fetch_status: row.fetch_status,
    translation_status: row.translation_status,
    current_version_id: row.current_version_id,
    source_checksum: row.source_checksum,
    translation_checksum: row.translation_checksum,
    translation_version: row.translation_version,
    qa_state: row.qa_state,
    last_error: row.last_error,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

async function getArticle(env, articleId) {
  return env.DB.prepare(`
    SELECT * FROM rss_articles WHERE article_id = ?
  `).bind(articleId).first();
}

async function readObjectJson(env, key) {
  if (!key) return null;
  const object = await env.ARTIFACTS.get(key);
  if (!object) return null;
  return parseJson(await object.text());
}

function articleArtifact(article, fetched, checksum) {
  return {
    version: 1,
    articleId: article.article_id,
    stableKey: article.stable_key,
    canonicalUrl: article.canonical_url,
    sourceKey: article.source_key,
    sourceName: article.source_name,
    sourceLanguage: article.source_language,
    title: article.title,
    publishedAt: article.published_at,
    fetchedAt: new Date().toISOString(),
    sourceChecksum: checksum,
    fetch: {
      route: fetched.route || null,
      resolvedUrl: fetched.resolvedUrl || article.canonical_url,
      coverage: fetched.coverage || "unknown",
      truncated: Boolean(fetched.truncated),
      chars: Number(fetched.chars || String(fetched.rawText || "").length),
    },
    body: String(fetched.rawText || "").trim(),
  };
}

async function persistFetchedArticle(env, article, fetched) {
  const body = String(fetched.rawText || "").trim();
  if (!body) throw new Error("EMPTY_FETCH_BODY");

  const checksum = await sha256Hex(body);
  const versionId = `${article.article_id}:${checksum.slice(0, 24)}`;
  const objectKey = `rss-library/original/${article.article_id}/${checksum}.json`;
  const artifact = articleArtifact(article, fetched, checksum);

  await env.ARTIFACTS.put(objectKey, JSON.stringify(artifact), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: {
      articleId: article.article_id.slice(0, 160),
      sourceKey: article.source_key.slice(0, 80),
      checksum: checksum.slice(0, 64),
      kind: "rss-original",
    },
  });

  const versionStmt = env.DB.prepare(`
    INSERT INTO rss_article_versions (
      version_id, article_id, source_checksum, object_key, fetch_route,
      resolved_url, content_chars, truncated, coverage, metadata, fetched_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(article_id, source_checksum) DO UPDATE SET
      object_key = excluded.object_key,
      fetch_route = excluded.fetch_route,
      resolved_url = excluded.resolved_url,
      content_chars = excluded.content_chars,
      truncated = excluded.truncated,
      coverage = excluded.coverage,
      metadata = excluded.metadata,
      fetched_at = CURRENT_TIMESTAMP
  `).bind(
    versionId, article.article_id, checksum, objectKey,
    fetched.route || null, fetched.resolvedUrl || article.canonical_url,
    body.length, fetched.truncated ? 1 : 0, fetched.coverage || null,
    JSON.stringify({ extractedTitle: fetched.extractedTitle || null })
  );

  const nativeVi = article.source_language === "vi";
  const articleStmt = env.DB.prepare(`
    UPDATE rss_articles SET
      fetch_status = 'fetched',
      current_version_id = ?,
      original_object_key = ?,
      source_checksum = ?,
      vi_object_key = CASE WHEN source_language = 'vi' THEN ? ELSE vi_object_key END,
      translation_checksum = CASE WHEN source_language = 'vi' THEN ? ELSE translation_checksum END,
      translation_status = CASE WHEN source_language = 'vi' THEN 'native_vi' ELSE
        CASE WHEN source_checksum IS NOT ? THEN 'pending' ELSE translation_status END END,
      translation_version = CASE WHEN source_language = 'vi' THEN 'native-source' ELSE translation_version END,
      qa_state = CASE WHEN source_language = 'vi' THEN 'native_vi' ELSE
        CASE WHEN source_checksum IS NOT ? THEN NULL ELSE qa_state END END,
      last_error = NULL,
      updated_at = CURRENT_TIMESTAMP
    WHERE article_id = ?
  `).bind(versionId, objectKey, checksum, objectKey, checksum, checksum, checksum, article.article_id);

  const statements = [versionStmt, articleStmt];
  if (nativeVi) {
    statements.push(env.DB.prepare(`
      INSERT INTO rss_translations (
        translation_id, article_id, version_id, target_language, source_checksum,
        translation_checksum, object_key, status, translation_version,
        source_section_count, translated_section_count, coverage_ratio,
        coverage_qa, consistency_qa, qa_state, metadata, updated_at
      ) VALUES (?, ?, ?, 'vi', ?, ?, ?, 'native_vi', 'native-source', ?, ?, 1.0, ?, ?, 'native_vi', ?, CURRENT_TIMESTAMP)
      ON CONFLICT(version_id, target_language) DO UPDATE SET
        translation_checksum = excluded.translation_checksum,
        object_key = excluded.object_key,
        status = 'native_vi',
        translation_version = 'native-source',
        source_section_count = excluded.source_section_count,
        translated_section_count = excluded.translated_section_count,
        coverage_ratio = 1.0,
        coverage_qa = excluded.coverage_qa,
        consistency_qa = excluded.consistency_qa,
        qa_state = 'native_vi',
        updated_at = CURRENT_TIMESTAMP
    `).bind(
      `${versionId}:vi`, article.article_id, versionId, checksum, checksum, objectKey,
      semanticSections(body).length, semanticSections(body).length,
      JSON.stringify({ ok: true, nativeVi: true, coverageRatio: 1 }),
      JSON.stringify({ ok: true, nativeVi: true }),
      JSON.stringify({ nativeVi: true })
    ));
  }
  await env.DB.batch(statements);

  return { checksum, versionId, objectKey, chars: body.length, nativeVi };
}

async function fetchOne(env, article) {
  if (!env.RSS_FASTLANE || typeof env.RSS_FASTLANE.fetch !== "function") {
    throw new Error("RSS_FASTLANE_NOT_BOUND");
  }

  const target = new URL("https://rss-fastlane/v1/rss/fetch");
  target.searchParams.set("sourceKey", article.source_key);
  target.searchParams.set("url", article.canonical_url);
  target.searchParams.set("title", article.title);
  if (RESTRICTED_PROXY_SOURCES.has(article.source_key)) target.searchParams.set("accessMode", "direct_only");

  const response = await env.RSS_FASTLANE.fetch(new Request(target.toString(), { method: "GET" }));
  const payload = await response.json().catch(() => null);
  const fetched = payload?.fetched?.[0] || null;
  if (!response.ok || !fetched) {
    const detail = payload?.errors?.[0]?.error || payload?.error || `fastlane HTTP ${response.status}`;
    await env.DB.prepare(`
      UPDATE rss_articles SET fetch_status = 'error', last_error = ?, updated_at = CURRENT_TIMESTAMP
      WHERE article_id = ?
    `).bind(String(detail).slice(0, 1000), article.article_id).run();
    throw new Error(String(detail));
  }

  if (RESTRICTED_PROXY_SOURCES.has(article.source_key) && fetched.route !== "direct") {
    const detail = "RESTRICTED_PROXY_FALLBACK_REJECTED";
    await env.DB.prepare(`
      UPDATE rss_articles SET fetch_status = 'blocked', last_error = ?, updated_at = CURRENT_TIMESTAMP
      WHERE article_id = ?
    `).bind(detail, article.article_id).run();
    throw new Error(detail);
  }

  return persistFetchedArticle(env, article, fetched);
}

function safeLimit(url) {
  const raw = Number(url.searchParams.get("limit") || 50);
  if (!Number.isFinite(raw)) return 50;
  return Math.max(1, Math.min(MAX_LIST, Math.floor(raw)));
}

async function listArticles(env, url) {
  const limit = safeLimit(url);
  const result = await env.DB.prepare(`
    SELECT article_id, stable_key, canonical_url, source_key, source_name, source_language,
           item_type, title, published_at, fetch_status, translation_status,
           current_version_id, source_checksum, translation_checksum, translation_version,
           qa_state, last_error, created_at, updated_at
    FROM rss_articles
    ORDER BY published_at DESC, article_id
    LIMIT ?
  `).bind(limit).all();
  return json({ ok: true, articles: (result.results || []).map(cleanRow), count: result.results?.length || 0 });
}

async function articleDetail(env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  const translations = await env.DB.prepare(`
    SELECT translation_id, version_id, target_language, status, translation_version,
           glossary_version, source_section_count, translated_section_count,
           coverage_ratio, coverage_qa, consistency_qa, qa_state, created_at, updated_at
    FROM rss_translations WHERE article_id = ? ORDER BY updated_at DESC
  `).bind(articleId).all();
  return json({
    ok: true,
    article: cleanRow(article),
    translations: (translations.results || []).map((row) => ({
      ...row,
      coverage_qa: parseJson(row.coverage_qa, row.coverage_qa),
      consistency_qa: parseJson(row.consistency_qa, row.consistency_qa),
    })),
  });
}

async function originalView(env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  if (!article.original_object_key) {
    return json({ ok: false, error: "ORIGINAL_NOT_FETCHED", article: cleanRow(article) }, 409);
  }
  const artifact = await readObjectJson(env, article.original_object_key);
  if (!artifact) return json({ ok: false, error: "ORIGINAL_ARTIFACT_MISSING", article: cleanRow(article) }, 500);
  return json({ ok: true, article: cleanRow(article), view: "original", artifact });
}

async function viView(env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  if (article.source_language === "vi") {
    if (!article.original_object_key) return json({ ok: false, error: "ORIGINAL_NOT_FETCHED", article: cleanRow(article) }, 409);
    const artifact = await readObjectJson(env, article.original_object_key);
    if (!artifact) return json({ ok: false, error: "ORIGINAL_ARTIFACT_MISSING" }, 500);
    return json({ ok: true, article: cleanRow(article), view: "vi", nativeVi: true, artifact });
  }
  if (!article.vi_object_key) {
    return json({ ok: false, error: "TRANSLATION_NOT_READY", article: cleanRow(article) }, 409);
  }
  const artifact = await readObjectJson(env, article.vi_object_key);
  if (!artifact) return json({ ok: false, error: "TRANSLATION_ARTIFACT_MISSING", article: cleanRow(article) }, 500);
  return json({ ok: true, article: cleanRow(article), view: "vi", nativeVi: false, artifact });
}

async function translationPacket(env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  if (article.source_language === "vi") return json({ ok: false, error: "NATIVE_VI_NO_TRANSLATION_REQUIRED" }, 409);
  if (!article.original_object_key || !article.source_checksum) {
    return json({ ok: false, error: "ORIGINAL_NOT_FETCHED" }, 409);
  }
  const artifact = await readObjectJson(env, article.original_object_key);
  if (!artifact?.body) return json({ ok: false, error: "ORIGINAL_ARTIFACT_MISSING" }, 500);
  const sections = semanticSections(artifact.body);
  return json({
    ok: true,
    article: cleanRow(article),
    sourceChecksum: article.source_checksum,
    sectionCount: sections.length,
    sections,
    translationPolicy: {
      targetLanguage: "vi",
      semanticFidelity: "near-1:1",
      summary: false,
      preserveFactsNumbersUrls: true,
      requireEverySection: true,
    },
  });
}

async function publishTranslation(request, env, articleId) {
  const article = await getArticle(env, articleId);
  if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
  if (article.source_language === "vi") return json({ ok: false, error: "NATIVE_VI_NO_TRANSLATION_REQUIRED" }, 409);
  if (!article.original_object_key || !article.source_checksum || !article.current_version_id) {
    return json({ ok: false, error: "ORIGINAL_NOT_FETCHED" }, 409);
  }

  const payload = await request.json().catch(() => null);
  if (!payload || payload.sourceChecksum !== article.source_checksum) {
    return json({ ok: false, error: "SOURCE_CHECKSUM_MISMATCH" }, 409);
  }
  if (!Array.isArray(payload.sections) || payload.sections.length > MAX_TRANSLATION_SECTIONS) {
    return json({ ok: false, error: "INVALID_TRANSLATION_SECTIONS" }, 400);
  }

  const original = await readObjectJson(env, article.original_object_key);
  if (!original?.body) return json({ ok: false, error: "ORIGINAL_ARTIFACT_MISSING" }, 500);
  const sourceSections = semanticSections(original.body);
  const expected = new Map(sourceSections.map((section) => [section.id, section.text]));
  const supplied = new Map();
  let chars = 0;
  for (const section of payload.sections) {
    const id = String(section?.id || "");
    const vi = String(section?.vi || "").trim();
    if (!expected.has(id) || supplied.has(id) || !vi) {
      return json({ ok: false, error: "INVALID_OR_DUPLICATE_SECTION", sectionId: id || null }, 400);
    }
    chars += vi.length;
    if (chars > MAX_TRANSLATION_CHARS) return json({ ok: false, error: "TRANSLATION_TOO_LARGE" }, 413);
    supplied.set(id, vi);
  }

  const missingSectionIds = sourceSections.filter((s) => !supplied.has(s.id)).map((s) => s.id);
  const coverageRatio = sourceSections.length ? supplied.size / sourceSections.length : 0;
  const assembled = sourceSections.map((s) => supplied.get(s.id) || "").join("\n\n").trim();
  const sourceTokens = extractTokens(original.body);
  const targetTokens = extractTokens(assembled);
  const targetUrlSet = new Set(targetTokens.urls);
  const targetNumberSet = new Set(targetTokens.numbers);
  const missingUrls = sourceTokens.urls.filter((x) => !targetUrlSet.has(x));
  const missingNumbers = sourceTokens.numbers.filter((x) => !targetNumberSet.has(x));
  const thinSections = sourceSections.filter((s) => {
    const vi = supplied.get(s.id) || "";
    return s.text.length >= 160 && vi.length / s.text.length < 0.2;
  }).map((s) => s.id);

  const coverageQa = {
    ok: missingSectionIds.length === 0 && coverageRatio === 1,
    sourceSectionCount: sourceSections.length,
    translatedSectionCount: supplied.size,
    coverageRatio,
    missingSectionIds,
  };
  const consistencyQa = {
    ok: missingUrls.length === 0 && missingNumbers.length === 0 && thinSections.length === 0,
    missingUrls,
    missingNumbers,
    thinSections,
  };
  if (!coverageQa.ok || !consistencyQa.ok) {
    return json({ ok: false, error: "TRANSLATION_QA_FAILED", coverageQa, consistencyQa }, 422);
  }

  const translationChecksum = await sha256Hex(assembled);
  const translationVersion = String(payload.translationVersion || "manual-v1").slice(0, 120);
  const glossaryVersion = payload.glossaryVersion ? String(payload.glossaryVersion).slice(0, 120) : null;
  const objectKey = `rss-library/vi/${article.article_id}/${article.source_checksum}/${translationChecksum}.json`;
  const artifact = {
    version: 1,
    articleId: article.article_id,
    canonicalUrl: article.canonical_url,
    sourceChecksum: article.source_checksum,
    translationChecksum,
    translationVersion,
    glossaryVersion,
    targetLanguage: "vi",
    sourceSectionCount: sourceSections.length,
    translatedSectionCount: supplied.size,
    coverageQa,
    consistencyQa,
    sections: sourceSections.map((s) => ({ id: s.id, source: s.text, vi: supplied.get(s.id) })),
    body: assembled,
    publishedAt: new Date().toISOString(),
  };

  await env.ARTIFACTS.put(objectKey, JSON.stringify(artifact), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: {
      articleId: article.article_id.slice(0, 160),
      sourceChecksum: article.source_checksum.slice(0, 64),
      translationChecksum: translationChecksum.slice(0, 64),
      kind: "rss-vi",
    },
  });

  const translationId = `${article.current_version_id}:vi`;
  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO rss_translations (
        translation_id, article_id, version_id, target_language, source_checksum,
        translation_checksum, object_key, status, translation_version, glossary_version,
        source_section_count, translated_section_count, coverage_ratio,
        coverage_qa, consistency_qa, qa_state, metadata, updated_at
      ) VALUES (?, ?, ?, 'vi', ?, ?, ?, 'published', ?, ?, ?, ?, 1.0, ?, ?, 'pass', ?, CURRENT_TIMESTAMP)
      ON CONFLICT(version_id, target_language) DO UPDATE SET
        translation_checksum = excluded.translation_checksum,
        object_key = excluded.object_key,
        status = 'published',
        translation_version = excluded.translation_version,
        glossary_version = excluded.glossary_version,
        source_section_count = excluded.source_section_count,
        translated_section_count = excluded.translated_section_count,
        coverage_ratio = 1.0,
        coverage_qa = excluded.coverage_qa,
        consistency_qa = excluded.consistency_qa,
        qa_state = 'pass',
        metadata = excluded.metadata,
        updated_at = CURRENT_TIMESTAMP
    `).bind(
      translationId, article.article_id, article.current_version_id, article.source_checksum,
      translationChecksum, objectKey, translationVersion, glossaryVersion,
      sourceSections.length, supplied.size, JSON.stringify(coverageQa), JSON.stringify(consistencyQa),
      JSON.stringify({ publisher: "rss-library-api" })
    ),
    env.DB.prepare(`
      UPDATE rss_articles SET
        vi_object_key = ?, translation_checksum = ?, translation_status = 'published',
        translation_version = ?, qa_state = 'pass', last_error = NULL,
        updated_at = CURRENT_TIMESTAMP
      WHERE article_id = ? AND source_checksum = ?
    `).bind(objectKey, translationChecksum, translationVersion, article.article_id, article.source_checksum),
  ]);

  return json({ ok: true, articleId, translationChecksum, objectKey, coverageQa, consistencyQa });
}

function libraryHtml() {
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RSS Library</title><style>body{font:16px system-ui;max-width:980px;margin:28px auto;padding:0 16px;line-height:1.5}input,button{font:inherit;padding:9px}button{cursor:pointer}.top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.item{padding:14px 0;border-bottom:1px solid #ddd}.meta{font-size:13px;opacity:.7}.bad{color:#a00}.ok{color:#075}a{color:inherit}</style></head><body><h1>RSS Library</h1><div class="top"><input id="token" type="password" placeholder="Runner3 Core token"><button id="save">Lưu token phiên này</button><button id="reload">Tải lại</button></div><p id="status"></p><main id="list"></main><script>
const token=document.querySelector('#token'),status=document.querySelector('#status'),list=document.querySelector('#list');token.value=sessionStorage.getItem('runner3CoreToken')||'';
document.querySelector('#save').onclick=()=>{sessionStorage.setItem('runner3CoreToken',token.value.trim());load()};document.querySelector('#reload').onclick=load;
async function api(path){const t=sessionStorage.getItem('runner3CoreToken')||token.value.trim();const r=await fetch(path,{headers:{Authorization:'Bearer '+t}});const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
async function load(){list.textContent='';status.textContent='Đang tải…';try{const j=await api('/api/rss/library?limit=100');status.textContent=j.count+' bài';for(const a of j.articles){const d=document.createElement('div');d.className='item';const h=document.createElement('a');h.href='/rss/article/'+encodeURIComponent(a.article_id);h.textContent=a.title;const m=document.createElement('div');m.className='meta';m.textContent=[a.source_name,a.published_at,'fetch:'+a.fetch_status,'vi:'+a.translation_status].filter(Boolean).join(' · ');d.append(h,m);list.append(d)}}catch(e){status.textContent=e.message;status.className='bad'}}load();
</script></body></html>`;
}

function articleHtml(articleId) {
  const encoded = JSON.stringify(articleId);
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RSS Article</title><style>body{font:16px system-ui;max-width:900px;margin:28px auto;padding:0 16px;line-height:1.65}.top{display:flex;gap:8px;flex-wrap:wrap}button{font:inherit;padding:9px 12px;cursor:pointer}pre{white-space:pre-wrap;font:inherit}.meta{font-size:13px;opacity:.7}.bad{color:#a00}</style></head><body><p><a href="/rss/library">← Library</a></p><h1 id="title">RSS Article</h1><div class="top"><button id="original">Original</button><button id="vi">Tiếng Việt</button><button id="fetch">Fetch source</button></div><p class="meta" id="meta"></p><p class="bad" id="error"></p><pre id="body"></pre><script>
const id=${encoded},body=document.querySelector('#body'),err=document.querySelector('#error'),meta=document.querySelector('#meta'),title=document.querySelector('#title');
async function api(path,opt={}){const t=sessionStorage.getItem('runner3CoreToken')||'';const headers={Authorization:'Bearer '+t,...(opt.headers||{})};const r=await fetch(path,{...opt,headers});const j=await r.json();if(!r.ok)throw Object.assign(new Error(j.error||r.status),{data:j});return j}
async function detail(){try{const j=await api('/api/rss/articles/'+encodeURIComponent(id));title.textContent=j.article.title;meta.textContent=[j.article.source_name,j.article.published_at,'fetch:'+j.article.fetch_status,'vi:'+j.article.translation_status].filter(Boolean).join(' · ')}catch(e){err.textContent=e.message}}
async function view(kind){err.textContent='';body.textContent='Đang tải…';try{const j=await api('/api/rss/articles/'+encodeURIComponent(id)+'/'+kind);body.textContent=j.artifact.body||''}catch(e){body.textContent='';err.textContent=e.message}}
document.querySelector('#original').onclick=()=>view('original');document.querySelector('#vi').onclick=()=>view('vi');document.querySelector('#fetch').onclick=async()=>{err.textContent='';try{await api('/api/rss/articles/'+encodeURIComponent(id)+'/fetch',{method:'POST'});await detail();await view('original')}catch(e){err.textContent=e.message}};detail();
</script></body></html>`;
}

export async function handleRssLibrary(request, env, url) {
  if (request.method === "GET" && url.pathname === "/rss/library") {
    return new Response(libraryHtml(), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
  }

  const uiMatch = url.pathname.match(/^\/rss\/article\/([^/]+)$/);
  if (request.method === "GET" && uiMatch) {
    let articleId;
    try { articleId = decodeURIComponent(uiMatch[1]); } catch { return new Response("Bad Request", { status: 400 }); }
    return new Response(articleHtml(articleId), { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
  }

  if (!url.pathname.startsWith("/api/rss/")) return null;
  const bindingError = requireBindings(env);
  if (bindingError) return bindingError;
  const authError = requireAuth(request, env);
  if (authError) return authError;

  if (request.method === "GET" && url.pathname === "/api/rss/library") return listArticles(env, url);

  const match = url.pathname.match(/^\/api\/rss\/articles\/([^/]+)(?:\/(original|vi|translation-status|translation-packet|fetch|translation))?$/);
  if (!match) return json({ ok: false, error: "RSS_ROUTE_NOT_FOUND" }, 404);
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400); }
  const action = match[2] || "detail";

  if (request.method === "GET" && action === "detail") return articleDetail(env, articleId);
  if (request.method === "GET" && action === "original") return originalView(env, articleId);
  if (request.method === "GET" && action === "vi") return viView(env, articleId);
  if (request.method === "GET" && action === "translation-status") return articleDetail(env, articleId);
  if (request.method === "GET" && action === "translation-packet") return translationPacket(env, articleId);
  if (request.method === "POST" && action === "fetch") {
    const article = await getArticle(env, articleId);
    if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404);
    try {
      const result = await fetchOne(env, article);
      return json({ ok: true, articleId, ...result });
    } catch (error) {
      return json({ ok: false, error: String(error?.message || error) }, 502);
    }
  }
  if (request.method === "POST" && action === "translation") return publishTranslation(request, env, articleId);

  return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
}
