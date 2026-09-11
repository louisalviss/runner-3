const mod=await import('../cloudflare/runner3-core/artifact-library-reader-v82-stable-shell-entry.js?smoke='+Date.now());
const key='core/ebook/smoke/final/Smoke.epub';
const request=new Request('https://example.test/artifact-library/read?key='+encodeURIComponent(key));
const env={ARTIFACTS:{head:async value=>value===key?{key:value}:null}};
const response=await mod.default.fetch(request,env,{});
const html=await response.text();
if(response.status!==200)throw new Error('compose status '+response.status+': '+html.slice(0,240));
if(response.headers.get('x-r3-reader-stable-shell')!=='v82')throw new Error('missing stable-shell header');
if(response.headers.get('x-r3-reader-pagination-owner')!=='v82')throw new Error('missing pagination-owner header');
for(const marker of [
  'data-r3-stable-shell-early-v82="1"',
  'data-r3-stable-shell-runtime-v82="1"',
  'data-r3-audio-continuity-v34="1"',
  'data-r3-audio-continuity-v35="1"',
  'cfiFromRange(range)',
  "owner: 'stable-shell-v82'",
  'data-r3-nonblocking-restore-v89="1"',
  'body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(76px',
]) if(!html.includes(marker))throw new Error('missing composed marker '+marker);
console.log('READER_V82_OUTER_COMPOSITION_SMOKE=PASS bytes='+html.length);
