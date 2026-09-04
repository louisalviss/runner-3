#!/usr/bin/env python3
"""Persistent Ebook Reader TTS consumer for the Linveo VPS.

Uses Runner3 Core's authenticated internal Ebook Reader audio API, so the VPS
never needs direct Cloudflare/R2 credentials. The existing synthesis/timing
implementation remains canonical in ebook_reader_audio_tts[_v2].py.
"""

import argparse
import asyncio
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ebook_reader_audio_tts_v2 as timing_worker

base = timing_worker.base

CORE_URL = os.environ.get("RUNNER3_CORE_URL", "https://runner3-core.ducduy2411.workers.dev").rstrip("/")
TOKEN_FILE = os.environ.get("EBOOK_AUDIO_VPS_TOKEN_FILE", "").strip()
FILE_TOKEN = Path(TOKEN_FILE).read_text(encoding="utf-8").rstrip("\r\n") if TOKEN_FILE else ""
CORE_TOKEN = (
    FILE_TOKEN
    or os.environ.get("EBOOK_AUDIO_VPS_TOKEN", "").strip()
    or os.environ.get("RUNNER3_CORE_TOKEN", "").strip()
)
SOURCE = os.environ.get("RUNNER3_SOURCE", "linveo-vps1").strip() or "linveo-vps1"
POLL_SECONDS = max(0.25, min(float(os.environ.get("EBOOK_AUDIO_VPS_POLL_SECONDS", "1")), 30.0))
IDLE_HEARTBEAT_SECONDS = max(10.0, min(float(os.environ.get("EBOOK_AUDIO_VPS_HEARTBEAT_SECONDS", "30")), 300.0))
LOCK_PATH = os.environ.get("EBOOK_AUDIO_VPS_LOCK", "/run/ebook-reader-audio-consumer.lock")
WORKER_NAME = os.environ.get("EBOOK_AUDIO_VPS_WORKER", "linveo-vps1-ebook-audio").strip() or "linveo-vps1-ebook-audio"
try:
    MAX_CONCURRENCY = max(1, min(int(os.environ.get("EBOOK_AUDIO_VPS_CONCURRENCY", "2")), 4))
except (TypeError, ValueError):
    MAX_CONCURRENCY = 2
try:
    TTS_CHUNK_CONCURRENCY = max(1, min(int(os.environ.get("EBOOK_AUDIO_TTS_CHUNK_CONCURRENCY", "2")), 3))
except (TypeError, ValueError):
    TTS_CHUNK_CONCURRENCY = 2

STOP = False


def now_iso():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def headers(content_type=None):
    if not CORE_TOKEN:
        raise RuntimeError("Ebook audio Core token is required")
    out = {
        "Authorization": f"Bearer {CORE_TOKEN}",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": "runner3-ebook-audio-vps/1.0",
        "X-Runner3-Source": SOURCE,
        "X-Ebook-Audio-Worker": WORKER_NAME,
    }
    if content_type:
        out["Content-Type"] = content_type
    return out


def request_json(method, path, payload=None, timeout=60):
    data = None
    req_headers = headers("application/json" if payload is not None else None)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(CORE_URL + path, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body}") from exc


def put_bytes(path, payload, content_type, timeout=180):
    req_headers = headers(content_type)
    req_headers["Content-Length"] = str(len(payload))
    req = urllib.request.Request(CORE_URL + path, data=payload, headers=req_headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"PUT {path} -> HTTP {exc.code}: {body}") from exc


def report_state(status, detail):
    try:
        return request_json(
            "PUT",
            "/state/ebook-audio-vps-consumer",
            {
                "status": status,
                "run_id": WORKER_NAME,
                "detail": {**detail, "worker": WORKER_NAME, "reportedAt": now_iso()},
            },
            timeout=15,
        )
    except Exception as exc:
        print(json.dumps({"event": "heartbeat-error", "error": str(exc)[:500]}, ensure_ascii=False), flush=True)
        return None


def acquire_process_lock():
    path = Path(LOCK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another ebook audio consumer already owns the VPS lock") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()} worker={WORKER_NAME} started={now_iso()}\n")
    handle.flush()
    return handle


def claim_next_job():
    payload = request_json("GET", "/api/internal/ebook-reader-audio/job", timeout=30)
    if payload.get("ok") is not True:
        raise RuntimeError(f"job claim failed: {payload}")
    job = payload.get("job")
    return job if isinstance(job, dict) else None


