#!/usr/bin/env python3
import json
import os
from urllib.parse import quote

import requests

CORE_URL = os.environ.get('RUNNER3_CORE_URL', 'https://runner3-core.ducduy2411.workers.dev').rstrip('/')
TOKEN = os.environ.get('RUNNER3_CORE_TOKEN', '').strip()
SOURCE = os.environ.get('RUNNER3_SOURCE', 'audio-library-public-workflow')[:200]
AUDIO_PREFIX = 'audio-library/'


def _headers(content_type=None):
    if not TOKEN:
        raise RuntimeError('RUNNER3_CORE_TOKEN missing')
    headers = {
        'Authorization': 'Bearer ' + TOKEN,
        'X-Runner3-Source': SOURCE,
        'Accept': 'application/json',
    }
    if content_type:
        headers['Content-Type'] = content_type
    return headers


def _key(key):
    value = str(key or '').lstrip('/')
    if not value.startswith(AUDIO_PREFIX):
        raise ValueError('audio key must start with audio-library/')
    if '\\' in value or any(part in ('.', '..') for part in value.split('/')):
        raise ValueError('invalid audio key')
    return value


def _url_for_key(key):
    return CORE_URL + '/audio-media/' + quote(_key(key), safe='/')


def list_objects(prefix=AUDIO_PREFIX, limit=1000):
    prefix = _key(prefix)
    out = []
    cursor = None
    remaining = max(1, int(limit))
    while remaining > 0:
        page_limit = min(1000, remaining)
        params = {'prefix': prefix, 'limit': page_limit}
        if cursor:
            params['cursor'] = cursor
        response = requests.get(CORE_URL + '/audio-media', headers=_headers(), params=params, timeout=45)
        response.raise_for_status()
        data = response.json()
        rows = data.get('objects') or []
        out.extend(rows)
        remaining -= len(rows)
        cursor = data.get('cursor') if data.get('truncated') else None
        if not cursor or not rows:
            break
    return out


def get_bytes(key):
    response = requests.get(_url_for_key(key), headers=_headers(), timeout=45)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def get_json(key):
    raw = get_bytes(key)
    if raw is None:
        return None
    return json.loads(raw.decode('utf-8'))


def put_bytes(key, payload, content_type='application/octet-stream'):
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    response = requests.put(
        _url_for_key(key),
        headers=_headers(content_type),
        data=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def put_json(key, value):
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return put_bytes(key, payload, 'application/json; charset=utf-8')


def delete(key):
    response = requests.delete(_url_for_key(key), headers=_headers(), timeout=45)
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True


def reddit_source(url):
    response = requests.post(
        CORE_URL + '/audio-reddit/source',
        headers=_headers('application/json'),
        json={'url': str(url)},
        timeout=90,
    )
    try:
        data = response.json()
    except Exception:
        data = {'ok': False, 'error': f'non-json:{response.status_code}:{len(response.content)}'}
    if response.status_code not in (200, 502):
        response.raise_for_status()
    return response.status_code, data
