#!/usr/bin/env python3
"""Durable handoff for ChatGPT-edited YouTube story packets.

The VPS owns deterministic packetization, hashes and checkpoints. ChatGPT owns
literary reconstruction. This helper never calls an LLM/provider itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import youtube_story as ys

EDITOR_KIND = "chatgpt"
SCHEMA = "youtube-story-chatgpt-handoff-v1"


def _load_edits(work: Path) -> dict[int, dict[str, Any]]:
    rows = ys.load_numbered(work / "edits", "packet-*.edit.json")
    return {int(row["packet_id"]): row for row in rows}


def _next_context(work: Path) -> dict[str, Any]:
    packets = ys.load_numbered(work / "packets", "packet-*.json")
    if not packets:
        raise ValueError("no prepared packets")
    edits = _load_edits(work)
    state: dict[str, Any] = {}
    previous_tail = ""
    next_packet = None
    for packet in packets:
        pid = int(packet["packet_id"])
        existing = edits.get(pid)
        if existing:
            if existing.get("input_sha256") != packet.get("source_sha256"):
                raise ValueError(f"stale accepted edit for packet {pid}")
            state = ys._clean_state(existing.get("continuity_state")) or state
            previous_tail = str(existing.get("edited_body") or "")[-1800:]
            continue
        next_packet = packet
        break
    return {
        "schema": SCHEMA,
        "done": next_packet is None,
        "completed": len(edits),
        "total": len(packets),
        "next_packet": next_packet,
        "continuity_state_before": state,
        "previous_edited_tail": previous_tail,
        "required_response": {
            "edited_body": "full prose reconstruction, not summary",
            "chapter_title_hint": "short title or empty",
            "scene_break_after": False,
            "continuity_state": {
                "characters": [], "factions": [], "realms": [],
                "techniques": [], "items": [], "locations": [],
                "terminology": [], "unresolved_threads": [],
                "timeline_checkpoint": "", "current_scene": "",
            },
        },
    }


def cmd_next(args: argparse.Namespace) -> int:
    print(json.dumps(_next_context(Path(args.work)), ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    ctx = _next_context(Path(args.work))
    packet = ctx.get("next_packet") or {}
    print(json.dumps({
        "schema": SCHEMA,
        "done": ctx["done"],
        "completed": ctx["completed"],
        "total": ctx["total"],
        "next_packet_id": packet.get("packet_id"),
        "next_source_sha256": packet.get("source_sha256"),
    }, ensure_ascii=False))
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    work = Path(args.work)
    ctx = _next_context(work)
    packet = ctx.get("next_packet")
    if not packet:
        print(json.dumps({"ok": True, "stage": "accept", "done": True}))
        return 0
    raw = ys.read_json(args.response)
    if raw.get("packet_id") not in (None, int(packet["packet_id"])):
        print(json.dumps({"ok": False, "error": "packet_id_mismatch"}))
        return 2
    if raw.get("source_sha256") not in (None, packet["source_sha256"]):
        print(json.dumps({"ok": False, "error": "source_sha256_mismatch"}))
        return 2
    edit, errors = ys.validate_edit(packet, raw)
    if errors:
        print(json.dumps({"ok": False, "stage": "accept", "packet_id": packet["packet_id"], "errors": errors}, ensure_ascii=False))
        return 3
    edit["editor_kind"] = EDITOR_KIND
    edit["editor_identity"] = args.editor_identity
    edit["handoff_schema"] = SCHEMA
    target = work / "edits" / f"packet-{int(packet['packet_id']):04d}.edit.json"
    ys.atomic_json(target, edit)
    next_ctx = _next_context(work)
    print(json.dumps({
        "ok": True,
        "stage": "accept",
        "packet_id": packet["packet_id"],
        "input_sha256": packet["source_sha256"],
        "edited_chars": edit["edited_chars"],
        "length_ratio": edit["length_ratio"],
        "completed": next_ctx["completed"],
        "total": next_ctx["total"],
        "next_packet_id": (next_ctx.get("next_packet") or {}).get("packet_id"),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("next"); p.add_argument("--work", required=True); p.set_defaults(func=cmd_next)
    p = sub.add_parser("status"); p.add_argument("--work", required=True); p.set_defaults(func=cmd_status)
    p = sub.add_parser("accept"); p.add_argument("--work", required=True); p.add_argument("--response", required=True); p.add_argument("--editor-identity", default="chatgpt:gpt-5.6-sol"); p.set_defaults(func=cmd_accept)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
