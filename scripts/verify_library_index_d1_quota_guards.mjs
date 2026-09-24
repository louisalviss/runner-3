import fs from 'node:fs';
const file = 'cloudflare/runner3-core/src/library-index.js';
const src = fs.readFileSync(file, 'utf8');
const required = [
  'WHERE ${TABLE}.row_hash IS NOT excluded.row_hash',
  "WHERE library_index_meta_v1.v IS NOT excluded.v",
  'const changed = writeResults.reduce',
  'if (changed > 0)',
  'accepted: items.length, changed,'
];
for (const needle of required) {
  if (!src.includes(needle)) throw new Error(`LIBRARY_D1_QUOTA_GUARD_MISSING: ${needle}`);
}
console.log('LIBRARY_D1_QUOTA_GUARDS_PASS');
