from pathlib import Path

AUDIO = Path('cloudflare/runner3-core/src/ebook-reader-audio.js')
V34 = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')

a = AUDIO.read_text()
v = V34.read_text()

if 'PREFETCH_QUEUE_PREFIX' not in a:
    needle = 'const QUEUE_PREFIX = "audio-library/ebook-reader-queue/";\n'
    if needle not in a:
        raise SystemExit('V60_AUDIO_QUEUE_PREFIX_ANCHOR_MISSING')
    a = a.replace(
        needle,
        needle
        + 'const FOREGROUND_QUEUE_PREFIX = "audio-library/ebook-reader-queue-foreground/";\n'
        + 'const PREFETCH_QUEUE_PREFIX = "audio-library/ebook-reader-queue-prefetch/";\n',
        1,
    )

    needle = 'function queueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }\n'
    replacement = '''function queueKey(id, priority = "foreground") {
  const prefix = priority === "prefetch" ? PREFETCH_QUEUE_PREFIX : FOREGROUND_QUEUE_PREFIX;
  return `${prefix}${id}.json`;
}
function legacyQueueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }
async function deleteQueueKeys(env, id) {
  await Promise.all([
    env.AUDIO_MEDIA.delete(queueKey(id, "foreground")),
    env.AUDIO_MEDIA.delete(queueKey(id, "prefetch")),
    env.AUDIO_MEDIA.delete(legacyQueueKey(id)),
  ]);
}
'''
    if needle not in a:
        raise SystemExit('V60_AUDIO_QUEUE_KEY_ANCHOR_MISSING')
    a = a.replace(needle, replacement, 1)

    start = a.find('async function nextInternalJob(env) {')
    end = a.find('\nasync function handleInternal(', start)
    if start < 0 or end < 0:
        raise SystemExit('V60_AUDIO_NEXT_JOB_ANCHOR_MISSING')
    replacement = '''async function claimInternalQueuePrefix(env, prefix) {
  const listing = await env.AUDIO_MEDIA.list({ prefix, limit: CLAIM_SCAN_LIMIT });
  const objects = [...(listing.objects || [])].sort((x, y) => String(x.uploaded || "").localeCompare(String(y.uploaded || "")));
  for (const object of objects) {
    const queue = await getJson(env.AUDIO_MEDIA, object.key);
    if (!queue || queue.kind !== "ebook-reader" || !idValid(queue.id)) {
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    const item = await getJson(env.AUDIO_MEDIA, queue.itemKey || itemKey(queue.id));
    if (!item || item.kind !== "ebook-reader" || item.status === "ready" || item.status === "error") {
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    if (item.status === "processing" && processingLeaseFresh(item)) {
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    const scriptObject = await env.AUDIO_MEDIA.get(queue.scriptKey || `${mediaPrefix(queue.id)}script.txt`);
    if (!scriptObject) {
      item.status = "error";
      item.error = "Audio script missing";
      item.updatedAt = new Date().toISOString();
      await putJson(env.AUDIO_MEDIA, itemKey(queue.id), item);
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    const script = await scriptObject.text();
    const now = new Date().toISOString();
    const priority = queue.priority === "prefetch" || prefix === PREFETCH_QUEUE_PREFIX ? "prefetch" : "foreground";
    item.status = "processing";
    item.priority = priority;
    item.error = null;
    item.processingAt = now;
    item.updatedAt = now;
    await putJson(env.AUDIO_MEDIA, itemKey(queue.id), item);
    await env.AUDIO_MEDIA.delete(object.key);
    return { ...queue, priority, script };
  }
  return null;
}

async function nextInternalJob(env) {
  // User-visible playback must always beat speculative work. Legacy queue
  // entries are drained before the low-priority prefetch lane.
  for (const prefix of [FOREGROUND_QUEUE_PREFIX, QUEUE_PREFIX, PREFETCH_QUEUE_PREFIX]) {
    const job = await claimInternalQueuePrefix(env, prefix);
    if (job) return job;
  }
  return null;
}
'''
    a = a[:start] + replacement + a[end:]

    a = a.replace('await env.AUDIO_MEDIA.delete(queueKey(bodyId));', 'await deleteQueueKeys(env, bodyId);')

    start = a.find('  if (route.kind === "status" && request.method === "POST") {')
    end = a.find('\n  const bookKey = normalizeBookKey(url.searchParams.get("bookKey"));', start)
    if start < 0 or end < 0:
        raise SystemExit('V60_AUDIO_PUBLIC_POST_ANCHOR_MISSING')
    replacement = '''  if (route.kind === "status" && request.method === "POST") {
    const body = await request.json().catch(() => ({}));
    const bookKey = normalizeBookKey(body?.bookKey);
    if (!bookKey) return json({ ok: false, error: "BOOK_KEY_REQUIRED" }, 400);
    if (!validFinalEpubKey(bookKey)) return json({ ok: false, error: "FINAL_EPUB_ONLY" }, 403);
    const script = normalizeSpeechText(body?.text);
    if (script.length < 80) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_SHORT" }, 422);
    if (script.length > MAX_SCRIPT_CHARS) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_LONG" }, 413);

    const requestedPriority = body?.prefetch === true ? "prefetch" : "foreground";
    const textSha256 = await sha256Hex(script);
    const id = await audioId(bookKey, textSha256);
    const key = itemKey(id);
    const prefix = mediaPrefix(id);
    const existing = await getJson(env.AUDIO_MEDIA, key);
    const now = new Date().toISOString();
    const queueFor = (priority) => ({
      id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix,
      audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, priority, createdAt: now,
    });

    if (existing && existing.kind === "ebook-reader" && existing.bookKey === bookKey && existing.textSha256 === textSha256) {
      if (existing.status === "ready") return json(await publicStateWithMedia(env, existing));

      if (existing.status === "pending") {
        // Opening/playing a chapter that was only prefetched promotes the exact
        // job rather than creating duplicate TTS work.
        if (requestedPriority === "foreground" && existing.priority !== "foreground") {
          existing.priority = "foreground";
          existing.updatedAt = now;
          await putJson(env.AUDIO_MEDIA, key, existing);
          await env.AUDIO_MEDIA.delete(queueKey(id, "prefetch"));
          await env.AUDIO_MEDIA.delete(legacyQueueKey(id));
          await putJson(env.AUDIO_MEDIA, queueKey(id, "foreground"), queueFor("foreground"));
        }
        return json(publicState(existing));
      }

      if (existing.status === "processing" && processingLeaseFresh(existing)) {
        return json(await publicStateWithMedia(env, existing));
      }

      if (existing.status === "processing") {
        await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, { httpMetadata: { contentType: "text/plain; charset=utf-8" }, customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION } });
        const recoveredPriority = requestedPriority === "foreground" || existing.priority === "foreground" ? "foreground" : "prefetch";
        existing.status = "pending";
        existing.priority = recoveredPriority;
        existing.error = null;
        existing.processingAt = null;
        existing.updatedAt = now;
        await putJson(env.AUDIO_MEDIA, key, existing);
        await deleteQueueKeys(env, id);
        await putJson(env.AUDIO_MEDIA, queueKey(id, recoveredPriority), queueFor(recoveredPriority));
        return json(publicState(existing), 202);
      }
    }

    await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, { httpMetadata: { contentType: "text/plain; charset=utf-8" }, customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION } });
    const item = {
      id, kind: "ebook-reader", bookKey,
      chapterTitle: String(body?.chapterTitle || "").trim().slice(0, 240) || null,
      chapterHref: String(body?.chapterHref || "").trim().slice(0, 600) || null,
      title: String(body?.bookTitle || "Ebook").trim().slice(0, 240) || "Ebook",
      sourceLabel: "Ebook Library", status: "pending", priority: requestedPriority,
      createdAt: existing?.createdAt || now, updatedAt: now,
      expiresAt: null, pinned: true, durationSeconds: null, progressSeconds: 0, audioUrl: null, transcriptUrl: null, timingUrl: null,
      mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, error: null,
    };
    await putJson(env.AUDIO_MEDIA, key, item);
    await deleteQueueKeys(env, id);
    await putJson(env.AUDIO_MEDIA, queueKey(id, requestedPriority), queueFor(requestedPriority));
    return json(publicState(item), 202);
  }
'''
    a = a[:start] + replacement + a[end:]

