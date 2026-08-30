#!/usr/bin/env python3
"""Real Ebook Reader audio E2E smoke using a final EPUB already stored in R2.

Flow:
R2 final EPUB -> extract a real spine sample -> live /artifact-library/audio POST
-> repository_dispatch/GitHub TTS worker -> R2 MP3 + timing -> live media/timing verify.
"""

import io
import json
import os
import posixpath
import re
import time
import zipfile
from html.parser import HTMLParser
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET

import requests

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
SOURCE_BUCKET = os.environ.get("EBOOK_SOURCE_BUCKET", "runner3-artifacts").strip()
AUDIO_BUCKET = os.environ.get("EBOOK_AUDIO_BUCKET", "runner3-wp-media").strip()
CORE_URL = os.environ.get("RUNNER3_CORE_URL", "https://runner3-core.ducduy2411.workers.dev").rstrip("/")
HTTP_TIMEOUT = 90
POLL_SECONDS = 2
MAX_WAIT_SECONDS = 12 * 60
SAMPLE_MAX_CHARS = 3600


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.heading = ""
        self._skip = 0
        self._heading_tag = None
        self._heading_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "svg"}:
            self._skip += 1
        if tag in {"h1", "h2", "h3"} and not self.heading and not self._skip:
            self._heading_tag = tag
            self._heading_parts = []
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "blockquote"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "svg"} and self._skip:
            self._skip -= 1
        if self._heading_tag == tag:
            candidate = " ".join(self._heading_parts)
            candidate = re.sub(r"\s+", " ", candidate).strip()
            if candidate:
                self.heading = candidate[:240]
            self._heading_tag = None
            self._heading_parts = []
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        value = str(data or "")
        if self._heading_tag:
            self._heading_parts.append(value)
        self.parts.append(value)

    def text(self):
        value = "".join(self.parts).replace("\u00a0", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def require_env():
    missing = [name for name, value in {
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
        "CLOUDFLARE_API_TOKEN": API_TOKEN,
        "EBOOK_SOURCE_BUCKET": SOURCE_BUCKET,
        "EBOOK_AUDIO_BUCKET": AUDIO_BUCKET,
    }.items() if not value]
    if missing:
        raise RuntimeError("Missing environment: " + ", ".join(missing))


def headers(content_type=None):
    result = {"Authorization": f"Bearer {API_TOKEN}"}
    if content_type:
        result["Content-Type"] = content_type
    return result


def object_url(bucket, key=None):
    base = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/buckets/{quote(bucket, safe='')}/objects"
    return base if key is None else base + "/" + quote(str(key), safe="/")


def checked(response, label):
    if 200 <= response.status_code < 300:
        return response
    detail = response.text[:700].replace("\n", " ")
    raise RuntimeError(f"{label} failed HTTP {response.status_code}: {detail}")


def r2_list(bucket, prefix):
    rows = []
    cursor = None
    while True:
        params = {"prefix": prefix, "per_page": 1000}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(object_url(bucket), headers=headers(), params=params, timeout=HTTP_TIMEOUT)
        payload = checked(response, f"R2 LIST {bucket}/{prefix}").json()
        if not payload.get("success", False):
            raise RuntimeError(f"R2 LIST {bucket}/{prefix} returned success=false")
        rows.extend(payload.get("result") or [])
        info = payload.get("result_info") or {}
        if not info.get("is_truncated"):
            break
        cursor = info.get("cursor")
        if not cursor:
            break
    return rows


def r2_get(bucket, key):
    response = requests.get(object_url(bucket, key), headers=headers(), timeout=HTTP_TIMEOUT)
    return checked(response, f"R2 GET {bucket}/{key}").content


def choose_final_epub():
    rows = r2_list(SOURCE_BUCKET, "core/ebook/")
    candidates = []
    for row in rows:
        key = str(row.get("key") or "")
        lower = key.lower()
        if key.startswith("core/ebook/") and "/final/" in lower and lower.endswith(".epub"):
            stamp = str(row.get("last_modified") or row.get("uploaded") or "")
            candidates.append((stamp, key))
    if not candidates:
        raise RuntimeError("No final EPUB found in R2 core/ebook/*/final/*.epub")
    candidates.sort()
    return candidates[-1][1], len(candidates)


def xml_local(tag):
    return str(tag).split("}")[-1]


def resolve_epub(epub_bytes):
    with zipfile.ZipFile(io.BytesIO(epub_bytes)) as archive:
        names = set(archive.namelist())
        if "META-INF/container.xml" in names:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next((node.attrib.get("full-path") for node in container.iter() if xml_local(node.tag) == "rootfile" and node.attrib.get("full-path")), None)
        else:
            rootfile = None
        if not rootfile:
            rootfile = next((name for name in archive.namelist() if name.lower().endswith(".opf")), None)
        if not rootfile or rootfile not in names:
            raise RuntimeError("EPUB OPF not found")

        opf = ET.fromstring(archive.read(rootfile))
        title = next((str(node.text or "").strip() for node in opf.iter() if xml_local(node.tag) == "title" and str(node.text or "").strip()), "Ebook")
        manifest = {}
        for node in opf.iter():
            if xml_local(node.tag) != "item":
                continue
            item_id = node.attrib.get("id")
            href = node.attrib.get("href")
            if item_id and href:
                manifest[item_id] = {"href": href, "media": node.attrib.get("media-type", "")}
        spine = [node.attrib.get("idref") for node in opf.iter() if xml_local(node.tag) == "itemref" and node.attrib.get("idref")]
        base = posixpath.dirname(rootfile)

        for idref in spine:
            item = manifest.get(idref) or {}
            href = str(item.get("href") or "").split("#", 1)[0]
            media = str(item.get("media") or "").lower()
            if not href or not ("html" in media or href.lower().endswith((".xhtml", ".html", ".htm"))):
                continue
            path = posixpath.normpath(posixpath.join(base, href))
            if path not in names:
                continue
            raw = archive.read(path)
            text = raw.decode("utf-8", errors="ignore")
            parser = TextExtractor()
            parser.feed(text)
            clean = parser.text()
            if len(clean) < 300:
                continue
            sample = clean[:SAMPLE_MAX_CHARS]
            if len(clean) > SAMPLE_MAX_CHARS:
                cut = max(sample.rfind(". "), sample.rfind("! "), sample.rfind("? "), sample.rfind("… "))
                if cut >= 1800:
                    sample = sample[:cut + 1]
            sample = sample.strip()
            if len(sample) < 300:
                continue
            chapter_title = parser.heading or posixpath.basename(path)
            return {
                "bookTitle": title[:240],
                "chapterTitle": chapter_title[:240],
                "chapterHref": path[:600],
                "text": sample,
                "sampleChars": len(sample),
            }
    raise RuntimeError("No readable spine chapter found in EPUB")


def post_audio(book_key, chapter):
    response = requests.post(
        CORE_URL + "/artifact-library/audio",
        json={
            "bookKey": book_key,
            "text": chapter["text"],
            "chapterTitle": chapter["chapterTitle"],
            "chapterHref": chapter["chapterHref"],
            "bookTitle": chapter["bookTitle"],
            "clientVersion": "ebook-reader-audio-r2-e2e-v1",
        },
        timeout=HTTP_TIMEOUT,
    )
    data = response.json() if "json" in response.headers.get("content-type", "") else {}
    if response.status_code not in (200, 202):
        raise RuntimeError(f"Live audio POST failed HTTP {response.status_code}: {str(data)[:600]}")
    job_id = str(data.get("id") or "")
    if not re.fullmatch(r"ebook-[a-f0-9]{32}", job_id):
        raise RuntimeError("Live audio POST returned invalid id")
    return job_id, data


def poll_ready(job_id, book_key, initial):
    state = initial
    deadline = time.time() + MAX_WAIT_SECONDS
    while time.time() < deadline:
        if state.get("status") == "ready":
            return state
        if state.get("status") == "error":
            raise RuntimeError("Audio worker returned error: " + str(state.get("error") or "unknown"))
        time.sleep(POLL_SECONDS)
        response = requests.get(
            CORE_URL + "/artifact-library/audio",
            params={"id": job_id, "bookKey": book_key},
            headers={"Cache-Control": "no-cache"},
            timeout=HTTP_TIMEOUT,
        )
        state = checked(response, "Live audio status").json()
        print(json.dumps({"jobId": job_id, "status": state.get("status")}, ensure_ascii=False), flush=True)
    raise RuntimeError(f"Audio did not become ready within {MAX_WAIT_SECONDS}s")


def verify_outputs(job_id, book_key, state):
    item = json.loads(r2_get(AUDIO_BUCKET, f"audio-library/items/{job_id}.json").decode("utf-8"))
    mp3 = r2_get(AUDIO_BUCKET, f"audio-library/media/{job_id}/episode.mp3")
    timing = json.loads(r2_get(AUDIO_BUCKET, f"audio-library/media/{job_id}/timing.json").decode("utf-8"))
    if item.get("status") != "ready":
        raise RuntimeError("R2 item is not ready")
    if len(mp3) < 1500:
        raise RuntimeError("R2 MP3 is unexpectedly small")
    if not (mp3.startswith(b"ID3") or (len(mp3) >= 2 and mp3[0] == 0xFF and (mp3[1] & 0xE0) == 0xE0)):
        raise RuntimeError("R2 output does not look like MP3")
    words = timing.get("words") or []
    if not words:
        raise RuntimeError("R2 timing has no WordBoundary entries")
    if timing.get("id") != job_id:
        raise RuntimeError("R2 timing id mismatch")

    media_url = state.get("mediaUrl")
    timing_url = state.get("timingUrl")
    if not media_url or not timing_url:
        raise RuntimeError("Ready state is missing signed media/timing URLs")
    media_response = requests.get(urljoin(CORE_URL + "/", media_url), headers={"Range": "bytes=0-511"}, timeout=HTTP_TIMEOUT)
    if media_response.status_code not in (200, 206) or not media_response.content:
        raise RuntimeError(f"Live signed media range failed HTTP {media_response.status_code}")
    live_timing = checked(requests.get(urljoin(CORE_URL + "/", timing_url), timeout=HTTP_TIMEOUT), "Live timing GET").json()
    if not (live_timing.get("words") or []):
        raise RuntimeError("Live timing endpoint returned no words")

    return {
        "r2Mp3Bytes": len(mp3),
        "r2TimingWords": len(words),
        "durationSeconds": state.get("durationSeconds") or item.get("durationSeconds"),
        "mediaRangeStatus": media_response.status_code,
        "timingAvailable": bool(state.get("timingAvailable")),
    }


def main():
    require_env()
    book_key, final_count = choose_final_epub()
    epub = r2_get(SOURCE_BUCKET, book_key)
    chapter = resolve_epub(epub)
    print(json.dumps({"phase": "source", "bookKey": book_key, "finalEpubCandidates": final_count, "chapterTitle": chapter["chapterTitle"], "sampleChars": chapter["sampleChars"]}, ensure_ascii=False), flush=True)
    job_id, initial = post_audio(book_key, chapter)
    print(json.dumps({"phase": "queued", "jobId": job_id, "initialStatus": initial.get("status")}, ensure_ascii=False), flush=True)
    ready = poll_ready(job_id, book_key, initial)
    proof = verify_outputs(job_id, book_key, ready)
    result = {"ok": True, "bookKey": book_key, "chapterTitle": chapter["chapterTitle"], "jobId": job_id, **proof}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
