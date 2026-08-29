export const READER_CLEAN_VERSION = "rss-reader-clean-v2";

const FONT_CONTROL_RE = /^(?:c(?:ỡ|o)\s*ch(?:ữ|u)\s*)?a\s*\+\s*(?:a\s*[-−–—])?$|^a\s*[-−–—]$/iu;
const PHOTO_CREDIT_RE = /(?:^|[\s(])(?:(?:ảnh|hình|photo|image|picture|nguồn ảnh|photo credit|image credit|credit)\s*:|photo\s+by\b)/iu;
const NAV_SEQUENCE_RE = /^(?:(?:trang chu|home|bai viet|article|tin tuc|news|chuyen muc|category|latest|moi nhat)(?:\s+|$)){1,6}$/;
const AUTHOR_PREFIX_RE = /^(?:tac gia|author|by)\s*:?\s*/;

function fold(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[“”"'‘’]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function comparable(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[“”"'‘’]/g, "")
    .replace(/[\s\u00a0]+/g, " ")
    .replace(/[\s.!,:;\-–—]+$/g, "")
    .trim();
}

function imageCaptionKeys(images) {
  const out = new Set();
  for (const image of Array.isArray(images) ? images : []) {
    for (const value of [image?.caption, image?.alt]) {
      const key = comparable(value);
      if (key) out.add(key);
    }
  }
  return out;
}

function looksLikeNamePart(value) {
  const text = String(value || "").trim();
  if (!text || text.length > 80 || /[!?;:]/u.test(text)) return false;
  if (!/^[\p{L}\p{M}.'’\-\s]+$/u.test(text)) return false;
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length < 1 || words.length > 6) return false;
  return words.every((word) => {
    const first = [...word][0] || "";
    return !/\p{L}/u.test(first) || first === first.toLocaleUpperCase();
  });
}

function looksLikeByline(line, author, early) {
  if (!early) return false;
  const folded = fold(line);
  const authorFolded = fold(author);
  if (authorFolded && (folded === authorFolded || folded === `by ${authorFolded}` || folded === `tac gia ${authorFolded}`)) return true;

  const withoutPrefix = folded.replace(AUTHOR_PREFIX_RE, "");
  if (authorFolded && withoutPrefix === authorFolded) return true;

  const parts = String(line || "").split("|").map((x) => x.trim()).filter(Boolean);
  return parts.length >= 2 && parts.length <= 6 && parts.every(looksLikeNamePart);
}

function looksLikeTitleChrome(line, title, early) {
  if (!early) return false;
  const lineFolded = fold(line);
  const titleFolded = fold(title);
  if (!lineFolded) return false;
  if (titleFolded && lineFolded === titleFolded) return true;
  if (titleFolded && lineFolded.endsWith(titleFolded)) {
    const prefix = lineFolded.slice(0, -titleFolded.length).trim();
    if (prefix && NAV_SEQUENCE_RE.test(`${prefix} `)) return true;
  }
  return NAV_SEQUENCE_RE.test(`${lineFolded} `);
}

function nextNonEmpty(lines, start) {
  for (let i = start; i < lines.length; i++) {
    const value = String(lines[i] || "").trim();
    if (value) return value;
  }
  return "";
}

function isExplicitPhotoCaption(line) {
  const text = String(line || "").trim();
  return text.length <= 500 && PHOTO_CREDIT_RE.test(text);
}

export function cleanReaderBoilerplate(value, meta = {}) {
  const lines = String(value ?? "").replace(/\r/g, "").split("\n");
  const captionKeys = imageCaptionKeys(meta.images);
  const out = [];
  let nonEmptySeen = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = String(line || "").trim();
    if (!trimmed) {
      out.push(line);
      continue;
    }

    nonEmptySeen += 1;
    const early = nonEmptySeen <= 30 || i < Math.max(12, Math.floor(lines.length * 0.22));
    const key = comparable(trimmed);

    if (FONT_CONTROL_RE.test(trimmed)) continue;
    if (looksLikeTitleChrome(trimmed, meta.title, early)) continue;
    if (looksLikeByline(trimmed, meta.author, early)) continue;
    if (captionKeys.has(key)) continue;
    if (isExplicitPhotoCaption(trimmed)) continue;

    const next = nextNonEmpty(lines, i + 1);
    if (early && trimmed.length <= 350 && next && isExplicitPhotoCaption(next)) continue;

    out.push(line);
  }

  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
