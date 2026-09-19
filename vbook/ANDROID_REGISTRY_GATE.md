# Android registry gate

`android_registry_gate.py` is the canonical physical-device health gate for the VBook strict/live registries.

## Safety policy

- `PASS_READER` -> `KEEP`.
- `PASS_SOURCE_EXTERNAL_TAKEOVER` -> `KEEP_WITH_ANOMALY`; an external app takeover is not a source failure.
- `SOURCE_FAIL_NO_DATA` is drop-eligible only when every run agrees, at least two runs were requested, the result is stable, and there were no transient control anomalies.
- `SOURCE_FAIL_NO_CONTENT_CARD` -> `REVIEW`; UI/adapter parsing can cause this result.
- Transport, lock-screen/control, selector, `UNRESOLVED_*`, and `SOURCE_PATH_PARTIAL_*` outcomes -> `DEFER`; they never remove a source.
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

The default source set is Vietnamese `novel` entries in the strict registry. The JSON audit records checker output, per-source verdicts, transient anomalies, and `proposed_drop`.

## Regression test

```bash
cd vbook
python3 -m unittest -v test_android_registry_gate.py
```
