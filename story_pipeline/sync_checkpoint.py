#!/usr/bin/env python3
"""Sync VBTH to the generic ebook checkpoint flow and preserve the legacy checkpoint."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY_DIR = ROOT / "story_pipeline"
sys.path.insert(0, str(STORY_DIR))
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from ebook_checkpoint import load_manifest, sync_book_main  # noqa: E402
from runner3_core import get_checkpoint, report_status, save_checkpoint  # noqa: E402

STATE_PATH = STORY_DIR / "state.json"
MANIFEST_PATH = STORY_DIR / "books" / "vbth.json"

LEGACY_PROJECT = "vbth-editorial"
LEGACY_SCOPE = "main"
LEGACY_SOURCE = "runner-3/story_pipeline"


def sync_legacy(state: dict, status: str) -> dict:
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
        "migrated_to": "ebook-editorial/book:vbth:main",
    }
    released = int(position["released_original_chapters_through"] or 0)
    checkpoint = save_checkpoint(
        LEGACY_PROJECT,
        LEGACY_SOURCE,
        scope=LEGACY_SCOPE,
        status=status,
        position=position,
    )
    durable = get_checkpoint(LEGACY_PROJECT, LEGACY_SCOPE)
    if not durable or (durable.get("position") or {}).get("released_original_chapters_through") != released:
        raise SystemExit("VBTH legacy D1 checkpoint round-trip mismatch")
    report_status(
        LEGACY_PROJECT,
        status,
        run_id=os.getenv("GITHUB_RUN_ID"),
        detail={"scope": LEGACY_SCOPE, "position": position, "compatibility_mirror": True},
    )
    return {"checkpoint": checkpoint, "verified": durable}


def main() -> int:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest(MANIFEST_PATH)
    generic = sync_book_main(manifest, state)
    legacy = sync_legacy(state, generic["status"])
    print(json.dumps({
        "ok": True,
        "book_id": manifest["book_id"],
        "generic": generic,
        "legacy": legacy,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
