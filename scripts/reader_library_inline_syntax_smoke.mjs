import { createHash } from 'node:crypto';
import app from '../cloudflare/runner3-core/artifact-library-simple-entry.js';

const token='reader-inline-syntax-smoke-token';
const session=createHash('sha256').update(`runner3-artifact-library-v1:${token}`).digest('hex');
const request=new Request('https://reader-smoke.invalid/artifact-library',{headers:{Cookie:`r3_artifact_library=${session}`}});
const response=await app.fetch(request,{RUNNER3_CORE_TOKEN:token},{});
if (response.status !== 200) throw new Error(`LIBRARY_HTML_HTTP_${response.status}`);
const html = await response.text();
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)]
  .map((m) => m[1])
  .filter((source) => source.trim().length > 0);
if (!scripts.length) throw new Error('LIBRARY_INLINE_SCRIPT_MISSING');
for (let i = 0; i < scripts.length; i += 1) {
  try { new Function(scripts[i]); }
  catch (error) { throw new Error(`LIBRARY_INLINE_SCRIPT_SYNTAX_${i}: ${error.message}`); }
}
console.log(`READER_LIBRARY_INLINE_SYNTAX=PASS scripts=${scripts.length}`);
