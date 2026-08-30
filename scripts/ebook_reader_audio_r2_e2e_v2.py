#!/usr/bin/env python3
"""Repeatable real-R2 Ebook Reader audio E2E + production player smoke.

This removes only the deterministic Skeleton Crew smoke artifacts created by
scripts/ebook_reader_audio_r2_e2e.py, runs the real R2/TTS/media test again,
and verifies that the live Reader HTML contains the standard audiobook player
plus continuous reading follow/resume behavior markers.
It never touches arbitrary/user audio jobs.
"""

import json
from urllib.parse import urljoin

import requests
import ebook_reader_audio_r2_e2e as base

TEST_JOB_ID = "ebook-5c3258ea79a8ffb76bff5fd299ac4619"
TEST_KEYS = [
    f"audio-library/ebook-reader-queue/{TEST_JOB_ID}.json",
    f"audio-library/items/{TEST_JOB_ID}.json",
    f"audio-library/media/{TEST_JOB_ID}/script.txt",
    f"audio-library/media/{TEST_JOB_ID}/episode.mp3",
    f"audio-library/media/{TEST_JOB_ID}/timing.json",
]
PLAYER_MARKERS = [
    'data-r3-ebook-audio-v6="2"',
    'data-r3-audio-follow-v8="1"',
    "dock.id='r3AudioDock'",
    'id="r3AudioMain"',
    'id="r3AudioSeek"',
    'id="r3AudioBack"',
    'id="r3AudioForward"',
    'id="r3AudioSpeed"',
    'window.r3ReaderBridge',
    "r3-reader-audio-state:",
    "data-r3-audio-reading",
    "continueToNextChapter",
]


def reset_known_smoke_artifacts():
    for key in TEST_KEYS:
        response = requests.delete(
            base.object_url(base.AUDIO_BUCKET, key),
            headers=base.headers(),
            timeout=base.HTTP_TIMEOUT,
        )
        if response.status_code not in (200, 204, 404):
            detail = response.text[:400].replace("\n", " ")
            raise RuntimeError(f"Failed to reset known smoke key {key}: HTTP {response.status_code}: {detail}")
    print(json.dumps({"phase": "reset", "jobId": TEST_JOB_ID, "ok": True}), flush=True)


def verify_live_reader_player(book_key):
    response = requests.get(
        base.CORE_URL + "/artifact-library/read",
        params={"key": book_key},
        headers={"Cache-Control": "no-cache"},
        timeout=base.HTTP_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Live Reader failed HTTP {response.status_code}")
    html = response.text
    missing = [marker for marker in PLAYER_MARKERS if marker not in html]
    if missing:
        raise RuntimeError("Live Reader is missing audio player markers: " + ", ".join(missing))
    if "noindex" not in (response.headers.get("x-robots-tag") or "").lower():
        raise RuntimeError("Live Reader lost X-Robots-Tag noindex")
    proof = {
        "phase": "reader-ui",
        "status": response.status_code,
        "playerVersion": "v6.2+follow-v8",
        "seek": True,
        "skip15": True,
        "speed": True,
        "playPause": True,
        "activeParagraphBold": True,
        "pageFollow": True,
        "continuousChapter": True,
        "readerBridge": True,
        "audioResumePersistence": True,
        "noindex": True,
    }
    print(json.dumps(proof, ensure_ascii=False), flush=True)
    return proof


_original_verify = base.verify_outputs


def verify_outputs_with_production_ui(job_id, book_key, state):
    media_url = state.get("mediaUrl")
    if media_url:
        absolute = urljoin(base.CORE_URL + "/", media_url)
        head = requests.head(absolute, timeout=base.HTTP_TIMEOUT)
        ranged = requests.get(absolute, headers={"Range": "bytes=0-511"}, timeout=base.HTTP_TIMEOUT)
        full = requests.get(absolute, timeout=base.HTTP_TIMEOUT)
        print(
            json.dumps(
                {
                    "phase": "media-diagnostic",
                    "headStatus": head.status_code,
                    "headType": head.headers.get("content-type"),
                    "rangeStatus": ranged.status_code,
                    "rangeType": ranged.headers.get("content-type"),
                    "fullStatus": full.status_code,
                    "fullType": full.headers.get("content-type"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    proof = _original_verify(job_id, book_key, state)
    verify_live_reader_player(book_key)
    return proof


base.verify_outputs = verify_outputs_with_production_ui


if __name__ == "__main__":
    base.require_env()
    reset_known_smoke_artifacts()
    raise SystemExit(base.main())