from pathlib import Path

backend = Path('cloudflare/runner3-core/src/ebook-reader-audio.js').read_text()
reader = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js').read_text()

required_backend = [
    'function queuePriorityRank(queue)',
    'const isPrefetch = body?.prefetch === true',
    'const requestPriority = isPrefetch ? "prefetch" : "foreground"',
    'queued.priority = "foreground"',
    'queued.promotedAt = now',
    'priority: requestPriority',
    'queuePriorityRank(queueCache.get(a.key))',
]
for marker in required_backend:
    if marker not in backend:
        raise SystemExit(f'READER_V60_BACKEND_MISSING:{marker}')

required_reader = [
    "clientVersion:'reader-audio-v60-prefetch',prefetch:true",
    "clientVersion:'reader-audio-v60-warm-current',prefetch:true",
    'async function warmCurrentChapter()',
    'warmCurrentTimer=setTimeout(()=>warmCurrentChapter(),650)',
    'warmCurrentChapter();if(currentId())schedulePrefetch();',
    "setTimeout(()=>prefetchOne(1),0)",
    "setTimeout(()=>prefetchOne(2),150)",
]
for marker in required_reader:
    if marker not in reader:
        raise SystemExit(f'READER_V60_READER_MISSING:{marker}')

# Background prefetch must enqueue only. Polling ready for prefetch used to add hundreds
# of status requests and does not help the persistent R2 cache.
prefetch_start = reader.find('async function prefetchOne(offset)')
prefetch_end = reader.find('function schedulePrefetch()', prefetch_start)
if prefetch_start < 0 or prefetch_end < 0:
    raise SystemExit('READER_V60_PREFETCH_FUNCTION_RANGE_MISSING')
prefetch_body = reader[prefetch_start:prefetch_end]
if 'waitPrefetchReady(state.id)' in prefetch_body:
    raise SystemExit('READER_V60_PREFETCH_STILL_POLLS_READY')

# Keep the optimization bounded: exactly two look-ahead submissions.
if 'prefetchOne(3)' in reader or 'peekReadableAhead(3)' in reader:
    raise SystemExit('READER_V60_PREFETCH_UNBOUNDED')

print('READER_V60_AUDIO_PRIORITY_PREFETCH_CHECK=PASS')
