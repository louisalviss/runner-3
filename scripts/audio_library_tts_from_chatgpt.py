#!/usr/bin/env python3
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
import requests

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
VOICE = os.environ.get('AUDIO_LIBRARY_VOICE', 'vi-VN-NamMinhNeural')
VOICE_RATE = os.environ.get('AUDIO_LIBRARY_VOICE_RATE', '+3%')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def runner_token():
    raw = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not raw:
        raise RuntimeError('CLOUDFLARE_API_TOKEN missing')
    return hashlib.sha256(raw.encode()).hexdigest()


def worker_url():
    return load_json(ROOT / 'ops/audio-library/status.json')['url'].rstrip('/')


def api(path, payload):
    r = requests.post(worker_url() + path, json=payload, headers={'X-Runner-Token': runner_token()}, timeout=45)
    if r.status_code >= 400:
        raise RuntimeError(f'Worker API {r.status_code}: {r.text[:300]}')
    return r.json() if r.content else None


def tts_chunks(text, limit=3200):
    sentences = re.split(r'(?<=[.!?…])\s+|\n+', text)
    chunks, buf = [], ''
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(buf) + len(sentence) + 1 <= limit:
            buf = (buf + ' ' + sentence).strip()
            continue
        if buf:
            chunks.append(buf)
        while len(sentence) > limit:
            cut = sentence.rfind(' ', 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        buf = sentence
    if buf:
        chunks.append(buf)
    return chunks


async def synthesize(text, work):
    parts = []
    for idx, chunk in enumerate(tts_chunks(text)):
        path = work / f'part-{idx:03d}.mp3'
        await edge_tts.Communicate(chunk, VOICE, rate=VOICE_RATE).save(str(path))
        if not path.exists() or path.stat().st_size < 1500:
            raise RuntimeError(f'TTS part {idx} too small')
        parts.append(path)
    concat = work / 'concat.txt'
    concat.write_text(''.join(f"file '{p.resolve()}'\n" for p in parts), encoding='utf-8')
    out = work / 'episode.mp3'
    subprocess.check_call(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c:a','libmp3lame','-b:a','128k','-ar','44100',str(out)])
    return out


def duration(path):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(path)], text=True).strip())


def r2_put(file, key, content_type):
    subprocess.check_call(['npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',f'--file={file}',f'--content-type={content_type}','--remote'], cwd=ROOT)


def process(payload_path):
    payload = load_json(payload_path)
    item_id = str(payload['id'])
    title = str(payload.get('title') or 'Audio').strip()[:240]
    source_label = str(payload.get('sourceLabel') or 'Web').strip()[:80]
    script = str(payload.get('script') or '').strip()
    if len(script) < 300:
        raise RuntimeError('ChatGPT script too short')
    base = load_json(ROOT / 'ops/r2-media/status.json')['baseUrl'].rstrip('/')
    prefix = f'audio-library/media/{item_id}/'
    with tempfile.TemporaryDirectory(prefix='chatgpt-audio-') as td:
        work = Path(td)
        script_file = work / 'script.txt'
        script_file.write_text(script, encoding='utf-8')
        mp3 = asyncio.run(synthesize(script, work))
        r2_put(mp3, prefix + 'episode.mp3', 'audio/mpeg')
        r2_put(script_file, prefix + 'script.txt', 'text/plain; charset=utf-8')
        api('/api/runner/complete', {
            'id': item_id,
            'title': title,
            'sourceLabel': source_label,
            'durationSeconds': duration(mp3),
            'audioUrl': base + '/' + prefix + 'episode.mp3',
            'transcriptUrl': base + '/' + prefix + 'script.txt',
            'truncated': False,
        })


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: audio_library_tts_from_chatgpt.py payload.json')
    process(sys.argv[1])
