import { createHash } from 'node:crypto';
const key='core/ebook/smoke/final/Smoke.epub';
const token='smoke-core-token-v83';
const session=createHash('sha256').update('runner3-artifact-library-v1:'+token).digest('hex');
const mod=await import('../cloudflare/runner3-core/artifact-library-simple-entry.js?fastv83='+Date.now());
const request=new Request('https://example.test/artifact-library/read?key='+encodeURIComponent(key),{headers:{cookie:'r3_artifact_library='+session}});
const env={RUNNER3_CORE_TOKEN:token,ARTIFACTS:{head:async value=>value===key?{key:value}:null,list:async()=>({objects:[{key,size:1234,uploaded:new Date()}],truncated:false,delimitedPrefixes:[]})}};
const response=await mod.default.fetch(request,env,{});
const html=await response.text();
if(response.status!==200)throw new Error('fastpath status '+response.status+': '+html.slice(0,260));
if(response.headers.get('x-r3-reader-stable-shell')!=='v82')throw new Error('missing v82 stable-shell header');
if(response.headers.get('x-r3-reader-pagination-owner')!=='v82')throw new Error('missing v82 pagination header');
if(response.headers.get('x-r3-reader-fastpath')!=='v83-v82')throw new Error('missing v83 fastpath header');
for(const marker of [
  'data-r3-stable-shell-early-v82="1"',
  'data-r3-stable-shell-runtime-v82="1"',
  'html.r3-v82-restoring body::after',
]) if(!html.includes(marker))throw new Error('missing fastpath marker '+marker);
if(html.includes('data-r3-iframe-swipe="1"'))throw new Error('legacy iframe swipe owner still injected');
console.log('READER_V83_FASTPATH_V82_SMOKE=PASS bytes='+html.length);
