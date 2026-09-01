#!/usr/bin/env python3
"""Compatibility wrapper for Ebook Reader TTS with explicit WordBoundary timing.

edge-tts 7.2+ changed Communicate's default metadata boundary to SentenceBoundary.
The base worker expects WordBoundary events, so this wrapper pins WordBoundary
explicitly without duplicating the queue/R2/idempotency implementation.

Microsoft's consumer Edge TTS websocket can intermittently reject or fail a
handshake. Retry those transport-level failures inside one queue attempt so a
short service/network incident does not burn the job's durable retry budget.

The wrapper also re-discovers the durable queue after each processed batch.
That closes the gap where an Ebook Reader auto-next request can be queued while
a workflow run is already active: the same run can now pick it up instead of
waiting for the next scheduled scan.
"""

import asyncio
import json
import os

import aiohttp
import edge_tts
import ebook_reader_audio_tts as base

base.TIMING_VERSION = "ebook-reader-timing-v2"


async def synthesize_part_word_boundary(text, path):
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
