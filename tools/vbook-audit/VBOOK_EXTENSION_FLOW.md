# VBook Extension Canonical Flow

Status: canonical operating flow for this repository.

## 0. Scope and invariants

- **Project scope is text-story/novel extensions only:** registry `type` must be `novel` or `chinese_novel`.
- Comics, video, audio, TTS, translate and other utility/media types are explicitly outside this project and must not be audited, fixed, promoted, or used to block this flow.
- Production registry URL: `vbook/louis-vbook.json` on branch `vbook-sources`.
- `louis-vbook-live.json` and `louis-vbook-strict-20260918.json` are compatibility aliases only and must remain byte-equivalent in data.
- Every production audit resolves the `vbook-sources` branch to an immutable commit SHA first. All package and registry evidence in one run must come from that same snapshot.
- Never infer source failure from transport, device-precondition, UI-control, or temporary no-data placeholders.
- A behavior change in a plugin must increment `metadata.version` and publish a new package filename (`plugin-vN.zip`) to defeat client/raw cache ambiguity.

## 1. Discovery / candidate admission

For the Vietnamese discovery project, admit text-story/novel sources only. Reject comics, video, audio/TTS, mirrors of an already-covered canonical system, dead domains, and obvious challenge-only sources before implementation.

Before coding:
1. Prove the canonical domain and that the content is distinct.
2. Identify real routes for list/search/detail/TOC/chapter.
3. Record at least one real title and chapter URL as a fixture.
4. Prefer stable JSON/API endpoints when the website itself uses them; use HTML parsing only when necessary.
5. Determine whether Cloudflare/CDN/browser state is required. Do not silently rely on a VPS-only request path.

## 2. Implementation contract

A novel extension should provide the VBook manifest plus scripts for discovery/home, search, detail, TOC and chapter content. Use `page.js` only when the source actually requires a page-resolution stage.

Cross-platform rules:
- Keep JavaScript compatible with the VBook runtime; avoid unnecessary engine-specific DOM bridge assumptions.
- For Vietnamese search input, normalize to NFC when the upstream search is normalization-sensitive.
- Do not assume accentless/fuzzy search upstream supports Vietnamese. It is a capability, not a universal requirement.
- Prefer raw HTML/string parsing or stable JSON endpoints when Android/iOS DOM wrappers differ.
- Return absolute canonical URLs where possible.

## 3. Package / registry integrity gate — mandatory

Before runtime testing:
1. ZIP downloads successfully and opens.
2. `plugin.json` exists and parses.
3. Registry version equals manifest version.
4. Registry type is consistent with the manifest. A registry `source` override that differs from the manifest is recorded as WARN and must be backed by runtime E2E; it is not a package hard-fail by itself.
5. All manifest-referenced scripts exist in the package.
6. Novel/chinese_novel packages declare search, detail, toc and chap scripts for new/maintained sources.
7. Canonical registry has no duplicate exact source/name/path entries.
8. Compatibility aliases remain synchronized with canonical.

Version mismatch, type mismatch, missing package/script, malformed ZIP/manifest, or duplicate canonical identity is a hard FAIL. Legacy `source` override mismatch is WARN unless runtime evidence also fails.

## 4. VBook engine E2E gate — mandatory

Run the actual VBook JavaScript engine on Android/KVM, not a Node/browser imitation.

For text novels the required chain is:
`discover/home -> real book -> detail -> toc -> real chapter -> chapter content`

PASS requires meaningful chapter text (>=120 normalized text characters). Non-text extension types are out of scope and are not admitted into this project audit set.

Never call a source PASS merely because homepage/list parsing succeeds.

## 5. Search identity gate — mandatory for novel/chinese_novel

The gate must use a **real title discovered from the source itself**, not a generic query such as `tiên`.

Required sequence:
1. Discover a real book.
2. Resolve its canonical title from detail.
3. Search exact NFC title and prove the same book is returned (URL match preferred).
4. Search the NFD/decomposed variant and prove the same book is returned.
5. Search the accentless variant and record support as a capability/WARN; accentless failure alone is not a hard failure.
6. From the matched search result, rerun `detail -> toc -> chapter` and prove content is readable.

Hard failures: no search script for a maintained novel source, NFC miss, NFD miss, wrong-book match, or broken search-result read chain.

When a user reports a specific failed title, add that exact query as a regression probe in addition to identity testing before claiming the bug fixed.

## 6. Physical-device gate — mandatory before publishing new/changed VN source

After engine PASS, validate in the real VBook app/device:
`candidate registry isolated -> exact candidate package reinstalled -> source picker -> book -> detail -> TOC -> chapter -> reader stable`

Pre-production version-proof rules:
- Never accept `extension installed` as proof that the device is running the candidate version; VBook can retain an older installed package while a newer registry entry is present.
- While testing a changed extension, temporarily isolate the candidate registry from production aliases/registries that contain the same extension identity.
- Force reinstall only the extension under test from the isolated candidate registry (uninstall -> library install), then run the physical reader path. Preserve unrelated installed extensions.
- After the candidate verdict, restore the normal single canonical production registry and remove the temporary candidate registry. Do not leave `strict`, canonical, and candidate Louis registries active together.
- The production steady state is one Louis registry URL: `vbook/louis-vbook.json`.

Policy:
- `PASS_READER` -> KEEP / eligible for publish.
- External takeover with source path proven -> keep with anomaly, investigate separately.
- `DEVICE_PRECONDITION_*`, ADB/transport/control failure, unresolved UI state -> DEFER, never classify as parser failure.
- A temporary `Không có dữ liệu hiển thị.` immediately after source selection is not a source failure; wait/reload within a bounded window.
- Drop eligibility requires repeated clean source failures, never a single device/control failure.

For iOS-specific user reports, Android PASS is not proof of iOS PASS. Use cross-platform-safe code and require the reported iOS flow to be rechecked before calling the iOS issue closed.

## 7. Promotion

Only after required gates pass:
1. Publish the immutable `plugin-vN.zip`.
2. Update **only canonical** `vbook/louis-vbook.json` as the source of truth; update aliases in the same commit for backward compatibility.
3. Verify raw GitHub returns the expected version/package.
4. Pin the exact tested package commit in audit/candidate metadata.
5. Keep evidence: integrity report, VBook E2E artifact, search-identity artifact, and physical-device verdict for changed VN sources.

## 8. Full text-registry regression

Use `VBook Text Novel Acceptance` to audit the complete **text-story subset** of production from one immutable registry SHA. The planner filters canonical entries to `novel` / `chinese_novel` before any package or runtime work begins. Non-text entries are absent from the audit set rather than reported as SKIP.

The text regression performs:
- package/manifest integrity for every text-story entry;
- VBook engine `discover -> detail -> toc -> chapter` E2E for every text-story entry;
- real-title NFC/NFD search identity for every maintained text-story entry;
- accentless search capability reporting;
- merged failure inventory with exact source and stage.

Physical UI testing is intentionally not run concurrently across all entries because the one authorized device is stateful. Physical testing is queued for changed sources and for engine/identity anomalies requiring device discrimination.

## 9. Evidence rule

A claim of PASS must name the layer that passed. Use `PACKAGE PASS`, `ENGINE PASS`, `SEARCH_IDENTITY PASS`, `PHYSICAL PASS`, or `iOS USER-VERIFIED PASS`. Never collapse these into an unspecified “works”.
