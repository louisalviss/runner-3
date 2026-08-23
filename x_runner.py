#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
ALLOWED_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
IMAGE_HINTS = ("pbs.twimg.com/media/", ".jpg", ".jpeg", ".png", ".webp")
VIDEO_HINTS = ("video.twimg.com/", ".mp4")
SOURCE_TIMEOUT_SECONDS = 6


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_x_url(url):
    p = urlparse(url)
    if p.scheme != "https" or p.netloc.lower() not in ALLOWED_HOSTS:
        raise ValueError("url must be a public https://x.com/.../status/... or twitter.com status URL")
    m = re.search(r"/([^/]+)/status/(\d+)", p.path)
    if not m:
        raise ValueError("url must contain /<handle>/status/<tweet_id>")
    return m.group(1), m.group(2), f"https://x.com/{m.group(1)}/status/{m.group(2)}"


def fetch_json(url, timeout=SOURCE_TIMEOUT_SECONDS):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
    try:
        with urlopen(req, timeout=timeout) as r:
            body = r.read()
            status = getattr(r, "status", 200)
            ctype = r.headers.get("content-type", "")
    except HTTPError as e:
        return {"ok": False, "status": e.code, "url": url, "error": str(e), "data": None}
    except (URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": None, "url": url, "error": str(e), "data": None}
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception as e:
        return {"ok": False, "status": status, "url": url, "error": f"invalid json ({ctype}): {e}", "data": None}
    return {"ok": 200 <= status < 300, "status": status, "url": url, "error": None, "data": data}


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def first_text(payloads):
    preferred = ("text", "full_text", "tweet_text", "description")
    for payload in payloads:
        if not payload:
            continue
        for node in walk(payload):
            for key in preferred:
                value = node.get(key)
                if isinstance(value, str) and 2 <= len(value.strip()) <= 10000:
                    return value.strip()
    return ""


def collect_media(payloads):
    images, videos = [], []
    seen_i, seen_v = set(), set()
    for payload in payloads:
        if not payload:
            continue
        for value in strings(payload):
            if not value.startswith("http"):
                continue
            clean = value.replace("\\/", "/")
            low = clean.lower()
            if any(h in low for h in VIDEO_HINTS):
                if clean not in seen_v:
                    seen_v.add(clean)
                    videos.append(clean)
            elif any(h in low for h in IMAGE_HINTS):
                if clean not in seen_i:
                    seen_i.add(clean)
                    images.append(clean)

    def image_rank(url):
        low = url.lower()
        score = 0
        if "pbs.twimg.com/media/" in low:
            score += 100
        if "profile_images" in low:
            score -= 50
        if "profile_banners" in low:
            score -= 50
        if "format=jpg" in low or ".jpg" in low or ".jpeg" in low:
            score += 5
        return -score

    images.sort(key=image_rank)
    return images, videos


def download(url, path, max_bytes=80 * 1024 * 1024, timeout=30):
    req = Request(url, headers={"User-Agent": UA, "Referer": "https://x.com/"})
    with urlopen(req, timeout=timeout) as r:
        total = 0
        with path.open("wb") as f:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"download exceeds {max_bytes} bytes")
                f.write(chunk)
    return total


def make_frames(video_path, outdir):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    pattern = outdir / "frame_%02d.jpg"
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path),
        "-vf", "fps=1/5,scale=1280:-2:force_original_aspect_ratio=decrease",
        "-frames:v", "3", str(pattern),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return sorted(p.name for p in outdir.glob("frame_*.jpg"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_file")
    ap.add_argument("--output-root", default="x-results")
    args = ap.parse_args()

    job = json.loads(Path(args.job_file).read_text(encoding="utf-8"))
    url = str(job.get("x_url") or job.get("url") or "").strip()
    if not url:
        raise SystemExit("job must contain x_url")
    handle, tweet_id, canonical = parse_x_url(url)

    outdir = Path(args.output_root) / tweet_id
    outdir.mkdir(parents=True, exist_ok=True)

    endpoints = {
        "legacy": f"https://api.fxtwitter.com/{handle}/status/{tweet_id}",
        "vx": f"https://api.vxtwitter.com/{handle}/status/{tweet_id}",
        "syndication": f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en",
        "conversation": f"https://api.fxtwitter.com/2/conversation/{tweet_id}?count=100",
    }
    fetched = {}
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        futures = {pool.submit(fetch_json, endpoint): name for name, endpoint in endpoints.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                fetched[name] = future.result()
            except Exception as exc:
                fetched[name] = {"ok": False, "status": None, "url": endpoints[name], "error": str(exc), "data": None}

    priority = ("legacy", "vx", "syndication", "conversation")
    payloads = [
        fetched[name]["data"]
        for name in priority
        if fetched.get(name, {}).get("ok") and fetched[name].get("data") is not None
    ]

    if not payloads:
        result = {
            "ok": False,
            "tweet_id": tweet_id,
            "handle": handle,
            "url": canonical,
            "fetched_at": now_iso(),
            "sources": {k: {kk: vv for kk, vv in v.items() if kk != "data"} for k, v in fetched.items()},
            "error": "all public X mirrors/endpoints failed",
        }
        (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 1

    images, videos = collect_media(payloads)
    media_files = []
    media_error = None

    if images:
        try:
            preview = outdir / "preview.jpg"
            download(images[0], preview, max_bytes=12 * 1024 * 1024)
            media_files.append(preview.name)
        except Exception as exc:
            media_error = f"image preview: {exc}"

    if videos:
        for candidate in reversed(videos):
            try:
                video_path = outdir / "video.mp4"
                download(candidate, video_path)
                frames = make_frames(video_path, outdir)
                media_files.extend(frames)
                video_path.unlink(missing_ok=True)
                if frames:
                    break
            except Exception as exc:
                media_error = f"video frame: {exc}"
                (outdir / "video.mp4").unlink(missing_ok=True)

    result = {
        "ok": True,
        "tweet_id": tweet_id,
        "handle": handle,
        "url": canonical,
        "fetched_at": now_iso(),
        "text": first_text(payloads),
        "image_urls": images[:20],
        "video_urls": videos[:20],
        "media_files": list(dict.fromkeys(media_files)),
        "media_error": media_error,
        "sources": {k: {kk: vv for kk, vv in v.items() if kk != "data"} for k, v in fetched.items()},
        "raw": {k: v["data"] for k, v in fetched.items() if v.get("ok")},
    }
    (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("ok", "tweet_id", "handle", "text", "media_files")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
