from pathlib import Path

backend = Path('cloudflare/runner3-core/src/ebook-reader-audio.js')
reader = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')

b = backend.read_text()
r = reader.read_text()

# --- Backend priority model -------------------------------------------------
lease = '''function processingLeaseFresh(item, nowMs = Date.now()) {
  const leaseAt = Date.parse(String(item?.processingAt || item?.updatedAt || ""));
  return Number.isFinite(leaseAt) && nowMs - leaseAt < PROCESSING_LEASE_MS;
}
'''
if lease not in b:
    raise SystemExit('V60_BACKEND_MISSING_PROCESSING_LEASE')
b = b.replace(lease, lease + '''\nfunction queuePriorityRank(queue) {
  // Legacy queue entries are treated as foreground. Only explicit prefetch is low priority.
  return String(queue?.priority || "foreground") === "prefetch" ? 1 : 0;
}
''', 1)

job_head = '''async function nextInternalJob(env) {
  const listing = await env.AUDIO_MEDIA.list({ prefix: QUEUE_PREFIX, limit: CLAIM_SCAN_LIMIT });
  const objects = [...(listing.objects || [])].sort((a, b) => String(a.uploaded || "").localeCompare(String(b.uploaded || "")));
  for (const object of objects) {
    const queue = await getJson(env.AUDIO_MEDIA, object.key);
'''
job_new = '''async function nextInternalJob(env) {
  const listing = await env.AUDIO_MEDIA.list({ prefix: QUEUE_PREFIX, limit: CLAIM_SCAN_LIMIT });
  const objects = [...(listing.objects || [])];
  const queueCache = new Map();
  for (const object of objects) queueCache.set(object.key, await getJson(env.AUDIO_MEDIA, object.key));
  objects.sort((a, b) => {
    const priority = queuePriorityRank(queueCache.get(a.key)) - queuePriorityRank(queueCache.get(b.key));
    if (priority) return priority;
    return String(a.uploaded || "").localeCompare(String(b.uploaded || ""));
  });
  for (const object of objects) {
    const queue = queueCache.get(object.key);
'''
if job_head not in b:
    raise SystemExit('V60_BACKEND_MISSING_JOB_HEAD')
b = b.replace(job_head, job_new, 1)

body_anchor = '''    const body = await request.json().catch(() => ({}));
    const bookKey = normalizeBookKey(body?.bookKey);
'''
body_new = '''    const body = await request.json().catch(() => ({}));
    const clientVersion = String(body?.clientVersion || "");
    const isPrefetch = body?.prefetch === true || /prefetch|warm-current/i.test(clientVersion);
    const requestPriority = isPrefetch ? "prefetch" : "foreground";
    const bookKey = normalizeBookKey(body?.bookKey);
'''
if body_anchor not in b:
    raise SystemExit('V60_BACKEND_MISSING_PUBLIC_BODY')
b = b.replace(body_anchor, body_new, 1)

existing_anchor = '''    if (existing && existing.kind === "ebook-reader" && existing.bookKey === bookKey && existing.textSha256 === textSha256) {
      if (existing.status === "ready" || existing.status === "pending" || (existing.status === "processing" && processingLeaseFresh(existing))) {
        return json(await publicStateWithMedia(env, existing));
      }
      if (existing.status === "processing") {
'''
existing_new = '''    if (existing && existing.kind === "ebook-reader" && existing.bookKey === bookKey && existing.textSha256 === textSha256) {
      if (existing.status === "ready") return json(await publicStateWithMedia(env, existing));
      if (existing.status === "pending") {
        if (requestPriority === "foreground" && existing.requestPriority !== "foreground") {
          existing.requestPriority = "foreground";
          existing.updatedAt = now;
          const queued = await getJson(env.AUDIO_MEDIA, queueKey(id));
          if (queued) {
            queued.priority = "foreground";
            queued.promotedAt = now;
            await putJson(env.AUDIO_MEDIA, queueKey(id), queued);
          }
          await putJson(env.AUDIO_MEDIA, key, existing);
        }
        return json(await publicStateWithMedia(env, existing));
      }
      if (existing.status === "processing" && processingLeaseFresh(existing)) {
        return json(await publicStateWithMedia(env, existing));
      }
      if (existing.status === "processing") {
'''
if existing_anchor not in b:
    raise SystemExit('V60_BACKEND_MISSING_EXISTING_BRANCH')
b = b.replace(existing_anchor, existing_new, 1)

recovery_old = '''const recoveryQueue = { id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, createdAt: now };'''
recovery_new = '''const recoveryQueue = { id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, priority: requestPriority, createdAt: now };'''
if recovery_old not in b:
    raise SystemExit('V60_BACKEND_MISSING_RECOVERY_QUEUE')
b = b.replace(recovery_old, recovery_new, 1)

