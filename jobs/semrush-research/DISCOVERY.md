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


## Acceptance state — 2026-10-07

- Runtime regression: 3/3 PASS.
- R24 one-path acceptance: 8 root modifiers acquired; discovery shortlisted 6; exact SERP returned 6/6 `DROP_SERP_SATURATED`; registry advanced to 127.
- R25 one-command acceptance through `discovery_cycle.py`: terminal `COMPLETE_NO_SURVIVOR`; 8 candidates tested; 7 `DROP_SERP_SATURATED`, 1 `WATCH_COMPETITION`; registry advanced to 135.
- R25 strongest watch only: snowboard-length cluster, not promoted.
- Current overall leader remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- Next run identity should start at R26 or later. R20-R25 are terminal and must not be reacquired.
- Modifier miner now filters duplicate themes, exact-SERP-tested candidates, obvious informational noise, retail-calculator noise, weapon-related queries, and medical/YMYL calculator noise.
