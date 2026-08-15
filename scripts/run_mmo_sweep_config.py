#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def expand_section(section):
    if section.get("urls"):
        return section
    base = section["base"].rstrip("/") + "/"
    pages = int(section.get("pages", 1))
    urls = [base]
    urls.extend(base + f"page-{p}/" for p in range(2, pages + 1))
    out = dict(section)
    out["urls"] = urls
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--output", default="mmo_sweep_output")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    for source in cfg["sources"]:
        source["sections"] = [expand_section(x) for x in source["sections"]]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
        json.dump(cfg, fh, ensure_ascii=False)
        expanded = fh.name
    subprocess.run([sys.executable, "scripts/mmo_forum_sweep.py", expanded, "--output", args.output], check=True)


if __name__ == "__main__":
    main()
