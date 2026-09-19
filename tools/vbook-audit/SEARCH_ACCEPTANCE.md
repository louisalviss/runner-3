# VBook search acceptance gate

For any source that exposes `search.js`, a normal browse/detail/chapter PASS is not sufficient. Target Android/KVM audits also run a search identity gate.

## Required path

1. Discover a real item from the source.
2. Open `detail.js` and use the canonical title returned by the source.
3. Search the exact NFC title and require the result set to contain the same item.
4. Search the NFD/decomposed form of the same title and require the same item again.
5. From the NFC search result, execute `detail -> TOC -> chapter` and require meaningful chapter content.
6. Search an accentless form and record whether the same item is found. Accentless/fuzzy support is informative, not a universal hard requirement.

## Verdicts

- `PASS_SEARCH_IDENTITY`: NFC and NFD both find the same real item and the search-result path reaches chapter content.
- `FAIL_SEARCH_IDENTITY_NFC`: ordinary canonical-title search cannot find the same item.
- `FAIL_SEARCH_IDENTITY_NFD`: decomposed Unicode loses the item; this is an iOS/cross-platform regression.
- `FAIL_SEARCH_CHAIN`: search finds the item, but `detail -> TOC -> chapter` from that result fails.
- `SKIP_NO_SEARCH`: source has no search script; this gate does not apply.

The target workflow fails on any required `FAIL_*` or harness error, while still uploading `out/search-identity.json` for diagnosis.