if 'reader-audio-v60-prefetch' not in v:
    v = v.replace('    prefetchReady:0,\n', '    prefetchReady:0,\n    prefetchEnqueued:0,\n', 1)
    start = v.find('  async function waitPrefetchReady(id){')
    end = v.find('\n  function schedulePrefetch(){', start)
    if start < 0 or end < 0:
        raise SystemExit('V60_V34_PREFETCH_BLOCK_ANCHOR_MISSING')
    replacement = '''  async function prefetchOne(offset){
    const key='ahead:'+offset;
    if(prefetching.has(key))return prefetching.get(key);
    const task=(async()=>{
      const b=bridge();
      if(!b||typeof b.peekReadableAhead!=='function')return null;
      const payload=await b.peekReadableAhead(offset);
      if(!payload||!payload.text||String(payload.text).length<80||!payload.chapterHref)return null;
      const existing=prefetchCache.get(payload.chapterHref);
      if(existing&&existing.state&&['ready','pending','processing'].includes(String(existing.state.status||'')))return existing;
      debug.prefetchRequests++;
      debug.lastPrefetchChapter=payload.chapterHref;
      const response=await rawFetch('/artifact-library/audio',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',prefetch:true,clientVersion:'reader-audio-v60-prefetch'})});
      const state=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(state.error||('HTTP_'+response.status));
      if(!state.id)throw new Error('PREFETCH_ID_MISSING');
      const value={payload,state,canonical:canonical(payload.text),queuedAt:Date.now()};
      prefetchCache.set(payload.chapterHref,value);
      if(state.status==='ready'&&state.mediaUrl&&state.timingUrl)debug.prefetchReady++;
      else debug.prefetchEnqueued++;
      return value;
    })().catch(error=>{debug.lastError=String(error&&error.message||error||'prefetch failed').slice(0,180);return null;}).finally(()=>prefetching.delete(key));
    prefetching.set(key,task);
    return task;
  }
'''
    v = v[:start] + replacement + v[end:]

AUDIO.write_text(a)
V34.write_text(v)
print('READER_V60_AUDIO_PRIORITY_PREFETCH_PATCH=PASS')
