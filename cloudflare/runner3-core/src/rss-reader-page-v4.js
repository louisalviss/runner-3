import { renderReaderArticlePageV3 } from "./rss-reader-page-v3.js";

export function repairGeneratedReaderHtml(html) {
  const source = String(html || "");
  const broken = "normalized.split(/\n{2,}/)";
  const fixed = "normalized.split('\\n\\n')";
  return source.includes(broken) ? source.replace(broken, fixed) : source;
}

export async function renderReaderArticlePageV4(request, url) {
  const response = renderReaderArticlePageV3(request, url);
  if (!response) return null;
  const html = repairGeneratedReaderHtml(await response.text());
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  headers.set("content-type", "text/html; charset=utf-8");
  return new Response(html, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
