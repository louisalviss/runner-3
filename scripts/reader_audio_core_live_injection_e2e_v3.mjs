import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const sourcePath = 'scripts/reader_audio_core_live_injection_e2e_v2.mjs';
const outPath = 'scripts/.reader_audio_core_live_injection_e2e_v3.generated.mjs';
let source = fs.readFileSync(sourcePath, 'utf8');

function patchOnce(needle, replacement, label) {
  const first = source.indexOf(needle);
  if (first < 0) throw new Error(`V3_PATCH_MISSING:${label}`);
  if (source.indexOf(needle, first + needle.length) >= 0) throw new Error(`V3_PATCH_AMBIGUOUS:${label}`);
  source = source.slice(0, first) + replacement + source.slice(first + needle.length);
}

patchOnce(
  "  await page.evaluate(async ({ first, last }) => {\n    const { adapter } = window.__r3CoreE2EV2;",
  "  await page.evaluate(() => window.__r3CoreE2EV2.adapter.pause());\n  await page.waitForTimeout(120);\n\n  await page.evaluate(async ({ first, last }) => {\n    const { adapter } = window.__r3CoreE2EV2;",
  'manual-race-anchor',
);

patchOnce(
  "  const runtime = response?.headers()?.['x-r3-reader-runtime'] || '';\n  if (runtime !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_BASELINE_NOT_V31:${runtime || 'missing'}`);\n  await page.waitForSelector('#viewer iframe', { timeout: 30000 });\n  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });\n  return runtime;",
  "  const runtimeHeader = response?.headers()?.['x-r3-reader-runtime'] || '';\n  await page.waitForSelector('#viewer iframe', { timeout: 30000 });\n  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });\n  await page.waitForFunction(() => window.__r3AudioHighSpeedFollowV31 === true, null, { timeout: 10000 });\n  const markerV31 = await page.evaluate(() => window.__r3AudioHighSpeedFollowV31 === true);\n  if (runtimeHeader && runtimeHeader !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_BASELINE_WRONG_HEADER:${runtimeHeader}`);\n  if (!markerV31) throw new Error(`LIVE_BASELINE_NOT_V31:${runtimeHeader || 'missing'}`);\n  return runtimeHeader || 'v31-high-speed-serialized-follow';",
  'browser-runtime-gate',
);

fs.writeFileSync(outPath, source, 'utf8');

try {
  await import(pathToFileURL(outPath).href + `?v=${Date.now()}`);
} finally {
  try { fs.unlinkSync(outPath); } catch {}
}
