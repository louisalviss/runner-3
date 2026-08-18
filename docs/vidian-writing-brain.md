# Vidian Writing Brain

Purpose: turn Vidian `chi-dao-sang-tac` into a specialized, evidence-backed writing knowledge layer rather than mixing writing advice into the general story/entity graph.

## Data boundary

- Category membership is recovered from the live `chi-dao-sang-tac` listing and joined against the canonical 8,826-article semantic corpus.
- The category listing is treated as Vidian's own classification. The build does not brute-force every article page because doing so triggers 429/503 rate limits and adds an unnecessary network dependency.
- The canonical corpus does not persist raw source prose. `rule` and `evidence_surface` are reconstructed from dependency-edge token order and must not be presented as verbatim quotations.
- Every evidence candidate retains the source URL and source sentence SHA for verification.

## Taxonomy

The v1 taxonomy covers 23 craft dimensions: opening/hook, plot/arc structure, pacing/tension, cliffhanger, character design, motivation/conflict, antagonist, progression/power, reward/payoff, worldbuilding, system design, foreshadow/payoff, mystery/reveal, stakes, dialogue/voice, description/scene, combat/action, emotion/immersion, romance/relationship, style/prose, editing/consistency, serialization/reader retention, and theme/meaning.

Rule candidates are classified as `do`, `dont`, `warning`, `technique`, `example`, `diagnostic`, or `principle`.

## Quality layer

Use `scripts/vidian_writing_agent.py` for user-facing retrieval. The lower-level `scripts/vidian_writing.py` remains the index/build engine.

The quality layer adds:

- Vietnamese-diacritic-aware directive detection so `chớ` does not collapse into `cho`, and `kỵ` does not collapse into `kỳ`.
- Low-signal descriptive pruning for category items that are not strongly craft-oriented.
- Actionable-evidence filtering and reranking for Query, Direct, Review, and Checklist.
- Regression gates requiring directive labels to be supported by the visible reconstructed rule text.

## Interfaces

### Query

Search actionable writing knowledge by concept with optional topic/kind filters.

```bash
python scripts/vidian_writing_agent.py query --index vidian_writing --q "mở đầu tiên hiệp" --mode hybrid
```

### Direct

Convert a writing brief into evidence grouped into `must_do`, `avoid`, and `techniques` for the most relevant craft dimensions.

```bash
python scripts/vidian_writing_agent.py direct --index vidian_writing --brief "Tiên hiệp, main thận trọng, progression rõ, arc 30 chương"
```

Use this before drafting. Treat rules as craft constraints, not prose to copy.

### Review

Convert a draft into a review packet: detect likely craft dimensions and retrieve actionable Vidian rules as critique criteria.

```bash
python scripts/vidian_writing_agent.py review --index vidian_writing --file chapter.md
```

Use this after drafting. Identify concrete weaknesses in the draft and support recommendations with retrieved evidence where possible.

### Checklist

Retrieve the strongest actionable rule candidates for one craft dimension.

```bash
python scripts/vidian_writing_agent.py checklist --index vidian_writing --topic character_design
```

## Recommended composition loop

1. Brief → `direct`.
2. Convert retrieved rules into scene/arc-specific constraints.
3. Draft without copying source wording.
4. Draft → `review`.
5. Repair only weaknesses that are actually present and evidence-supported.
6. Use `checklist` for focused passes such as character, pacing, progression, worldbuilding, or dialogue.
7. For exact wording or disputed advice, open the original Vidian source URL; parser-derived text is not authoritative quotation text.

## Retrieval

- SQLite FTS5 BM25.
- TF-IDF + TruncatedSVD + cosine latent semantic retrieval.
- Filters by topic and rule kind.
- This is not an LLM embedding vector database.
