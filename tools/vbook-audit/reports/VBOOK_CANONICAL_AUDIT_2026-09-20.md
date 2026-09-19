# VBook Canonical Full Audit — 2026-09-20

## Snapshot

- Workflow run: `35471000904`
- Main flow commit: `add64febc7fe8ca904bab98510d242259f0323a8`
- Immutable registry SHA: `216e687bf1bcb72111f0361d2495fc858acc2e07`
- Canonical registry entries: **99**
- Coverage received: **99/99**, no missing IDs, no duplicate audit IDs.

## Engine E2E

- `PASS_E2E`: **95/99**
- `CHAP_FAIL`: **1** — `Tiểu Bạch TV`; page/detail/TOC resolved, but the HLS stream probe returned HTTP 403.
- `NO_ITEM`: **3** — `Bing TTS`, `Edge Translate`, `Gemini TTS`. These are utility extensions, not content sources, so `NO_ITEM` is a harness classification gap rather than proof they are broken. They require a utility-specific voice/translate gate.

## Package / registry integrity

- Strict package pass under the current checker: **84/99**.
- 15 entries were flagged.
- Definite version mismatches:
  - `Wiki Dịch`: registry 26 vs manifest 27.
  - `ffxs8`: registry 1 vs manifest 2.
  - `qimao - repo Đường đen`: registry 32 vs manifest 33.
- The remaining flagged entries are primarily registry `source` overrides differing from manifest source/domain/protocol and require review rather than automatic deletion.
- Registry warning: `Bing TTS` and `Edge Translate` share `https://www.bing.com/translator` as registry source.

## Search identity

Real-title identity flow: discover a real item -> detail canonical title -> exact NFC search -> NFD search -> same-book match -> detail -> TOC -> chapter. Accentless search is capability-only.

- `PASS_SEARCH_IDENTITY`: **28**
- `FAIL_NO_SEARCH`: **31**
- `FAIL_SEARCH_IDENTITY_NFC`: **15**
- `FAIL_SEARCH_IDENTITY_NFD`: **3**
- `FAIL_SEARCH_IDENTITY_NFC_NFD`: **7**
- `SKIP_NON_TEXT_NOVEL`: **15**

Recent VN sources (IDs 82–98):
- PASS: `TruyenHub`, `HiBook`, `VTruyen`, `TruyenHVL`, `uTruyen`.
- `TruyenHH`: exact/NFD search returned results but did not return the discovered canonical book.
- `Nghiện Truyện`: the user-reported `tho san toi pham` regression PASSed separately end-to-end, but a different real discovered title failed identity because the site's autocomplete API returns only its top suggestions. This means v3 fixed the reported title but search is not yet globally complete.
- Missing `search.js`: `LinkTruyen`, `Storya`, `TruyenYY`, `Webnovel.vn`, `SSTruyen`, `DTruyen.club`, `TruyenStory`, `Thính Phong Các`, `TruyenNet.vn`, `VnTruyen.org`.

## Interpretation

Do not collapse these layers into one PASS. An extension can pass content E2E while failing package integrity or search identity. New/modified VN sources must also pass the physical VBook UI gate before production promotion. Android engine PASS is not proof of iOS PASS.
