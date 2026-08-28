# Writing Brain V2.3 integration

## Goal

Use Writing Brain as a context-sensitive craft retrieval layer, not as a replacement for ainovel-cli orchestration and not as a static rule dump.

Expected flow:

```text
ainovel Engine
  -> Architect / Writer / Editor
     -> writing_brain tool
        -> production V2.3 CLI
           -> canonical rules
           -> effective Vietnamese stance/context
           -> resolved relation graph
           -> NLI evidence where available
           -> linked source evidence
```

## Why a tool instead of `.ainovel/rules`

Writing Brain contains 16,697 canonical rules. Injecting all of them as global/static rules would inflate context and remove the runtime's context/conflict semantics. Retrieval should normally return about 8-15 task-specific rules.

## Agent use

Architect:
- `query` or `direct` for premise, character, progression, worldbuilding and outline decisions.

Writer:
- `query` before chapter planning/drafting using the chapter goal and compact current context;
- `direct` when a broader chapter directive is useful;
- do not repeatedly call it with equivalent queries in one chapter.

Editor:
- `review` for weak prose/scenes;
- `query` for pacing, hook, logic, foreshadow/payoff and revision strategy.

`checklist` is available only when a valid canonical topic is already known. Invalid topics are rejected by the production CLI.

## Configuration

The tool is disabled unless BOTH are set:

```text
AINOVEL_WRITING_BRAIN_INDEX
AINOVEL_WRITING_BRAIN_SCRIPT
```

The script must be the existing `scripts/webnovel_writing_brain_context_agent.py` from the Writing Brain repository/runtime. Its Python imports must resolve, normally by keeping the script inside the runner-3 `scripts/` directory.

## Fail-open policy

Default: `AINOVEL_WRITING_BRAIN_FAIL_OPEN=true`.

If the subprocess times out or fails, the tool returns structured `available:false` JSON and ainovel can continue without retrieval. This avoids turning a knowledge add-on into a hard dependency for normal writing.

For controlled A/B benchmark or integration debugging, use `false` so failures are visible as tool errors.

## Trace

Default trace directory:

```text
<bookDir>/meta/writing_brain/
```

Files:

```text
global.jsonl
chapter_001.jsonl
chapter_002.jsonl
...
```

Each record stores Writing Brain release/hash, phase, chapter, request context and full returned JSON. This preserves rule IDs, relations and evidence for failure analysis.

## Benchmark

The integration is designed to support the current real-world benchmark gate:

```text
A = same ainovel model/config + Writing Brain disabled
B = same ainovel model/config + Writing Brain enabled
```

Keep model, reasoning level, prompt intent and output budget matched. Judge hook, pacing, continuity, logic, specificity, redundancy, contradiction and genre/task fit. Trace treatment failures back to retrieved rule IDs/evidence.

## Upstream sync

Only one core upstream file is patched: `internal/agents/build.go`. If upstream changes worker assembly, re-apply the two small registration edits manually rather than carrying a deep fork of Engine/Arbiter.
