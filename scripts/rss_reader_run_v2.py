#!/usr/bin/env python3
"""Canonical Runner15 ingestion gate.

Runs core12 RSS, Võ Hoàng Hạc hybrid, and Hồ Quốc Tuấn + vnhacker through their
public Substack archive APIs. The gate fails closed unless all 15 logical
sources are healthy. It never advances reader-state.json.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import rss_reader_run as legacy

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rss-reader"
CORE_HEALTH = DATA / "health.json"
VHH_HEALTH = DATA / "substack-health.json"
DIRECT_RSS_HEALTH = DATA / "direct-substack-health.json"
RUNTIME_HEALTH = DATA / "runtime-health.json"
STATE = DATA / "reader-state.json"
SOURCES_ROOT = DATA / "sources"
LOGICAL_SOURCE_COUNT = 15
RSS_EXTRA_KEYS = ["hoquoctuan", "vnhacker"]
ALLOWED_EXTRA_TRANSPORTS = {"rss", "substack-archive-api"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_collector(script):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return {
        "script": script,
        "exitCode": proc.returncode,
        "stdout": proc.stdout.strip()[-4000:],
        "stderr": proc.stderr.strip()[-4000:],
    }


def validate_extra_rss(health):
    problems = []
    sources = health.get("sources") if isinstance(health, dict) else None
    if not isinstance(sources, dict):
        return False, ["Substack source health missing sources object"]
    for key in RSS_EXTRA_KEYS:
        row = sources.get(key) or {}
        mirror = read_json(SOURCES_ROOT / f"{key}.json")
        if row.get("ok") is not True:
            problems.append(f"{key}: collector not healthy")
        if mirror.get("sourceKey") != key:
            problems.append(f"{key}: mirror missing or sourceKey mismatch")
        if mirror.get("transport") not in ALLOWED_EXTRA_TRANSPORTS:
            problems.append(
                f"{key}: mirror transport={mirror.get('transport')!r} "
                f"expected one of {sorted(ALLOWED_EXTRA_TRANSPORTS)}"
            )
        if not isinstance(mirror.get("items"), list) or not mirror.get("items"):
            problems.append(f"{key}: mirror has no items")
    if health.get("okCount") != 2 or health.get("failedCount") != 0 or health.get("status") != "healthy":
        problems.append("HQT/vnhacker health counters/status invalid")
    return not problems, problems


def main():
    started = now_iso()
    core_run = run_collector("rss_reader_collect_v2.py")
    vhh_run = run_collector("rss_substack_collect_v2.py")
    direct_rss_run = run_collector("rss_direct_substack_collect.py")

    core_health = read_json(CORE_HEALTH)
    vhh_health = read_json(VHH_HEALTH)
    vhh_mirror = read_json(SOURCES_ROOT / "vohoanghac.json")
    direct_rss_health = read_json(DIRECT_RSS_HEALTH)
    state = read_json(STATE)

    core_ok, core_problems = legacy.validate_core(core_health)
    vhh_ok, vhh_problems = legacy.validate_vhh(vhh_health, vhh_mirror)
    extra_ok, extra_problems = validate_extra_rss(direct_rss_health)
    state_ok, state_problems = legacy.validate_state(state)

    ingestion_ok = (
        core_ok and vhh_ok and extra_ok and state_ok
        and core_run["exitCode"] == 0
        and vhh_run["exitCode"] == 0
        and direct_rss_run["exitCode"] == 0
    )

    result = {
        "version": 3,
        "collector": "runner-3",
        "scope": "ai-rss-reader-ingestion-runner15",
        "runStartedAt": started,
        "runFinishedAt": now_iso(),
        "logicalSourceCount": LOGICAL_SOURCE_COUNT,
        "runner3LogicalSources": 15,
        "chatgptDirectSources": [],
        "status": "healthy" if ingestion_ok else "failed",
        "ingestionOk": ingestion_ok,
        "gate": {
            "core12": {"ok": core_ok, "problems": core_problems},
            "vohoanghacHybrid": {"ok": vhh_ok, "problems": vhh_problems},
            "substackArchive2": {"ok": extra_ok, "problems": extra_problems},
            "readerStateShape": {"ok": state_ok, "problems": state_problems},
        },
        "collectorRuns": {
            "core": core_run,
            "vohoanghac": vhh_run,
            "substackArchive2": direct_rss_run,
        },
        "readerStateAdvanced": False,
    }
    write_json(RUNTIME_HEALTH, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ingestion_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
