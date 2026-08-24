#!/usr/bin/env python3
"""D1 shadow state for AI RSS Reader.

The collector only reports operational state. It MUST NOT advance
data/rss-reader/reader-state.json and MUST NOT write the full-reader checkpoint.

`commit-render` is an explicit postcondition step for a successfully completed
15/15 render, after the canonical reader-state file has already been advanced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_HELPERS = ROOT / ".github" / "scripts"
if str(CORE_HELPERS) not in sys.path:
    sys.path.insert(0, str(CORE_HELPERS))

from runner3_core import save_checkpoint, save_state  # noqa: E402

SOURCE = "rss-reader"
PROJECT = "ai-rss-reader"
FULL_READER_SCOPE = "full-reader"
DEFAULT_RUNTIME_HEALTH = ROOT / "data" / "rss-reader" / "runtime-health.json"
DEFAULT_READER_STATE = ROOT / "data" / "rss-reader" / "reader-state.json"
EXPECTED_SOURCE_COUNT = 15


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return obj


def canonical_hash(obj: dict[str, Any]) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_reader_state(state: dict[str, Any]) -> None:
    sources = state.get("sources")
    source_count = state.get("sourceCount")
    if source_count != EXPECTED_SOURCE_COUNT:
        raise ValueError(f"reader-state sourceCount must be {EXPECTED_SOURCE_COUNT}, got {source_count!r}")
    if not isinstance(sources, dict) or len(sources) != EXPECTED_SOURCE_COUNT:
        actual = len(sources) if isinstance(sources, dict) else None
        raise ValueError(f"reader-state must contain exactly {EXPECTED_SOURCE_COUNT} sources, got {actual!r}")


def operational_detail(health: dict[str, Any]) -> dict[str, Any]:
    gate = health.get("gate") if isinstance(health.get("gate"), dict) else {}
    return {
        "scope": health.get("scope"),
        "status": health.get("status"),
        "ingestion_ok": health.get("ingestionOk") is True,
        "run_started_at": health.get("runStartedAt"),
        "run_finished_at": health.get("runFinishedAt"),
        "logical_source_count": health.get("logicalSourceCount"),
        "reader_state_advanced": health.get("readerStateAdvanced") is True,
        "gate": {
            "core12_ok": (gate.get("core12") or {}).get("ok") is True,
            "vohoanghac_hybrid_ok": (gate.get("vohoanghacHybrid") or {}).get("ok") is True,
            "reader_state_shape_ok": (gate.get("readerStateShape") or {}).get("ok") is True,
        },
        "cursor_authority": "data/rss-reader/reader-state.json",
        "full_render_checkpoint_mutated": False,
    }


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def cmd_operational(args: argparse.Namespace) -> int:
    health = load_json(Path(args.runtime_health))
    detail = operational_detail(health)
    status = "success" if detail["ingestion_ok"] else str(health.get("status") or "failed")
    if status == "healthy":
        status = "success"
    state = save_state(
        SOURCE,
        status=status,
        run_id=args.run_id,
        detail=detail,
        core_url=args.core_url,
    )
    emit({"ok": True, "mode": "operational", "state": state})
    return 0


def cmd_commit_render(args: argparse.Namespace) -> int:
    state = load_json(Path(args.reader_state))
    validate_reader_state(state)
    position = {
        "version": 1,
        "phase": "rendered",
        "render_id": args.render_id,
        "run_id": args.run_id,
        "source_count": EXPECTED_SOURCE_COUNT,
        "full_gate": "15/15",
        "reader_state_updated_at": state.get("updatedAt"),
        "reader_state_sha256": canonical_hash(state),
        "item_count": args.item_count,
        "latest_item_at": args.latest_item_at,
        "cursor_authority": "data/rss-reader/reader-state.json",
    }
    position = {k: v for k, v in position.items() if v is not None}
    checkpoint = save_checkpoint(
        PROJECT,
        SOURCE,
        scope=FULL_READER_SCOPE,
        status="success",
        position=position,
        core_url=args.core_url,
    )
    emit({"ok": True, "mode": "commit-render", "checkpoint": checkpoint})
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core-url", default=os.environ.get("RUNNER3_CORE_URL"))
    sub = p.add_subparsers(dest="command", required=True)

    o = sub.add_parser("operational", help="shadow collector health into workflow_state only")
    o.add_argument("--runtime-health", default=str(DEFAULT_RUNTIME_HEALTH))
    o.add_argument("--run-id")
    o.set_defaults(func=cmd_operational)

    c = sub.add_parser("commit-render", help="commit a successful canonical 15/15 render checkpoint")
    c.add_argument("--reader-state", default=str(DEFAULT_READER_STATE))
    c.add_argument("--render-id", required=True)
    c.add_argument("--run-id")
    c.add_argument("--item-count", type=int)
    c.add_argument("--latest-item-at")
    c.set_defaults(func=cmd_commit_render)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
