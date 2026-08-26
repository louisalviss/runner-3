import app from "./reddit-entry.js";
import {
  preserveArticleImages,
  pruneExpiredReaderImages,
  selectContentImages,
  serveCachedReaderImage,
} from "./src/rss-image-enrich.js";

function readerViewArticleId(url) {
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/(?:original|vi)$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

function readerStateArticleId(request, url) {
  if (request.method !== "POST") return null;
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/state$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

function shouldPreserveImages(body) {
  return Boolean(body && (
    body.featured === true ||
    body.preference === "like" ||
    body.lifecycle === "archived"
  ));
}

function stripMarkdownImages(value) {
  let text = String(value ?? "");

  // Extractors can leave a linked-image placeholder in the readable body even
  // though images are already carried separately in artifact.images:
  // [![Image 3](thumb.jpg)](full.jpg "caption")
  // Remove both linked and standalone image markdown, including line breaks
  // introduced by source formatting. Normal text links are intentionally kept.
  text = text.replace(
    /\[\s*!\[[^\]]{0,500}\]\(\s*https?:\/\/[\s\S]{1,2500}?\)\s*\]\(\s*https?:\/\/[\s\S]{1,3500}?\)/gi,
    "\n"
  );
  text = text.replace(
    /!\[[^\]]{0,500}\]\(\s*https?:\/\/[\s\S]{1,3000}?\)/gi,
    "\n"
  );

  // Defensive cleanup for malformed extractor placeholders such as a bare
  // "[Image 3]" marker. Do not remove ordinary prose containing the word image.
  text = text.replace(/^\s*\[!?\s*(?:image|ảnh)\s*\d*\s*\]\s*$/gim, "");
  return text;
}

function cleanReaderBody(value) {
  const withoutImageMarkdown = stripMarkdownImages(String(value ?? "").replace(/\r/g, ""));
  const lines = withoutImageMarkdown.split("\n");
  const boilerplate = /^(?:advertisement|quảng cáo|nội dung tài trợ|sponsored(?: content)?|promoted content|tiếp tục sau quảng cáo|đăng ký nhận (?:tin|bản tin)|subscribe(?: now| to (?:our )?newsletter)?|newsletter|related articles?|bài viết liên quan|tin liên quan|xem thêm|đọc thêm|share|chia sẻ)\s*:?[\s.!-]*$/i;
  const trackingUrl = /^https?:\/\/(?:[^/]*\.)?(?:doubleclick\.net|googlesyndication\.com|googleadservices\.com|taboola\.com|outbrain\.com)\S*$/i;
  const out = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (boilerplate.test(trimmed) || trackingUrl.test(trimmed)) continue;
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

async function sanitizeReaderView(response, url) {
  if (!response?.ok || !readerViewArticleId(url)) return response;
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return response;
  const payload = await response.json().catch(() => null);
  if (!payload?.artifact) return Response.json(payload ?? { ok: false, error: "READER_PAYLOAD_INVALID" }, { status: response.status });

  if (Array.isArray(payload.artifact.images)) {
    payload.artifact.images = selectContentImages(payload.artifact.images);
    payload.artifact.imageCount = payload.artifact.images.length;
  }
  if (typeof payload.artifact.body === "string") {
    payload.artifact.body = cleanReaderBody(payload.artifact.body);
  }

  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "private, no-store");
  headers.set("content-type", "application/json; charset=utf-8");
  return new Response(JSON.stringify(payload), { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const mediaResponse = await serveCachedReaderImage(request, env, url);
    if (mediaResponse) return mediaResponse;

    const stateArticleId = readerStateArticleId(request, url);
    const stateClone = stateArticleId ? request.clone() : null;
    const response = await app.fetch(request, env, ctx);

    if (stateArticleId && response?.ok && stateClone) {
      const body = await stateClone.json().catch(() => null);
      if (shouldPreserveImages(body)) {
        const task = preserveArticleImages(env, stateArticleId).catch((error) => {
          console.warn("rss image preserve failed", stateArticleId, String(error?.message || error));
        });
        if (ctx?.waitUntil) ctx.waitUntil(task);
        else await task;
      }
    }

    return sanitizeReaderView(response, url);
  },

  async scheduled(controller, env, ctx) {
    const prune = pruneExpiredReaderImages(env).catch((error) => {
      console.warn("rss image prune failed", String(error?.message || error));
    });
    if (ctx?.waitUntil) ctx.waitUntil(prune);
    else await prune;
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
