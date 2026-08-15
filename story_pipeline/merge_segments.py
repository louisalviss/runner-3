#!/usr/bin/env python3
"""Merge edited TiênVuc parts into original chapters at segment-level boundaries.

Boundaries may fall inside a TiênVuc web part. Chinese sources are reference-only
for locating the cuts; the merged prose is always sliced from edited TiênVuc text.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slice_segment(body, segment):
    start_at = segment.get("start_at")
    end_before = segment.get("end_before")
    start = 0
    end = len(body)
    if start_at:
        idx = body.find(start_at)
        if idx < 0:
            raise ValueError(f"start_at marker not found: {start_at!r}")
        start = idx
    if end_before:
        idx = body.find(end_before, start)
        if idx < 0:
            raise ValueError(f"end_before marker not found: {end_before!r}")
        end = idx
    if end <= start:
        raise ValueError("segment boundary produces empty/reversed text")
    return body[start:end].strip()


def merge(edited_dir, map_file, output_dir):
    edited_dir, output_dir = Path(edited_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping = read_json(map_file)
    merged = []
    failures = []
    for ch in mapping.get("chapters", []):
        segments = ch.get("segments") or [{"part": p} for p in ch.get("source_parts", [])]
        bodies = []
        errors = []
        for seg in segments:
            part = int(seg["part"])
            p = edited_dir / f"part-{part:04d}.json"
            if not p.exists():
                errors.append(f"part {part}: missing")
                continue
            try:
                bodies.append(slice_segment(read_json(p)["body"], seg))
            except ValueError as exc:
                errors.append(f"part {part}: {exc}")
        if errors:
            failures.append({"chapter": ch.get("original_no"), "errors": errors})
            continue
        body = "\n\n".join(bodies)
        rec = {
            "original_no": ch["original_no"],
            "volume": ch.get("volume"),
            "title_vi": ch["title_vi"],
            "title_zh": ch.get("title_zh"),
            "segments": segments,
            "body": body,
            "body_chars": len(body),
            "merged_at": now_iso(),
        }
        write_json(output_dir / f"chapter-{int(ch['original_no']):04d}.json", rec)
        merged.append(rec)
    manifest = {
        "stage": "segment-merge",
        "count": len(merged),
        "failed": len(failures),
        "chapters": [x["original_no"] for x in merged],
        "failures": failures,
        "generated_at": now_iso(),
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--edited", required=True)
    p.add_argument("--map", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    manifest = merge(args.edited, args.map, args.output)
    print(json.dumps(manifest, ensure_ascii=False))
    return 1 if manifest["failed"] else (0 if manifest["count"] else 2)


if __name__ == "__main__":
    raise SystemExit(main())
