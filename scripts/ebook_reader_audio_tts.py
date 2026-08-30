#!/usr/bin/env python3
"""GitHub-hosted Ebook Reader TTS worker.

Consumes Ebook Reader queue objects from R2, synthesizes Nam Minh audio with
Edge TTS WordBoundary timing, publishes episode.mp3 + timing.json, and updates
the item state used by artifact-library-reader-v6+.
"""

import asyncio
import datetime as dt
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

import edge_tts
import requests

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
BUCKET = os.environ.get("EBOOK_AUDIO_BUCKET", "runner3-wp-media").strip()
VOICE = os.environ.get("EBOOK_AUDIO_VOICE", "vi-VN-NamMinhNeural").strip()
VOICE_RATE = os.environ.get("EBOOK_AUDIO_VOICE_RATE", "+3%").strip()
AUDIO_VERSION = "ebook-reader-audio-v1"
TIMING_VERSION = "ebook-reader-timing-v1"
ITEM_PREFIX = "audio-library/items/"
QUEUE_PREFIX = "audio-library/ebook-reader-queue/"
MEDIA_PREFIX = "audio-library/media/"
LEASE_SECONDS = 20 * 60
MAX_ATTEMPTS = 3
MAX_JOBS_PER_RUN = 4
CHUNK_CHARS = 3200
HTTP_TIMEOUT = 90

ID_RE = re.compile(r"^ebook-([a-f0-9]{32})$")


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(value=None):
    return (value or utcnow()).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def require_env():
    missing = []
    if not ACCOUNT_ID:
        missing.append("CLOUDFLARE_ACCOUNT_ID")
    if not API_TOKEN:
        missing.append("CLOUDFLARE_API_TOKEN")
    if not BUCKET:
        missing.append("EBOOK_AUDIO_BUCKET")
    if missing:
        raise RuntimeError("Missing environment: " + ", ".join(missing))


def api_headers(content_type=None):
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def object_url(key=None):
    base = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/buckets/{quote(BUCKET, safe='')}/objects"
    if key is None:
        return base
    # Cloudflare requires slashes in object keys to remain literal.
    return base + "/" + quote(str(key), safe="/")


def check_response(response, operation):
    if 200 <= response.status_code < 300:
        return response
    text = response.text[:500].replace("\n", " ")
    raise RuntimeError(f"R2 {operation} failed HTTP {response.status_code}: {text}")


def r2_get_bytes(key, *, missing_ok=False):
    response = requests.get(object_url(key), headers=api_headers(), timeout=HTTP_TIMEOUT)
    if response.status_code == 404 and missing_ok:
        return None
    return check_response(response, f"GET {key}").content


def r2_get_json(key, *, missing_ok=False):
    raw = r2_get_bytes(key, missing_ok=missing_ok)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON in {key}: {type(exc).__name__}") from exc


def r2_put_bytes(key, data, content_type):
    response = requests.put(
        object_url(key),
        headers=api_headers(content_type),
        data=data,
        timeout=HTTP_TIMEOUT,
    )
    check_response(response, f"PUT {key}")


def r2_put_json(key, value):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    r2_put_bytes(key, payload, "application/json; charset=utf-8")


def r2_delete(key, *, missing_ok=True):
    response = requests.delete(object_url(key), headers=api_headers(), timeout=HTTP_TIMEOUT)
    if missing_ok and response.status_code == 404:
        return
    check_response(response, f"DELETE {key}")


def r2_list(prefix):
    rows = []
    cursor = None
    while True:
        params = {"prefix": prefix, "per_page": 1000}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(object_url(), headers=api_headers(), params=params, timeout=HTTP_TIMEOUT)
        payload = check_response(response, f"LIST {prefix}").json()
        if not payload.get("success", False):
            raise RuntimeError(f"R2 LIST {prefix} returned success=false")
        rows.extend(payload.get("result") or [])
        info = payload.get("result_info") or {}
        if not info.get("is_truncated"):
            break
        cursor = info.get("cursor")
        if not cursor:
            break
    return rows


def normalize_job_id(value):
    raw = str(value or "").strip()
    if re.fullmatch(r"[a-f0-9]{32}", raw):
        raw = "ebook-" + raw
    if not ID_RE.fullmatch(raw):
        raise RuntimeError("Invalid Ebook audio job id")
    return raw


def queue_key(job_id):
    return f"{QUEUE_PREFIX}{job_id}.json"


