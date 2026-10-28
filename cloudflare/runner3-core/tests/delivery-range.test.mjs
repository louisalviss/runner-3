import assert from 'node:assert/strict';
import { handleDelivery } from '../src/delivery.js';

const origin = 'https://runner3-core.example.test';
const data = Uint8Array.from({ length: 4096 }, (_, i) => i % 251);
const key = 'core/video/pokemon-fix/clip.mp4';
const metadata = {
  size: data.length,
  httpEtag: '"test-etag"',
  writeHttpMetadata(headers) { headers.set('content-type', 'video/mp4'); },
};
let getCalls = 0;
const env = {
  RUNNER3_CORE_TOKEN: 'test-secret-for-signed-links',
  ARTIFACTS: {
    async head(k) { return k === key ? metadata : null; },
    async get(k, options) {
      if (k !== key) return null;
      getCalls += 1;
      const offset = options?.range?.offset ?? 0;
      const length = options?.range?.length ?? data.length;
      const payload = data.slice(offset, offset + length);
      return { ...metadata, body: new Response(payload).body };
    },
  },
};

async function handler(request) {
  return handleDelivery(request, env, new URL(request.url));
}

const signedRequest = new Request(origin + '/delivery-links', {
  method: 'POST',
  headers: { Authorization: 'Bearer ' + env.RUNNER3_CORE_TOKEN, 'content-type': 'application/json' },
  body: JSON.stringify({ project: 'video', scope: 'pokemon-fix', name: 'clip.mp4', ttl_seconds: 3600 }),
});
const signedResult = await handler(signedRequest);
assert.equal(signedResult.status, 200);
const payload = await signedResult.json();
assert.equal(payload.ok, true);
const link = payload.delivery.url;

async function checkCase(range, status, first, last) {
  const headers = range ? { range } : {};
  const result = await handler(new Request(link, { headers }));
  assert.equal(result.status, status, range || 'no range');
  assert.equal(result.headers.get('content-type'), 'video/mp4');
  assert.equal(result.headers.get('accept-ranges'), 'bytes');
  assert.match(result.headers.get('content-disposition'), /^inline;/);
  const bytes = new Uint8Array(await result.arrayBuffer());
  if (status === 416) {
    assert.equal(result.headers.get('content-range'), 'bytes */4096');
    assert.equal(bytes.length, 0);
  } else {
    assert.equal(bytes.length, last - first + 1);
    assert.deepEqual(bytes, data.slice(first, last + 1));
    if (status === 206) assert.equal(result.headers.get('content-range'), 'bytes ' + first + '-' + last + '/4096');
    else assert.equal(result.headers.get('content-range'), null);
  }
  assert.equal(Number(result.headers.get('content-length')), bytes.length);
  return result;
}

await checkCase(null, 200, 0, 4095);
await checkCase('bytes=0-0', 206, 0, 0);
await checkCase('bytes=0-1023', 206, 0, 1023);
await checkCase('bytes=1000-1023', 206, 1000, 1023);
await checkCase('bytes=1000-', 206, 1000, 4095);
await checkCase('bytes=-512', 206, 3584, 4095);
await checkCase('bytes=4090-999999', 206, 4090, 4095);
const beforeInvalid = getCalls;
await checkCase('bytes=4096-', 416, 0, 0);
await checkCase('bytes=300-200', 416, 0, 0);
await checkCase('bytes=-0', 416, 0, 0);
await checkCase('bytes=0-100,200-300', 416, 0, 0);
assert.equal(getCalls, beforeInvalid, 'malformed ranges must not fetch private R2 bytes');

const head = await handler(new Request(link, { method: 'HEAD' }));
assert.equal(head.status, 200);
assert.equal(head.headers.get('content-length'), '4096');
assert.equal(head.headers.get('accept-ranges'), 'bytes');
assert.equal(head.body, null);
const bad = new URL(link);
bad.searchParams.set('sig', 'invalid');
const rejected = await handler(new Request(bad));
assert.equal(rejected.status, 401);
const untrusted = await handler(new Request(origin + '/delivery/video/pokemon-fix/clip.mp4'));
assert.equal(untrusted.status, 401);

console.log('RANGE_DELIVERY_TESTS=PASS cases=14 signed-auth=PASS HEAD=PASS invalid-range=416');


// Audio: browser/Safari should play rather than download, with byte ranges for seeking.
// All other artifacts retain their attachment disposition.
const audioObjects = {
  'core/music/chords/preview.mp3': 'audio/mpeg',
  'core/music/chords/notes.mid': 'audio/midi',
  'core/docs/public/manual.pdf': 'application/pdf',
};
const modifiedEnv = {
  ...env,
  ARTIFACTS: {
    async head(k) {
      const contentType = audioObjects[k];
      if (!contentType) return null;
      return { ...metadata, writeHttpMetadata(h) { h.set('content-type', contentType); } };
    },
    async get(k, opt) {
      const contentType = audioObjects[k];
      if (!contentType) return null;
      const offset = opt?.range?.offset ?? 0;
      const length = opt?.range?.length ?? data.length;
      return {
        ...metadata,
        writeHttpMetadata(h) { h.set('content-type', contentType); },
        body: new Response(data.slice(offset, offset + length)).body,
      };
    },
  },
};
async function newLink(project, scope, name) {
  const result = await handleDelivery(
    new Request(origin + '/delivery-links', {
      method: 'POST', headers: { Authorization: 'Bearer ' + env.RUNNER3_CORE_TOKEN, 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, scope, name, ttl_seconds: 3600 }),
    }), modifiedEnv, new URL(origin + '/delivery-links')
  );
  assert.equal(result.status, 200);
  return (await result.json()).delivery.url;
}
for (const [project, scope, name, expectedType, expectedMode] of [
  ['music','chords','preview.mp3','audio/mpeg','inline'],
  ['music','chords','notes.mid','audio/midi','inline'],
  ['docs','public','manual.pdf','application/pdf','attachment'],
]) {
  const audioLink = await newLink(project, scope, name);
  for (const range of [null, 'bytes=100-199']) {
    const request = new Request(audioLink, { headers: range ? {Range: range} : {} });
    const result = await handleDelivery(request, modifiedEnv, new URL(audioLink));
    assert.equal(result.status, range ? 206 : 200);
    assert.equal(result.headers.get('content-type'), expectedType);
    assert.match(result.headers.get('content-disposition'), new RegExp('^'+expectedMode+';'));
    assert.equal(result.headers.get('accept-ranges'), 'bytes');
    assert.equal((await result.arrayBuffer()).byteLength, range ? 100 : 4096);
  }
  const headRequest = new Request(audioLink, {method:'HEAD'});
  const headResult = await handleDelivery(headRequest, modifiedEnv, new URL(audioLink));
  assert.equal(headResult.status, 200);
  assert.match(headResult.headers.get('content-disposition'), new RegExp('^'+expectedMode+';'));
  assert.equal(headResult.headers.get('content-length'), '4096');
}
console.log('AUDIO_INLINE_DELIVERY_TESTS=PASS audio/mp3 audio/midi GET/HEAD/RANGE pdf-attachment');
