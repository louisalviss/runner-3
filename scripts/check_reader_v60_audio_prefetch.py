from pathlib import Path

backend = Path('cloudflare/runner3-core/src/ebook-reader-audio.js').read_text()
reader = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js').read_text()
v35 = Path('cloudflare/runner3-core/artifact-library-reader-v35-continuity-single-owner-entry.js').read_text()

required_backend = [
    'const FOREGROUND_QUEUE_PREFIX = "audio-library/ebook-reader-queue-foreground/";',
    'const PREFETCH_QUEUE_PREFIX = "audio-library/ebook-reader-queue-prefetch/";',
    'for (const prefix of [FOREGROUND_QUEUE_PREFIX, QUEUE_PREFIX, PREFETCH_QUEUE_PREFIX])',
    'const requestedPriority = body?.prefetch === true ? "prefetch" : "foreground";',
    'await env.AUDIO_MEDIA.delete(queueKey(id, "prefetch"));',
    'await putJson(env.AUDIO_MEDIA, queueKey(id, "foreground"), queueFor("foreground"));',
    'priority: requestedPriority',
    'await deleteQueueKeys(env, id);',
]
for marker in required_backend:
    if marker not in backend:
        raise SystemExit(f'READER_V60_BACKEND_MISSING:{marker}')

required_reader = [
    "clientVersion:'reader-audio-v60-prefetch'",
    "clientVersion:'reader-audio-v60-warm-current'",
    'prefetch:true',
    'async function warmCurrentChapter()',
    'warmCurrentTimer=setTimeout(()=>warmCurrentChapter(),650)',
    'warmCurrentChapter();if(currentId())schedulePrefetch();',
    'prefetchEnqueued:0',
    "setTimeout(()=>prefetchOne(1),0)",
    "setTimeout(()=>prefetchOne(2),150)",
]
for marker in required_reader:
    if marker not in reader:
        raise SystemExit(f'READER_V60_READER_MISSING:{marker}')

# v35 deliberately owns runtime event listeners, but its replacement contract
# must continue to include warm-current so the v34 patch composes cleanly.
required_v35 = [
    'manualArmedAt=Date.now();tick();warmCurrentChapter();if(currentId())schedulePrefetch();',
    'manualArmedAt=Date.now();tick();warmCurrentChapter();armCurrentMedia();',
    "out = replaceScoped(out, V34_MARKER, oldRuntime, newRuntime, 'single-audio-owner');",
]
for marker in required_v35:
    if marker not in v35:
        raise SystemExit(f'READER_V60_V35_COMPOSITION_MISSING:{marker}')

# Background speculative work must enqueue once and return. Poll-until-ready
# would create hundreds of requests and defeats the purpose of R2 persistence.
prefetch_start = reader.find('async function prefetchOne(offset)')
prefetch_end = reader.find('function schedulePrefetch()', prefetch_start)
if prefetch_start < 0 or prefetch_end < 0:
    raise SystemExit('READER_V60_PREFETCH_FUNCTION_RANGE_MISSING')
prefetch_body = reader[prefetch_start:prefetch_end]
if 'waitPrefetchReady' in prefetch_body or 'await new Promise(resolve=>setTimeout(resolve,1500))' in prefetch_body:
    raise SystemExit('READER_V60_PREFETCH_STILL_POLLS_READY')

# Keep speculative load bounded at current + exactly two chapters ahead.
if 'prefetchOne(3)' in reader or 'peekReadableAhead(3)' in reader:
    raise SystemExit('READER_V60_PREFETCH_UNBOUNDED')

# The foreground lane must be checked before prefetch, otherwise an old queue
# can still make the user wait behind speculative jobs.
order = backend.find('for (const prefix of [FOREGROUND_QUEUE_PREFIX, QUEUE_PREFIX, PREFETCH_QUEUE_PREFIX])')
if order < 0:
    raise SystemExit('READER_V60_FOREGROUND_ORDER_MISSING')

print('READER_V60_AUDIO_PRIORITY_PREFETCH_CHECK=PASS')
