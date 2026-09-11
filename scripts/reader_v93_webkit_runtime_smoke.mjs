import fs from 'node:fs';
const v82=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v82-patch.js','utf8');
const v9=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v9-runtime-entry.js','utf8');
const v10=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v10-runtime-entry.js','utf8');
const shell=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v82-stable-shell-entry.js','utf8');
if(!v82.includes('data-r3-webkit-inline-compat-v93="1"')) throw new Error('V93_INLINE_COMPAT_MARKER_MISSING');
if(!v82.includes('globalThis.__name=globalThis.__name||((target,value)=>target)')) throw new Error('V93_NAME_HELPER_MISSING');
for(const [name,text] of [['v9',v9],['v10',v10]]){
  if(!text.includes("connect-src 'self' https: blob:")) throw new Error('V93_BLOB_CONNECT_MISSING_'+name);
}
if(!shell.includes("X-R3-Reader-WebKit-Runtime', 'compat-v93'")) throw new Error('V93_LIVE_HEADER_MISSING');
console.log('READER_V93_WEBKIT_RUNTIME_SMOKE=PASS');