def publish_failure(job_id, exc):
    error = f"{type(exc).__name__}: {exc}"[:800]
    try:
        request_json(
            "POST",
            "/api/internal/ebook-reader-audio/fail",
            {"id": job_id, "error": error, "failedAt": now_iso()},
            timeout=30,
        )
    except Exception as publish_exc:
        print(
            json.dumps(
                {"event": "failure-publish-error", "jobId": job_id, "error": str(publish_exc)[:500]},
                ensure_ascii=False,
            ),
            flush=True,
        )


async def synthesize_parallel(script, work):
    """Synthesize independent TTS chunks concurrently, preserving order and timing."""
    chunks = base.tts_chunks(script)
    if not chunks:
        raise RuntimeError("Empty Ebook audio script")
    if len(chunks) == 1 or TTS_CHUNK_CONCURRENCY <= 1:
        return await base.synthesize(script, work)

    semaphore = asyncio.Semaphore(TTS_CHUNK_CONCURRENCY)

    async def render(index, text):
        part = work / f"part-{index:04d}.mp3"
        async with semaphore:
            boundaries = await base.synthesize_part(text, part)
        seconds = base.media_duration(part)
        return index, part, seconds, boundaries

    rendered = await asyncio.gather(*(render(index, text) for index, text in enumerate(chunks)))
    rendered.sort(key=lambda row: row[0])

    parts = []
    words = []
    base_ms = 0.0
    for _index, part, part_seconds, boundaries in rendered:
        for event in boundaries:
            start_ms = base_ms + event["offsetMs"]
            duration_ms = max(0.0, event["durationMs"])
            words.append({
                "text": event["text"],
                "startMs": round(start_ms, 3),
                "durationMs": round(duration_ms, 3),
                "endMs": round(start_ms + duration_ms, 3),
            })
        base_ms += part_seconds * 1000.0
        parts.append(part)

    concat_file = work / "concat.txt"
    concat_file.write_text("".join(f"file '{part.resolve()}'\n" for part in parts), encoding="utf-8")
    output = work / "episode.mp3"
    subprocess.check_call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(output),
    ])
    output_seconds = base.media_duration(output)
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


def process_job(job):
    job_id = base.normalize_job_id(job.get("id"))
    script = str(job.get("script") or "").strip()
    if len(script) < 80:
        raise RuntimeError("Ebook audio script too short")

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ebook-reader-audio-vps-") as temp_dir:
        work = Path(temp_dir)
        mp3, seconds, words, chunks = asyncio.run(synthesize_parallel(script, work))
        timing = {
            "version": base.TIMING_VERSION,
            "id": job_id,
            "audioVersion": base.AUDIO_VERSION,
            "voice": base.VOICE,
            "voiceRate": base.VOICE_RATE,
            "durationSeconds": round(seconds, 6),
            "wordCount": len(words),
            "chunkCount": chunks,
            "words": words,
        }
        media_payload = mp3.read_bytes()
        put_bytes(
            f"/api/internal/ebook-reader-audio/media?id={job_id}",
            media_payload,
            "audio/mpeg",
            timeout=300,
        )
        request_json(
            "PUT",
            f"/api/internal/ebook-reader-audio/timing?id={job_id}",
            timing,
            timeout=180,
        )
        complete = request_json(
            "POST",
            "/api/internal/ebook-reader-audio/complete",
            {
                "id": job_id,
                "durationSeconds": round(seconds, 6),
                "wordCount": len(words),
                "speed": 1.03,
                "completedAt": now_iso(),
            },
            timeout=60,
        )
        if complete.get("ok") is not True or complete.get("status") != "ready":
            raise RuntimeError(f"complete rejected: {complete}")

    elapsed = round(time.monotonic() - started, 3)
    result = {
        "event": "job-ready",
        "jobId": job_id,
        "durationSeconds": round(seconds, 3),
        "wordCount": len(words),
        "chunkCount": chunks,
        "chunkConcurrency": TTS_CHUNK_CONCURRENCY,
        "renderSeconds": elapsed,
        "status": "ready",
    }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def handle_signal(signum, _frame):
    global STOP
    STOP = True
    print(json.dumps({"event": "signal", "signal": signum}), flush=True)


