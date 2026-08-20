# Webnovel Writing Brain — Checkpoint 2026-08-21

## Production baseline

- Default knowledge mode: `semantic-canonical-context-nli-first`
- Language mode: `vi-first`
- Production release: `webnovel-writing-brain-nli-v2-3-2026-08-20`
- Production asset: `webnovel-writing-brain-nli-v2-3-2026-08-20.zip`
- Passages/evidence preserved: 21,210
- Atomic rules: 23,509
- Canonical rules: 16,697
- Cross-source canonical rules: 1,098
- Context relations: 26,320
- Retrieval ranking preserved from V2.2/V2.1 semantic baseline.

## Relation state after Context V2.2 + NLI V2.3

Final relations:
- complementary: 22,412
- conditional: 2,538
- true_conflict: 256
- direction_error: 10
- review: 1,104

V2.3 resolved 1,390 of the 2,494 unresolved V2.2 review pairs (55.7338%). Remaining review rate: 4.1945% of all 26,320 relations.

NLI model: `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`.

Model sanity checks:
- paraphrase entailment: 0.998555
- explicit contradiction: 0.999454
- contextual neutral: 0.992848

## Decision / freeze point

Do **not** aggressively force-resolve the remaining 1,104 review relations. At this point marginal benefit is low and false-resolution risk rises.

Freeze V2.3 as the stable baseline and move from knowledge engineering to real-world validation.

## Next step — Real-World Benchmark V1

Build an 80–120 task benchmark covering at least:
- chapter-1/opening hooks
- 20–50 chapter outlines
- progression / power-system design
- protagonist / antagonist design
- pacing / cliffhanger
- combat/action scenes
- worldbuilding
- rewriting weak prose/scenes
- logic / continuity / foreshadow-payoff review
- continuing chapters from prior context

For every task compare:
1. baseline AI without Writing Brain
2. AI using Writing Brain V2.3

Score at minimum:
- coherence
- specificity
- usefulness
- repetition
- contradiction rate
- genre fit
- reader hook
- continuity retention

Trace regressions back to retrieved rules/evidence instead of changing the knowledge layer blindly.

## Third-source gate

**Do not add a third source yet.**

Only after the real-world benchmark shows a clear, robust improvement over baseline should a third source be added (examples: Zhihu, Longkong, or another high-quality Chinese webnovel-writing source).

Any new source must enter through the existing pipeline:

`raw evidence -> atomic rules -> semantic canonicalization -> context resolution -> NLI -> retrieval`

The third source should expand coverage / improve weak benchmark dimensions, not simply increase corpus size.

## Canonical next action

Implement **Writing Brain Real-World Benchmark V1** first. If it passes clearly, then evaluate and ingest a third source. If it does not, diagnose benchmark regressions before adding more knowledge.