def validate_queue(queue, expected_job_id=None):
    if not isinstance(queue, dict):
        raise RuntimeError("Queue payload is not an object")
    job_id = normalize_job_id(queue.get("id"))
    if expected_job_id and job_id != normalize_job_id(expected_job_id):
        raise RuntimeError("Queue id mismatch")
    if queue.get("kind") != "ebook-reader":
        raise RuntimeError("Unsupported queue kind")
    if queue.get("audioVersion") != AUDIO_VERSION:
        raise RuntimeError("Unsupported audio version")
    if queue.get("voice") != VOICE or queue.get("voiceRate") != VOICE_RATE:
        raise RuntimeError("Queue voice contract mismatch")

    short_id = ID_RE.fullmatch(job_id).group(1)
    expected_item = f"{ITEM_PREFIX}{job_id}.json"
    expected_prefix = f"{MEDIA_PREFIX}{job_id}/"
    expected_script = expected_prefix + "script.txt"
    if queue.get("itemKey") != expected_item:
        raise RuntimeError("Queue itemKey mismatch")
    if queue.get("mediaPrefix") != expected_prefix:
        raise RuntimeError("Queue mediaPrefix mismatch")
    if queue.get("scriptKey") != expected_script:
        raise RuntimeError("Queue scriptKey mismatch")
    if not re.fullmatch(r"[a-f0-9]{64}", str(queue.get("textSha256") or "")):
        raise RuntimeError("Queue textSha256 invalid")
    return job_id, short_id


def is_claimable(queue):
    status = str(queue.get("workerStatus") or "pending")
    if status in ("", "pending", "error"):
        return True
    if status != "processing":
        return False
    lease_until = parse_iso(queue.get("leaseUntil"))
    return lease_until is None or lease_until <= utcnow()


def claim(job_id, queue):
    attempts = int(queue.get("attempts") or 0)
    if attempts >= MAX_ATTEMPTS:
        return None
    now = utcnow()
    claimed = dict(queue)
    claimed.update(
        {
            "workerStatus": "processing",
            "attempts": attempts + 1,
            "claimedAt": iso(now),
            "leaseUntil": iso(now + dt.timedelta(seconds=LEASE_SECONDS)),
            "lastError": None,
        }
    )
    r2_put_json(queue_key(job_id), claimed)

    item = r2_get_json(claimed["itemKey"], missing_ok=True) or {}
    if item.get("textSha256") != claimed.get("textSha256"):
        raise RuntimeError("Item/queue textSha256 mismatch")
    item.update({"status": "processing", "updatedAt": iso(), "error": None})
    r2_put_json(claimed["itemKey"], item)
    return claimed


def tts_chunks(text, limit=CHUNK_CHARS):
    text = str(text or "").strip()
    if not text:
        return []
    pieces = re.split(r"(?<=[.!?…])\s+|\n+", text)
    chunks = []
    buf = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(buf) + len(piece) + 1 <= limit:
            buf = (buf + " " + piece).strip()
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        buf = piece
    if buf:
        chunks.append(buf)
    return chunks


def media_duration(path):
    value = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        text=True,
    ).strip()
    return float(value)


async def synthesize_part(text, path):
    boundaries = []
    communicate = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE)
    with path.open("wb") as handle:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                handle.write(chunk["data"])
            elif kind == "WordBoundary":
                # Edge TTS offsets/durations are 100-nanosecond ticks.
                boundaries.append(
                    {
                        "text": str(chunk.get("text") or ""),
                        "offsetMs": float(chunk.get("offset") or 0) / 10_000.0,
                        "durationMs": float(chunk.get("duration") or 0) / 10_000.0,
                    }
                )
    if not path.exists() or path.stat().st_size < 1500:
        raise RuntimeError("Edge TTS produced an invalid audio part")
    return boundaries


async def synthesize(script, work):
    chunks = tts_chunks(script)
    if not chunks:
        raise RuntimeError("Empty Ebook audio script")

    parts = []
    words = []
    base_ms = 0.0
    for index, text in enumerate(chunks):
        part = work / f"part-{index:04d}.mp3"
        boundaries = await synthesize_part(text, part)
        part_seconds = media_duration(part)
        for event in boundaries:
            start_ms = base_ms + event["offsetMs"]
            duration_ms = max(0.0, event["durationMs"])
            words.append(
                {
                    "text": event["text"],
                    "startMs": round(start_ms, 3),
                    "durationMs": round(duration_ms, 3),
                    "endMs": round(start_ms + duration_ms, 3),
                }
            )
        base_ms += part_seconds * 1000.0
        parts.append(part)

    concat_file = work / "concat.txt"
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    output = work / "episode.mp3"
    subprocess.check_call(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(output),
        ]
    )
    output_seconds = media_duration(output)

    # Re-encoding can shift total duration slightly. Scale captured boundaries so
    # the final timing contract lands on the actual published MP3 duration.
    if base_ms > 0 and output_seconds > 0:
        scale = output_seconds * 1000.0 / base_ms
        if abs(scale - 1.0) > 0.000001:
            for word in words:
                start = float(word["startMs"]) * scale
                duration_ms = float(word["durationMs"]) * scale
                word["startMs"] = round(start, 3)
                word["durationMs"] = round(duration_ms, 3)
                word["endMs"] = round(start + duration_ms, 3)

    return output, output_seconds, words, len(chunks)


