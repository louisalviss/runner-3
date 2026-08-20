#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / 'ops/audio-library/chatgpt-bridge-status.json'
INBOX_DIR = ROOT / 'ops/audio-library/chatgpt-inbox'
OUTBOX_DIR = ROOT / 'ops/audio-library/chatgpt-outbox'
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
MAX_ITEMS = int(os.environ.get('AUDIO_LIBRARY_EXTRACT_MAX_ITEMS', '3'))
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'
UA = 'Runner3AudioCloudflareRelay/1.0'


def bridge_status():
    return json.loads(STATUS_PATH.read_text(encoding='utf-8'))


def bridge_url():
    return str(bridge_status()['url']).rstrip('/')


def queue_token():
    token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not token:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    return hashlib.sha256(b'runner3-chatgpt-queue-v2\0' + token.encode()).hexdigest()


def pending_items():
    r = requests.get(
        bridge_url() + '/pending',
        params={'token': queue_token()},
        headers={'User-Agent': UA},
        timeout=40,
    )
    r.raise_for_status()
    return (r.json().get('items') or [])[:MAX_ITEMS]


def encrypt_payload(payload: dict, recipient_b64: str):
    recipient = X25519PublicKey.from_public_bytes(base64.b64decode(recipient_b64))
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(recipient)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'runner3-audio-library-inbox-v1',
    ).derive(shared)
    item_id = str(payload['id'])
    nonce = secrets.token_bytes(12)
    plain = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    cipher = ChaCha20Poly1305(key).encrypt(nonce, plain, item_id.encode())
    return {
        'v': 1,
        'id': item_id,
        'ephemeralPublicKey': base64.b64encode(
            eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ).decode(),
        'nonce': base64.b64encode(nonce).decode(),
        'ciphertext': base64.b64encode(cipher).decode(),
    }


def wrangler_get(key: str):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run = subprocess.run(
            ['npx', '-y', 'wrangler@4.123.0', 'r2', 'object', 'get', f'{BUCKET}/{key}', f'--file={path}', '--remote'],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if run.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)


def wrangler_put(key: str, value: dict):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        json.dump(value, tmp, ensure_ascii=False, separators=(',', ':'))
        path = Path(tmp.name)
    try:
        subprocess.check_call(
            [
                'npx', '-y', 'wrangler@4.123.0', 'r2', 'object', 'put', f'{BUCKET}/{key}',
                f'--file={path}', '--content-type=application/json; charset=utf-8', '--remote',
            ],
            cwd=ROOT,
        )
    finally:
        path.unlink(missing_ok=True)


def update_canonical(item_id: str, original_url: str, canonical_url: str):
    if not canonical_url or '/comments/' not in canonical_url:
        return False
    item_key = f'{ITEM_PREFIX}{item_id}.json'
    queue_key = f'{QUEUE_PREFIX}{item_id}.json'
    item = wrangler_get(item_key)
    if item:
        item['sharedUrl'] = item.get('sharedUrl') or original_url
        item['sourceUrl'] = canonical_url
        item['canonicalUrl'] = canonical_url
        item['error'] = None
        item['updatedAt'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        wrangler_put(item_key, item)
    queue = wrangler_get(queue_key)
    if queue:
        queue['sharedUrl'] = queue.get('sharedUrl') or original_url
        queue['sourceUrl'] = canonical_url
        wrangler_put(queue_key, queue)
    return bool(item or queue)


def safe_diagnostics(data):
    out = []
    for entry in (data.get('diagnostics') or [])[:12]:
        text = str(entry)
        # Never publish source/canonical URLs in workflow checkpoints.
        if 'http://' in text or 'https://' in text:
            text = text.split(':', 2)[0] + ':url-redacted'
        out.append(text[:120])
    return out


def main():
    recipient = os.environ.get('CHATGPT_INBOX_PUBLIC_KEY', '').strip()
    if not recipient:
        raise SystemExit('CHATGPT_INBOX_PUBLIC_KEY missing')
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for item in pending_items():
        item_id = str(item.get('id') or '')
        source_url = str(item.get('sourceUrl') or '')
        if not item_id or 'reddit.com' not in source_url.lower():
            continue
        inbox = INBOX_DIR / f'{item_id}.json'
        outbox = OUTBOX_DIR / f'{item_id}.json'
        if inbox.exists() or outbox.exists():
            results.append({'id': item_id, 'status': 'skip_existing'})
            continue
        try:
            response = requests.post(
                bridge_url() + '/source/reddit',
                params={'token': queue_token()},
                json={'url': source_url},
                headers={'User-Agent': UA, 'Accept': 'application/json'},
                timeout=75,
            )
            try:
                data = response.json()
            except Exception:
                data = {'ok': False, 'diagnostics': [f'non-json:{response.status_code}:{len(response.content)}']}

            canonical = str(data.get('canonicalUrl') or '')
            raw = str(data.get('rawText') or '')
            if data.get('ok') and len(raw) >= 400:
                payload = {
                    'id': item_id,
                    'sourceUrl': source_url,
                    'canonicalUrl': canonical or source_url,
                    'sourceLabel': 'Reddit',
                    'title': str(data.get('title') or item.get('title') or 'Reddit'),
                    'rawText': raw,
                    'rawTruncated': False,
                    'extractedAt': datetime.now(timezone.utc).isoformat(),
                    'extractTransport': 'cloudflare-worker-egress',
                    'editorPolicy': 'RAW_SOURCE_ONLY_NO_TRANSLATION_NO_SUMMARY_NO_LLM',
                }
                envelope = encrypt_payload(payload, recipient)
                inbox.write_text(json.dumps(envelope, separators=(',', ':')) + '\n', encoding='utf-8')
                update_canonical(item_id, source_url, canonical)
                results.append({
                    'id': item_id,
                    'status': 'staged',
                    'chars': len(raw),
                    'canonicalResolved': bool(canonical),
                    'transport': 'cloudflare-worker-egress',
                })
                continue

            updated = update_canonical(item_id, source_url, canonical) if canonical else False
            results.append({
                'id': item_id,
                'status': 'canonical_only' if canonical else 'unresolved',
                'httpStatus': response.status_code,
                'canonicalResolved': bool(canonical),
                'r2Updated': updated,
                'diagnostics': safe_diagnostics(data),
            })
        except Exception as error:
            results.append({'id': item_id, 'status': 'error', 'error': type(error).__name__})
    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))


if __name__ == '__main__':
    main()
