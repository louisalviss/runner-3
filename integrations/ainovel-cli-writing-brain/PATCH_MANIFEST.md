# Patch manifest

Target: `voocel/ainovel-cli`
Target base SHA: `c0900290be8dfbae4d1614726e48b53259efbd47`
Integration: Writing Brain V2.3

Files added to target:
- `internal/tools/writing_brain.go`
- `docs/WRITING_BRAIN_INTEGRATION.md`
- `configs/writing-brain.env.example`

File patched in target:
- `internal/agents/build.go`

Patch behavior:
1. `NewWritingBrainToolFromEnv(store.Dir())` returns nil unless both index and script paths are configured.
2. When configured, the same read-only tool is registered for Architect, Writer and Editor.
3. Agent calls are routed to the existing V2.3 Python CLI (`query`, `direct`, `review`, `checklist`).
4. Rule output is capped at 15.
5. Each call is traced as JSONL, grouped by chapter when chapter is supplied.
6. Failure defaults to fail-open; set `AINOVEL_WRITING_BRAIN_FAIL_OPEN=false` for strict benchmark/debug runs.

Out of scope by design:
- Writing Brain build/canonicalization/NLI jobs;
- the 169 MB production asset;
- changes to ainovel Engine or Arbiter;
- adding new knowledge sources;
- changing Writing Brain retrieval ranking.
