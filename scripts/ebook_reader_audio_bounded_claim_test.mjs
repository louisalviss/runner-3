import assert from 'node:assert/strict';
import { handleBoundedEbookAudioInternal } from '../cloudflare/runner3-core/src/ebook-reader-audio-bounded-claim.js';

const TOKEN = 'test-core-token';
const QUEUE_PREFIX = 'audio-library/ebook-reader-queue/';
const ITEM_PREFIX = 'audio-library/items/';
const MEDIA_PREFIX = 'audio-library/media/';

class MemoryObject {
  constructor(value) { this.value = value; }
  async text() { return typeof this.value === 'string' ? this.value : JSON.stringify(this.value); }
}

class MemoryBucket {
  constructor() {
    this.store = new Map();
    this.uploaded = new Map();
    this.ops = [];
  }
  resetOps() { this.ops.length = 0; }
  async list({ prefix = '', limit = 1000 } = {}) {
    this.ops.push(['list', prefix, limit]);
    const keys = [...this.store.keys()].filter((key) => key.startsWith(prefix)).sort();
    return { objects: keys.slice(0, limit).map((key) => ({ key, uploaded: this.uploaded.get(key) || '2026-01-01T00:00:00Z' })) };
  }
  async get(key) {
    this.ops.push(['get', key]);
    return this.store.has(key) ? new MemoryObject(this.store.get(key)) : null;
  }
  async put(key, value) {
    this.ops.push(['put', key]);
    const decoded = typeof value === 'string' ? value : new TextDecoder().decode(value);
    this.store.set(key, decoded);
    if (!this.uploaded.has(key)) this.uploaded.set(key, new Date().toISOString());
  }
  async delete(key) {
    this.ops.push(['delete', key]);
    this.store.delete(key);
    this.uploaded.delete(key);
  }
  seed(key, value, uploaded = '2026-01-01T00:00:00Z') {
    this.store.set(key, typeof value === 'string' ? value : JSON.stringify(value));
    this.uploaded.set(key, uploaded);
  }
}

function id(n) { return `ebook-${n.toString(16).padStart(32, '0')}`; }
function queueKey(jobId) { return `${QUEUE_PREFIX}${jobId}.json`; }
function itemKey(jobId) { return `${ITEM_PREFIX}${jobId}.json`; }
function scriptKey(jobId) { return `${MEDIA_PREFIX}${jobId}/script.txt`; }
function seedJob(bucket, jobId, status, { processingAt = null } = {}) {
  bucket.seed(queueKey(jobId), { id: jobId, kind: 'ebook-reader', itemKey: itemKey(jobId), scriptKey: scriptKey(jobId), createdAt: '2026-01-01T00:00:00Z' });
  bucket.seed(itemKey(jobId), { id: jobId, kind: 'ebook-reader', status, processingAt, updatedAt: processingAt || '2026-01-01T00:00:00Z' });
  bucket.seed(scriptKey(jobId), 'Đây là nội dung kiểm tra đủ dài để mô phỏng một đoạn sách hợp lệ cho bộ tổng hợp giọng nói trên consumer VPS. '.repeat(2));
}
function req(path) {
  return new Request(`https://core.invalid${path}`, { headers: { authorization: `Bearer ${TOKEN}`, 'x-ebook-audio-worker': 'test-worker' } });
}
async function body(response) { return JSON.parse(await response.text()); }

{
  const bucket = new MemoryBucket();
  for (let n = 1; n <= 14; n++) seedJob(bucket, id(n), 'ready');
  const target = id(99);
  seedJob(bucket, target, 'pending');
  const env = { RUNNER3_CORE_TOKEN: TOKEN, AUDIO_MEDIA: bucket };

  bucket.resetOps();
  const first = await body(await handleBoundedEbookAudioInternal(req('/api/internal/ebook-reader-audio/job'), env));
  assert.equal(first.ok, true);
  assert.equal(first.job, null);
  assert.equal(first.claim.scanned, 10);
  assert.equal(first.claim.cleaned, 10);
  assert.equal(first.claim.scanLimit, 10);
  assert.ok(bucket.ops.length <= 31, `first claim used ${bucket.ops.length} bucket ops`);

  bucket.resetOps();
  const second = await body(await handleBoundedEbookAudioInternal(req('/api/internal/ebook-reader-audio/job'), env));
  assert.equal(second.ok, true);
  assert.equal(second.job.id, target);
  assert.equal(second.job.processingWorker, 'test-worker');
  assert.equal(second.job.processingLeaseSeconds, 900);
  assert.ok(bucket.ops.length <= 20, `second claim used ${bucket.ops.length} bucket ops`);
  const stored = JSON.parse(bucket.store.get(itemKey(target)));
  assert.equal(stored.status, 'processing');
  assert.equal(stored.processingWorker, 'test-worker');
  assert.equal(stored.claimAttempt, 1);
}

{
  const bucket = new MemoryBucket();
  const leased = id(200);
  const pending = id(201);
  seedJob(bucket, leased, 'processing', { processingAt: new Date().toISOString() });
  seedJob(bucket, pending, 'pending');
  const env = { RUNNER3_CORE_TOKEN: TOKEN, AUDIO_MEDIA: bucket };
  const result = await body(await handleBoundedEbookAudioInternal(req('/api/internal/ebook-reader-audio/job'), env));
  assert.equal(result.job.id, pending);
  assert.equal(result.claim.leased, 1);
  const leasedItem = JSON.parse(bucket.store.get(itemKey(leased)));
  assert.equal(leasedItem.claimAttempt, undefined);
}

{
  const bucket = new MemoryBucket();
  const stale = id(300);
  seedJob(bucket, stale, 'processing', { processingAt: new Date(Date.now() - 16 * 60 * 1000).toISOString() });
  const env = { RUNNER3_CORE_TOKEN: TOKEN, AUDIO_MEDIA: bucket };
  const result = await body(await handleBoundedEbookAudioInternal(req('/api/internal/ebook-reader-audio/job'), env));
  assert.equal(result.job.id, stale);
  const item = JSON.parse(bucket.store.get(itemKey(stale)));
  assert.equal(item.claimAttempt, 1);
  assert.equal(item.processingWorker, 'test-worker');
}

{
  const bucket = new MemoryBucket();
  const env = { RUNNER3_CORE_TOKEN: TOKEN, AUDIO_MEDIA: bucket };
  bucket.resetOps();
  const response = await handleBoundedEbookAudioInternal(req('/api/internal/ebook-reader-audio/health'), env);
  const health = await body(response);
  assert.deepEqual(health, { ok: true, mode: 'vps-bounded-lease-v1', scanLimit: 10, processingLeaseSeconds: 900, mutatesQueue: false });
  assert.equal(bucket.ops.length, 0, 'health endpoint must not touch queue/R2');
}

console.log(JSON.stringify({ ok: true, scanLimit: 10, processingLeaseSeconds: 900, staleCleanupBounded: true, freshLeaseSkipped: true, staleLeaseReclaimed: true, healthMutatesQueue: false }));
console.log('EBOOK_AUDIO_BOUNDED_CLAIM_TEST=PASS');
