// v31 high-speed smoke trigger: 2x page-boundary serialized follow proof.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const sourcePath = path.resolve('scripts/ebook_reader_viewport_word_smoke.mjs');
const outPath = path.resolve('scripts/.ebook_reader_v31_high_speed_generated.mjs');
let s = fs.readFileSync(sourcePath, 'utf8');

function replaceOnce(needle, replacement, label) {
  const first = s.indexOf(needle);
  if (first < 0) throw new Error(`V31_SMOKE_PATCH_MISSING:${label}`);
  if (s.indexOf(needle, first + needle.length) >= 0) throw new Error(`V31_SMOKE_PATCH_AMBIGUOUS:${label}`);
  s = s.slice(0, first) + replacement + s.slice(first + needle.length);
}

replaceOnce("const TEST_ID = 'seek-smoke-v16';", "const TEST_ID = 'seek-smoke-v31';", 'testId');
replaceOnce("runtime.includes('v16')", "runtime.includes('v31')", 'runtimeCheck');
replaceOnce('live Reader is not v16:', 'live Reader is not v31:', 'runtimeError');
replaceOnce(
  'window.__r3AudioViewportWordV15 === true && window.__r3AudioOuterGeometryV16 === true',
  'window.__r3AudioViewportWordV15 === true && window.__r3AudioHighSpeedFollowV31 === true',
  'runtimeMarker',
);

replaceOnce(
  '  const beforeFollowCfi = started.cfi;',
  [
    '  const beforeFollowCfi = started.cfi;',
    "  await page.evaluate(() => document.getElementById('r3AudioElement')?.pause());",
    '  await page.waitForTimeout(180);',
  ].join('\n'),
  'manualPaginationPause',
);

replaceOnce(
  [
    '  await page.evaluate(t => {',
    "    const a = document.getElementById('r3AudioElement');",
    '    a.currentTime = t;',
    "    a.dispatchEvent(new Event('seeked'));",
    "    a.dispatchEvent(new Event('timeupdate'));",
    '  }, followTime);',
    '  await page.waitForTimeout(1500);',
  ].join('\n'),
  [
    '  const highSpeedStart = Math.max(0, followTime - 0.5);',
    '  await page.evaluate(async t => {',
    "    const a = document.getElementById('r3AudioElement');",
    '    a.pause();',
    '    a.playbackRate = 2;',
    '    a.defaultPlaybackRate = 2;',
    '    a.currentTime = t;',
    "    a.dispatchEvent(new Event('seeked'));",
    '    try { await a.play(); } catch {}',
    '  }, highSpeedStart);',
    '  await page.waitForFunction(() => Number(window.__r3AudioHighSpeedV31Debug?.ticks || 0) >= 4, null, { timeout: 4000 });',
    '  await page.waitForTimeout(900);',
  ].join('\n'),
  'highSpeedFollow',
);

const followAssert = '  if (afterFollow.visibleTokenOrdinal < Math.max(0, followIndex - 30)) throw new Error(`Reader did not follow audio word closely enough: target=${followIndex} visible=${afterFollow.visibleTokenOrdinal}`);';
replaceOnce(
  followAssert,
  [
    followAssert,
    "  await page.evaluate(() => document.getElementById('r3AudioElement')?.pause());",
    '  await page.waitForTimeout(220);',
    '  const v31debug = await page.evaluate(() => window.__r3AudioHighSpeedV31Debug || null);',
    "  console.log(JSON.stringify({phase:'high-speed-v31',v31debug,followIndex,visibleTokenOrdinal:afterFollow.visibleTokenOrdinal,afterCfi:afterFollow.cfi}));",
    "  if (!v31debug || v31debug.ticks < 4) throw new Error('v31 high-speed clock did not tick');",
    "  if (Number(v31debug.lastRate || 0) < 1.9) throw new Error('v31 proof did not run near 2x: '+JSON.stringify(v31debug));",
    "  if (Number(v31debug.maxConcurrent || 0) !== 1) throw new Error('v31 follow overlap detected: '+JSON.stringify(v31debug));",
    "  if (Number(v31debug.currentConcurrent || 0) !== 0) throw new Error('v31 follow remained in flight after pause: '+JSON.stringify(v31debug));",
    '  if (afterFollow.visibleTokenOrdinal > followIndex + 120) throw new Error(`v31 double-jump suspected: target=${followIndex} visible=${afterFollow.visibleTokenOrdinal}`);',
    '  await page.evaluate(t => {',
    "    const a = document.getElementById('r3AudioElement');",
    '    a.pause();',
    '    a.playbackRate = 1;',
    '    a.defaultPlaybackRate = 1;',
    '    a.currentTime = t;',
    "    a.dispatchEvent(new Event('seeked'));",
    "    a.dispatchEvent(new Event('timeupdate'));",
    '  }, followTime);',
    '  await page.waitForTimeout(350);',
  ].join('\n'),
  'highSpeedAssertions',
);

replaceOnce(
  "  console.log(JSON.stringify({ phase: 'viewport-word-proof', ok: true, runtime, exactVisibleWordStart: true, expectedStart, actualStart: started.time, exactWordPageFollow: true, refreshResume: true, duplicatePostAfterRefresh: false, postCount, mediaGetCount, mediaRangeCount }));",
  "  console.log(JSON.stringify({ phase: 'viewport-word-proof', ok: true, runtime, exactVisibleWordStart: true, expectedStart, actualStart: started.time, exactWordPageFollow: true, highSpeed2xSerialized: true, refreshResume: true, duplicatePostAfterRefresh: false, postCount, mediaGetCount, mediaRangeCount }));",
  'finalProof',
);

fs.writeFileSync(outPath, s, 'utf8');
try {
  await import(pathToFileURL(outPath).href + `?v=${Date.now()}`);
} finally {
  try { fs.unlinkSync(outPath); } catch {}
}
