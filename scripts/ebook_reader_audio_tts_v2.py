#!/usr/bin/env python3
"""Compatibility wrapper for Ebook Reader TTS with explicit WordBoundary timing.

edge-tts 7.2+ changed Communicate's default metadata boundary to SentenceBoundary.
The base worker expects WordBoundary events, so this wrapper pins WordBoundary
explicitly without duplicating the queue/R2/idempotency implementation.

Microsoft's consumer Edge TTS websocket can intermittently reject or fail a
handshake. Retry those transport-level failures inside one queue attempt so a
short service/network incident does not burn the job's durable retry budget.
"""

import asyncio

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

if __name__ == "__main__":
    raise SystemExit(base.main())
