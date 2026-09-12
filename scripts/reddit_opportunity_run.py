#!/usr/bin/env python3
"""Canonical manual Reddit Opportunity run: scan -> curate -> isolated R2 archive."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stage(name, cmd):
    print(json.dumps({"stage": name, "command": cmd}, ensure_ascii=False), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id")
    ap.add_argument("--output-dir")
    ap.add_argument("--max-subs", type=int, default=0)
    ap.add_argument("--per-listing", type=int, default=30)
    ap.add_argument("--confirmations", type=int, default=60)
    ap.add_argument("--delay", type=float, default=0.05)
    ap.add_argument("--live-first", action="store_true", help="Try normal Reddit transport instead of archive fast-path")
    ap.add_argument("--r2-dry-run", action="store_true", help="Build archive manifest but do not upload")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = Path(args.output_dir) if args.output_dir else ROOT / "ops/reddit-opportunity" / run_id
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty run directory: {out}")

    scanner = "scripts/reddit_opportunity_scan.py" if args.live_first else "scripts/reddit_opportunity_scan_archive.py"
    scan_cmd = [sys.executable, scanner, "--output-dir", str(out),
                "--per-listing", str(args.per_listing), "--confirmations", str(args.confirmations),
                "--delay", str(args.delay)]
    if args.max_subs:
        scan_cmd += ["--max-subs", str(args.max_subs)]
    stage("scan", scan_cmd)

    stage("curate", [sys.executable, "scripts/reddit_opportunity_curate.py",
                      str(out / "candidates.jsonl"), "--output-dir", str(out / "curated")])

    archive_cmd = [sys.executable, "scripts/reddit_opportunity_r2_archive.py", str(out), "--run-id", run_id]
    if args.r2_dry_run:
        archive_cmd.append("--dry-run")
    stage("archive-r2", archive_cmd)

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    curated = json.loads((out / "curated/curation_summary.json").read_text(encoding="utf-8"))
    print(json.dumps({"ok": True, "run_id": run_id, "output_dir": str(out),
                      "raw_posts": summary.get("unique_posts"), "actionable": curated.get("kept"),
                      "r2": "dry-run" if args.r2_dry_run else "uploaded-and-verified"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
