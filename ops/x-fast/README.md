# Runner-3 X Fast canonical flow

Use this order only:

1. `runner3-x-fast-direct` Cloudflare Worker for normal X status reads.
   - FxTwitter API and public X HTML start together.
   - First usable response wins.
   - FxTwitter hard timeout: 2.2s.
   - X HTML hard timeout: 3.2s.
2. `jobs/x-fast/*.json` + `.github/workflows/x-fast.yml` only when the caller cannot reach the Worker or both direct sources fail.
   - Jobs may run concurrently.
   - Results are persisted immediately under `results/x-fast/<job-stem>/`.
3. `x_runner.py` is deep/multi-source fallback only. Its public endpoints run in parallel with a 6s source timeout.

Do not create new `jobs/x-readable/*` jobs. The temporary `x-fast-readable` bridge is removed because `x-fast.yml` now persists readable output itself.
