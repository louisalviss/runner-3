#!/usr/bin/env python3
"""Repeatable R2 E2E harness for the known test job produced by v1 smoke.

This removes only the deterministic Skeleton Crew smoke artifacts created by
scripts/ebook_reader_audio_r2_e2e.py, then executes that real-R2 test again.
It never touches arbitrary/user audio jobs.
"""

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
    print(f'{{"phase":"reset","jobId":"{TEST_JOB_ID}","ok":true}}', flush=True)


_original_verify = base.verify_outputs


def verify_outputs_with_diagnostics(job_id, book_key, state):
    media_url = state.get("mediaUrl")
    if media_url:
        absolute = urljoin(base.CORE_URL + "/", media_url)
        head = requests.head(absolute, timeout=base.HTTP_TIMEOUT)
        ranged = requests.get(absolute, headers={"Range": "bytes=0-511"}, timeout=base.HTTP_TIMEOUT)
        full = requests.get(absolute, timeout=base.HTTP_TIMEOUT)
        print(
            {
                "phase": "media-diagnostic",
                "headStatus": head.status_code,
                "headType": head.headers.get("content-type"),
                "rangeStatus": ranged.status_code,
                "rangeType": ranged.headers.get("content-type"),
                "rangeBody": ranged.text[:300] if "json" in (ranged.headers.get("content-type") or "") else "<binary-or-empty>",
                "fullStatus": full.status_code,
                "fullType": full.headers.get("content-type"),
                "fullBody": full.text[:300] if "json" in (full.headers.get("content-type") or "") else "<binary-or-empty>",
            },
            flush=True,
        )
    return _original_verify(job_id, book_key, state)


base.verify_outputs = verify_outputs_with_diagnostics


if __name__ == "__main__":
    base.require_env()
    reset_known_smoke_artifacts()
    raise SystemExit(base.main())
