# ainovel-cli × Writing Brain V2.3 integration overlay

Staging package for integrating the production Webnovel Writing Brain V2.3 into upstream `voocel/ainovel-cli` without coupling the upstream engine to the knowledge asset.

Target upstream commit: `c0900290be8dfbae4d1614726e48b53259efbd47` (main, 2026-08-25).

## Architecture

- `ainovel-cli`: deterministic orchestration, story state, checkpoints, Architect/Writer/Editor.
- Writing Brain V2.3: retrieval/review knowledge layer.
- LLM: planning, generation and judgement.

The integration adds one read-only agent tool, `writing_brain`, to Architect, Writer and Editor. The Engine and Arbiter are not modified.

## Production Writing Brain pin

- release: `webnovel-writing-brain-nli-v2-3-2026-08-20`
- mode: `semantic-canonical-context-nli-first`
- asset SHA-256: `f961aa5d4b924b4ef7201fb2d0f5b676fa7fd6579e0d70eedbe5669447fbc4db`
- canonical rules: 16,697
- context relations: 26,320

The 169,140,679-byte asset is intentionally NOT committed here.

## Apply to a fork of upstream

From the root of an `ainovel-cli` checkout:

```bash
/path/to/this-package/apply.sh .
cp /path/to/this-package/configs/writing-brain.env.example .env.writing-brain
```

Then configure the actual Writing Brain index and runtime paths. See `docs/WRITING_BRAIN_INTEGRATION.md`.

## Runtime contract

The tool calls the existing production CLI:

```bash
python3 scripts/webnovel_writing_brain_context_agent.py query \
  --index /path/to/index \
  --q "..." \
  --limit 12
```

It also supports the CLI's `direct`, `review`, and `checklist` operations. Returned JSON is wrapped with release/version metadata and traced per chapter for A/B benchmark and failure analysis.

## Safety / upstream maintainability

- no shell execution; subprocess arguments are passed directly;
- retrieval limit capped at 15 to avoid context flooding;
- default fail-open keeps novel generation usable if the external brain is unavailable;
- no change to the deterministic Engine/Arbiter;
- integration is isolated to `internal/tools/writing_brain.go` plus a small worker registration hunk;
- knowledge data remains external and version-pinned.
