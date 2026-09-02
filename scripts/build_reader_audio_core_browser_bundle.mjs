import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { build } from 'esbuild';

execFileSync('python3', ['scripts/apply_reader_v44_build_patch.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v49_epub_idb_cache.py'], { stdio: 'inherit' });
execFileSync('node', ['cloudflare/runner3-core/reader-audio-core/reader-v49-epub-cache-smoke.mjs'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v51_live_session_library.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_artifact_library_r2_upload.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v52_r2_upload.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v52_r2_upload.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v53_simple_library_upload.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v54_library_ux.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v54_library_ux.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v54_library_ux.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v55_progress_real_covers.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v55_progress_real_covers.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v55_live_cover_followup.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v55_progress_real_covers.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v56_auto_enrich_progress_migration.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v56_auto_enrich_progress_migration.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v56_auto_enrich_progress_migration.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v57_resource_fastpath.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v57_resource_fastpath.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v57_resource_fastpath.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v58_rendered_normalize.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v58_live_search_normalize.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v58_atomic_boot_library_sort.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v58_atomic_boot_library_sort.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v58_atomic_boot_library_sort.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v59_compact_library_filter.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v59_compact_library_filter.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v59_compact_library_filter.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v60_audio_prefetch.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v60_audio_prefetch.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v60_audio_prefetch.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v61_safari_boot_geometry.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v61_safari_boot_geometry.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v61_safari_boot_geometry.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v62_paginated_vertical_clamp.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v62_paginated_vertical_clamp.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v62_paginated_vertical_clamp.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v63_library_recovery.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v63_library_recovery.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v63_library_recovery.py'], { stdio: 'inherit' });
execFileSync('python3', ['-m', 'py_compile', 'scripts/patch_reader_v64_progress_repair.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/patch_reader_v64_progress_repair.py'], { stdio: 'inherit' });
execFileSync('python3', ['scripts/check_reader_v64_progress_repair.py'], { stdio: 'inherit' });
execFileSync('node', ['--check', 'cloudflare/runner3-core/src/ebook-reader-audio.js'], { stdio: 'inherit' });
execFileSync('node', ['--check', 'cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js'], { stdio: 'inherit' });
execFileSync('node', ['--check', 'cloudflare/runner3-core/artifact-library-simple-entry.js'], { stdio: 'inherit' });
execFileSync('node', ['--check', 'cloudflare/runner3-core/artifact-library-reader-v2-entry.js'], { stdio: 'inherit' });
execFileSync('node', ['--check', 'cloudflare/runner3-core/artifact-library-reader-v5-entry.js'], { stdio: 'inherit' });
execFileSync('node', ['--check', 'cloudflare/runner3-core/opportunity-router-entry.js'], { stdio: 'inherit' });

const entry = path.resolve('cloudflare/runner3-core/reader-audio-core/browser-production-integration.js');
const output = path.resolve('cloudflare/runner3-core/reader-audio-core/browser-production-bundle.generated.js');
const result = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: 'iife',
  platform: 'browser',
  target: ['es2020'],
  minify: true,
  legalComments: 'none',
});
if (!result.outputFiles?.length) throw new Error('READER_AUDIO_CORE_BUNDLE_EMPTY');
let source = result.outputFiles[0].text;
source = source.replace(/<\/script/gi, '<\\/script');
fs.writeFileSync(output, `// Generated by scripts/build_reader_audio_core_browser_bundle.mjs\nexport default ${JSON.stringify(source)};\n`, 'utf8');
console.log(`READER_AUDIO_CORE_BROWSER_BUNDLE=PASS bytes=${Buffer.byteLength(source)}`);
