#!/usr/bin/env python3
import asyncio
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from langdetect import detect
from pypdf import PdfReader
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "ops/audio-library/status.json"
R2_STATUS_PATH = ROOT / "ops/r2-media/status.json"
BUCKET = os.environ.get("AUDIO_LIBRARY_BUCKET", "runner3-wp-media")
VOICE = os.environ.get("AUDIO_LIBRARY_VOICE", "vi-VN-NamMinhNeural")
VOICE_RATE = os.environ.get("AUDIO_LIBRARY_VOICE_RATE", "+3%")
MAX_CHARS = int(os.environ.get("AUDIO_LIBRARY_MAX_CHARS", "14000"))
MAX_JOBS = int(os.environ.get("AUDIO_LIBRARY_MAX_JOBS", "2"))
UA = "Mozilla/5.0 (compatible; Runner3AudioLibrary/1.0; +https://github.com/louisalviss/runner-3)"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def worker_url():
    data = load_json(STATUS_PATH)
    url = str(data.get("url") or "").rstrip("/")
    if not url:
        raise RuntimeError("Audio Library Worker URL missing")
    return url


def runner_token():
    raw = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not raw:
        raise RuntimeError("CLOUDFLARE_API_TOKEN missing")
    return hashlib.sha256(raw.encode()).hexdigest()


def runner_headers():
    return {"X-Runner-Token": runner_token(), "User-Agent": UA}


def api(method, path, **kwargs):
    headers = dict(runner_headers())
    headers.update(kwargs.pop("headers", {}))
    r = requests.request(method, worker_url() + path, headers=headers, timeout=45, **kwargs)
    if r.status_code == 204:
        return None
    if r.status_code >= 400:
        raise RuntimeError(f"Worker API {r.status_code}: {r.text[:400]}")
    return r.json()


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", " ", text)
    text = re.sub(r"[`*_>#|]", " ", text)
    lines = []
    banned = re.compile(r"^(cookie|privacy|sign in|log in|subscribe|advertisement|all rights reserved|accept all|reject all)\b", re.I)
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if len(line) < 2 or banned.search(line):
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def trim_text(text: str, limit=MAX_CHARS):
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("\n"))
    if boundary > limit * 0.75:
        cut = cut[: boundary + 1]
    return cut.strip(), True


def extract_reddit(url: str):
    parsed = urlparse(url)
    base_path = parsed.path.rstrip("/")
    hosts = ["www.reddit.com", "old.reddit.com", "en.reddit.com"]
    candidates = [f"https://{h}{base_path}.rss?sort=best" for h in hosts]
    last_error = None
    for feed_url in candidates:
        try:
            r = requests.get(feed_url, headers={"User-Agent": UA, "Accept": "application/atom+xml,text/xml,*/*"}, timeout=30)
            if r.status_code != 200 or len(r.text) < 800:
                last_error = f"{feed_url} -> {r.status_code}/{len(r.text)}"
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            title = clean_text((soup.find("title").get_text(" ", strip=True) if soup.find("title") else "Reddit"))
            entries = []
            for entry in soup.find_all("entry")[:24]:
                content = entry.find("content")
                if not content:
                    continue
                body = BeautifulSoup(content.get_text(" ", strip=True), "html.parser").get_text(" ", strip=True)
                body = clean_text(body)
                if len(body) >= 80:
                    entries.append(body)
            if entries:
                text = "\n\n".join(entries)
                return title or "Reddit", text, "Reddit"
            last_error = "RSS loaded but no useful entries"
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(f"Reddit fetch failed: {last_error}")


def parse_vtt(text: str):
    out, prev = [], None
    for line in text.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"&nbsp;", " ", line)
        line = html.unescape(line)
        if line == prev:
            continue
        prev = line
        out.append(line)
    return clean_text(" ".join(out))


