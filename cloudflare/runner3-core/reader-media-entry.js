import app from "./reddit-entry.js";
import { handleContentIntelligence } from "./src/content-intelligence.js";
import { handleRssReaderPlus } from "./src/rss-reader-plus.js";
import { renderReaderArticlePageV3 } from "./src/rss-reader-page-v3.js";
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

const BOILERPLATE = /^(?:advertisement|quảng cáo|nội dung tài trợ|sponsored(?: content)?|promoted content|tiếp tục sau quảng cáo|đăng ký nhận (?:tin|bản tin)|subscribe(?: now| to (?:our )?newsletter)?|newsletter|related articles?|bài viết liên quan|tin liên quan|xem thêm|đọc thêm|share|chia sẻ)\s*:?[\s.!-]*$/i;
const TRACKING_URL = /^https?:\/\/(?:[^/]*\.)?(?:doubleclick\.net|googlesyndication\.com|googleadservices\.com|taboola\.com|outbrain\.com)\S*$/i;
const IMAGE_LABEL = /^\s*\[!?\s*(?:image|ảnh)\s*\d*\s*\]\s*$/i;
const TAIL_ATTRIBUTION = /^(?:theo\s*:?[\s-]*)?(?:đời\s*sống\s*(?:&|và)?\s*pháp\s*luật|đspl)\s*[.!-]*$/i;

function comparableText(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[“”"'‘’]/g, "")
    .replace(/[\s\u00a0]+/g, " ")
    .replace(/[\s.!,:;\-–—]+$/g, "")
    .trim();
}

function urlKeys(value) {
  const out = [];
  try {
    const url = new URL(String(value || ""));
    out.push(`${url.hostname.toLowerCase()}${url.pathname}`);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length) out.push(parts[parts.length - 1].toLowerCase());
  } catch {}
  return out;
}

function parseImageLine(value) {
  const line = String(value || "").trim();
  let match = line.match(/^\[!\[([^\]]*)\]\((https?:\/\/[^)\s]+)(?:\s+"([^"]*)")?\)\]\((https?:\/\/[^)\s]+)(?:\s+"([^"]*)")?\)$/i);
  if (match) {
    return {
      alt: match[1] || "",
      urls: [match[2], match[4]].filter(Boolean),
      title: match[5] || match[3] || "",
    };
  }
  match = line.match(/^!\[([^\]]*)\]\((https?:\/\/[^)\s]+)(?:\s+"([^"]*)")?\)$/i);
  if (match) return { alt: match[1] || "", urls: [match[2]], title: match[3] || "" };
  return null;
}

function findImageIndex(ref, images, used) {
  const exact = new Set(ref.urls.flatMap(urlKeys));
  for (let i = 0; i < images.length; i++) {
    if (used.has(i)) continue;
    const itemKeys = [images[i]?.source_url, images[i]?.url].flatMap(urlKeys);
    if (itemKeys.some((key) => exact.has(key))) return i;
  }
  const fileKeys = new Set([...exact].filter((key) => !key.includes("/")));
  if (!fileKeys.size) return -1;
  const matches = [];
  for (let i = 0; i < images.length; i++) {
    if (used.has(i)) continue;
    const itemKeys = [images[i]?.source_url, images[i]?.url].flatMap(urlKeys);
    if (itemKeys.some((key) => fileKeys.has(key))) matches.push(i);
  }
  return matches.length === 1 ? matches[0] : -1;
}

function captionCandidates(ref, image) {
  return new Set([ref?.alt, ref?.title, image?.alt, image?.caption].map(comparableText).filter(Boolean));
}

function buildReaderContent(value, images) {
  const lines = String(value ?? "").replace(/\r/g, "").split("\n");
  const blocks = [];
  const used = new Set();
  let textLines = [];
  let pendingCaption = null;
  const flushText = () => {
    const text = textLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    if (text) blocks.push({ type: "text", text });
    textLines = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (pendingCaption && trimmed) {
      const normalized = comparableText(trimmed);
      if (normalized && pendingCaption.has(normalized)) {
        pendingCaption = null;
        continue;
      }
      pendingCaption = null;
    }
    const ref = parseImageLine(trimmed);
    if (ref) {
      flushText();
      const imageIndex = findImageIndex(ref, images, used);
      const image = imageIndex >= 0 ? images[imageIndex] : null;
      pendingCaption = captionCandidates(ref, image);
      if (imageIndex >= 0) {
        used.add(imageIndex);
        blocks.push({ type: "image", imageIndex });
      }
      continue;
    }
    if (IMAGE_LABEL.test(trimmed)) continue;
    if ((trimmed.startsWith("![") || trimmed.startsWith("[![")) && trimmed.includes("http")) continue;
    if (BOILERPLATE.test(trimmed) || TRACKING_URL.test(trimmed)) continue;
    const nearTail = i >= lines.length - 20 || i >= Math.floor(lines.length * 0.82);
    if (nearTail && TAIL_ATTRIBUTION.test(comparableText(trimmed))) continue;
    textLines.push(line);
  }
  flushText();
  const body = blocks.filter((block) => block.type === "text").map((block) => block.text).join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
  return { body, blocks };
}

async function sanitizeReaderView(response, url) {
  if (!response?.ok || !readerViewArticleId(url)) return response;
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return response;
  const payload = await response.json().catch(() => null);
  if (!payload?.artifact) return Response.json(payload ?? { ok: false, error: "READER_PAYLOAD_INVALID" }, { status: response.status });
  const images = selectContentImages(Array.isArray(payload.artifact.images) ? payload.artifact.images : []);
  payload.artifact.images = images;
  payload.artifact.imageCount = images.length;
  if (typeof payload.artifact.body === "string") {
    const rendered = buildReaderContent(payload.artifact.body, images);
    payload.artifact.body = rendered.body;
    payload.artifact.renderBlocks = rendered.blocks;
  } else {
    payload.artifact.renderBlocks = [];
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

    const plusResponse = await handleRssReaderPlus(request, env, url);
    if (plusResponse) return plusResponse;

    const articlePage = renderReaderArticlePageV3(request, url);
    if (articlePage) return articlePage;

    const ciResponse = await handleContentIntelligence(request, env, url);
    if (ciResponse) return ciResponse;

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
