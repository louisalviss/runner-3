#!/usr/bin/env python3
"""Fail-safe Android/VBook gate for the published registry.

The physical-device checker is evidence, not authority to mutate the registry.
Transport, lock-screen, external-app takeover, selector, and unresolved UI states
must never be converted into source failures.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

PASS_READER = "PASS_READER"
PASS_TAKEOVER = "PASS_SOURCE_EXTERNAL_TAKEOVER"
HARD_FAIL = "SOURCE_FAIL_NO_DATA"
REVIEW_FAILS = {"SOURCE_FAIL_NO_CONTENT_CARD"}
TRANSIENT_EXACT = {
    "TRANSPORT_OFFLINE",
    "TRANSPORT_INTERRUPTED",
    "CONTROL_TRANSIENT",
    "SOURCE_NOT_FOUND",
    "EXTERNAL_TAKEOVER_BEFORE_CONTENT",
}


def is_defer_result(result: str) -> bool:
    return (
        result in TRANSIENT_EXACT
        or result.startswith("UNRESOLVED_")
        or result.startswith("SOURCE_PATH_PARTIAL_")
        or result.startswith("DEVICE_PRECONDITION_")
    )


def _run_one_checker(source: str, repeats: int, guard_seconds: float, timeout: int, registry_url: str | None = None) -> dict[str, Any]:
    cmd = [
        "/usr/local/bin/nokia",
        "vbook-check-sources",
        source,
        "--repeats", str(repeats),
        "--guard-seconds", str(guard_seconds),
    ]
    if registry_url:
        cmd.extend(["--registry-url", registry_url])
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "fatal": "CHECKER_TIMEOUT",
            "returncode": None,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        return {
            "ok": False,
            "fatal": "CHECKER_BAD_JSON",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    payload["_returncode"] = proc.returncode
    if proc.stderr:
        payload["_stderr_tail"] = proc.stderr[-2000:]
    return payload


def run_checker(sources: list[str], repeats: int, guard_seconds: float, timeout: int, registry_url: str | None = None) -> dict[str, Any]:
    """Run one bounded Nokia process per source and merge evidence.

    Long multi-source Nokia processes have been observed to receive external
    SIGTERM despite healthy device control. Per-source processes isolate that
    infrastructure failure so it cannot contaminate unrelated source verdicts.
    """
    merged: dict[str, Any] = {
        "ok": True,
        "summary": {},
        "runs": [],
        "attempts_log": [],
        "per_source": {},
        "per_source_errors": {},
    }
    for source in sources:
        payload = _run_one_checker(source, repeats, guard_seconds, timeout, registry_url) if registry_url else _run_one_checker(source, repeats, guard_seconds, timeout)
        merged["per_source"][source] = payload
        summary = (payload.get("summary") or {}).get(source)
        if isinstance(summary, dict):
            merged["summary"][source] = summary
        merged["runs"].extend(r for r in (payload.get("runs") or []) if r.get("source") == source)
        merged["attempts_log"].extend(r for r in (payload.get("attempts_log") or []) if r.get("source") == source)
        if payload.get("fatal") or not isinstance(summary, dict):
            merged["ok"] = False
            merged["per_source_errors"][source] = payload.get("fatal") or "NO_CHECKER_SUMMARY"
    return merged


def classify(source: str, checker: dict[str, Any], registered: bool, repeats: int) -> dict[str, Any]:
    summary = (checker.get("summary") or {}).get(source)
    runs = [r for r in checker.get("runs") or [] if r.get("source") == source]
    if not isinstance(summary, dict):
        return {
            "source": source,
            "registered": registered,
            "verdict": "DEFER",
            "reason": (checker.get("per_source_errors") or {}).get(source) or checker.get("fatal") or "NO_CHECKER_SUMMARY",
            "drop_eligible": False,
            "runs": runs,
        }

    results = {str(k): int(v) for k, v in (summary.get("results") or {}).items()}
    transients = {str(k): int(v) for k, v in (summary.get("transient_anomalies") or {}).items()}
    total = sum(results.values())
    result_keys = set(results)

    if total == repeats and result_keys and result_keys <= {PASS_READER, PASS_TAKEOVER}:
        anomaly = bool(transients) or PASS_TAKEOVER in result_keys or bool(summary.get("takeover_packages"))
        verdict = "KEEP_WITH_ANOMALY" if anomaly else "KEEP"
        reason = "SOURCE_PATH_PASSED_WITH_TRANSIENT_OR_TAKEOVER" if anomaly else "READER_STABLE"
        drop_eligible = False
    elif (
        results.get(HARD_FAIL) == repeats
        and total == repeats
        and repeats >= 2
        and summary.get("stable") is True
        and not transients
    ):
        verdict = "FAIL_CONFIRMED"
        reason = "NO_DATA_REPEATED_WITHOUT_CONTROL_ANOMALY"
        drop_eligible = bool(registered)
    elif HARD_FAIL in result_keys:
        verdict = "REVIEW"
        reason = "NO_DATA_NOT_STRONG_ENOUGH_FOR_AUTO_DROP"
        drop_eligible = False
    elif result_keys & REVIEW_FAILS:
        verdict = "REVIEW"
        reason = "CONTENT_CARD_FAILURE_CAN_BE_UI_OR_ADAPTER_FAILURE"
        drop_eligible = False
    elif any(is_defer_result(k) for k in result_keys) or not result_keys:
        verdict = "DEFER"
        reason = "CONTROL_TRANSPORT_OR_UI_UNRESOLVED"
        drop_eligible = False
    else:
        verdict = "REVIEW"
        reason = "UNCLASSIFIED_CHECKER_RESULT"
        drop_eligible = False

    return {
        "source": source,
        "registered": registered,
        "verdict": verdict,
        "reason": reason,
        "drop_eligible": drop_eligible,
        "stable": summary.get("stable"),
        "results": results,
        "transient_anomalies": transients,
        "takeover_packages": summary.get("takeover_packages") or {},
        "runs": runs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-safe physical Android gate for VBook registry health")
    ap.add_argument("--registry", default="vbook/louis-vbook.json")
    ap.add_argument("--registry-url", default="https://raw.githubusercontent.com/louisalviss/runner-3/vbook-sources/vbook/louis-vbook.json", help="registry URL used by the physical VBook precondition/install path")
    ap.add_argument("--source", action="append", dest="sources", help="source name; repeat for multiple")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--guard-seconds", type=float, default=1.2)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--audit-output", default=None)
    ap.add_argument("--apply-drops", action="store_true", help="write a filtered COPY; never overwrites input")
    ap.add_argument("--output-registry", default=None)
    args = ap.parse_args()

    repeats = max(1, min(args.repeats, 10))
    registry_path = Path(args.registry)
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = raw.get("data")
    if not isinstance(entries, list):
        raise SystemExit("registry data must be a list")

    by_name = {str(x.get("name")): x for x in entries if isinstance(x, dict) and x.get("name")}
    if args.sources:
        sources = list(dict.fromkeys(s.strip() for s in args.sources if s and s.strip()))
    else:
        sources = [
            str(x.get("name")) for x in entries
            if isinstance(x, dict) and x.get("type") == "novel" and x.get("locale") == "vi_VN" and x.get("name")
        ]
    if not sources:
        raise SystemExit("no sources selected")

    checker = run_checker(sources, repeats, args.guard_seconds, args.timeout, args.registry_url)
    rows = [classify(name, checker, name in by_name, repeats) for name in sources]
    proposed_drop = [r["source"] for r in rows if r["drop_eligible"]]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit = {
        "schema": "vbook-android-registry-gate-v1",
        "created_at": now,
        "registry": str(registry_path),
        "registry_url": args.registry_url,
        "registry_entries": len(entries),
        "selected_sources": sources,
        "repeats": repeats,
        "guard_seconds": args.guard_seconds,
        "policy": {
            "PASS_READER": "KEEP",
            "PASS_SOURCE_EXTERNAL_TAKEOVER": "KEEP_WITH_ANOMALY",
            "SOURCE_FAIL_NO_DATA": "DROP_ELIGIBLE_ONLY_IF_ALL_REPEATS_MATCH_AND_NO_TRANSIENTS",
            "SOURCE_FAIL_NO_CONTENT_CARD": "REVIEW",
            "transport_control_ui_unresolved": "DEFER_NEVER_DROP",
            "minimum_repeats_for_drop": 2,
            "execution_isolation": "ONE_SOURCE_PER_NOKIA_PROCESS",
        },
        "checker_ok": bool(checker.get("ok")),
        "checker_fatal": checker.get("fatal"),
        "summary": counts,
        "proposed_drop": proposed_drop,
        "results": rows,
        "checker": checker,
    }

    audit_path = Path(args.audit_output) if args.audit_output else Path("/tmp") / f"vbook-android-registry-gate-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit["audit_output"] = str(audit_path)

    if args.apply_drops:
        if repeats < 2:
            raise SystemExit("refusing apply: repeats must be >= 2")
        if not args.output_registry:
            raise SystemExit("refusing apply: --output-registry is required")
        out_path = Path(args.output_registry)
        if out_path.resolve() == registry_path.resolve():
            raise SystemExit("refusing apply: output must differ from input registry")
        filtered = copy.deepcopy(raw)
        drop_set = set(proposed_drop)
        filtered["data"] = [x for x in entries if str(x.get("name")) not in drop_set]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        audit["output_registry"] = str(out_path)
        audit["output_registry_entries"] = len(filtered["data"])

    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "audit_output": str(audit_path),
        "summary": counts,
        "proposed_drop": proposed_drop,
        "results": [{k: r.get(k) for k in ("source", "registered", "verdict", "reason", "drop_eligible", "results", "transient_anomalies")} for r in rows],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
