# Validation

Date: 2026-08-28

## Verified

- Upstream target resolved to `voocel/ainovel-cli` main commit `c0900290be8dfbae4d1614726e48b53259efbd47`.
- Actual Writing Brain production runtime inspected: `scripts/webnovel_writing_brain_context_agent.py`.
- Runtime commands verified from source: `query`, `direct`, `review`, `checklist`, `stats`.
- Query default limit in the production CLI is 12; ainovel adapter caps all retrieval output at 15.
- V2.3 production identity pinned to release `webnovel-writing-brain-nli-v2-3-2026-08-20` and SHA-256 `f961aa5d4b924b4ef7201fb2d0f5b676fa7fd6579e0d70eedbe5669447fbc4db`.
- `writing_brain.go` passed `gofmt` locally.
- `writing_brain.go` passed Go syntax/type compilation against a local stub of the only external package used directly by the new file (`github.com/voocel/agentcore/schema`).
- `apply.sh` was executed twice against a representative `build.go` fixture; both constructor and registration edits remained single-instance (idempotence pass).
- Staging branch and adapter file were read back from GitHub after write.

## Not yet claimed

- Full `go test ./...` against an actual checkout of upstream ainovel-cli was not executed in this environment.
- End-to-end retrieval against the 169 MB production Writing Brain index was not executed here because the production index asset is deliberately external to this staging package.
- No `louisalviss/ainovel-cli` fork/repository has been created by this connector; repository/fork creation is not exposed by the connected GitHub actions.

These are deployment/E2E gates, not reasons to merge the overlay into `runner-3/main`.
