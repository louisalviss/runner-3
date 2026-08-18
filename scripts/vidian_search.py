#!/usr/bin/env python3
"""Build/query a zero-API SQLite FTS5 search index over Vidian semantic corpus.

Input may be either the final corpus ZIP or an extracted corpus directory containing
`chunks/*.jsonl.gz`. The index stores article-level searchable text plus source URL,
title and compact metadata. Query uses SQLite FTS5 BM25; no embeddings or paid API.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path


def iter_records(src: Path):
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            names = sorted(n for n in zf.namelist() if n.endswith(".jsonl.gz"))
            if not names:
                raise SystemExit("no semantic .jsonl.gz chunks found in ZIP")
            for name in names:
                with zf.open(name) as raw, gzip.open(raw, "rt", encoding="utf-8") as fh:
                    for line in fh:
                        if line.strip():
                            yield json.loads(line)
        return
    files = sorted(src.glob("chunks/*.jsonl.gz")) if src.is_dir() else []
    if not files:
        raise SystemExit("expected final corpus ZIP or directory with chunks/*.jsonl.gz")
    for p in files:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def frame_text(rec: dict) -> str:
    parts: list[str] = []
    # Preserve article surface text first when present.
    for key in ("title", "text", "body", "clean_text", "content"):
        v = rec.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    # Semantic corpus variants may store sentence/frame arrays instead of article text.
    for key in ("sentences", "frames", "semantic_frames"):
        arr = rec.get(key)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if isinstance(item, str):
                t = item.strip()
                if t:
                    parts.append(t)
            elif isinstance(item, dict):
                for k in ("text", "sentence", "surface", "raw"):
                    v = item.get(k)
                    if isinstance(v, str) and v.strip():
                        parts.append(v.strip())
                        break
    # Fall back to paragraph arrays if needed.
    paras = rec.get("paragraphs")
    if isinstance(paras, list):
        parts.extend(str(x).strip() for x in paras if str(x).strip())
    # Deduplicate adjacent/repeated representations while preserving order.
    seen = set(); out = []
    for p in parts:
        norm = re.sub(r"\s+", " ", p).strip()
        if norm and norm not in seen:
            seen.add(norm); out.append(norm)
    return "\n".join(out)


def build(src: Path, db: Path):
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript("""
      CREATE TABLE articles(
        rowid INTEGER PRIMARY KEY,
        url TEXT NOT NULL UNIQUE,
        title TEXT,
        text TEXT NOT NULL,
        meta_json TEXT
      );
      CREATE VIRTUAL TABLE articles_fts USING fts5(
        title, text, content='articles', content_rowid='rowid',
        tokenize='unicode61 remove_diacritics 2'
      );
      CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
        INSERT INTO articles_fts(rowid,title,text) VALUES(new.rowid,new.title,new.text);
      END;
    """)
    count = 0
    for rec in iter_records(src):
        url = str(rec.get("url") or rec.get("source_url") or "").strip()
        if not url:
            raise SystemExit(f"record without URL near #{count}")
        title = str(rec.get("title") or "").strip()
        text = frame_text(rec)
        if not text:
            # Keep corpus cardinality exact even if a future format lacks surface text.
            text = title or url
        meta = {k: rec.get(k) for k in ("status", "chunk", "category", "author", "date") if k in rec}
        con.execute(
            "INSERT INTO articles(url,title,text,meta_json) VALUES(?,?,?,?)",
            (url, title, text, json.dumps(meta, ensure_ascii=False, separators=(",", ":"))),
        )
        count += 1
        if count % 500 == 0:
            con.commit()
    con.commit()
    fts_count = con.execute("SELECT count(*) FROM articles_fts").fetchone()[0]
    uniq = con.execute("SELECT count(DISTINCT url) FROM articles").fetchone()[0]
    con.execute("PRAGMA optimize")
    con.close()
    print(json.dumps({"records": count, "unique_urls": uniq, "fts_rows": fts_count, "db": str(db)}, ensure_ascii=False))
    if count != uniq or count != fts_count:
        raise SystemExit("index cardinality mismatch")


def to_fts_query(q: str) -> str:
    terms = re.findall(r"[\wÀ-ỹĐđ]+", q, flags=re.UNICODE)
    if not terms:
        raise SystemExit("empty query")
    # AND gives high precision for factual lookup; caller can retry simpler terms.
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)


def query(db: Path, q: str, limit: int):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    fts_q = to_fts_query(q)
    rows = con.execute(
        """
        SELECT a.url,a.title,bm25(articles_fts,5.0,1.0) AS score,
               snippet(articles_fts,1,'[[',']]', ' … ',32) AS snippet
        FROM articles_fts
        JOIN articles a ON a.rowid=articles_fts.rowid
        WHERE articles_fts MATCH ?
        ORDER BY score LIMIT ?
        """,
        (fts_q, limit),
    ).fetchall()
    print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
    con.close()


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--corpus", required=True, type=Path)
    b.add_argument("--db", required=True, type=Path)
    q = sp.add_parser("query")
    q.add_argument("--db", required=True, type=Path)
    q.add_argument("--q", required=True)
    q.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()
    if args.cmd == "build": build(args.corpus, args.db)
    else: query(args.db, args.q, args.limit)


if __name__ == "__main__":
    main()
