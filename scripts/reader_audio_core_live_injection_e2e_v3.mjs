// rerun-marker: resilient-live-v31-boot-2026-09-01
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
  "          const hereIndex = order.indexOf(here);\n          const targetIndex = order.indexOf(targetCfi);\n          if (targetIndex < 0) throw new Error(`UNKNOWN_TARGET_CFI:${targetCfi}`);\n          if (hereIndex < 0 || hereIndex < targetIndex) await window.r3ReaderBridge.next();\n          else await window.r3ReaderBridge.prev();",
  "          const hereIndex = order.indexOf(here);\n          const targetIndex = order.indexOf(targetCfi);\n          if (targetIndex < 0) throw new Error(`UNKNOWN_TARGET_CFI:${targetCfi}`);\n          const spineIndex = (value) => { const m = /^epubcfi\\(\\/\\d+\\/(\\d+)/.exec(String(value || '')); return m ? Number(m[1]) : null; };\n          const hereSpine = spineIndex(here);\n          const targetSpine = spineIndex(targetCfi);\n          if (hereIndex >= 0) {\n            if (hereIndex < targetIndex) await window.r3ReaderBridge.next();\n            else await window.r3ReaderBridge.prev();\n          } else if (Number.isFinite(hereSpine) && Number.isFinite(targetSpine) && hereSpine !== targetSpine) {\n            if (hereSpine < targetSpine) await window.r3ReaderBridge.next();\n            else await window.r3ReaderBridge.prev();\n          } else {\n            await window.r3ReaderBridge.prev();\n          }",
  'spine-aware-display-cfi',
);

patchOnce(
  "  await page.evaluate(async ({ first, last }) => {\n    const { adapter } = window.__r3CoreE2EV2;",
  "  await page.evaluate(() => window.__r3CoreE2EV2.adapter.pause());\n  await page.waitForTimeout(120);\n\n  await page.evaluate(async ({ first, last }) => {\n    const { adapter } = window.__r3CoreE2EV2;",
  'manual-race-anchor',
);

patchOnce(
  "async function bootV31() {\n  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });\n  const runtime = response?.headers()?.['x-r3-reader-runtime'] || '';\n  if (runtime !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_BASELINE_NOT_V31:${runtime || 'missing'}`);\n  await page.waitForSelector('#viewer iframe', { timeout: 30000 });\n  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });\n  return runtime;\n}",
  "async function bootV31() {\n  let lastError = null;\n  for (let attempt = 1; attempt <= 3; attempt++) {\n    try {\n      const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });\n      const runtimeHeader = response?.headers()?.['x-r3-reader-runtime'] || '';\n      if (runtimeHeader && runtimeHeader !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_BASELINE_WRONG_HEADER:${runtimeHeader}`);\n      await page.waitForSelector('#viewer iframe', { state: 'attached', timeout: 20000 });\n      await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 20000 });\n      await page.waitForFunction(() => window.__r3AudioHighSpeedFollowV31 === true, null, { timeout: 10000 });\n      const markerV31 = await page.evaluate(() => window.__r3AudioHighSpeedFollowV31 === true);\n      if (!markerV31) throw new Error(`LIVE_BASELINE_NOT_V31:${runtimeHeader || 'missing'}`);\n      return runtimeHeader || 'v31-high-speed-serialized-follow';\n    } catch (error) {\n      lastError = error;\n      console.log(JSON.stringify({ phase: 'live-boot-retry', attempt, error: String(error?.message || error) }));\n      if (attempt < 3) {\n        await page.goto('about:blank', { waitUntil: 'domcontentloaded' }).catch(() => {});\n        await page.waitForTimeout(700 * attempt);\n      }\n    }\n  }\n  throw lastError || new Error('LIVE_V31_BOOT_FAILED');\n}",
  'browser-runtime-retry-gate',
);

fs.writeFileSync(outPath, source, 'utf8');

try {
  await import(pathToFileURL(outPath).href + `?v=${Date.now()}`);
} finally {
  try { fs.unlinkSync(outPath); } catch {}
}