def run_once():
    job = claim_next_job()
    if not job:
        return {"status": "idle", "worker": WORKER_NAME}
    job_id = str(job.get("id") or "")
    try:
        return process_job(job)
    except Exception as exc:
        publish_failure(job_id, exc)
        raise


def daemon_loop():
    processed = 0
    failures = 0
    last_heartbeat = 0.0
    active = {}
    print(
        json.dumps(
            {
                "event": "consumer-start",
                "worker": WORKER_NAME,
                "pollSeconds": POLL_SECONDS,
                "concurrency": MAX_CONCURRENCY,
                "chunkConcurrency": TTS_CHUNK_CONCURRENCY,
                "pid": os.getpid(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    report_state("active", {"phase": "start", "processed": processed, "failures": failures, "active": 0, "concurrency": MAX_CONCURRENCY})
    last_heartbeat = time.monotonic()

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY, thread_name_prefix="ebook-audio") as pool:
        while not STOP or active:
            completed = [future for future in active if future.done()]
            for future in completed:
                job_id = active.pop(future)
                try:
                    future.result()
                    processed += 1
                    report_state("active", {"phase": "ready", "jobId": job_id, "processed": processed, "failures": failures, "active": len(active), "concurrency": MAX_CONCURRENCY})
                except Exception as exc:
                    failures += 1
                    publish_failure(job_id, exc)
                    print(
                        json.dumps(
                            {"event": "job-error", "jobId": job_id, "error": f"{type(exc).__name__}: {exc}"[:800]},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    report_state("degraded", {"phase": "job-error", "jobId": job_id, "processed": processed, "failures": failures, "active": len(active), "concurrency": MAX_CONCURRENCY})
                last_heartbeat = time.monotonic()

            claimed = False
            if not STOP:
                try:
                    while len(active) < MAX_CONCURRENCY:
                        job = claim_next_job()
                        if not job:
                            break
                        job_id = str(job.get("id") or "")
                        future = pool.submit(process_job, job)
                        active[future] = job_id
                        claimed = True
                        print(json.dumps({"event": "job-start", "jobId": job_id, "active": len(active), "concurrency": MAX_CONCURRENCY}, ensure_ascii=False), flush=True)
                except Exception as exc:
                    failures += 1
                    print(json.dumps({"event": "poll-error", "error": f"{type(exc).__name__}: {exc}"[:800]}, ensure_ascii=False), flush=True)
                    report_state("degraded", {"phase": "poll-error", "processed": processed, "failures": failures, "active": len(active), "concurrency": MAX_CONCURRENCY})
                    last_heartbeat = time.monotonic()
                    time.sleep(min(10.0, max(POLL_SECONDS, 2.0)))
                    continue

            now = time.monotonic()
            if now - last_heartbeat >= IDLE_HEARTBEAT_SECONDS:
                report_state("active", {"phase": "busy" if active else "idle", "processed": processed, "failures": failures, "active": len(active), "concurrency": MAX_CONCURRENCY})
                last_heartbeat = now
            if not claimed and not completed:
                time.sleep(min(POLL_SECONDS, 0.5) if active else POLL_SECONDS)

    report_state("stopped", {"phase": "shutdown", "processed": processed, "failures": failures, "active": 0, "concurrency": MAX_CONCURRENCY})
    print(json.dumps({"event": "consumer-stop", "processed": processed, "failures": failures, "concurrency": MAX_CONCURRENCY}, ensure_ascii=False), flush=True)
    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Claim and process at most one job, then exit")
    parser.add_argument("--check-config", action="store_true", help="Validate runtime configuration without claiming a job")
    args = parser.parse_args()

    if not CORE_TOKEN:
        raise RuntimeError("Ebook audio Core token is required")
    if not CORE_URL.startswith("https://"):
        raise RuntimeError("RUNNER3_CORE_URL must be HTTPS")
    if args.check_config:
        print(json.dumps({"ok": True, "coreUrl": CORE_URL, "worker": WORKER_NAME, "pollSeconds": POLL_SECONDS, "concurrency": MAX_CONCURRENCY}, ensure_ascii=False))
        return 0

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    lock = acquire_process_lock()
    try:
        if args.once:
            result = run_once()
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return 0
        return daemon_loop()
    finally:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
