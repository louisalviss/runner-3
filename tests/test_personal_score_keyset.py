"""Behavioral regression for personal-v4 score feature keyset pagination.

Synthetic SQLite fixture only; no production D1 or credentials required.
"""
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "cloudflare/runner3-core/src/content-personalization.js").read_text()
PAGE_SIZE = 1000
COLUMNS = "f.item_id,f.feature_type,f.feature_key,f.weight,f.confidence,i.published_at"
FROM = "FROM content_features f JOIN content_items i ON i.item_id=f.item_id"
FILTER = "f.feature_type IN ('topic','mechanism','concept')"
ORDER = "ORDER BY f.item_id,f.feature_type,f.feature_key"


def load_fixture():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE content_items (item_id TEXT PRIMARY KEY, published_at TEXT)")
    db.execute("""CREATE TABLE content_features (
        item_id TEXT NOT NULL, feature_type TEXT NOT NULL,
        feature_key TEXT NOT NULL, weight REAL, confidence REAL,
        PRIMARY KEY(item_id, feature_type, feature_key))""")
    db.executemany(
        "INSERT INTO content_items VALUES (?,?)",
        [(f"item-{i:05d}", "2026-10-09") for i in range(1600)]
        + [("item-quo'te", None), ("item-🌐", "2026-10-08")],
    )
    types = ("topic", "mechanism", "concept", "source")
    features = [
        (f"item-{i // 3:05d}", types[i % 4], f"feature-{i:05d}", 1.0, 0.95)
        for i in range(4300)
    ]
    features += [
        ("item-quo'te", "topic", "a'quote", 2.0, 0.9),
        ("item-🌐", "concept", "unicode", 3.0, 0.8),
    ]
    db.executemany("INSERT INTO content_features VALUES (?,?,?,?,?)", features)
    return db


def baseline(db):
    rows = []
    offset = 0
    while True:
        page = db.execute(
            f"SELECT {COLUMNS} {FROM} WHERE {FILTER} {ORDER} LIMIT ? OFFSET ?",
            (PAGE_SIZE, offset),
        ).fetchall()
        rows += page
        if len(page) < PAGE_SIZE:
            return rows
        offset += len(page)


def keyset(db):
    rows = []
    cursor = None
    while True:
        seek = "AND (f.item_id,f.feature_type,f.feature_key) > (?,?,?)" if cursor else ""
        sql = f"SELECT {COLUMNS} {FROM} WHERE {FILTER} {seek} {ORDER} LIMIT ?"
        args = (*cursor, PAGE_SIZE) if cursor else (PAGE_SIZE,)
        page = db.execute(sql, args).fetchall()
        rows += page
        if len(page) < PAGE_SIZE:
            return rows
        cursor = tuple(page[-1][:3])


class TestPersonalScoreKeyset(unittest.TestCase):
    def test_full_result_parity_across_pages_and_quoted_keys(self):
        db = load_fixture()
        before = baseline(db)
        after = keyset(db)
        self.assertGreater(len(before), 3000)
        self.assertEqual(after, before)
        self.assertEqual(len({r[:3] for r in after}), len(after))
        self.assertTrue(any(r[0] == "item-quo'te" for r in after))
        self.assertTrue(any(r[0] == "item-🌐" for r in after))

    def test_canonical_runtime_uses_seek_not_offset(self):
        start = SOURCE.index("export async function recomputePersonalScores(")
        end = SOURCE.index("  const scoreRows = [];", start)
        ingest = SOURCE[start:end]
        self.assertIn("(f.item_id,f.feature_type,f.feature_key) > (?,?,?)", ingest)
        self.assertIn("query.bind(...cursor,PERSONAL_SCORE_READ_PAGE)", ingest)
        self.assertNotIn("LIMIT ? OFFSET ?", ingest)
        self.assertNotIn("offset += ", ingest)


if __name__ == "__main__":
    unittest.main()
