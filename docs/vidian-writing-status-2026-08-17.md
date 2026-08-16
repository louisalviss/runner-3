# Vidian Writing Brain — Final Status 2026-08-17

## Canonical source and coverage

- Source corpus scanned: 8,826 canonical Vidian records.
- Source category: `chi-dao-sang-tac`.
- Category URLs: 282.
- Matched category articles in canonical corpus: 282.
- Missing category URLs: 0.
- Source prose persisted: no. Evidence surfaces are reconstructed from parser dependency-edge token order and are not verbatim quotations.

## Final Writing Knowledge Layer

- Schema: `vidian-writing-knowledge-v1`.
- Quality/interface generation: Writing Quality v1.2.
- Craft taxonomy: 23 topics.
- Passages: 11,921.
- Directive rules: 4,425.
  - do: 3,006
  - dont: 560
  - warning: 410
- Topics with rules: 23.

## Retrieval

- Lexical: SQLite FTS5 BM25.
- Semantic: TF-IDF + TruncatedSVD + cosine.
- Semantic dimensions: 96.
- Semantic features: 39,835.
- Semantic vectors: 11,939.
- User-facing retrieval applies sentence-first topic assignment, weighted topic tie-breaking, Vietnamese-diacritic-aware directive parsing, ambiguous-marker suppression, low-signal pruning, topic alignment, actionable-evidence filtering and reranking.

## User-facing interfaces

Preferred CLI: `scripts/vidian_writing_agent.py`.

Supported modes:

1. `query` — concept/rule retrieval.
2. `direct` — writing brief → relevant craft dimensions → `must_do` / `avoid` / `techniques` evidence packet.
3. `review` — draft → detected craft dimensions → evidence-backed review criteria.
4. `checklist` — focused actionable checklist for a single craft topic.

GitHub Actions interface: `.github/workflows/vidian-writing-interface.yml`.

The interface self-test ran end-to-end on run `31966882404`: download durable release → run Direct → validate provenance/actionability → upload result artifact. It completed successfully.

## Final QA/build

Final Writing Brain build run: `31966693850`.

The following steps all completed successfully:

- Download canonical corpus and SHA verification.
- Build Writing Knowledge Layer.
- QA gate.
- Agent smoke tests.
- Package.
- Publish durable release.
- Upload Actions artifact.

Regression gates cover known false positives including Vietnamese diacritic collisions (`chớ` vs `cho`, `kỵ` vs `kỳ`), proper-name `Kỵ`, ordinary `cách một ngày`, generic `tốt nhất`, broad `chương` retention matching, and topic alignment.

## Durable release

- Tag: `vidian-writing-v1-2026-08-17`.
- Release ID: 371400985.
- Asset: `vidian-writing-v1-2026-08-17.zip`.
- Asset ID: 517130362.
- Asset size: 38,512,468 bytes.
- Asset SHA256: `6753fed05dcca517750569eb5db02541c36a78d473ba168105429dd4ea362b91`.

Final build Actions artifact:

- Artifact ID: 9268693243.
- Artifact size: 77,008,317 bytes.
- Artifact digest: `sha256:e40c2e14cb0aec1ae11a9be1fef2beda29ca3ecd7ddc13cab1e96857e1404c9b`.

Interface smoke artifact:

- Artifact ID: 9268726746.
- Artifact digest: `sha256:8ee98391210fc510cdfdcc84b7aacdfdb7cff1e159a9edca2b347ef418e1719f`.

## Known limitation

This is a retrieval/directive layer over parser-reconstructed evidence, not a replacement for original source text. For exact wording or disputed advice, verify against the original Vidian article URL. Semantic retrieval is latent TF-IDF/SVD rather than a neural embedding model.
