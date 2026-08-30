#!/usr/bin/env python3
import asyncio
import json
import os
import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CORE_BASE = os.getenv("EBOOK_AUDIO_CORE_BASE", "https://runner3-core.ducduy2411.workers.dev").rstrip("/")
TOKEN = os.getenv("RUNNER3_CORE_TOKEN", "")
VOICE = os.getenv("AUDIO_TTS_VOICE", "vi-VN-NamMinhNeural")
RATE = os.getenv("AUDIO_TTS_RATE", "+3%")
MAX_JOBS = max(1, min(20, int(os.getenv("EBOOK_AUDIO_MAX_JOBS", "8"))))


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request(path, method="GET", payload=None, raw=False, content_type=None, timeout=180):
    if not TOKEN:
        raise RuntimeError("RUNNER3_CORE_TOKEN is required")
    body = None
    if payload is not None:
        body = payload if raw else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "runner-3/ebook-reader-tts",
    }
    if body is not None:
        headers["Content-Type"] = content_type or ("application/octet-stream" if raw else "application/json; charset=utf-8")
    req = urllib.request.Request(f"{CORE_BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read(), response.status, response.headers
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail[:800]}") from exc


def request_json(path, method="GET", payload=None):
    data, _, _ = request(path, method=method, payload=payload)
    return json.loads(data.decode("utf-8")) if data else {}


def parse_rate(value):
    value = str(value or "").strip()
    if not value:
        return 1.0
    sign = -1 if value.startswith("-") else 1
    digits = value.lstrip("+-").rstrip("%")
    try:
        return max(0.5, min(2.0, 1 + sign * float(digits) / 100))
    except ValueError:
        return 1.0


async def synthesize(text, out_path):
    import edge_tts

    words = []
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    with out_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                audio_file.write(chunk.get("data") or b"")
            elif kind == "WordBoundary":
                offset = int(chunk.get("offset") or 0)
                duration = int(chunk.get("duration") or 0)
                words.append({
                    "text": str(chunk.get("text") or ""),
                    "offsetSeconds": round(offset / 10_000_000, 4),
                    "durationSeconds": round(duration / 10_000_000, 4),
                })
    if not out_path.exists() or out_path.stat().st_size < 512:
        raise RuntimeError("Edge TTS returned no usable audio")
    return words


def probe_duration(path, words):
    try:
        from mutagen.mp3 import MP3
        return round(float(MP3(path).info.length), 2)
    except Exception:
        if words:
            last = words[-1]
            return round(float(last.get("offsetSeconds", 0)) + float(last.get("durationSeconds", 0)), 2)
        return None


def fail_job(job_id, error):
    try:
        request_json("/api/internal/ebook-reader-audio/fail", method="POST", payload={
            "id": job_id,
            "error": str(error)[:800],
            "failedAt": now_iso(),
        })
    except Exception as nested:
        print(f"WARN fail callback {job_id}: {nested}")


async def render_job(job):
    job_id = str(job.get("id") or "")
    script = str(job.get("script") or "").strip()
    if not job_id or not script:
        raise RuntimeError("Invalid ebook audio job")

    voice = str(job.get("voice") or VOICE)
    rate = str(job.get("voiceRate") or RATE)
    if voice != VOICE or rate != RATE:
        raise RuntimeError(f"Voice contract mismatch: {voice} {rate}")

    print(f"PROCESS {job_id} chars={len(script)} voice={VOICE} rate={RATE}")
    with tempfile.TemporaryDirectory() as temp_dir:
        mp3 = pathlib.Path(temp_dir) / "episode.mp3"
        words = await synthesize(script, mp3)
        duration = probe_duration(mp3, words)
        timing = {
            "version": "ebook-reader-word-boundary-v1",
            "id": job_id,
            "voice": VOICE,
            "voiceRate": RATE,
            "durationSeconds": duration,
            "generatedAt": now_iso(),
            "words": words,
        }
        encoded_id = urllib.parse.quote(job_id, safe="")
        request(
            f"/api/internal/ebook-reader-audio/media?id={encoded_id}",
            method="PUT",
            payload=mp3.read_bytes(),
            raw=True,
            content_type="audio/mpeg",
            timeout=300,
        )
        request(
            f"/api/internal/ebook-reader-audio/timing?id={encoded_id}",
            method="PUT",
            payload=json.dumps(timing, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            raw=True,
            content_type="application/json; charset=utf-8",
            timeout=180,
        )
        result = request_json("/api/internal/ebook-reader-audio/complete", method="POST", payload={
            "id": job_id,
            "durationSeconds": duration,
            "wordCount": len(words),
            "voice": VOICE,
            "voiceRate": RATE,
            "speed": parse_rate(RATE),
            "completedAt": now_iso(),
        })
    print(f"READY {job_id} duration={duration} words={len(words)} result={result.get('status', 'ok')}")


async def main():
    processed = 0
    for _ in range(MAX_JOBS):
        response = request_json("/api/internal/ebook-reader-audio/job")
        job = response.get("job")
        if not job:
            print(f"DONE processed={processed} queue=empty")
            return
        job_id = str(job.get("id") or "unknown")
        try:
            await render_job(job)
            processed += 1
        except Exception as exc:
            print(f"ERROR {job_id}: {exc}")
            fail_job(job_id, exc)
    print(f"DONE processed={processed} max_jobs={MAX_JOBS}")


if __name__ == "__main__":
    asyncio.run(main())