def complete_job(job_id, queue, mp3, duration_seconds, words, chunk_count):
    media_prefix = queue["mediaPrefix"]
    audio_key = media_prefix + "episode.mp3"
    timing_key = media_prefix + "timing.json"

    timing = {
        "version": TIMING_VERSION,
        "id": job_id,
        "audioVersion": AUDIO_VERSION,
        "voice": VOICE,
        "voiceRate": VOICE_RATE,
        "durationSeconds": round(duration_seconds, 6),
        "wordCount": len(words),
        "chunkCount": chunk_count,
        "words": words,
    }
    r2_put_bytes(audio_key, mp3.read_bytes(), "audio/mpeg")
    r2_put_json(timing_key, timing)

    item = r2_get_json(queue["itemKey"], missing_ok=False)
    if item.get("textSha256") != queue.get("textSha256"):
        raise RuntimeError("Item changed while TTS was running")
    item.update(
        {
            "status": "ready",
            "updatedAt": iso(),
            "durationSeconds": round(duration_seconds, 6),
            "progressSeconds": 0,
            "audioUrl": audio_key,
            "transcriptUrl": queue["scriptKey"],
            "timingUrl": timing_key,
            "error": None,
        }
    )
    r2_put_json(queue["itemKey"], item)
    r2_delete(queue_key(job_id))


def fail_job(job_id, queue, exc):
    message = f"{type(exc).__name__}: {exc}"[:500]
    attempts = int(queue.get("attempts") or 1)
    terminal = attempts >= MAX_ATTEMPTS

    item = r2_get_json(queue["itemKey"], missing_ok=True) or {}
    item.update(
        {
            "status": "error" if terminal else "pending",
            "updatedAt": iso(),
            "error": message if terminal else None,
        }
    )
    r2_put_json(queue["itemKey"], item)

    if terminal:
        r2_delete(queue_key(job_id))
    else:
        retry = dict(queue)
        retry.update({"workerStatus": "pending", "leaseUntil": None, "lastError": message, "updatedAt": iso()})
        r2_put_json(queue_key(job_id), retry)


def process_job(job_id):
    job_id = normalize_job_id(job_id)
    key = queue_key(job_id)
    queue = r2_get_json(key, missing_ok=True)
    if queue is None:
        print(json.dumps({"jobId": job_id, "status": "not-found"}))
        return "not-found"

    validate_queue(queue, job_id)
    if not is_claimable(queue):
        print(json.dumps({"jobId": job_id, "status": "busy"}))
        return "busy"
    if int(queue.get("attempts") or 0) >= MAX_ATTEMPTS:
        print(json.dumps({"jobId": job_id, "status": "attempt-limit"}))
        return "attempt-limit"

    claimed = claim(job_id, queue)
    if claimed is None:
        return "attempt-limit"

    try:
        raw = r2_get_bytes(claimed["scriptKey"], missing_ok=False)
        script = raw.decode("utf-8").strip()
        if len(script) < 80:
            raise RuntimeError("Ebook audio script too short")

        with tempfile.TemporaryDirectory(prefix="ebook-reader-audio-") as temp_dir:
            work = Path(temp_dir)
            mp3, seconds, words, chunks = asyncio.run(synthesize(script, work))
            complete_job(job_id, claimed, mp3, seconds, words, chunks)

        print(
            json.dumps(
                {
                    "jobId": job_id,
                    "status": "ready",
                    "durationSeconds": round(seconds, 3),
                    "wordCount": len(words),
                    "chunkCount": chunks,
                },
                ensure_ascii=False,
            )
        )
        return "ready"
    except Exception as exc:
        fail_job(job_id, claimed, exc)
        print(json.dumps({"jobId": job_id, "status": "failed", "errorType": type(exc).__name__}))
        raise


def discover_jobs():
    rows = r2_list(QUEUE_PREFIX)
    jobs = []
    for row in sorted(rows, key=lambda value: str(value.get("last_modified") or "")):
        key = str(row.get("key") or "")
        match = re.fullmatch(re.escape(QUEUE_PREFIX) + r"(ebook-[a-f0-9]{32})\.json", key)
        if match:
            jobs.append(match.group(1))
        if len(jobs) >= MAX_JOBS_PER_RUN:
            break
    return jobs


def main():
    require_env()
    requested = os.environ.get("EBOOK_AUDIO_JOB_ID", "").strip()
    jobs = [normalize_job_id(requested)] if requested else discover_jobs()
    if not jobs:
        print(json.dumps({"status": "idle", "queuePrefix": QUEUE_PREFIX}))
        return 0

    failures = 0
    for job_id in jobs:
        try:
            process_job(job_id)
        except Exception:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
