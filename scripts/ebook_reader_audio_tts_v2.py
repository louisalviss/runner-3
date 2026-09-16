#!/usr/bin/env python3
"""Compatibility wrapper for Ebook Reader TTS with explicit WordBoundary timing.

edge-tts 7.2+ changed Communicate's default metadata boundary to SentenceBoundary.
The base worker expects WordBoundary events, so this wrapper pins WordBoundary
explicitly without duplicating the queue/R2/idempotency implementation.

Microsoft's consumer Edge TTS websocket can intermittently reject or fail a
handshake. Retry those transport-level failures inside one queue attempt so a
short service/network incident does not burn the job's durable retry budget.

The wrapper also supports an optional bounded on-disk segment cache. Identical
text/voice/rate segments can reuse their MP3 bytes plus WordBoundary metadata
across retries and later jobs without changing the final episode.mp3 contract.
"""

import asyncio
import hashlib
import json
import os
import shutil
import threading
from pathlib import Path

import aiohttp
import edge_tts
import ebook_reader_audio_tts as base

base.TIMING_VERSION = "ebook-reader-timing-v2"

CACHE_SCHEMA = "ebook-reader-segment-cache-v1"
CACHE_DIR_RAW = os.environ.get("EBOOK_AUDIO_TTS_SEGMENT_CACHE_DIR", "").strip()
CACHE_DIR = Path(CACHE_DIR_RAW) if CACHE_DIR_RAW else None
try:
    CACHE_MAX_BYTES = max(0, min(int(os.environ.get("EBOOK_AUDIO_TTS_SEGMENT_CACHE_MAX_BYTES", str(128 * 1024 * 1024))), 1024 * 1024 * 1024))
except (TypeError, ValueError):
    CACHE_MAX_BYTES = 128 * 1024 * 1024
