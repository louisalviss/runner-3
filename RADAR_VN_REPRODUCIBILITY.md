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

- `VOZ F33` is rendered from the pinned F33 artifact only.
- `VOZ discussion` may only summarize posts from that F33 thread's fully read pages 1..N.
- Otofun, Tinhte, GameVN, Trends, press and social evidence must never be inserted into `VOZ discussion`.
- Cross-source evidence is attached only during post-F33 clustering for New/Material/Policy/Business/Breakout/Utility/Forum sections.

## Dedup and scope

- Outside F33 source coverage, one narrative equals one reader slot across the entire report.
- Google Trends and forum engagement are signals, not factual authority and not automatic slot generators.
- Main Radar is Vietnam-centered only. Standalone international stories stay out of main reader lanes; international F33 page-1 threads are eligible only when selected as F33 discussion signals.

## Reader render policy v3.5 — delta-first, anti-underfill

The reader report must be dense enough to cover the day without padding or repeating the same story.

### Story fingerprint

- Build a canonical fingerprint for every narrative from normalized `entity/topic + event family + geography + action/policy/case id`.
- Compare against the previous 72 hours of archived Radar reports before assigning a reader slot.
- A story already covered inside the 72-hour window is blocked from `NEW SINCE YESTERDAY`.
- It may return only in `MATERIAL UPDATE` when `material_delta=true`.

### Material delta definition

A delta is material when at least one of these changes:

- legal/procedural status: proposal -> issuance, investigation -> prosecution/arrest/indictment/verdict;
- official effective date, scope, eligibility, fee, tax, fine, entitlement or compliance requirement;
- confirmed casualty/outcome/closure/opening/launch/recovery;
- official number or market threshold changes enough to alter the story meaningfully;
- operational action: service begins/stops, route opens, infrastructure enters use, regulator starts enforcement;
- a new primary-source disclosure materially changes the interpretation.

A new article, repost, commentary, headline rewrite, minor quote or routine continuation is not a material delta.

### Freshness gate

- Main reader lanes prefer events whose factual core happened or was officially disclosed inside the target-day window.
- A resurfaced old fact with no material delta is not allowed into New/Policy/Business/Breakout/Utility merely because it trends or reappears on F33.
- Useful resurfaced/misleading items may appear only in `CORRECTION / MISLEADING / OLD RESURFACED`.

### Coverage budget

- One fingerprint gets one primary lane only.
- Do not retell a story in multiple lanes. A secondary lane may use at most a short cross-reference when necessary.
- F33 discussion is allowed to reference the same real-world event because it is a provenance-separated community lens, but the factual story must not be re-explained there at full length.
- Never fill a weak lane with low-value stories just to hit a quota.

### Reader lane order and target sizes

1. `NEW SINCE YESTERDAY` — 5–8 genuinely new independent stories.
2. `MATERIAL UPDATE` — 3–6 previously covered stories with material delta. Omit or state none when empty.
3. `VOZ F33 — STRONGEST DISCUSSIONS` — target 7–10 strongest page-1 threads after reading all pages; minimum 5 only when discussion quality is genuinely weak. Rank by engagement + reasoning value + Vietnam relevance, not raw post count alone.
4. `POLICY / MONEY / RULE CHANGE` — 3–5 unique actionable changes. Format should answer: what changed, effective date, who is affected, action needed.
5. `BUSINESS & MARKET SIGNAL` — 3–5 structural signals: liquidity, rates, business formation/closure, FDI, M&A, defaults, major capital allocation, sector inflection.
6. `INTERNET BREAKOUT` — 3–6 fast-rising Trends/social narratives not already assigned. Explain why it is rising and whether it is transient or worth following.
7. `LOCAL / PRACTICAL UTILITY` — 2–5 transport, weather, outages, airport, service, deadline or local-operation items with immediate utility.
8. `FORUM SIGNAL` — sublanes: Tech/AI; Work/Salary; MMO; Crypto; Consumer/Auto/Home. Explicitly report `no material signal` for checked sublanes with no qualifying candidate.
9. `CORRECTION / MISLEADING / OLD RESURFACED` — 1–3 only when useful: fix bait headlines, special conditions, wrong dates, or old stories resurfacing as if new.
10. `WATCH TOMORROW` — 2–4 only when there is a concrete future hinge (deadline, hearing, launch, effective date, scheduled result, weather arrival, official release). Never make generic predictions.

### Underfill check

Before rendering, run this self-check:

- Were at least 5 genuinely new stories found when the day supports them?
- Were material updates separated from new stories rather than dropped as duplicates?
- Were breakout Trends candidates actually resolved instead of ignored?
- Were policy/money and business signals covered even when not viral?
- Were checked Forum sublanes explicitly marked empty rather than silently omitted?
- Were misleading or resurfaced headlines corrected?
- Did every repeated story earn its slot via material delta?

If the source pool contains qualifying stories and the report is materially thinner because of renderer selection, treat that as renderer underfill and repair before delivery.

## Replay behavior

- After a Radar is rendered successfully, save the exact delivered report at `radar_vn_reports/YYYY-MM-DD.md` together with a reference to `radar_vn_history/YYYY-MM-DD.json`.
- When the user later asks for the same historical date, replay the archived report by default.
- Recompute/rewrite only when the user explicitly asks to rerun, recompute, refresh, or regenerate that date.
- If an archived report and its pinned manifest disagree, stop replay and repair the archive; never silently mix sources.

## Quality definition

`full_quality=true` means all three structural inputs are usable: Trends HEALTHY with exactly 10 rows; F33 HEALTHY with all expected pages fetched, missing pages zero and artifact present; Forum Signal HEALTHY/DEGRADED usable with artifact present.

`close_quality=true` additionally means the pinned snapshots are late-day snapshots suitable for a near-end-of-day historical report. `full_quality` can be true while `close_quality` is false for older backfilled dates; this must not be confused with missing/incomplete F33 pages.
