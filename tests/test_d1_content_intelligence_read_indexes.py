"""No-network, no-production read-quota index migration equivalence checks."""
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'cloudflare/runner3-core/content-intelligence-schema.sql'
MIGRATION = ROOT / 'cloudflare/runner3-core/sql/content-intelligence-d1-read-indexes.sql'
EXPECTED = {'idx_content_items_collector_item', 'idx_user_content_events_item_type'}


class D1ReadIndexesTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript(SCHEMA.read_text())
        self.db.execute('INSERT INTO content_items(item_id,canonical_url,source_type,metadata_json) VALUES (?,?,?,?)',
                        ('auto-1','https://github.com/a/b','github','{"collector":"auto-intelligence-vps"}'))
        self.db.execute('INSERT INTO content_items(item_id,canonical_url,source_type,metadata_json) VALUES (?,?,?,?)',
                        ('rss-1','https://example.com/rss','rss','{"collector":"rss"}'))
        self.db.execute('INSERT INTO content_items(item_id,canonical_url,source_type,metadata_json) VALUES (?,?,?,?)',
                        ('auto-2','https://github.com/a/c','github','{"collector":"auto-intelligence-vps"}'))
        self.db.executemany('INSERT INTO user_content_events(item_id,event_type) VALUES (?,?)',
                            [('auto-1','deep_read'),('rss-1','shown'),('rss-1','deep_read'),('auto-2','shown')])
        self.db.commit()

    def test_migration_idempotent_read_only_data(self):
        snapshot = self.db.execute('SELECT item_id,event_type FROM user_content_events ORDER BY id').fetchall()
        text = MIGRATION.read_text()
        self.assertNotIn('DELETE FROM', text.upper())
        self.assertNotIn('UPDATE ', text.upper())
        self.db.executescript(text)
        self.db.executescript(text)
        self.assertEqual(self.db.execute('SELECT item_id,event_type FROM user_content_events ORDER BY id').fetchall(), snapshot)
        for table,index in [('content_items','idx_content_items_collector_item'),
                            ('user_content_events','idx_user_content_events_item_type')]:
            self.assertIn(index, [r[1] for r in self.db.execute('PRAGMA index_list('+repr(table)+')')])

    def test_collector_event_aggregation_equivalent(self):
        old = """SELECT e.event_type,COUNT(*) FROM user_content_events e
                 JOIN content_items i ON i.item_id=e.item_id
                 WHERE json_extract(i.metadata_json,'$.collector')=?
                 GROUP BY e.event_type ORDER BY e.event_type"""
        new = """SELECT e.event_type,COUNT(*) FROM content_items i
                 CROSS JOIN user_content_events e
                 WHERE json_extract(i.metadata_json,'$.collector')=?
                   AND e.item_id=i.item_id
                 GROUP BY e.event_type ORDER BY e.event_type"""
        for collector in ['auto-intelligence-vps','rss','none']:
            self.assertEqual(self.db.execute(old,(collector,)).fetchall(),
                             self.db.execute(new,(collector,)).fetchall())
        self.db.executescript(MIGRATION.read_text())
        plan = [row[3] for row in self.db.execute('EXPLAIN QUERY PLAN '+new,('auto-intelligence-vps',))]
        self.assertTrue(any('idx_content_items_collector_item' in line for line in plan),plan)

    def test_preference_rollup_excludes_shown_via_partial_index(self):
        partial = ROOT / 'cloudflare/runner3-core/sql/content-intelligence-d1-personal-signals-index.sql'
        self.db.executescript(partial.read_text())
        self.db.executescript(partial.read_text())
        plan = [row[3] for row in self.db.execute('''EXPLAIN QUERY PLAN
          SELECT item_id, MAX(event_at) FROM user_content_events
          WHERE event_type <> 'shown' GROUP BY item_id''')]
        self.assertTrue(any('idx_user_content_events_preference_signal' in line for line in plan),plan)

    def test_preference_lookup_index_available(self):
        self.db.executescript(MIGRATION.read_text())
        plan = [row[3] for row in self.db.execute("""EXPLAIN QUERY PLAN
            SELECT 1 FROM user_content_events INDEXED BY idx_user_content_events_item_type
            WHERE item_id IN ('auto-1','auto-2') AND event_type IN ('shown','deep_read') LIMIT 1""")]
        self.assertTrue(any('idx_user_content_events_item_type' in line for line in plan),plan)


if __name__ == '__main__':
    unittest.main()
