import { handleContentIntelligence } from '../cloudflare/runner3-core/src/content-intelligence.js';

const canonicalUrl = 'https://example.test/social/post/123';
const existingItemId = '123';
const proposedItemId = 'facebook:123';
const seen = [];

class Statement {
  constructor(sql) { this.sql = sql; this.args = []; }
  bind(...args) { this.args = args; seen.push({ sql: this.sql, args }); return this; }
  async first() {
    if (this.sql.includes('SELECT item_id FROM content_items WHERE canonical_url=?')) return { item_id: existingItemId };
    if (this.sql.includes('SELECT COUNT(*) AS n, MAX(id) AS id FROM user_content_events')) return { n: 1, id: 77 };
    throw new Error('unexpected first(): ' + this.sql);
  }
  async run() {
    if (this.sql.includes('INSERT INTO content_items(')) {
      if (this.args[0] !== existingItemId) throw new Error('item upsert did not reuse canonical identity');
      return { meta: { changes: 0 } };
    }
    if (this.sql.includes('UPDATE content_items SET last_seen_at=')) {
      if (this.args[0] !== existingItemId) throw new Error('heartbeat used proposed identity');
      return { meta: { changes: 0 } };
    }
    if (this.sql.includes('INSERT OR IGNORE INTO user_content_events')) {
      if (this.args[0] !== existingItemId) throw new Error('interest event used proposed identity');
      return { meta: { changes: 0 } };
    }
    throw new Error('unexpected run(): ' + this.sql);
  }
}

const env = {
  RUNNER3_CORE_TOKEN: 'test-token',
  DB: { prepare(sql) { return new Statement(sql); } },
};

const url = new URL('https://example.test/content-intelligence/interests/ingest');
const request = new Request(url, {
  method: 'POST',
  headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
  body: JSON.stringify({
    item: { item_id: proposedItemId, canonical_url: canonicalUrl, source_type: 'facebook' },
    render_id: 'interest-save:identity-regression:123',
  }),
});
const response = await handleContentIntelligence(request, env, url);
const body = await response.json();
if (response.status !== 200 || body.ok !== true) throw new Error('interest ingest failed: ' + JSON.stringify(body));
if (body.item_id !== existingItemId) throw new Error('response did not expose reused canonical item id');
if (body.d1_readback !== true || body.event_id !== 77) throw new Error('durable readback proof missing');
if (!seen.some((x) => x.sql.includes('SELECT item_id FROM content_items WHERE canonical_url=?') && x.args[0] === canonicalUrl)) {
  throw new Error('canonical identity lookup was not executed');
}
console.log('CONTENT_IDENTITY_RESOLUTION_PASS', JSON.stringify({ canonicalUrl, proposedItemId, existingItemId }));
