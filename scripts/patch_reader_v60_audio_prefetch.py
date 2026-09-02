from pathlib import Path

p = Path('cloudflare/runner3-core/reader-audio-core/browser-production-integration.js')
s = p.read_text()

needle = """  async function prepareCurrent() {\n"""
if needle not in s:
    raise SystemExit('V60_MISSING_PREPARE_CURRENT')

insert = r'''  const R3_AUDIO_PREFETCH_AHEAD_V60 = 2;
  const r3AudioPrefetchSeenV60 = new Map();

  function r3AudioPrefetchKeyV60(bookKey, href, text) {
    return `${bookKey}::${href || ''}::${String(text || '').slice(0, 160)}`;
  }

  async function r3AudioPrefetchChapterV60(payload) {
    const text = String(payload?.text || '').trim();
    const bookKey = String(payload?.bookKey || '').trim();
    const chapterHref = String(payload?.chapterHref || '').trim();
    if (!bookKey || text.length < 80) return;
    const key = r3AudioPrefetchKeyV60(bookKey, chapterHref, text);
    const now = Date.now();
    const seenAt = Number(r3AudioPrefetchSeenV60.get(key) || 0);
    if (seenAt && now - seenAt < 6 * 60 * 60 * 1000) return;
    r3AudioPrefetchSeenV60.set(key, now);
    try {
      await fetch('/artifact-library/audio', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          bookKey,
          text,
          chapterTitle: payload.chapterTitle || null,
          chapterHref: chapterHref || null,
          bookTitle: payload.bookTitle || 'Ebook',
          prefetch: true,
        }),
        credentials: 'same-origin',
        cache: 'no-store',
        keepalive: false,
      });
    } catch (_) {
      // Prefetch is best-effort and must never affect current playback.
    }
  }

  async function r3AudioPrefetchNextV60(current) {
    const bridge = window.r3ReaderBridge || {};
    if (typeof bridge.getAdjacentChapterAudioPayloads !== 'function') return;
    let next = [];
    try {
      next = await bridge.getAdjacentChapterAudioPayloads(R3_AUDIO_PREFETCH_AHEAD_V60);
    } catch (_) {
      return;
    }
    if (!Array.isArray(next) || !next.length) return;
    for (const payload of next.slice(0, R3_AUDIO_PREFETCH_AHEAD_V60)) {
      // Sequential submission deliberately avoids queue bursts on the VPS consumer.
      await r3AudioPrefetchChapterV60(payload);
    }
  }

'''
s = s.replace(needle, insert + needle, 1)

# After current chapter reaches ready, fire background prefetch without delaying playback.
ready_needles = [
    "return ready;",
    "return result;",
]
patched = False
for rn in ready_needles:
    if rn in s:
        s = s.replace(rn, "queueMicrotask(() => { r3AudioPrefetchNextV60(current).catch(() => {}); });\n    " + rn, 1)
        patched = True
        break
if not patched:
    # Safer fallback: schedule once prepareCurrent has obtained current payload, before normal logic continues.
    marker = "const current ="
    idx = s.find(marker, s.find("async function prepareCurrent"))
    if idx < 0:
        raise SystemExit('V60_MISSING_CURRENT_PAYLOAD')
    line_end = s.find('\n', idx)
    s = s[:line_end+1] + "    queueMicrotask(() => { r3AudioPrefetchNextV60(current).catch(() => {}); });\n" + s[line_end+1:]

p.write_text(s)
print('READER_V60_AUDIO_PREFETCH_PATCH=PASS')
