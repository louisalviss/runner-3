#!/usr/bin/env python3
"""Single canonical Runner3 entrypoint for AI RSS Reader ingestion.

Runs the 12 RSS-only sources and Võ Hoàng Hạc hybrid collector, then enforces
one explicit machine-readable health gate. It never advances reader-state.json.
Hồ Quốc Tuấn and vnhacker remain ChatGPT-direct sources at render time.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rss-reader"
CORE_HEALTH = DATA / "health.json"
VHH_HEALTH = DATA / "substack-health.json"
RUNTIME_HEALTH = DATA / "runtime-health.json"
STATE = DATA / "reader-state.json"
VHH_MIRROR = DATA / "sources" / "vohoanghac.json"

CORE_KEYS = [
    "tinhte",
    "genk",
    "gamek",
    "fulcrum",
    "nghiencuuquocte",
    "noema",
    "projectsyndicate",
    "economist",
    "theatlantic",
    "grimlogs",
    "scientificamerican",
    "quanta",
]
LOGICAL_SOURCE_COUNT = 15


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


def validate_core(health):
    sources = health.get("sources") if isinstance(health, dict) else None
    if not isinstance(sources, dict):
        return False, ["core health missing sources object"]
    problems = []
    for key in CORE_KEYS:
        if sources.get(key, {}).get("ok") is not True:
            problems.append(f"{key}: not healthy")
    if health.get("okCount") != len(CORE_KEYS):
        problems.append(f"okCount={health.get('okCount')} expected={len(CORE_KEYS)}")
    if health.get("failedCount") != 0:
        problems.append(f"failedCount={health.get('failedCount')} expected=0")
    if health.get("status") != "healthy":
        problems.append(f"status={health.get('status')} expected=healthy")
    return not problems, problems


def validate_vhh(health, mirror):
    source = (health.get("sources") or {}).get("vohoanghac", {}) if isinstance(health, dict) else {}
    components = source.get("components") or {}
    problems = []
    if source.get("ok") is not True:
        problems.append("vohoanghac: logical source not healthy")
    if components.get("articles", {}).get("ok") is not True:
        problems.append("vohoanghac.articles: not healthy")
    if components.get("notes", {}).get("ok") is not True:
        problems.append("vohoanghac.notes: not healthy")
    if health.get("status") != "healthy" or health.get("okCount") != 1 or health.get("failedCount") != 0:
        problems.append("vohoanghac health counters/status invalid")
    if mirror.get("transport") != "hybrid-rss+substack-profile":
        problems.append(f"vohoanghac mirror transport={mirror.get('transport')!r}")
    if not isinstance(mirror.get("profileUserId"), int) or mirror.get("profileUserId") <= 0:
        problems.append("vohoanghac mirror missing verified profileUserId")
    if not any(item.get("itemType") == "note" for item in mirror.get("items") or []):
        problems.append("vohoanghac mirror contains no verified Notes")
    return not problems, problems


def validate_state(state):
    problems = []
    if state.get("sourceCount") != LOGICAL_SOURCE_COUNT:
        problems.append(f"reader-state sourceCount={state.get('sourceCount')} expected={LOGICAL_SOURCE_COUNT}")
    sources = state.get("sources")
    if not isinstance(sources, dict) or len(sources) != LOGICAL_SOURCE_COUNT:
        problems.append("reader-state does not contain exactly 15 logical source cursors")
    return not problems, problems


def main():
    started = now_iso()
    core_run = run_collector("rss_reader_collect_v2.py")
    vhh_run = run_collector("rss_substack_collect_v2.py")

    core_health = read_json(CORE_HEALTH)
    vhh_health = read_json(VHH_HEALTH)
    vhh_mirror = read_json(VHH_MIRROR)
    state = read_json(STATE)

    core_ok, core_problems = validate_core(core_health)
    vhh_ok, vhh_problems = validate_vhh(vhh_health, vhh_mirror)
    state_ok, state_problems = validate_state(state)
    ingestion_ok = core_ok and vhh_ok and state_ok and core_run["exitCode"] == 0 and vhh_run["exitCode"] == 0

    result = {
        "version": 1,
        "collector": "runner-3",
        "scope": "ai-rss-reader-ingestion",
        "runStartedAt": started,
        "runFinishedAt": now_iso(),
        "logicalSourceCount": LOGICAL_SOURCE_COUNT,
        "runner3LogicalSources": 13,
        "chatgptDirectSources": ["hoquoctuan", "vnhacker"],
        "status": "healthy" if ingestion_ok else "failed",
        "ingestionOk": ingestion_ok,
        "gate": {
            "core12": {"ok": core_ok, "problems": core_problems},
            "vohoanghacHybrid": {"ok": vhh_ok, "problems": vhh_problems},
            "readerStateShape": {"ok": state_ok, "problems": state_problems},
        },
        "collectorRuns": {"core": core_run, "vohoanghac": vhh_run},
        "readerStateAdvanced": False,
    }
    write_json(RUNTIME_HEALTH, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ingestion_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
