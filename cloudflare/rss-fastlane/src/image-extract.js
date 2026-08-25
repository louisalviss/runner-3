function decodeEntities(input) {
  const named = {
    amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ",
    ndash: "–", mdash: "—", hellip: "…", rsquo: "’", lsquo: "‘",
    rdquo: "”", ldquo: "“", copy: "©", reg: "®",
  };
  return String(input ?? "").replace(/&(#x?[0-9a-f]+|[a-z][a-z0-9]+);/gi, (whole, entity) => {
    if (entity[0] === "#") {
      const raw = entity.slice(1);
      const base = raw[0]?.toLowerCase() === "x" ? 16 : 10;
      const digits = base === 16 ? raw.slice(1) : raw;
      const code = Number.parseInt(digits, base);
      if (Number.isFinite(code) && code > 0 && code <= 0x10ffff) {
        try { return String.fromCodePoint(code); } catch { return whole; }
      }
      return whole;
    }
    return named[entity.toLowerCase()] ?? whole;
  });
}

function textFromHtml(value) {
  return decodeEntities(String(value ?? "").replace(/<[^>]+>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

function attr(tag, name) {
  const quoted = tag.match(new RegExp(`\\b${name}\\s*=\\s*(["'])([\\s\\S]*?)\\1`, "i"));
  if (quoted) return quoted[2].trim();
  const bare = tag.match(new RegExp(`\\b${name}\\s*=\\s*([^\\s>]+)`, "i"));
  return bare ? bare[1].trim() : "";
}

function srcsetCandidate(value) {
  const parts = String(value || "").split(",").map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return "";
  return parts[parts.length - 1].split(/\s+/)[0] || "";
}

function normalizeImageUrl(value, baseUrl) {
  const raw = decodeEntities(String(value || "").trim());
  if (!raw || /^(data|blob|javascript):/i.test(raw)) return "";
  try {
    const url = new URL(raw, baseUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    return url.toString();
  } catch {
    return "";
  }
}

function imageFromTag(tag, baseUrl, caption = "") {
  const source = [
    attr(tag, "data-original"),
    attr(tag, "data-src"),
    attr(tag, "data-lazy-src"),
    attr(tag, "data-url"),
    srcsetCandidate(attr(tag, "data-srcset")),
    srcsetCandidate(attr(tag, "srcset")),
    attr(tag, "src"),
  ].find(Boolean);
  const url = normalizeImageUrl(source, baseUrl);
  if (!url) return null;

  const alt = textFromHtml(attr(tag, "alt"));
  const title = textFromHtml(attr(tag, "title"));
  const width = Number.parseInt(attr(tag, "width") || "0", 10) || 0;
  const height = Number.parseInt(attr(tag, "height") || "0", 10) || 0;
  const haystack = `${url} ${alt} ${title}`.toLowerCase();
  if ((width && width < 100) || (height && height < 100)) return null;
  if (/(avatar|emoji|favicon|logo[-_.\/]|sprite|tracking|pixel|spacer|badge|icon[-_.\/]|ads?[-_.\/])/i.test(haystack)) return null;
  if (/\.(svg)(?:\?|$)/i.test(url)) return null;

  return {
    url,
    alt: alt || title || "",
    caption: textFromHtml(caption),
  };
}

function articleScope(rawHtml) {
  const html = String(rawHtml || "");
  const article = html.match(/<article\b[^>]*>[\s\S]*?<\/article\s*>/i);
  if (article) return article[0];
  const main = html.match(/<main\b[^>]*>[\s\S]*?<\/main\s*>/i);
  return main?.[0] || html;
}

export function extractArticleImages(rawHtml, baseUrl, maxImages = 24) {
  const scope = articleScope(rawHtml);
  const images = [];
  const seen = new Set();

  const add = (image) => {
    if (!image || seen.has(image.url) || images.length >= maxImages) return;
    seen.add(image.url);
    images.push(image);
  };

  for (const match of scope.matchAll(/<figure\b[^>]*>([\s\S]*?)<\/figure\s*>/gi)) {
    const block = match[1];
    const tag = block.match(/<img\b[^>]*>/i)?.[0];
    if (!tag) continue;
    const caption = block.match(/<figcaption\b[^>]*>([\s\S]*?)<\/figcaption\s*>/i)?.[1] || "";
    add(imageFromTag(tag, baseUrl, caption));
  }

  for (const match of scope.matchAll(/<img\b[^>]*>/gi)) {
    add(imageFromTag(match[0], baseUrl));
  }

  return images;
}
