# Vietnam Radar deterministic replay contract

This file is the implementation-side reproducibility contract for `Radar tin Việt Nam`.

## Date resolution

- Timezone is always `Asia/Ho_Chi_Minh`.
- `Hôm nay` resolves to the current Vietnam calendar date.
- `Hôm qua` resolves to current Vietnam calendar date minus one day.
- An explicit date always resolves to that exact Vietnam calendar date.
- Never substitute a later/current snapshot for a historical target date.

## Input selection

### Live / `Hôm nay`

1. Read `radar_vn_inputs_latest.json` first.
2. Render a full Radar only when `render_allowed=true`.
3. If blocked, recover/refresh the missing input first. Never silently fall back to a press-only Radar.

### Historical / `Hôm qua` / explicit past date

1. Read `radar_vn_history/YYYY-MM-DD.json` first.
2. That manifest is the authority for the exact Trends, F33 and Forum Signal inputs.
3. Do not re-select inputs by searching commits or choosing a different same-day run once a manifest is pinned.
4. If the manifest is missing or blocked, recover that target date and create/fix the manifest before rendering. Do not use current `*_latest.json` as a substitute.

## Daily history

- `trends_vn_history/YYYY-MM-DD.json` freezes the selected Google Trends VN snapshot for that Vietnam date.
- `voz_f33_history/YYYY-MM-DD.json` freezes the selected completed F33 full-crawl artifact for that Vietnam date.
- `forum_signal_history/YYYY-MM-DD.json` freezes the selected completed Forum Signal artifact for that Vietnam date.
- `radar_vn_history/YYYY-MM-DD.json` binds all three inputs, their hashes/IDs and structural health into one immutable reader manifest.
- Selection policy: latest completed snapshot whose local Vietnam date equals the target date. Same-day later completed snapshots may replace earlier ones before daily close; a later calendar day's snapshot may never overwrite the previous date.
- A late-close F33 backup is dispatched at 22:45 Vietnam time so historical reports do not get stuck with an early-day F33 snapshot.

## Render isolation

- `VOZ F33 — TRANG 1` is rendered from the pinned F33 artifact only.
- `VOZ discussion` may only summarize posts from that F33 thread's fully read pages 1..N.
- Otofun, Tinhte, GameVN, Trends, press and social evidence must never be inserted into `VOZ discussion`.
- Cross-source evidence is attached only during post-F33 clustering for Top/Breakout/category/Forum sections.

## Dedup and scope

- Outside mandatory F33, one narrative equals one reader slot across the entire report.
- If a narrative is in Top, it must not repeat in Breakout, AI/Tech, Money/Business, MXH or Forum Signal.
- Google Trends and forum engagement are signals, not factual authority and not automatic slot generators.
- Main Radar is Vietnam-centered only. Standalone international stories stay out of the main Radar; international F33 page-1 threads remain only in the mandatory F33 snapshot.

## Replay behavior

- After a Radar is rendered successfully, save the exact delivered report at `radar_vn_reports/YYYY-MM-DD.md` together with a reference to `radar_vn_history/YYYY-MM-DD.json`.
- When the user later asks for the same historical date, replay the archived report by default.
- Recompute/rewrite only when the user explicitly asks to rerun, recompute, refresh, or regenerate that date.
- If an archived report and its pinned manifest disagree, stop replay and repair the archive; never silently mix sources.

## Quality definition

`full_quality=true` means all three structural inputs are usable: Trends HEALTHY with exactly 10 rows; F33 HEALTHY with all expected pages fetched, missing pages zero and artifact present; Forum Signal HEALTHY/DEGRADED usable with artifact present.

`close_quality=true` additionally means the pinned snapshots are late-day snapshots suitable for a near-end-of-day historical report. `full_quality` can be true while `close_quality` is false for older backfilled dates; this must not be confused with missing/incomplete F33 pages.
