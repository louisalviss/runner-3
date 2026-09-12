#!/usr/bin/env python3
import argparse, gzip, hashlib, json, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/reddit-opportunity-storage.json"
WRANGLER = "4.131.1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def r2_put(bucket: str, key: str, path: Path, content_type: str, encoded=False):
    cmd = ["npx", "-y", f"wrangler@{WRANGLER}", "r2", "object", "put",
           f"{bucket}/{key}", f"--file={path}", f"--content-type={content_type}",
           "--remote", "--force"]
    if encoded:
        cmd += ["--content-encoding=gzip"]
    subprocess.check_call(cmd, cwd=ROOT, stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--run-id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = json.loads(CFG.read_text())
    bucket = cfg["bucket"]
    run_dir = args.run_dir.resolve()
    run_id = args.run_id or run_dir.name
    specs = [
        ("candidates.jsonl", "raw/posts.jsonl.gz", "application/x-ndjson", True),
        ("clusters.json", "derived/clusters.json.gz", "application/json", True),
        ("top_candidates.json", "derived/top-candidates.json.gz", "application/json", True),
        ("curated/actionable.jsonl", "derived/actionable.jsonl.gz", "application/x-ndjson", True),
        ("curated/top_actionable.json", "derived/top-actionable.json.gz", "application/json", True),
        ("summary.json", "meta/summary.json", "application/json; charset=utf-8", False),
        ("curated/curation_summary.json", "meta/curation-summary.json", "application/json; charset=utf-8", False),
    ]
    manifest = {"schema":"reddit-opportunity-r2-manifest/v2", "bucket":bucket,
                "run_id":run_id, "created_at":datetime.now(timezone.utc).isoformat(),
                "policy":cfg["policy"], "files":[]}
    with tempfile.TemporaryDirectory(prefix="reddit-opportunity-r2-") as td:
        td = Path(td)
        uploads = []
        for rel, key, ct, compress in specs:
            src = run_dir / rel
            if not src.exists():
                continue
            logical = src.read_bytes()
            out = td / key.replace("/", "__")
            stored = gzip.compress(logical, compresslevel=9, mtime=0) if compress else logical
            out.write_bytes(stored)
            full_key = f"{cfg['root_prefix']}/{run_id}/{key}"
            manifest["files"].append({"key":full_key, "logical_bytes":len(logical),
                "stored_bytes":len(stored), "sha256_logical":sha256(logical),
                "sha256_stored":sha256(stored), "content_encoding":"gzip" if compress else None})
            uploads.append((full_key, out, ct, compress))
        raw = run_dir / "candidates.jsonl"
        action = run_dir / "curated/actionable.jsonl"
        manifest["counts"] = {
            "raw_posts": sum(1 for _ in raw.open(encoding="utf-8")) if raw.exists() else None,
            "actionable_rows": sum(1 for _ in action.open(encoding="utf-8")) if action.exists() else None,
        }
        manifest_path = td / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
        latest = {"schema":"reddit-opportunity-latest/v1", "run_id":run_id,
                  "manifest_key":f"{cfg['root_prefix']}/{run_id}/manifest.json"}
        latest_path = td / "LATEST.json"
        latest_path.write_text(json.dumps(latest, indent=2)+"\n")
        if args.dry_run:
            print(json.dumps(manifest, ensure_ascii=False, indent=2)); return
        for key, path, ct, enc in uploads:
            r2_put(bucket, key, path, ct, enc)
        r2_put(bucket, f"{cfg['root_prefix']}/{run_id}/manifest.json", manifest_path, "application/json; charset=utf-8")
        r2_put(bucket, cfg["latest_pointer"], latest_path, "application/json; charset=utf-8")
    print(json.dumps({"ok":True, "bucket":bucket, "run_id":run_id,
                      "objects":len(manifest["files"])+2, "raw_posts":manifest["counts"]["raw_posts"]}))

if __name__ == "__main__":
    main()
