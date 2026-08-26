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

function looksLikeAdOrChrome(value) {
  const text = String(value || "").toLowerCase();
  if (/(?:doubleclick\.net|googlesyndication\.com|googleadservices\.com|adnxs\.com|criteo\.|taboola\.|outbrain\.)/.test(text)) return true;
  return /(?:^|[\s/_\-.])(ads?|advert|advertisement|banner|sponsor|sponsored|promo|promoted|tracking|pixel|beacon|spacer|favicon|logo|avatar|author-photo|sprite|badge|icon|emoji)(?:[\s/_\-.]|$)/i.test(text);
}

function classifyImage(text) {
  const value = String(text || "").toLowerCase();
  if (/\b(chart|graph|plot|histogram|candlestick|heatmap|scatter|timeseries|time series)\b/.test(value)) return "chart";
  if (/\b(screenshot|screen shot|dashboard|interface|app screen|terminal output|console output)\b/.test(value)) return "screenshot";
  if (/\b(diagram|architecture|schematic|flowchart|workflow|topology|infographic)\b/.test(value)) return "diagram";
  return "photo";
}

function imageFromTag(tag, baseUrl, caption = "", inFigure = false, surroundingHtml = "") {
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
  const cleanCaption = textFromHtml(caption);
  const className = textFromHtml(attr(tag, "class"));
  const id = textFromHtml(attr(tag, "id"));
  const role = textFromHtml(attr(tag, "role"));
  const width = Number.parseInt(attr(tag, "width") || "0", 10) || 0;
  const height = Number.parseInt(attr(tag, "height") || "0", 10) || 0;
  const localContext = String(surroundingHtml || "").slice(0, 1800);
  const haystack = `${url} ${alt} ${title} ${cleanCaption} ${className} ${id} ${role} ${localContext}`;

  if ((width && width < 120) || (height && height < 120)) return null;
  if (width && height) {
    const ratio = width / height;
    if ((ratio > 4.5 && height < 500) || (ratio < 0.18 && width < 500)) return null;
  }
  if (looksLikeAdOrChrome(haystack)) return null;
  if (/\.(svg)(?:\?|$)/i.test(url)) return null;

  const kind = classifyImage(`${url} ${alt} ${title} ${cleanCaption}`);
  let score = 0;
  if (kind !== "photo") score += 8;
  if (inFigure) score += 4;
  if (cleanCaption.length >= 12) score += 4;
  if ((alt || title).length >= 12) score += 2;
  if (width >= 500 || height >= 500) score += 2;
  if (!width && !height && !inFigure && !cleanCaption && !alt && !title) score -= 3;

  return {
    url,
    alt: alt || title || "",
    caption: cleanCaption,
    width,
    height,
    kind,
    score,
    inFigure,
  };
}

function articleScope(rawHtml) {
  const html = String(rawHtml || "");
  const article = html.match(/<article\b[^>]*>[\s\S]*?<\/article\s*>/i);
  if (article) return article[0];
  const main = html.match(/<main\b[^>]*>[\s\S]*?<\/main\s*>/i);
  return main?.[0] || html;
}

function surrounding(scope, start, length, radius = 420) {
  const from = Math.max(0, start - radius);
  const to = Math.min(scope.length, start + length + radius);
  return scope.slice(from, to);
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
    add(imageFromTag(tag, baseUrl, caption, true, match[0]));
  }

  for (const match of scope.matchAll(/<img\b[^>]*>/gi)) {
    const context = surrounding(scope, match.index || 0, match[0].length);
    add(imageFromTag(match[0], baseUrl, "", false, context));
  }

  return images;
}
