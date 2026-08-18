from __future__ import annotations

import argparse
import hashlib
import pathlib
import urllib.parse
import urllib.request

from common import ensure_dir, ffmpeg, json_dump, load_config, run

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: pathlib.Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("output_dir")
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = ensure_dir(args.output_dir)
    raw_dir = ensure_dir(root / "raw")
    norm_dir = ensure_dir(root / "normalized")
    fps = int(cfg.get("fps", 30))
    norm_seconds = float(cfg.get("ingest", {}).get("normalize_seconds", 6.0))

    manifest = {"job": cfg["job"], "sources": []}
    for src in cfg["sources"]:
        if src.get("kind") != "direct":
            raise SystemExit(f"unsupported source kind for {src.get('id')}: {src.get('kind')}")

        source_id = src["id"]
        url = src["url"]
        suffix = pathlib.Path(urllib.parse.urlparse(url).path).suffix.lower() or ".bin"
        if len(suffix) > 8:
            suffix = ".bin"
        raw = raw_dir / f"{source_id}{suffix}"
        normalized = norm_dir / f"{source_id}.mp4"

        print(f"downloading {source_id}: {url}", flush=True)
        download(url, raw)
        if raw.stat().st_size < 1024:
            raise SystemExit(f"source too small: {source_id} ({raw.stat().st_size} bytes)")

        run([
            ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "2", "-i", str(raw), "-t", f"{norm_seconds:.3f}",
            "-vf", f"fps={fps},scale=1280:534:force_original_aspect_ratio=increase,crop=1280:534,setsar=1,format=yuv420p",
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "19",
            str(normalized),
        ])

        manifest["sources"].append({
            "id": source_id,
            "url": url,
            "raw_file": str(raw.relative_to(root)),
            "raw_bytes": raw.stat().st_size,
            "raw_sha256": sha256(raw),
            "normalized_file": str(normalized.relative_to(root)),
            "normalized_bytes": normalized.stat().st_size,
            "normalized_sha256": sha256(normalized),
        })

    json_dump(root / "manifest.json", manifest)
    print(f"ingested {len(manifest['sources'])} source(s) for {cfg['job']}")


if __name__ == "__main__":
    main()