item_old = '''      sourceLabel: "Ebook Library", status: "pending", createdAt: existing?.createdAt || now, updatedAt: now,
'''
item_new = '''      sourceLabel: "Ebook Library", status: "pending", requestPriority, createdAt: existing?.createdAt || now, updatedAt: now,
'''
if item_old not in b:
    raise SystemExit('V60_BACKEND_MISSING_ITEM_PRIORITY')
b = b.replace(item_old, item_new, 1)

queue_old = '''    const queue = { id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, createdAt: now };
'''
queue_new = '''    const queue = { id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, priority: requestPriority, createdAt: now };
'''
if queue_old not in b:
    raise SystemExit('V60_BACKEND_MISSING_NEW_QUEUE')
b = b.replace(queue_old, queue_new, 1)

# --- Browser prefetch: enqueue only, do not poll in the background ----------
prefetch_post_old = """body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:'reader-audio-v34-prefetch'})"""
prefetch_post_new = """body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:'reader-audio-v60-prefetch',prefetch:true})"""
if prefetch_post_old not in r:
    raise SystemExit('V60_READER_MISSING_PREFETCH_POST')
r = r.replace(prefetch_post_old, prefetch_post_new, 1)

poll_old = '''      if(state.status!=='ready')state=await waitPrefetchReady(state.id);
      const value={payload,state,canonical:canonical(payload.text)};
      prefetchCache.set(payload.chapterHref,value);
      debug.prefetchReady++;
      return value;
'''
poll_new = '''      const value={payload,state,canonical:canonical(payload.text)};
      if(state.status==='ready'&&state.mediaUrl&&state.timingUrl){
        prefetchCache.set(payload.chapterHref,value);
        debug.prefetchReady++;
      }
      return value;
'''
if poll_old not in r:
    raise SystemExit('V60_READER_MISSING_PREFETCH_WAIT')
r = r.replace(poll_old, poll_new, 1)

location_var = '''  let relocatedOff=null;
  let locationTimer=0;
'''
location_new = '''  let relocatedOff=null;
  let locationTimer=0;
  let warmCurrentTimer=0;
  let warmCurrentSignature='';
'''
if location_var not in r:
    raise SystemExit('V60_READER_MISSING_LOCATION_VARS')
r = r.replace(location_var, location_new, 1)

schedule_anchor = '''  function schedulePrefetch(){
    setTimeout(()=>prefetchOne(1),0);
    setTimeout(()=>prefetchOne(2),150);
  }
'''
warm_block = '''  async function warmCurrentChapter(){
    const payload=framePayload();
    if(!payload||!payload.text||String(payload.text).length<80||!payload.chapterHref)return null;
    const signature=payload.chapterHref+'|'+payload.signature;
    if(signature===warmCurrentSignature)return null;
    warmCurrentSignature=signature;
    try{
      const response=await rawFetch('/artifact-library/audio',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bookKey,text:payload.text,chapterTitle:payload.chapterTitle,chapterHref:payload.chapterHref,bookTitle:document.title||'Ebook',clientVersion:'reader-audio-v60-warm-current',prefetch:true})});
      const state=await response.json().catch(()=>({}));
      if(!response.ok)return null;
      if(state.status==='ready'&&state.mediaUrl&&state.timingUrl){
        prefetchCache.set(payload.chapterHref,{payload,state,canonical:canonical(payload.text)});
        debug.prefetchReady++;
      }
      return state;
    }catch(error){debug.lastError=String(error&&error.message||error||'warm current failed').slice(0,180);return null;}
  }

  function schedulePrefetch(){
    setTimeout(()=>prefetchOne(1),0);
    setTimeout(()=>prefetchOne(2),150);
  }
'''
if schedule_anchor not in r:
    raise SystemExit('V60_READER_MISSING_SCHEDULE_PREFETCH')
r = r.replace(schedule_anchor, warm_block, 1)

reloc_old = '''        clearTimeout(locationTimer);
        locationTimer=setTimeout(()=>handleManualRelocation(loc),90);
'''
reloc_new = '''        clearTimeout(locationTimer);
        locationTimer=setTimeout(()=>handleManualRelocation(loc),90);
        clearTimeout(warmCurrentTimer);
        warmCurrentTimer=setTimeout(()=>warmCurrentChapter(),650);
'''
if reloc_old not in r:
    raise SystemExit('V60_READER_MISSING_RELOCATION_HOOK')
r = r.replace(reloc_old, reloc_new, 1)

boot_old = '''      setTimeout(()=>{manualArmedAt=Date.now();tick();if(currentId())schedulePrefetch();},700);
'''
boot_new = '''      setTimeout(()=>{manualArmedAt=Date.now();tick();warmCurrentChapter();if(currentId())schedulePrefetch();},700);
'''
if boot_old not in r:
    raise SystemExit('V60_READER_MISSING_BOOT_HOOK')
r = r.replace(boot_old, boot_new, 1)

backend.write_text(b)
reader.write_text(r)
print('READER_V60_AUDIO_PRIORITY_PREFETCH_PATCH=PASS')