def extract_youtube(url: str, work: Path):
    meta_cmd = [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--skip-download", "--no-warnings", url]
    meta_run = subprocess.run(meta_cmd, text=True, capture_output=True, timeout=90)
    meta = {}
    if meta_run.returncode == 0:
        try:
            meta = json.loads(meta_run.stdout)
        except Exception:
            meta = {}
    title = clean_text(str(meta.get("title") or "YouTube"))
    template = str(work / "youtube.%(ext)s")
    sub_cmd = [
        sys.executable, "-m", "yt_dlp", "--skip-download", "--no-warnings",
        "--write-subs", "--write-auto-subs", "--sub-langs", "vi.*,en.*", "--sub-format", "vtt",
        "-o", template, url,
    ]
    subprocess.run(sub_cmd, text=True, capture_output=True, timeout=150)
    texts = []
    for path in sorted(work.glob("youtube*.vtt")):
        parsed = parse_vtt(path.read_text(encoding="utf-8", errors="ignore"))
        if len(parsed) > 500:
            texts.append(parsed)
    if texts:
        texts.sort(key=len, reverse=True)
        return title, texts[0], "YouTube"
    desc = clean_text(str(meta.get("description") or ""))
    if len(desc) > 500:
        return title, desc, "YouTube"
    raise RuntimeError("YouTube không có transcript/description đủ dài")


def extract_pdf(content: bytes, url: str):
    reader = PdfReader(io.BytesIO(content))
    parts = []
    for page in reader.pages[:80]:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt:
            parts.append(txt)
    text = clean_text("\n\n".join(parts))
    title = Path(urlparse(url).path).name or "PDF"
    if len(text) < 500:
        raise RuntimeError("PDF không có đủ text để đọc")
    return title, text, "PDF"


def extract_web(url: str):
    last_error = None
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf,*/*"}, timeout=35, allow_redirects=True)
        ctype = (r.headers.get("content-type") or "").lower()
        if r.status_code == 200 and ("application/pdf" in ctype or r.url.lower().endswith(".pdf")):
            return extract_pdf(r.content, r.url)
        if r.status_code == 200 and len(r.text) > 500:
            soup = BeautifulSoup(r.text, "html.parser")
            title = clean_text((soup.title.get_text(" ", strip=True) if soup.title else urlparse(r.url).hostname or "Web"))
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "svg", "noscript"]):
                tag.decompose()
            root = soup.find("article") or soup.find("main") or soup.body or soup
            pieces = []
            for node in root.find_all(["h1", "h2", "h3", "p", "li"]):
                t = clean_text(node.get_text(" ", strip=True))
                if len(t) >= 35:
                    pieces.append(t)
            text = clean_text("\n\n".join(pieces))
            if len(text) >= 1000:
                return title, text, (urlparse(r.url).hostname or "Web").replace("www.", "")
            last_error = f"direct text too thin: {len(text)}"
        else:
            last_error = f"direct HTTP {r.status_code}"
    except Exception as e:
        last_error = str(e)

    try:
        jina = "https://r.jina.ai/" + url
        r = requests.get(jina, headers={"User-Agent": UA, "Accept": "text/plain"}, timeout=45)
        if r.status_code == 200 and len(r.text) >= 1000:
            body = clean_text(r.text)
            title = urlparse(url).hostname or "Web"
            m = re.search(r"(?:^|\n)Title:\s*(.+)", r.text)
            if m:
                title = clean_text(m.group(1))
            return title, body, (urlparse(url).hostname or "Web").replace("www.", "")
        last_error = f"{last_error}; Jina {r.status_code}/{len(r.text)}"
    except Exception as e:
        last_error = f"{last_error}; Jina {e}"
    raise RuntimeError(f"Không lấy được nội dung: {last_error}")


def extract_source(url: str, work: Path):
    host = (urlparse(url).hostname or "").lower()
    if "reddit.com" in host:
        return extract_reddit(url)
    if host in {"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com"} or host.endswith(".youtube.com"):
        return extract_youtube(url, work)
    return extract_web(url)


def likely_language(text: str):
    sample = re.sub(r"\s+", " ", text)[:5000]
    try:
        return detect(sample)
    except Exception:
        return "unknown"


def chunk_for_translate(text: str, limit=3500):
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= limit:
            buf = (buf + "\n" + p).strip()
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        while len(p) > limit:
            cut = p.rfind(". ", 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(p[:cut + (2 if cut != limit else 0)].strip())
            p = p[cut + (2 if cut != limit else 0):].strip()
        buf = p
    if buf:
        chunks.append(buf)
    return chunks


def translate_vi(text: str):
    lang = likely_language(text)
    if lang == "vi":
        return text, False
    translated = []
    translator = GoogleTranslator(source="auto", target="vi")
    for chunk in chunk_for_translate(text):
        translated.append(translator.translate(chunk))
    out = clean_text("\n\n".join(translated))
    if len(out) < 300:
        raise RuntimeError("Dịch sang tiếng Việt thất bại")
    return out, True


def tts_chunks(text: str, limit=3200):
    sentences = re.split(r"(?<=[.!?…])\s+|\n+", text)
    chunks, buf = [], ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(buf) + len(sentence) + 1 <= limit:
            buf = (buf + " " + sentence).strip()
            continue
        if buf:
            chunks.append(buf)
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        buf = sentence
    if buf:
        chunks.append(buf)
    return chunks


async def synthesize(text: str, work: Path):
    parts = []
    for idx, chunk in enumerate(tts_chunks(text)):
        path = work / f"part-{idx:03d}.mp3"
        communicate = edge_tts.Communicate(chunk, VOICE, rate=VOICE_RATE)
        await communicate.save(str(path))
        if not path.exists() or path.stat().st_size < 1500:
            raise RuntimeError(f"TTS part {idx} quá nhỏ")
        parts.append(path)
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    out = work / "episode.mp3"
    subprocess.check_call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat), "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(out)
    ])
    return out


def media_duration(path: Path):
    value = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)
    ], text=True).strip()
    return float(value)


def wrangler_put(file: Path, key: str, content_type: str, cache_control: str):
    cmd = [
        "npx", "-y", "wrangler@4.123.0", "r2", "object", "put", f"{BUCKET}/{key}",
        f"--file={file}", f"--content-type={content_type}", f"--cache-control={cache_control}", "--remote",
    ]
    subprocess.check_call(cmd, cwd=ROOT)


def process_item(item):
    item_id = item["id"]
    source_url = item["sourceUrl"]
    with tempfile.TemporaryDirectory(prefix="audio-library-") as td:
        work = Path(td)
        title, text, source_label = extract_source(source_url, work)
        text = clean_text(text)
        text, truncated = trim_text(text)
        if len(text) < 500:
            raise RuntimeError("Nội dung quá ngắn để tạo audio")
        translated, was_translated = translate_vi(text)
        intro = f"{title}. Nguồn {source_label}. Bản đọc tự động từ liên kết đã lưu."
        if truncated:
            intro += " Nội dung dài nên bản này đọc phần chính trong giới hạn của thư viện."
        narration = clean_text(intro + "\n\n" + translated)
        mp3 = asyncio.run(synthesize(narration, work))
        duration = media_duration(mp3)
        transcript = work / "transcript.txt"
        transcript.write_text(narration + "\n", encoding="utf-8")
        metadata = work / "metadata.json"
        metadata.write_text(json.dumps({
            "id": item_id,
            "title": title,
            "sourceUrl": source_url,
            "sourceLabel": source_label,
            "voice": VOICE,
            "voiceRate": VOICE_RATE,
            "durationSeconds": duration,
            "truncated": truncated,
            "translatedToVietnamese": was_translated,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prefix = f"audio-library/media/{item_id}"
        wrangler_put(mp3, f"{prefix}/episode.mp3", "audio/mpeg", "public, max-age=300")
        wrangler_put(transcript, f"{prefix}/transcript.txt", "text/plain; charset=utf-8", "public, max-age=60")
        wrangler_put(metadata, f"{prefix}/metadata.json", "application/json; charset=utf-8", "public, max-age=60")
        r2_base = str(load_json(R2_STATUS_PATH).get("baseUrl") or "").rstrip("/")
        if not r2_base:
            raise RuntimeError("R2 public base URL missing")
        payload = {
            "id": item_id,
            "title": title[:240],
            "sourceLabel": source_label[:80],
            "durationSeconds": duration,
            "audioUrl": f"{r2_base}/{prefix}/episode.mp3",
            "transcriptUrl": f"{r2_base}/{prefix}/transcript.txt",
            "truncated": truncated,
        }
        api("POST", "/api/runner/complete", json=payload)
        print(json.dumps({"status": "ready", **payload}, ensure_ascii=False), flush=True)


def main():
    completed = 0
    for _ in range(MAX_JOBS):
        claim = api("GET", "/api/runner/next")
        if not claim:
            break
        item = claim.get("item") or {}
        item_id = item.get("id")
        try:
            process_item(item)
            completed += 1
        except Exception as exc:
            detail = repr(exc)
            print(f"ERROR {item_id}: {detail}", file=sys.stderr, flush=True)
            try:
                api("POST", "/api/runner/fail", json={"id": item_id, "error": str(exc)[:180], "detail": detail[:1200]})
            except Exception as report_exc:
                print(f"Failed to report error: {report_exc}", file=sys.stderr)
    print(json.dumps({"processed": completed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
