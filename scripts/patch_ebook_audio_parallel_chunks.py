#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/ebook_reader_audio_tts_vps.py')
s = p.read_text(encoding='utf-8')

old = "import signal\nimport sys\nimport tempfile\nimport time\nimport urllib.error\n"
new = "import signal\nimport subprocess\nimport sys\nimport tempfile\nimport time\nimport urllib.error\n"
if old not in s:
    raise SystemExit('import marker missing')
s = s.replace(old, new, 1)

old = '''try:
    MAX_CONCURRENCY = max(1, min(int(os.environ.get("EBOOK_AUDIO_VPS_CONCURRENCY", "2")), 4))
except (TypeError, ValueError):
    MAX_CONCURRENCY = 2

STOP = False
'''
new = '''try:
    MAX_CONCURRENCY = max(1, min(int(os.environ.get("EBOOK_AUDIO_VPS_CONCURRENCY", "2")), 4))
except (TypeError, ValueError):
    MAX_CONCURRENCY = 2
try:
    TTS_CHUNK_CONCURRENCY = max(1, min(int(os.environ.get("EBOOK_AUDIO_TTS_CHUNK_CONCURRENCY", "2")), 3))
except (TypeError, ValueError):
    TTS_CHUNK_CONCURRENCY = 2

STOP = False
'''
if old not in s:
    raise SystemExit('concurrency marker missing')
s = s.replace(old, new, 1)

marker = 'def process_job(job):\n'
helper = r'''async def synthesize_parallel(script, work):
    """Synthesize independent TTS chunks concurrently, preserving order and timing."""
    chunks = base.tts_chunks(script)
    if not chunks:
        raise RuntimeError("Empty Ebook audio script")
    if len(chunks) == 1 or TTS_CHUNK_CONCURRENCY <= 1:
        return await base.synthesize(script, work)

    semaphore = asyncio.Semaphore(TTS_CHUNK_CONCURRENCY)

    async def render(index, text):
        part = work / f"part-{index:04d}.mp3"
        async with semaphore:
            boundaries = await base.synthesize_part(text, part)
        seconds = base.media_duration(part)
        return index, part, seconds, boundaries

    rendered = await asyncio.gather(*(render(index, text) for index, text in enumerate(chunks)))
    rendered.sort(key=lambda row: row[0])

    parts = []
    words = []
    base_ms = 0.0
    for _index, part, part_seconds, boundaries in rendered:
        for event in boundaries:
            start_ms = base_ms + event["offsetMs"]
            duration_ms = max(0.0, event["durationMs"])
            words.append({
                "text": event["text"],
                "startMs": round(start_ms, 3),
                "durationMs": round(duration_ms, 3),
                "endMs": round(start_ms + duration_ms, 3),
            })
        base_ms += part_seconds * 1000.0
        parts.append(part)

    concat_file = work / "concat.txt"
    concat_file.write_text("".join(f"file '{part.resolve()}'\n" for part in parts), encoding="utf-8")
    output = work / "episode.mp3"
    subprocess.check_call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(output),
    ])
    output_seconds = base.media_duration(output)
    if base_ms > 0 and output_seconds > 0:
        scale = output_seconds * 1000.0 / base_ms
        if abs(scale - 1.0) > 0.000001:
            for word in words:
                start = float(word["startMs"]) * scale
                duration_ms = float(word["durationMs"]) * scale
                word["startMs"] = round(start, 3)
                word["durationMs"] = round(duration_ms, 3)
                word["endMs"] = round(start + duration_ms, 3)
    return output, output_seconds, words, len(chunks)


def process_job(job):
'''
if marker not in s:
    raise SystemExit('process marker missing')
s = s.replace(marker, helper, 1)

old = '        mp3, seconds, words, chunks = asyncio.run(base.synthesize(script, work))\n'
new = '        mp3, seconds, words, chunks = asyncio.run(synthesize_parallel(script, work))\n'
if old not in s:
    raise SystemExit('synthesize call marker missing')
s = s.replace(old, new, 1)

old = '''        "chunkCount": chunks,
        "renderSeconds": elapsed,
        "status": "ready",
'''
new = '''        "chunkCount": chunks,
        "chunkConcurrency": TTS_CHUNK_CONCURRENCY,
        "renderSeconds": elapsed,
        "status": "ready",
'''
if old not in s:
    raise SystemExit('result marker missing')
s = s.replace(old, new, 1)

old = '''                "concurrency": MAX_CONCURRENCY,
                "pid": os.getpid(),
'''
new = '''                "concurrency": MAX_CONCURRENCY,
                "chunkConcurrency": TTS_CHUNK_CONCURRENCY,
                "pid": os.getpid(),
'''
if old not in s:
    raise SystemExit('consumer start marker missing')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
