import { handleContentIntelligence } from '../cloudflare/runner3-core/src/content-intelligence.js';

const TEST_URL = 'https://example.test/content-intelligence/items';

async function runCase(changed) {
  const heartbeatIds = [];
  const queryCount = { items: 0, heartbeat: 0 };
  const DB = {
    prepare(sql) {
      const statement = {
        sql,
        args: [],
        bind(...args) { statement.args = args; return statement; },
        async first() { return null; },
        async all() { return { results: [] }; },
        async run() { return { meta: { changes: 0 } }; },
      };
      return statement;
    },
    async batch(statements) {
      if (!statements.length) throw new Error('no empty batches permitted');
      if (statements[0].sql.includes('INSERT INTO content_items')) {
        queryCount.items += statements.length;
        return statements.map((_, i) => ({ meta: { changes: changed[i] ? 1 : 0 } }));
      }
      if (statements[0].sql.includes('UPDATE content_items SET last_seen_at')) {
        queryCount.heartbeat += statements.length;
        for (const stmt of statements) heartbeatIds.push(stmt.args[0]);
        return statements.map(() => ({ meta: { changes: 1 } }));
      }
      return statements.map(() => ({ meta: { changes: 0 } }));
    },
  };
  const rows = changed.map((_, i) => ({
    item_id: 'item-' + i,
    canonical_url: 'https://example.test/item-' + i,
    source_type: 'web',
    title: 'Example item',
  }));
  const request = new Request(TEST_URL, {
    method: 'POST',
    headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  });
  const response = await handleContentIntelligence(request, { DB, RUNNER3_CORE_TOKEN: 'test-token' }, new URL(TEST_URL));
  if (response?.status !== 200) throw new Error('unexpected HTTP status ' + response?.status);
  return { result: await response.json(), heartbeatIds, queryCount };
}

const allChanged = await runCase([true, true, true]);
if (allChanged.result.item_changes !== 3 || allChanged.result.heartbeat_changes !== 0 ||
    allChanged.queryCount.heartbeat !== 0) {
  throw new Error('changed upserts must skip redundant heartbeat');
}

const noChanges = await runCase([false, false, false]);
if (noChanges.result.item_changes !== 0 || noChanges.result.heartbeat_changes !== 3 ||
    noChanges.queryCount.heartbeat !== 3 || noChanges.heartbeatIds.join(',') !== 'item-0,item-1,item-2') {
  throw new Error('unchanged items must retain six-hour heartbeat path');
}

const mixed = await runCase([true, false, true, false]);
if (mixed.result.item_changes !== 2 || mixed.result.heartbeat_changes !== 2 ||
    mixed.heartbeatIds.join(',') !== 'item-1,item-3') {
  throw new Error('mixed upserts must only heartbeat unchanged items');
}

console.log('D1_SKIP_REDUNDANT_ITEM_HEARTBEAT_PASS', JSON.stringify({
  changed_only_heartbeat_statements: allChanged.queryCount.heartbeat,
  unchanged_heartbeat_statements: noChanges.queryCount.heartbeat,
  mixed_heartbeat_statements: mixed.queryCount.heartbeat,
}));
