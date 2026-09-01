#!/usr/bin/env python3
"""Low-latency VPS consumer for Ebook Reader TTS.

The VPS uses Runner3 Core's narrow internal Ebook Reader audio API. GitHub
Actions remains manual fallback only; it is not on the runtime queue path.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import ebook_reader_audio_tts_v2 as compat

base = compat.base
VERSION = "ebook-reader-audio-tts-v2-internal-api"
DEFAULT_ORIGIN = "https://runner3-core.ducduy2411.workers.dev"
ID_RE = re.compile(r"^ebook-[a-f0-9]{32}$")
MAX_JOB_FAILURES = 3


def env(name, default=""):
    return str(os.environ.get(name, default) or "").strip()


CORE_TOKEN = env("RUNNER3_CORE_TOKEN")
CORE_ORIGIN = env("RUNNER3_CORE_ORIGIN", DEFAULT_ORIGIN).rstrip("/")
POLL_SECONDS = max(0.5, float(env("EBOOK_AUDIO_POLL_SECONDS", "1") or "1"))
IDLE_MAX = max(POLL_SECONDS, float(env("EBOOK_AUDIO_IDLE_POLL_MAX_SECONDS", "3") or "3"))
AUTH_BACKOFF = max(30.0, float(env("EBOOK_AUDIO_AUTH_BACKOFF_SECONDS", "300") or "300"))
ERROR_MAX = max(POLL_SECONDS, float(env("EBOOK_AUDIO_ERROR_BACKOFF_MAX_SECONDS", "30") or "30"))
SOURCE = "ebook-reader-audio-tts-daemon-v2"


class CoreError(RuntimeError):
    def __init__(self, status, message):
        self.status = int(status or 0)
        super().__init__(message)


class JobError(RuntimeError):
    pass


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)


def safe_error(exc):
    return (str(exc).replace("\n", " ").replace("\r", " ").strip() or type(exc).__name__)[:500]


def core_request(method, path, body=None, content_type=None, timeout=90):
    if not CORE_TOKEN:
        raise CoreError(401, "RUNNER3_CORE_TOKEN missing")
    data = body.encode() if isinstance(body, str) else body
    cmd = [
        "curl", "-sS", "--max-time", str(int(timeout)), "-X", method,
        "-H", "Authorization: Bearer " + CORE_TOKEN,
        "-H", "X-Runner3-Source: " + SOURCE,
        "-H", "Accept: application/json,application/octet-stream,*/*",
    ]
    if content_type:
        cmd += ["-H", "Content-Type: " + content_type]
    if data is not None:
        cmd += ["--data-binary", "@-"]
    cmd += ["-w", "\n%{http_code}", CORE_ORIGIN + path]
    proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout + 5)
    if proc.returncode:
        raise CoreError(0, "curl failed: " + proc.stderr.decode("utf-8", "replace")[:300])
    payload, sep, code = proc.stdout.rpartition(b"\n")
    if not sep:
        raise CoreError(0, "core response missing status")
    try:
        status = int(code)
    except ValueError as exc:
        raise CoreError(0, "core response status invalid") from exc
    if status >= 400:
        raise CoreError(status, f"core {method} {path} -> {status}: " + payload.decode("utf-8", "replace")[:400])
    return payload


def core_json(method, path, value=None, timeout=90):
    body = None if value is None else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    payload = core_request(method, path, body, "application/json; charset=utf-8" if value is not None else None, timeout)
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise CoreError(0, f"invalid JSON from {method} {path}") from exc


def fetch_job():
    data = core_json("GET", "/api/internal/ebook-reader-audio/job", timeout=30)
    if not data.get("ok"):
        raise CoreError(0, "job endpoint returned ok=false")
    return data.get("job")


def validate_job(job):
    if not isinstance(job, dict):
        raise JobError("job payload is not an object")
    job_id = str(job.get("id") or "")
    if not ID_RE.fullmatch(job_id):
        raise JobError("invalid job id")
    if job.get("kind") != "ebook-reader":
        raise JobError("unsupported job kind")
    if job.get("audioVersion") != base.AUDIO_VERSION:
        raise JobError("audio version mismatch")
    if job.get("voice") != base.VOICE or job.get("voiceRate") != base.VOICE_RATE:
        raise JobError("voice contract mismatch")
    script = str(job.get("script") or "").strip()
    sha = str(job.get("textSha256") or "")
    if len(script) < 80:
        raise JobError("audio script too short")
    if not re.fullmatch(r"[a-f0-9]{64}", sha) or hashlib.sha256(script.encode()).hexdigest() != sha:
        raise JobError("audio script hash mismatch")
    return job_id, script


def publish(job_id, mp3, seconds, words, chunks):
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
    core_request("PUT", f"/api/internal/ebook-reader-audio/media?id={job_id}", mp3.read_bytes(), "audio/mpeg", 180)
    core_json("PUT", f"/api/internal/ebook-reader-audio/timing?id={job_id}", timing, 120)
    result = core_json("POST", "/api/internal/ebook-reader-audio/complete", {
        "id": job_id,
        "durationSeconds": round(seconds, 6),
        "wordCount": len(words),
        "speed": 1.03,
        "completedAt": base.iso(),
    })
    if not result.get("ok") or result.get("status") != "ready":
        raise CoreError(0, "complete endpoint did not return ready")


def report_fail(job_id, exc):
    try:
        core_json("POST", "/api/internal/ebook-reader-audio/fail", {
            "id": job_id,
            "error": safe_error(exc),
            "failedAt": base.iso(),
        }, 60)
    except Exception as report_error:
        emit({"event": "fail_report_error", "job_id": job_id, "error": safe_error(report_error)})


def process_one(failures):
    job = fetch_job()
    if not job:
        return {"ok": True, "processed": False, "status": "idle"}
    job_id = str(job.get("id") or "")
    try:
        job_id, script = validate_job(job)
        with tempfile.TemporaryDirectory(prefix="ebook-reader-audio-") as tmp:
            mp3, seconds, words, chunks = asyncio.run(base.synthesize(script, Path(tmp)))
            size = mp3.stat().st_size
            publish(job_id, mp3, seconds, words, chunks)
        failures.pop(job_id, None)
        return {"ok": True, "processed": True, "status": "ready", "job_id": job_id,
                "duration_seconds": round(seconds, 3), "word_count": len(words), "chunk_count": chunks, "bytes": size}
    except CoreError:
        raise
    except Exception as exc:
        count = failures.get(job_id, 0) + 1
        failures[job_id] = count
        emit({"event": "job_error", "job_id": job_id or None, "attempt": count, "error": safe_error(exc)})
        if ID_RE.fullmatch(job_id) and count >= MAX_JOB_FAILURES:
            report_fail(job_id, exc)
            failures.pop(job_id, None)
            return {"ok": False, "processed": True, "status": "failed", "job_id": job_id, "attempts": count}
        raise


def config_health():
    return {
        "ok": bool(CORE_TOKEN) and base.VOICE == "vi-VN-NamMinhNeural" and base.VOICE_RATE == "+3%",
        "version": VERSION,
        "core_token_present": bool(CORE_TOKEN),
        "origin": CORE_ORIGIN,
        "voice": base.VOICE,
        "voice_rate": base.VOICE_RATE,
        "poll_seconds": POLL_SECONDS,
        "ffmpeg_present": subprocess.run(["sh", "-c", "command -v ffmpeg >/dev/null"]).returncode == 0,
        "ffprobe_present": subprocess.run(["sh", "-c", "command -v ffprobe >/dev/null"]).returncode == 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-health", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.config_health:
        result = config_health(); emit(result); return 0 if result["ok"] else 2

    failures = {}
    if args.once:
        try:
            result = process_one(failures); emit(result); return 0 if result.get("ok") else 4
        except Exception as exc:
            emit({"ok": False, "error": safe_error(exc)}); return 5

    emit({"event": "daemon_start", "version": VERSION, "origin": CORE_ORIGIN, "poll_seconds": POLL_SECONDS})
    idle_count = error_count = 0
    while True:
        try:
            result = process_one(failures)
            if result.get("processed"):
                emit(result); idle_count = error_count = 0; continue
            idle_count += 1; error_count = 0
            delay = min(IDLE_MAX, POLL_SECONDS * (1 + min(idle_count, 4) / 2))
        except CoreError as exc:
            emit({"event": "core_error", "status": exc.status, "error": safe_error(exc)})
            idle_count = 0; error_count += 1
            delay = AUTH_BACKOFF if exc.status in (401, 403) else min(ERROR_MAX, POLL_SECONDS * (2 ** min(error_count, 4)))
        except Exception as exc:
            emit({"event": "worker_error", "error": safe_error(exc)})
            idle_count = 0; error_count += 1
            delay = min(ERROR_MAX, POLL_SECONDS * (2 ** min(error_count, 4)))
        time.sleep(delay)


if __name__ == "__main__":
    sys.exit(main())
