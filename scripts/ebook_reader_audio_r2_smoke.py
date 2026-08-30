#!/usr/bin/env python3
"""Seed and verify one real Ebook Reader audio job from a final EPUB in R2.

This is an integration smoke, not fixture data: it lists runner3-artifacts, selects
an actual core/ebook/*/final/*.epub, extracts a real spine chapter, writes the
same Ebook Reader queue/item/script contract into the audio R2 bucket, and can
verify the resulting MP3 + WordBoundary timing output after the normal worker runs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote

import requests

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
ARTIFACT_BUCKET = os.environ.get("EBOOK_ARTIFACT_BUCKET", "runner3-artifacts").strip()
AUDIO_BUCKET = os.environ.get("EBOOK_AUDIO_BUCKET", "runner3-wp-media").strip()
VOICE = os.environ.get("EBOOK_AUDIO_VOICE", "vi-VN-NamMinhNeural").strip()
VOICE_RATE = os.environ.get("EBOOK_AUDIO_VOICE_RATE", "+3%").strip()
AUDIO_VERSION = "ebook-reader-audio-v1"
ROOT = "core/ebook/"
ITEM_PREFIX = "audio-library/items/"
QUEUE_PREFIX = "audio-library/ebook-reader-queue/"
MEDIA_PREFIX = "audio-library/media/"
HTTP_TIMEOUT = 90
MAX_SMOKE_CHARS = int(os.environ.get("EBOOK_AUDIO_SMOKE_MAX_CHARS", "6500"))


def utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_env():
    missing = [name for name, value in (("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_ID), ("CLOUDFLARE_API_TOKEN", API_TOKEN)) if not value]
    if missing:
        raise RuntimeError("Missing environment: " + ", ".join(missing))


def headers(content_type=None):
    result = {"Authorization": f"Bearer {API_TOKEN}"}
    if content_type:
        result["Content-Type"] = content_type
    return result


def object_url(bucket, key=None):
    base = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/buckets/{quote(bucket, safe='')}/objects"
    if key is None:
        return base
    return base + "/" + quote(str(key), safe="/")


def checked(response, operation):
    if 200 <= response.status_code < 300:
        return response
    raise RuntimeError(f"R2 {operation} failed HTTP {response.status_code}: {response.text[:400].replace(chr(10), ' ')}")


def r2_list(bucket, prefix):
    rows, cursor = [], None
    while True:
        params = {"prefix": prefix, "per_page": 1000}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(object_url(bucket), headers=headers(), params=params, timeout=HTTP_TIMEOUT)
        payload = checked(response, f"LIST {bucket}:{prefix}").json()
        if not payload.get("success", False):
            raise RuntimeError(f"R2 LIST {bucket}:{prefix} returned success=false")
        rows.extend(payload.get("result") or [])
        info = payload.get("result_info") or {}
        if not info.get("is_truncated"):
            return rows
        cursor = info.get("cursor")
        if not cursor:
            return rows


def r2_get_bytes(bucket, key, missing_ok=False):
    response = requests.get(object_url(bucket, key), headers=headers(), timeout=HTTP_TIMEOUT)
    if missing_ok and response.status_code == 404:
        return None
    return checked(response, f"GET {bucket}:{key}").content


def r2_get_json(bucket, key, missing_ok=False):
    raw = r2_get_bytes(bucket, key, missing_ok=missing_ok)
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8"))


def r2_put_bytes(bucket, key, data, content_type):
    response = requests.put(object_url(bucket, key), headers=headers(content_type), data=data, timeout=HTTP_TIMEOUT)
    checked(response, f"PUT {bucket}:{key}")


def r2_put_json(bucket, key, value):
    r2_put_bytes(bucket, key, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8")


class TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "section", "article", "header", "footer", "main", "aside", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "blockquote"}
    SKIP = {"script", "style", "svg", "noscript", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self.depth += 1
        elif self.depth == 0 and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP:
            self.depth = max(0, self.depth - 1)
        elif self.depth == 0 and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.depth == 0 and data.strip():
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def final_epub_candidates():
    rows = r2_list(ARTIFACT_BUCKET, ROOT)
    candidates = []
    for row in rows:
        key = str(row.get("key") or "")
        if key.startswith(ROOT) and "/final/" in key and key.lower().endswith(".epub"):
            candidates.append(row)
    candidates.sort(key=lambda row: (str(row.get("last_modified") or ""), int(row.get("size") or 0)), reverse=True)
    return candidates


def opf_root_path(book: zipfile.ZipFile):
    raw = book.read("META-INF/container.xml")
    root = ET.fromstring(raw)
    node = root.find(".//{*}rootfile")
    if node is None or not node.attrib.get("full-path"):
        raise RuntimeError("EPUB container rootfile missing")
    return node.attrib["full-path"]


def chapter_from_epub(data):
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        opf_path = opf_root_path(book)
        opf = ET.fromstring(book.read(opf_path))
        base = posixpath.dirname(opf_path)
        manifest = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")
            if item_id and href:
                manifest[item_id] = (href, media_type)
        ordered = []
        for ref in opf.findall(".//{*}spine/{*}itemref"):
            item = manifest.get(ref.attrib.get("idref"))
            if item:
                ordered.append(item)
        if not ordered:
            ordered = list(manifest.values())

        for href, media_type in ordered:
            if media_type not in ("application/xhtml+xml", "text/html") and not href.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            path = posixpath.normpath(posixpath.join(base, href))
            try:
                raw = book.read(path)
            except KeyError:
                continue
            html = raw.decode("utf-8", errors="replace")
            parser = TextExtractor()
            parser.feed(html)
            text = parser.text()
            if len(text) < 300:
                continue
            title_match = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, flags=re.I | re.S)
            title = "R2 integration smoke"
            if title_match:
                title_parser = TextExtractor()
                title_parser.feed(title_match.group(1))
                title = title_parser.text()[:180] or title
            return path, title, text
    raise RuntimeError("No substantial XHTML chapter found in EPUB")


def normalize_speech_text(value):
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("\r", "").replace("\u00a0", " ")
    text = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    parts = []
    for part in re.split(r"\n\s*\n+", text):
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        if not re.search(r"[.!?…:;”’')\]}]$", part):
            part += "."
        parts.append(part)
    return "\n\n".join(parts).strip()


def smoke_script(text):
    text = normalize_speech_text(text)
    if len(text) <= MAX_SMOKE_CHARS:
        return text
    clipped = text[:MAX_SMOKE_CHARS]
    cut = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "), clipped.rfind("\n"))
    if cut >= int(MAX_SMOKE_CHARS * 0.7):
        clipped = clipped[: cut + 1]
    return normalize_speech_text(clipped)


def job_id(book_key, script):
    text_sha = hashlib.sha256(script.encode("utf-8")).hexdigest()
    raw = f"{AUDIO_VERSION}\0{book_key}\0{text_sha}\0{VOICE}\0{VOICE_RATE}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "ebook-" + digest[:32], text_sha


def seed():
    candidates = final_epub_candidates()
    if not candidates:
        raise RuntimeError("No core/ebook/*/final/*.epub found in R2")
    selected = candidates[0]
    book_key = str(selected["key"])
    epub = r2_get_bytes(ARTIFACT_BUCKET, book_key)
    chapter_href, chapter_title, chapter_text = chapter_from_epub(epub)
    script = smoke_script(chapter_text)
    if len(script) < 80:
        raise RuntimeError("Extracted smoke chapter text too short")
    jid, text_sha = job_id(book_key, script)
    item_key = f"{ITEM_PREFIX}{jid}.json"
    queue_key = f"{QUEUE_PREFIX}{jid}.json"
    media_prefix = f"{MEDIA_PREFIX}{jid}/"
    existing = r2_get_json(AUDIO_BUCKET, item_key, missing_ok=True)
    if existing and existing.get("status") == "ready":
        result = {
            "ok": True,
            "seeded": False,
            "existing": True,
            "jobId": jid,
            "bookKey": book_key,
            "chapterHref": chapter_href,
            "chapterTitle": chapter_title,
            "scriptChars": len(script),
            "status": "ready",
        }
        print(json.dumps(result, ensure_ascii=False))
        return result

    now = utc_iso()
    r2_put_bytes(AUDIO_BUCKET, media_prefix + "script.txt", script.encode("utf-8"), "text/plain; charset=utf-8")
    item = {
        "id": jid,
        "kind": "ebook-reader",
        "bookKey": book_key,
        "chapterTitle": chapter_title,
        "chapterHref": chapter_href,
        "title": "R2 real EPUB integration smoke",
        "sourceLabel": "Ebook Library",
        "status": "pending",
        "createdAt": (existing or {}).get("createdAt") or now,
        "updatedAt": now,
        "expiresAt": None,
        "pinned": True,
        "durationSeconds": None,
        "progressSeconds": 0,
        "audioUrl": None,
        "transcriptUrl": None,
        "timingUrl": None,
        "mediaPrefix": media_prefix,
        "audioVersion": AUDIO_VERSION,
        "voice": VOICE,
        "voiceRate": VOICE_RATE,
        "textSha256": text_sha,
        "error": None,
        "integrationSmoke": True,
    }
    queue = {
        "id": jid,
        "kind": "ebook-reader",
        "bookKey": book_key,
        "itemKey": item_key,
        "scriptKey": media_prefix + "script.txt",
        "mediaPrefix": media_prefix,
        "audioVersion": AUDIO_VERSION,
        "voice": VOICE,
        "voiceRate": VOICE_RATE,
        "textSha256": text_sha,
        "createdAt": now,
        "integrationSmoke": True,
    }
    r2_put_json(AUDIO_BUCKET, item_key, item)
    r2_put_json(AUDIO_BUCKET, queue_key, queue)
    result = {
        "ok": True,
        "seeded": True,
        "existing": False,
        "jobId": jid,
        "bookKey": book_key,
        "chapterHref": chapter_href,
        "chapterTitle": chapter_title,
        "scriptChars": len(script),
        "epubBytes": len(epub),
        "status": "pending",
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def verify(jid):
    if not re.fullmatch(r"ebook-[a-f0-9]{32}", jid or ""):
        raise RuntimeError("EBOOK_AUDIO_JOB_ID is invalid for smoke verification")
    item_key = f"{ITEM_PREFIX}{jid}.json"
    media_prefix = f"{MEDIA_PREFIX}{jid}/"
    item = r2_get_json(AUDIO_BUCKET, item_key, missing_ok=False)
    if item.get("status") != "ready":
        raise RuntimeError(f"Smoke item is not ready: {item.get('status')}")
    mp3 = r2_get_bytes(AUDIO_BUCKET, media_prefix + "episode.mp3", missing_ok=False)
    timing = r2_get_json(AUDIO_BUCKET, media_prefix + "timing.json", missing_ok=False)
    script = r2_get_bytes(AUDIO_BUCKET, media_prefix + "script.txt", missing_ok=False)
    if len(mp3) < 1500:
        raise RuntimeError("Smoke MP3 is unexpectedly small")
    if not isinstance(timing.get("words"), list) or not timing["words"]:
        raise RuntimeError("Smoke timing has no WordBoundary words")
    duration = float(timing.get("durationSeconds") or item.get("durationSeconds") or 0)
    if duration <= 0:
        raise RuntimeError("Smoke audio duration is invalid")
    result = {
        "ok": True,
        "verified": True,
        "jobId": jid,
        "bookKey": item.get("bookKey"),
        "status": item.get("status"),
        "mp3Bytes": len(mp3),
        "scriptBytes": len(script),
        "durationSeconds": round(duration, 3),
        "wordBoundaryCount": len(timing["words"]),
        "voice": timing.get("voice"),
        "voiceRate": timing.get("voiceRate"),
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def main():
    require_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--job-id", default=os.environ.get("EBOOK_AUDIO_JOB_ID", "").strip())
    args = parser.parse_args()
    if args.verify:
        verify(args.job_id)
    else:
        seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
