# Shared Flow Storage Standard

This is the default storage/control pattern for Runner3 flows that have durable machine state plus large or resumable artifacts.

## One-line rule

```text
D1 = machine state/index
R2 = machine artifacts
Google Sheet = human control/decision view
Dropbox = human library/final deliverables
GitHub = code/config/migrations
```

Do not use every layer mechanically. Use the smallest subset that preserves the roles below.

## Layer contracts

### Cloudflare D1

Use for bounded structured data that machines must query/update frequently:

- workflow status/checkpoints/cursors
- semantic identity and artifact hashes
- idempotency/resume metadata
- normalized indexes when queryability is a core workload requirement

Never store large prose, audio, raw archives, screenshots, generated binaries, or other object-like payloads in D1.

A D1 `success`/`complete` state may be committed only after the canonical business output has been successfully persisted and verified.

### Cloudflare R2

Use for machine-oriented objects:

- raw/source snapshots
- intermediate artifacts
- evidence archives
- QA artifacts
- generated media/documents
- machine final builds

Use one shared bucket where practical (`runner3-artifacts`) and isolate workloads by stable prefixes:

```text
<domain>/<flow>/<entity>/...
```

Examples:

```text
ebooks/vbth/...
reddit/RealDayTrading/runs/...
proof/ebook-flow/...
```

For resumable work, persist a semantic sidecar/manifest with hashes. Before D1 marks work complete, perform an R2 readback or equivalent integrity verification.

### Google Sheet

Use as the compact human control layer.

Default workbook: **AI Flow Control Center**.

A normal flow should occupy one concise row containing enough information to answer:

- What is this flow?
- Is it healthy/running/blocked?
- What progress has it made?
- Where are its machine artifacts?
- Where is its human output?
- What happens next?

Sheet status/progress is a projection, not runtime source of truth. Deleting or damaging the Sheet must not stop a normal machine flow.

Exception: a flow may explicitly declare selected Sheet columns as a human decision layer. Example: Opportunity Radar manual decision fields. Machine status columns must not overwrite human decisions.

### Dropbox

Use only as a human library:

- long-lived context/docs
- concise project overview
- samples useful for inspection
- final deliverables a human wants to open/download

Do not mirror R2. Do not publish raw/intermediate/retry/sidecar/QA-temp objects just because they exist.

Dropbox must not be in the critical execution path. A Dropbox sync failure must not make a completed D1+R2 workload fail.

### GitHub

Use for:

- code
- manifests/config
- migrations
- workflows
- small proof metadata

Do not use GitHub as the canonical object store for generated books/media/raw evidence.

## Commit order

Full artifact-bearing flow:

```text
work
 -> validate / QA
 -> write R2 artifact + semantic sidecar
 -> readback/hash verify R2
 -> commit D1 state/checkpoint/index
 -> project concise state to Google Sheet
 -> publish selected human output to Dropbox
```

State-only/lean flow:

```text
work
 -> persist/validate canonical business state
 -> commit D1
 -> optional Sheet/Dropbox projection
```

## Recovery order

Never trust state alone.

For artifact-bearing resumable work:

1. Load current semantic input identity.
2. Read D1 checkpoint.
3. Read/download the referenced R2 artifact + sidecar/manifest.
4. Verify source/config semantic hash and artifact hash.
5. If D1 + R2 identity match: SKIP.
6. If D1 is missing/stale but R2 + sidecar prove exact current identity: RECOVER D1.
7. Otherwise recompute/repair.

Mere object existence is not proof of completion.

## When R2 is optional

Do not force R2 when a flow has no meaningful object artifacts. RSS Reader and Vietnam Radar can remain D1-centric unless they begin retaining large raw evidence or generated archives.

## Registration

Flows using this standard should be added to `ops/flow-control/registry.json` with:

- stable `flow_id`
- pattern: `full`, `lean`, or `special`
- D1 project/scope convention
- R2 bucket/prefix when used
- Google Sheet projection identity
- Dropbox human-output policy

A new artifact-heavy/resumable flow defaults to `full` unless there is a concrete reason to use a smaller pattern.