CACHE_LOCK = threading.Lock()


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_key(text):
    engine = getattr(edge_tts, "__version__", "unknown")
    payload = "\0".join((
        CACHE_SCHEMA,
        str(base.AUDIO_VERSION),
        str(base.TIMING_VERSION),
        str(base.VOICE),
        str(base.VOICE_RATE),
        str(engine),
        str(text),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_paths(key):
    return CACHE_DIR / f"{key}.mp3", CACHE_DIR / f"{key}.json"


def _valid_boundaries(value):
    if not isinstance(value, list) or not value:
        return False
    for event in value:
        if not isinstance(event, dict) or not str(event.get("text") or ""):
            return False
        try:
            float(event.get("offsetMs"))
            float(event.get("durationMs"))
        except (TypeError, ValueError):
            return False
    return True


def _load_cached_segment(text, path):
    if CACHE_DIR is None or CACHE_MAX_BYTES <= 0:
        return None
    key = _cache_key(text)
    media_path, meta_path = _cache_paths(key)
    with CACHE_LOCK:
        try:
            if not media_path.is_file() or media_path.stat().st_size < 1500 or not meta_path.is_file():
                return None
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            boundaries = meta.get("boundaries")
            if meta.get("schema") != CACHE_SCHEMA or meta.get("key") != key or not _valid_boundaries(boundaries):
                return None
            if int(meta.get("bytes") or 0) != media_path.stat().st_size:
                return None
            if str(meta.get("sha256") or "") != _file_sha256(media_path):
                return None
            shutil.copyfile(media_path, path)
            now = None
            os.utime(media_path, now)
            os.utime(meta_path, now)
            print(f"EBOOK_TTS_SEGMENT_CACHE_HIT key={key[:12]} bytes={media_path.stat().st_size}")
            return boundaries
        except (OSError, ValueError, json.JSONDecodeError):
            return None


def _prune_cache_locked():
    if CACHE_DIR is None or CACHE_MAX_BYTES <= 0 or not CACHE_DIR.exists():
        return
    entries = []
    total = 0
    for media_path in CACHE_DIR.glob("*.mp3"):
        try:
            stat = media_path.stat()
        except OSError:
            continue
        total += stat.st_size
        entries.append((stat.st_mtime, stat.st_size, media_path))
    for _mtime, size, media_path in sorted(entries):
        if total <= CACHE_MAX_BYTES:
            break
        try:
            media_path.unlink(missing_ok=True)
            media_path.with_suffix(".json").unlink(missing_ok=True)
            total -= size
        except OSError:
            pass


def _store_cached_segment(text, path, boundaries):
    if CACHE_DIR is None or CACHE_MAX_BYTES <= 0 or not _valid_boundaries(boundaries):
        return
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError:
        return
    if size < 1500 or size > CACHE_MAX_BYTES:
        return
    key = _cache_key(text)
    media_path, meta_path = _cache_paths(key)
    token = f"{os.getpid()}-{threading.get_ident()}"
    temp_media = media_path.with_name(f".{media_path.name}.{token}.tmp")
    temp_meta = meta_path.with_name(f".{meta_path.name}.{token}.tmp")
    with CACHE_LOCK:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, temp_media)
            sha256 = _file_sha256(temp_media)
            temp_meta.write_text(
                json.dumps(
                    {
                        "schema": CACHE_SCHEMA,
                        "key": key,
                        "bytes": size,
                        "sha256": sha256,
                        "boundaries": boundaries,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            os.replace(temp_media, media_path)
            os.replace(temp_meta, meta_path)
            _prune_cache_locked()
        except OSError:
            pass
        finally:
            temp_media.unlink(missing_ok=True)
            temp_meta.unlink(missing_ok=True)


async def synthesize_part_word_boundary(text, path):
    cached = _load_cached_segment(text, path)
    if cached is not None:
        return cached

    delays = (0, 3, 8, 20)
    last_error = None

    for attempt, delay in enumerate(delays, start=1):
        if delay:
            await asyncio.sleep(delay)
        boundaries = []
        try:
            communicate = edge_tts.Communicate(
                text,
                base.VOICE,
                rate=base.VOICE_RATE,
                boundary="WordBoundary",
            )
            with path.open("wb") as handle:
                async for chunk in communicate.stream():
                    kind = chunk.get("type")
                    if kind == "audio":
                        handle.write(chunk["data"])
                    elif kind == "WordBoundary":
                        boundaries.append(
                            {
                                "text": str(chunk.get("text") or ""),
                                "offsetMs": float(chunk.get("offset") or 0) / 10_000.0,
                                "durationMs": float(chunk.get("duration") or 0) / 10_000.0,
                            }
                        )
            if not path.exists() or path.stat().st_size < 1500:
                raise RuntimeError("Edge TTS produced an invalid audio part")
            if not boundaries:
                raise RuntimeError("Edge TTS produced no WordBoundary timing")
            _store_cached_segment(text, path, boundaries)
            if attempt > 1:
                print(f"EDGE_TTS_TRANSPORT_RECOVERED attempt={attempt}")
            return boundaries
        except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
            last_error = exc
            print(
                f"EDGE_TTS_TRANSPORT_RETRY attempt={attempt}/{len(delays)} "
                f"error={type(exc).__name__} status={getattr(exc, 'status', '')}"
            )
            if attempt >= len(delays):
                raise

    raise last_error or RuntimeError("Edge TTS transport failed")


base.synthesize_part = synthesize_part_word_boundary


def main():
    base.require_env()
    requested = os.environ.get("EBOOK_AUDIO_JOB_ID", "").strip()
    pending = [base.normalize_job_id(requested)] if requested else []
    processed = set()
    failures = 0

    while len(processed) < base.MAX_JOBS_PER_RUN:
        if not pending:
            pending = [job_id for job_id in base.discover_jobs() if job_id not in processed]
            if not pending:
                break

        job_id = pending.pop(0)
        if job_id in processed:
            continue
        processed.add(job_id)

        try:
            base.process_job(job_id)
        except Exception as exc:
            failures += 1
            print(
                json.dumps(
                    {"jobId": job_id, "status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            )

    if not processed:
        print(json.dumps({"status": "idle", "queuePrefix": base.QUEUE_PREFIX}))
    else:
        print(
            json.dumps(
                {
                    "status": "complete" if not failures else "partial-error",
                    "processedJobs": len(processed),
                    "failures": failures,
                }
            )
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
