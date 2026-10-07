# Semrush Modifier-First Discovery

Canonical discovery flow:

1. `modifier_seed_bank.py` selects unseen generic utility roots from the curated catalog.
2. `live_collect.py` acquires the root universe through the single-owner Semrush broker.
3. `discovery_stage.py` runs `modifier_mine.py`, applies config/theme anti-repeat plus the exact-SERP tested registry, and emits a bounded `serp-dd-queue.json`.
4. `serp_dd_live.py` performs exact SERP DD only for shortlisted candidates.
5. `discovery_finalize.py` appends tested candidates to the registry and emits the survivor summary.

Hard rules:
- Never reacquire a terminal universe only to rerun discovery.
- Never exact-SERP-test a candidate already present in the tested registry.
- A zero-candidate or zero-survivor result is a valid terminal result.
- Do not promote a niche on volume/KD alone; exact SERP must survive.
- Authenticated Semrush I/O remains broker-only.

Canonical one-command entrypoint:

```bash
python3 discovery_cycle.py --run-dir <run> --config-dir <config> --tested-registry <registry>
```

The cycle auto-generates an unseen modifier seed bank when `--seed-bank` is omitted, resumes partial acquisition in the same run identity, skips provider work when `universe.json` already exists, runs bounded exact SERP DD, finalizes the tested registry, and returns `RESUME_NO_BACKTRACK` for terminal runs.
