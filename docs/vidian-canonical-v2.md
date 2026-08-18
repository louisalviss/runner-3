# Vidian Canonical Corpus v2

Canonical corpus artifact: `vidian-semantic-corpus-v2-full`

- Source workflow run: `31945936628`
- Artifact ID: `9265535962`
- Records: `8,826`
- Unique URLs: `8,826`
- Final semantic QA: PASS
- Artifact SHA-256: `f176ec9b1a0d5e71a6dfd0cf2f261ae2a72e04147bb0117e7c6a6885eb83c7b4`
- Artifact size: `129,952,248` bytes
- Created: 2026-08-16

The v1 corpus is superseded by this v2 full-refresh corpus. Do not use v1 for factual QA.

## Why v2 is canonical

The old extractor stopped at the first `Nguồn:` marker after the H1. Historical Vidian templates can place `Nguồn:` before the real article body, so some v1 pages were structurally valid but semantically truncated. v2 removes that invalid stop rule, keeps meaningful short fragments, drops separator-only noise, full-refreshes all 8,826 URLs, rebuilds all 64 semantic shards, and passes exact merge/final QA.

## Retrieval

Use `scripts/vidian_search.py` or workflow `vidian-search.yml` to build a SQLite FTS5/BM25 index from this artifact before answering corpus questions.
