#!/usr/bin/env python3
import base64
import hashlib
import html
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / 'ops/audio-library/chatgpt-bridge-status.json'
INBOX_DIR = ROOT / 'ops/audio-library/chatgpt-inbox'
OUTBOX_DIR = ROOT / 'ops/audio-library/chatgpt-outbox'
MAX_ITEMS = int(os.environ.get('AUDIO_LIBRARY_EXTRACT_MAX_ITEMS', '3'))
MAX_RAW_CHARS = int(os.environ.get('AUDIO_LIBRARY_MAX_RAW_CHARS', '120000'))
UA = 'Mozilla/5.0 (compatible; Runner3AudioExtractor/2.1; +https://github.com/louisalviss/runner-3)'


def clean_text(text: str) -> str:
    text = html.unescape(text or '')
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', ' ', text)
    text = re.sub(r'[`*_>#|]', ' ', text)
    lines = []
    banned = re.compile(r'^(cookie|privacy|sign in|log in|subscribe|advertisement|all rights reserved|accept all|reject all)\b', re.I)
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if len(line) < 2 or banned.search(line):
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def trim_raw(text: str):
    if len(text) <= MAX_RAW_CHARS:
        return text, False
    cut = text[:MAX_RAW_CHARS]
    boundary = max(cut.rfind('\n\n'), cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    if boundary > MAX_RAW_CHARS * 0.75:
        cut = cut[:boundary + 1]
    return cut.strip(), True


def resolve_url(url: str):
    r = requests.get(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*'}, timeout=35, allow_redirects=True)
    final = r.url
    if 'reddit.com' in (urlparse(final).hostname or '').lower() and '/s/' in urlparse(final).path:
        try:
            soup = BeautifulSoup(r.text, 'html.parser')
            canonical = soup.find('link', rel='canonical')
            if canonical and canonical.get('href'):
                final = canonical['href']
        except Exception:
            pass
    return final, r


def reddit_json_extract(canonical_url: str):
    base = canonical_url.split('?')[0].rstrip('/')
    if '/comments/' not in base:
        raise RuntimeError('Reddit canonical URL did not resolve to comments thread')
    endpoint = base + '.json?raw_json=1&limit=100&sort=top'
    r = requests.get(endpoint, headers={'User-Agent': UA, 'Accept': 'application/json'}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f'Reddit JSON HTTP {r.status_code}')
    data = r.json()
    if not isinstance(data, list) or len(data) < 2:
        raise RuntimeError('Reddit JSON shape invalid')
    post = data[0]['data']['children'][0]['data']
    title = clean_text(str(post.get('title') or 'Reddit'))
    selftext = clean_text(str(post.get('selftext') or ''))
    comments = []

    def walk(children, depth=0):
        if depth > 2 or len(comments) >= 120:
            return
        for child in children or []:
            if len(comments) >= 120:
                return
            if child.get('kind') != 't1':
                continue
            d = child.get('data') or {}
            body = clean_text(str(d.get('body') or ''))
            if len(body) >= 40:
                score = d.get('score')
                prefix = f'[Comment score {score}] ' if isinstance(score, int) else '[Comment] '
                comments.append(prefix + body)
            replies = d.get('replies')
            if isinstance(replies, dict):
                walk(((replies.get('data') or {}).get('children') or []), depth + 1)

    walk(((data[1].get('data') or {}).get('children') or []))
    parts = []
    if selftext:
        parts.append('[Post]\n' + selftext)
    parts.extend(comments)
    text = clean_text('\n\n'.join(parts))
    if len(text) < 400:
        raise RuntimeError('Reddit JSON returned too little useful text')
    return title, text, 'Reddit'


def reddit_rss_extract(canonical_url: str):
    parsed = urlparse(canonical_url)
    path = parsed.path.rstrip('/')
    errors = []
    for host in ['www.reddit.com', 'old.reddit.com', 'en.reddit.com']:
        feed_url = f'https://{host}{path}.rss?sort=top&limit=100'
        try:
            r = requests.get(feed_url, headers={'User-Agent': UA, 'Accept': 'application/atom+xml,text/xml,*/*'}, timeout=35)
            if r.status_code != 200 or len(r.text) < 800:
                errors.append(f'{host}:{r.status_code}/{len(r.text)}')
                continue
            soup = BeautifulSoup(r.text, 'xml')
            title_tag = soup.find('title')
            title = clean_text(title_tag.get_text(' ', strip=True) if title_tag else 'Reddit')
            entries = []
            for entry in soup.find_all('entry')[:100]:
                content = entry.find('content')
                if not content:
                    continue
                body = BeautifulSoup(content.get_text(' ', strip=True), 'html.parser').get_text(' ', strip=True)
                body = clean_text(body)
                if len(body) >= 50:
                    entries.append(body)
            text = clean_text('\n\n'.join(entries))
            if len(text) >= 400:
                return title, text, 'Reddit'
            errors.append(f'{host}:thin')
        except Exception as e:
            errors.append(f'{host}:{e}')
    raise RuntimeError('Reddit RSS failed: ' + '; '.join(errors))


def reddit_reader_extract(url: str):
    errors = []
    for prefix in ['https://r.jina.ai/https://', 'https://r.jina.ai/http://']:
        target = prefix + url.split('://', 1)[-1]
        try:
            r = requests.get(target, headers={'User-Agent': UA, 'Accept': 'text/plain'}, timeout=60)
            if r.status_code != 200 or len(r.text) < 800:
                errors.append(f'{r.status_code}/{len(r.text)}')
                continue
            raw = r.text
            title_match = re.search(r'(?mi)^Title:\s*(.+)$', raw)
            source_match = re.search(r'(?mi)^URL Source:\s*(https?://\S+)', raw)
            title = clean_text(title_match.group(1)) if title_match else 'Reddit'
            canonical = source_match.group(1).strip() if source_match else url
            text = clean_text(raw)
            # Remove Reader metadata from narration source, but keep the actual Reddit body/comments.
            text = re.sub(r'(?mi)^(Title|URL Source|Published Time|Markdown Content):\s*.*$', '', text)
            text = clean_text(text)
            if len(text) >= 800:
                return title, text, 'Reddit', canonical
            errors.append('reader-thin')
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError('Reddit reader fallback failed: ' + '; '.join(errors))


def extract_reddit(url: str):
    canonical, _first = resolve_url(url)
    json_error = None
    rss_error = None
    try:
        title, text, label = reddit_json_extract(canonical)
        return title, text, label, canonical
    except Exception as e:
        json_error = e
    try:
        title, text, label = reddit_rss_extract(canonical)
        return title, text, label, canonical
    except Exception as e:
        rss_error = e
    try:
        return reddit_reader_extract(url)
    except Exception as reader_error:
        raise RuntimeError(f'Reddit extract failed: JSON={json_error}; RSS={rss_error}; Reader={reader_error}; final={canonical}')


def parse_vtt(text: str):
    out, prev = [], None
    for line in text.splitlines():
        line = re.sub(r'<[^>]+>', '', line).strip()
        if not line or line.startswith('WEBVTT') or '-->' in line or re.fullmatch(r'\d+', line):
            continue
        line = html.unescape(line.replace('&nbsp;', ' '))
        if line == prev:
            continue
        prev = line
        out.append(line)
    return clean_text(' '.join(out))


def extract_youtube(url: str, work: Path):
    meta_cmd = [sys.executable, '-m', 'yt_dlp', '--dump-single-json', '--skip-download', '--no-warnings', url]
    meta_run = subprocess.run(meta_cmd, text=True, capture_output=True, timeout=90)
    meta = {}
    if meta_run.returncode == 0:
        try:
            meta = json.loads(meta_run.stdout)
        except Exception:
            meta = {}
    title = clean_text(str(meta.get('title') or 'YouTube'))
    canonical = str(meta.get('webpage_url') or url)
    template = str(work / 'youtube.%(ext)s')
    sub_cmd = [sys.executable, '-m', 'yt_dlp', '--skip-download', '--no-warnings', '--write-subs', '--write-auto-subs', '--sub-langs', 'vi.*,en.*', '--sub-format', 'vtt', '-o', template, url]
    subprocess.run(sub_cmd, text=True, capture_output=True, timeout=180)
    texts = []
    for path in sorted(work.glob('youtube*.vtt')):
        parsed = parse_vtt(path.read_text(encoding='utf-8', errors='ignore'))
        if len(parsed) > 500:
            texts.append(parsed)
    if texts:
        texts.sort(key=len, reverse=True)
        return title, texts[0], 'YouTube', canonical
    desc = clean_text(str(meta.get('description') or ''))
    if len(desc) > 500:
        return title, desc, 'YouTube', canonical
    raise RuntimeError('YouTube has no usable transcript or long description')


def extract_pdf(content: bytes, url: str):
    reader = PdfReader(io.BytesIO(content))
    parts = []
    for page in reader.pages[:120]:
        try:
            txt = page.extract_text() or ''
        except Exception:
            txt = ''
        if txt:
            parts.append(txt)
    text = clean_text('\n\n'.join(parts))
    if len(text) < 500:
        raise RuntimeError('PDF text too thin')
    return Path(urlparse(url).path).name or 'PDF', text, 'PDF', url


def extract_web(url: str):
    direct_error = None
    try:
        final, r = resolve_url(url)
        ctype = (r.headers.get('content-type') or '').lower()
        if r.status_code == 200 and ('application/pdf' in ctype or final.lower().endswith('.pdf')):
            return extract_pdf(r.content, final)
        if r.status_code == 200 and len(r.text) > 500:
            soup = BeautifulSoup(r.text, 'html.parser')
            title = clean_text(soup.title.get_text(' ', strip=True) if soup.title else (urlparse(final).hostname or 'Web'))
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'svg', 'noscript']):
                tag.decompose()
            root = soup.find('article') or soup.find('main') or soup.body or soup
            pieces = []
            for node in root.find_all(['h1', 'h2', 'h3', 'p', 'li', 'blockquote']):
                t = clean_text(node.get_text(' ', strip=True))
                if len(t) >= 30:
                    pieces.append(t)
            text = clean_text('\n\n'.join(pieces))
            if len(text) >= 800:
                return title, text, (urlparse(final).hostname or 'Web').replace('www.', ''), final
            direct_error = f'direct text too thin: {len(text)}'
        else:
            direct_error = f'direct HTTP {r.status_code}'
    except Exception as e:
        direct_error = str(e)

    try:
        r = requests.get('https://r.jina.ai/' + url, headers={'User-Agent': UA, 'Accept': 'text/plain'}, timeout=50)
        if r.status_code == 200 and len(r.text) >= 800:
            body = clean_text(r.text)
            m = re.search(r'(?:^|\n)Title:\s*(.+)', r.text)
            title = clean_text(m.group(1)) if m else (urlparse(url).hostname or 'Web')
            return title, body, (urlparse(url).hostname or 'Web').replace('www.', ''), url
        raise RuntimeError(f'Jina {r.status_code}/{len(r.text)}')
    except Exception as e:
        raise RuntimeError(f'Web extract failed: direct={direct_error}; fallback={e}')


