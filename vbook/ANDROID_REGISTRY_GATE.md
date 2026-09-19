# Android registry gate

`android_registry_gate.py` is the canonical physical-device health gate for the VBook strict/live registries.

## Safety policy

- `PASS_READER` -> `KEEP`.
- `PASS_SOURCE_EXTERNAL_TAKEOVER` -> `KEEP_WITH_ANOMALY`; an external app takeover is not a source failure.
- `SOURCE_FAIL_NO_DATA` is drop-eligible only when every run agrees, at least two runs were requested, the result is stable, and there were no transient control anomalies.
- `SOURCE_FAIL_NO_CONTENT_CARD` -> `REVIEW`; UI/adapter parsing can cause this result.
- Transport, lock-screen/control, selector, `UNRESOLVED_*`, `SOURCE_PATH_PARTIAL_*`, and `DEVICE_PRECONDITION_*` outcomes -> `DEFER`; they never remove a source.
- Physical Nokia preflight is part of the acceptance contract: canonical strict registry present -> source installed -> source picker -> content card -> detail -> TOC -> reader. The checker may self-heal a missing canonical registry entry or install the selected strict-registry source, but a failed device precondition is never interpreted as source breakage.
- VBook's transient `Không có dữ liệu hiển thị.` placeholder immediately after switching sources is not a source failure. The physical checker waits for content and performs one bounded reload before a persistent empty state can become `SOURCE_FAIL_NO_DATA`.
- The gate never overwrites its input registry. `--apply-drops` requires an explicit, different `--output-registry` path.

## Production use

Run on `runner-vps1` through the privileged SentinelX/root lane because `/run/nokia-control/control.sock` is intentionally not exposed to the GitHub runner account.

```bash
cd /opt/vps-mailbox/vbook-sources-work
python3 vbook/android_registry_gate.py \
  --registry vbook/louis-vbook-strict-20260918.json \
  --repeats 2
```

Targeted canary:

```bash
python3 vbook/android_registry_gate.py \
  --source "Wiki Dịch" \
  --source "Bạch Ngọc Sách" \
  --source "Truyện Full" \
  --repeats 2
```

To materialize confirmed removals, write a copy and inspect the audit first:

```bash
python3 vbook/android_registry_gate.py \
  --repeats 2 \
  --apply-drops \
  --output-registry /tmp/louis-vbook-strict-gated.json
```

The default source set is Vietnamese `novel` entries in the strict registry. The gate launches **one bounded Nokia checker process per source** and merges the evidence afterward; it must not run the whole registry in one long Nokia process. This isolates runtime/SIGTERM/transport failures from unrelated source health. The JSON audit records checker output, per-source verdicts, transient anomalies, and `proposed_drop`.

## Regression test

```bash
cd vbook
python3 -m unittest -v test_android_registry_gate.py
```
