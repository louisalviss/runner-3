#!/usr/bin/env python3
"""Compute a stable semantic identity for chapter-oriented EPUBs.

The identity deliberately ignores ZIP compression, timestamps, EPUB metadata and
XHTML serialization differences. It hashes ordered normalized block text from
chapter XHTML files, so a rebuilt artifact may be promoted only when its actual
reading content matches the pinned canonical master.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ALGORITHM = "ebook-xhtml-block-text-v1"
BLOCK_TAGS = {"h1", "h2", "h3", "p", "li", "blockquote"}
CHAPTER_RE = re.compile(r"(?:^|/)ch(\d{4})\.xhtml$")


def normalize_block(text: str) -> str:
    return " ".join(text.split())


def chapter_text(raw: bytes) -> str:
    root = ET.fromstring(raw)
    body = None
    for node in root.iter():
        tag = node.tag.split("}")[-1] if isinstance(node.tag, str) else ""
        if tag == "body":
            body = node
            break
    if body is None:
        body = root
    blocks: list[str] = []
    for node in body.iter():
        tag = node.tag.split("}")[-1] if isinstance(node.tag, str) else ""
        if tag not in BLOCK_TAGS:
            continue
        value = normalize_block("".join(node.itertext()))
        if value:
            blocks.append(value)
    return "\n".join(blocks)


def compute(path: str | Path) -> dict:
    path = Path(path)
    h = hashlib.sha256()
    rows = []
    chars = 0
    with zipfile.ZipFile(path) as zf:
        candidates = []
        for name in zf.namelist():
            match = CHAPTER_RE.search(name)
            if match:
                candidates.append((int(match.group(1)), name))
        candidates.sort()
        for ordinal, (chapter_no, name) in enumerate(candidates, 1):
            text = chapter_text(zf.read(name))
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chars += len(text)
            h.update(f"{ordinal:04d}\n{text}\n\x1e".encode("utf-8"))
            rows.append({"chapter": chapter_no, "path": name, "chars": len(text), "sha256": digest})
    return {
        "algorithm": ALGORITHM,
        "file": path.name,
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "chapter_count": len(rows),
        "normalized_chars": chars,
        "semantic_sha256": h.hexdigest(),
        "chapters": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("epub")
    p.add_argument("--expect-sha256")
    p.add_argument("--expect-chapters", type=int)
    p.add_argument("--expect-chars", type=int)
    p.add_argument("--summary-only", action="store_true")
    args = p.parse_args()
    result = compute(args.epub)
    failures = []
    if args.expect_sha256 and result["semantic_sha256"] != args.expect_sha256:
        failures.append("semantic_sha256")
    if args.expect_chapters is not None and result["chapter_count"] != args.expect_chapters:
        failures.append("chapter_count")
    if args.expect_chars is not None and result["normalized_chars"] != args.expect_chars:
        failures.append("normalized_chars")
    if args.summary_only:
        result = {k: v for k, v in result.items() if k != "chapters"}
    result["ok"] = not failures
    result["failures"] = failures
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