def extract_source(url: str, work: Path):
    host = (urlparse(url).hostname or '').lower()
    if 'reddit.com' in host:
        return extract_reddit(url)
    if host in {'youtu.be', 'youtube.com', 'www.youtube.com', 'm.youtube.com'} or host.endswith('.youtube.com'):
        return extract_youtube(url, work)
    return extract_web(url)


def bridge_url():
    data = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    return str(data['url']).rstrip('/')


def queue_token():
    token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not token:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    return hashlib.sha256(b'runner3-chatgpt-queue-v2\0' + token.encode()).hexdigest()


def pending_items():
    r = requests.get(bridge_url() + '/pending', params={'token': queue_token()}, headers={'User-Agent': UA}, timeout=40)
    r.raise_for_status()
    return (r.json().get('items') or [])[:MAX_ITEMS]


def encrypt_payload(payload: dict, recipient_b64: str):
    recipient = X25519PublicKey.from_public_bytes(base64.b64decode(recipient_b64))
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(recipient)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'runner3-audio-library-inbox-v1').derive(shared)
    item_id = str(payload['id'])
    nonce = secrets.token_bytes(12)
    plain = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    cipher = ChaCha20Poly1305(key).encrypt(nonce, plain, item_id.encode())
    return {
        'v': 1,
        'id': item_id,
        'ephemeralPublicKey': base64.b64encode(eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(),
        'nonce': base64.b64encode(nonce).decode(),
        'ciphertext': base64.b64encode(cipher).decode(),
    }


def main():
    recipient = os.environ.get('CHATGPT_INBOX_PUBLIC_KEY', '').strip()
    if not recipient:
        raise SystemExit('CHATGPT_INBOX_PUBLIC_KEY missing')
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    items = pending_items()
    results = []
    for item in items:
        item_id = str(item.get('id') or '')
        source_url = str(item.get('sourceUrl') or '')
        if not item_id or not source_url:
            continue
        inbox = INBOX_DIR / f'{item_id}.json'
        outbox = OUTBOX_DIR / f'{item_id}.json'
        if inbox.exists() or outbox.exists():
            results.append({'id': item_id, 'status': 'skip_existing'})
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='audio-extract-') as td:
                title, raw, source_label, canonical = extract_source(source_url, Path(td))
            raw = clean_text(raw)
            raw, truncated = trim_raw(raw)
            if len(raw) < 400:
                raise RuntimeError('extracted source too short')
            payload = {
                'id': item_id,
                'sourceUrl': source_url,
                'canonicalUrl': canonical,
                'sourceLabel': source_label or item.get('sourceLabel') or 'Web',
                'title': title or item.get('title') or item.get('sourceLabel') or 'Web',
                'rawText': raw,
                'rawTruncated': truncated,
                'extractedAt': datetime.now(timezone.utc).isoformat(),
                'editorPolicy': 'RAW_SOURCE_ONLY_NO_TRANSLATION_NO_SUMMARY_NO_LLM',
            }
            envelope = encrypt_payload(payload, recipient)
            inbox.write_text(json.dumps(envelope, separators=(',', ':')) + '\n', encoding='utf-8')
            results.append({'id': item_id, 'status': 'staged', 'chars': len(raw), 'sourceLabel': payload['sourceLabel']})
        except Exception as e:
            results.append({'id': item_id, 'status': 'error', 'error': str(e)[:500]})
    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
