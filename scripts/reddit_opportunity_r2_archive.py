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


def r2_get(bucket: str, key: str, path: Path, quiet=False) -> bool:
    cmd = ["npx", "-y", f"wrangler@{WRANGLER}", "r2", "object", "get",
           f"{bucket}/{key}", f"--file={path}", "--remote"]
    proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL if quiet else None)
    return proc.returncode == 0


def verify_remote(bucket: str, cfg: dict, run_id: str, manifest: dict,
                  manifest_path: Path, latest_path: Path, td: Path):
    manifest_key = f"{cfg['root_prefix']}/{run_id}/manifest.json"
    got_manifest = td / "verify-manifest.json"
    got_latest = td / "verify-latest.json"
    if not r2_get(bucket, manifest_key, got_manifest):
        raise RuntimeError("R2 verification failed: manifest missing")
    if not r2_get(bucket, cfg["latest_pointer"], got_latest):
        raise RuntimeError("R2 verification failed: LATEST missing")
    if got_manifest.read_bytes() != manifest_path.read_bytes():
        raise RuntimeError("R2 verification failed: manifest bytes mismatch")
    latest = json.loads(got_latest.read_text(encoding="utf-8"))
    if latest.get("run_id") != run_id or latest.get("manifest_key") != manifest_key:
        raise RuntimeError("R2 verification failed: LATEST pointer mismatch")

    raw_entry = next((x for x in manifest["files"]
                      if x["key"].endswith("/raw/posts.jsonl.gz")), None)
    if raw_entry:
        got_raw = td / "verify-raw.bin"
        if not r2_get(bucket, raw_entry["key"], got_raw):
            raise RuntimeError("R2 verification failed: raw object missing")
        digest = sha256(got_raw.read_bytes())
        if digest not in {raw_entry["sha256_logical"], raw_entry["sha256_stored"]}:
            raise RuntimeError("R2 verification failed: raw SHA-256 mismatch")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--run-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
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
    with tempfile.TemporaryDirectory(prefix="reddit-opportunity-r2-") as td_raw:
        td = Path(td_raw)
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
        manifest_key = f"{cfg['root_prefix']}/{run_id}/manifest.json"
        latest = {"schema":"reddit-opportunity-latest/v1", "run_id":run_id,
                  "manifest_key":manifest_key}
        latest_path = td / "LATEST.json"
        latest_path.write_text(json.dumps(latest, indent=2)+"\n")
        if args.dry_run:
            print(json.dumps(manifest, ensure_ascii=False, indent=2)); return

        existing = td / "existing-manifest.json"
        if r2_get(bucket, manifest_key, existing, quiet=True):
            raise SystemExit(f"Refusing to overwrite immutable R2 run: {manifest_key}")
        for key, path, ct, enc in uploads:
            r2_put(bucket, key, path, ct, enc)
        r2_put(bucket, manifest_key, manifest_path, "application/json; charset=utf-8")
        r2_put(bucket, cfg["latest_pointer"], latest_path, "application/json; charset=utf-8")

        verified = False
        if not args.no_verify:
            verify_remote(bucket, cfg, run_id, manifest, manifest_path, latest_path, td)
            verified = True
    print(json.dumps({"ok":True, "verified":verified, "bucket":bucket, "run_id":run_id,
                      "objects":len(manifest["files"])+2, "raw_posts":manifest["counts"]["raw_posts"]}))

if __name__ == "__main__":
    main()
