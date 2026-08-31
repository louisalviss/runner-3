import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const sourcePath = 'scripts/reader_audio_core_live_injection_e2e_v2.mjs';
const outPath = '/tmp/reader_audio_core_live_injection_e2e_v3.generated.mjs';
let source = fs.readFileSync(sourcePath, 'utf8');

const needle = "  await page.evaluate(async ({ first, last }) => {\n    const { adapter } = window.__r3CoreE2EV2;";
const replacement = "  await page.evaluate(() => window.__r3CoreE2EV2.adapter.pause());\n  await page.waitForTimeout(120);\n\n" + needle;
const first = source.indexOf(needle);
if (first < 0) throw new Error('V3_PATCH_MISSING:manual-race-anchor');
if (source.indexOf(needle, first + needle.length) >= 0) throw new Error('V3_PATCH_AMBIGUOUS:manual-race-anchor');
source = source.replace(needle, replacement);
fs.writeFileSync(outPath, source, 'utf8');

try {
  await import(pathToFileURL(outPath).href + `?v=${Date.now()}`);
} finally {
  try { fs.unlinkSync(outPath); } catch {}
}
