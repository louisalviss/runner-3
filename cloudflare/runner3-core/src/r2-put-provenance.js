// Opt-in R2 PUT provenance. No object keys, account identities or user content logged.
// This is intentionally NOT an account-wide source of truth: direct S3 PUT bypasses Worker.
const ALLOWED_WRITERS = new Set([
  "artifact-api",
  "rss-original",
  "rss-translation",
  "rss-import-media",
  "rss-import-original-rewrite",
  "rss-cache-image",
  "rss-cache-original-rewrite",
  "seotrends-emergency-sitemap",
  "seotrends-emergency-item",
  "seotrends-emergency-manifest",
  "seotrends-status",
]);

export function traceR2PutCompleted(env, writer) {
  if (!env || env.R2_PUT_PROVENANCE !== "enabled") return false;
  if (!ALLOWED_WRITERS.has(writer)) return false;
  try {
    console.info(JSON.stringify({
      event: "r2.put.completed",
      version: 1,
      bucket: "runner3-artifacts",
      writer,
    }));
    return true;
  } catch {
    // Logging must never affect the R2 write or the response.
    return false;
  }
}
