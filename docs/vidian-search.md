# Vidian Search / QA Engine

Canonical source corpus: `vidian-semantic-corpus-v2-full` from GitHub Actions run `31945936628` (8,826 unique Vidian URLs, full extractor v2, final semantic QA PASS).

## Purpose

Turn the canonical Vidian semantic corpus into a queryable local index without paid APIs or embeddings.

## Engine

- SQLite FTS5
- BM25 ranking
- `unicode61 remove_diacritics 2` tokenizer
- article-level URL/title/text retrieval
- no external API at query time

## Build

```bash
python scripts/vidian_search.py build \
  --corpus /path/to/vidian-semantic-corpus-v2-full.zip \
  --db vidian_fts.sqlite
```

The corpus may also be an extracted directory containing `chunks/*.jsonl.gz`.

## Query

```bash
python scripts/vidian_search.py query \
  --db vidian_fts.sqlite \
  --q "Cửu Giới" \
  --limit 8
```

Output is JSON with source URL, title, BM25 score and highlighted snippet. This is the retrieval layer for factual QA: retrieve top evidence first, then answer from the returned source passages/URLs.

## CI

`.github/workflows/vidian-search.yml` downloads the canonical corpus, builds the index, asserts exact cardinality `8826/8826/8826`, runs a Vietnamese smoke query, and uploads `vidian-search-index`.

## Canonical extraction lessons

1. `Nguồn:` cannot be treated as a universal footer marker; some historical Vidian templates place it before the article body.
2. GitHub Actions artifact enumeration must paginate beyond 100 artifacts.
3. Sampling/heuristics are useful for detection but not sufficient to prove complete reconstruction; the final canonical v2 was produced by full-refreshing all 8,826 URLs with extractor v2.
4. Semantic QA must reject separator-only pseudo-sentences and zero-word frames.
