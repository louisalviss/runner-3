#!/usr/bin/env python3
"""Mirror the current VBTH editorial state into Runner3 Core (Cloudflare D1)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from runner3_core import get_checkpoint, report_status, save_checkpoint  # noqa: E402

STATE_PATH = ROOT / "story_pipeline" / "state.json"
PROJECT = "vbth-editorial"
SCOPE = "main"
SOURCE = "runner-3/story_pipeline"


def main() -> int:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    prepared = state.get("prepared_source_parts") or {}
    editing = state.get("editing") or {}
    position = {
        "story": state.get("story"),
        "pipeline_version": state.get("pipeline_version"),
        "prepared_source_parts_through": prepared.get("through", 0),
        "edited_source_parts_through": editing.get("edited_source_parts_through", 0),
        "released_original_chapters_through": editing.get("released_original_chapters_through", 0),
        "story_bible_version": editing.get("story_bible_version"),
        "next_action": state.get("next_action"),
        "git_sha": os.getenv("GITHUB_SHA"),
        "run_id": os.getenv("GITHUB_RUN_ID"),
    }
    released = int(position["released_original_chapters_through"] or 0)
    prepared_through = int(position["prepared_source_parts_through"] or 0)
    edited = int(position["edited_source_parts_through"] or 0)
    status = "success" if released and released >= int((state.get("verified_original_chapters") or {}).get("through", 0) or 0) else "running"
    if prepared_through and edited < prepared_through:
        status = "running"

    checkpoint = save_checkpoint(
        PROJECT,
        SOURCE,
        scope=SCOPE,
        status=status,
        position=position,
    )
    durable = get_checkpoint(PROJECT, SCOPE)
    if not durable or (durable.get("position") or {}).get("released_original_chapters_through") != released:
        raise SystemExit("VBTH D1 checkpoint round-trip mismatch")
    report_status(
        PROJECT,
        status,
        run_id=os.getenv("GITHUB_RUN_ID"),
        detail={"scope": SCOPE, "position": position},
    )
    print(json.dumps({"ok": True, "checkpoint": checkpoint, "verified": durable}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
