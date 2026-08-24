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
RUNNER3_SOURCE = 'audio-runner'
CHECKPOINT_PROJECT = 'audio-library-tts'

sys.path.insert(0, str(ROOT / '.github' / 'scripts'))
from runner3_core import get_checkpoint, save_checkpoint  # noqa: E402


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


def payload_sha256(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def checkpoint_for(item_id):
    try:
        return get_checkpoint(CHECKPOINT_PROJECT, item_id)
    except Exception as exc:
        print(f'CHECKPOINT_READ_WARNING item={item_id} error={type(exc).__name__}: {exc}', file=sys.stderr)
        return None


def checkpoint_matches(checkpoint, item_id, digest):
    if not isinstance(checkpoint, dict) or checkpoint.get('status') != 'success':
        return False
    position = checkpoint.get('position')
    return bool(
        isinstance(position, dict)
        and str(position.get('item_id')) == str(item_id)
        and position.get('payload_sha256') == digest
        and position.get('phase') == 'complete'
    )


def remote_artifacts_match(audio_url, transcript_url, script):
    try:
        transcript = requests.get(transcript_url, timeout=30)
        if transcript.status_code >= 400 or transcript.text != script:
            return False
        audio = requests.head(audio_url, allow_redirects=True, timeout=20)
        return 200 <= audio.status_code < 400
    except Exception:
        return False


def save_success_checkpoint(item_id, digest, audio_url, transcript_url, duration_seconds, *, recovered=False):
    position = {
        'phase': 'complete',
        'item_id': item_id,
        'payload_sha256': digest,
        'audio_url': audio_url,
        'transcript_url': transcript_url,
        'duration_seconds': duration_seconds,
        'recovered_from_artifacts': bool(recovered),
    }
    try:
        return save_checkpoint(
            CHECKPOINT_PROJECT,
            RUNNER3_SOURCE,
            scope=item_id,
            status='success',
            position=position,
            last_error=None,
        )
    except Exception as exc:
        print(f'CHECKPOINT_WRITE_WARNING item={item_id} error={type(exc).__name__}: {exc}', file=sys.stderr)
        return None


def save_failure_checkpoint(item_id, digest, exc):
    try:
        save_checkpoint(
            CHECKPOINT_PROJECT,
            RUNNER3_SOURCE,
            scope=item_id,
            status='failure',
            position={
                'phase': 'failed',
                'item_id': item_id,
                'payload_sha256': digest,
            },
            last_error=f'{type(exc).__name__}: {exc}'[:4000],
        )
    except Exception as checkpoint_exc:
        print(
            f'CHECKPOINT_FAILURE_WRITE_WARNING item={item_id} '
            f'error={type(checkpoint_exc).__name__}: {checkpoint_exc}',
            file=sys.stderr,
        )


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

    digest = payload_sha256(payload)
    base = load_json(ROOT / 'ops/r2-media/status.json')['baseUrl'].rstrip('/')
    prefix = f'audio-library/media/{item_id}/'
    audio_url = base + '/' + prefix + 'episode.mp3'
    transcript_url = base + '/' + prefix + 'script.txt'

    checkpoint = checkpoint_for(item_id)
    checkpoint_ok = checkpoint_matches(checkpoint, item_id, digest)
    artifacts_ok = remote_artifacts_match(audio_url, transcript_url, script)
    if checkpoint_ok and artifacts_ok:
        print(json.dumps({'itemId': item_id, 'status': 'skipped', 'reason': 'checkpoint-and-artifacts-match'}))
        return {'itemId': item_id, 'status': 'skipped'}

    if artifacts_ok:
        prior_position = checkpoint.get('position') if isinstance(checkpoint, dict) else None
        prior_duration = prior_position.get('duration_seconds') if isinstance(prior_position, dict) else None
        save_success_checkpoint(
            item_id,
            digest,
            audio_url,
            transcript_url,
            prior_duration,
            recovered=True,
        )
        print(json.dumps({'itemId': item_id, 'status': 'skipped', 'reason': 'artifacts-match-checkpoint-recovered'}))
        return {'itemId': item_id, 'status': 'skipped'}

    try:
        with tempfile.TemporaryDirectory(prefix='chatgpt-audio-') as td:
            work = Path(td)
            script_file = work / 'script.txt'
            script_file.write_text(script, encoding='utf-8')
            mp3 = asyncio.run(synthesize(script, work))
            duration_seconds = duration(mp3)
            r2_put(mp3, prefix + 'episode.mp3', 'audio/mpeg')
            r2_put(script_file, prefix + 'script.txt', 'text/plain; charset=utf-8')
            api('/api/runner/complete', {
                'id': item_id,
                'title': title,
                'sourceLabel': source_label,
                'durationSeconds': duration_seconds,
                'audioUrl': audio_url,
                'transcriptUrl': transcript_url,
                'truncated': False,
            })
            save_success_checkpoint(
                item_id,
                digest,
                audio_url,
                transcript_url,
                duration_seconds,
            )
            print(json.dumps({'itemId': item_id, 'status': 'completed', 'durationSeconds': duration_seconds}))
            return {'itemId': item_id, 'status': 'completed', 'durationSeconds': duration_seconds}
    except Exception as exc:
        save_failure_checkpoint(item_id, digest, exc)
        raise


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: audio_library_tts_from_chatgpt.py payload.json')
    process(sys.argv[1])
