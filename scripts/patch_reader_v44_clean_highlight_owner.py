from pathlib import Path

v34 = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')
v35 = Path('cloudflare/runner3-core/artifact-library-reader-v35-continuity-single-owner-entry.js')

s34 = v34.read_text(encoding='utf-8')
s35 = v35.read_text(encoding='utf-8')

old_boot = "const SENTENCE_OWNER_BOOT = `<script data-r3-sentence-highlight-owner-v43=\"1\">window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER=true;</script>`;"
new_boot = r'''const SENTENCE_OWNER_BOOT = `<script data-r3-sentence-highlight-owner-v44="1">
(()=>{
  if(window.__r3SentenceHighlightV44)return;
  window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER=true;
  const NAME='r3-sentence-current-v44';
  const STYLE_ID='r3SentenceHighlightV44Style';
  const LEGACY_STYLE_IDS=['r3AudioDarkHighlightV30Style','r3AudioReadingStyleV34'];
  const debug={version:'v44',paintCalls:0,clearCalls:0,lastText:'',lastError:'',activeRegistries:0,legacyAttrs:0};

  function docs(){
    const out=new Set();
    for(const frame of document.querySelectorAll('#viewer iframe')){
      try{if(frame.contentDocument)out.add(frame.contentDocument);}catch{}
    }
    try{
      for(const content of window.r3ReaderBridge?.contents?.()||[]){
        const doc=content&&content.document;
        if(doc)out.add(doc);
      }
    }catch{}
    return [...out];
  }

  function registryFor(doc){
    try{return doc?.defaultView?.CSS?.highlights||null;}catch{return null;}
  }

  function clearRegistry(registry){
    if(!registry)return;
    try{
      if(typeof registry.clear==='function'){registry.clear();return;}
    }catch{}
    try{
      for(const item of [...registry]){
        const name=Array.isArray(item)?item[0]:item;
        try{registry.delete(name);}catch{}
      }
    }catch{}
  }

  function ensureStyle(doc){
    if(!doc)return;
    let style=doc.getElementById(STYLE_ID);
    if(style)return;
    style=doc.createElement('style');
    style.id=STYLE_ID;
    style.textContent='::highlight('+NAME+'){background:rgba(245,196,67,.28);color:inherit;text-decoration:underline rgba(245,196,67,.88) 1px;text-underline-offset:2px}';
    (doc.head||doc.documentElement).appendChild(style);
  }

  function scrubDoc(doc,{clearCustom=true}={}){
    if(!doc)return;
    try{for(const id of LEGACY_STYLE_IDS)doc.getElementById(id)?.remove();}catch{}
    try{doc.querySelectorAll('[data-r3-audio-reading-v11]').forEach(el=>el.removeAttribute('data-r3-audio-reading-v11'));}catch{}
    if(clearCustom)clearRegistry(registryFor(doc));
  }

  function validate(){
    let active=0,legacy=0;
    for(const doc of docs()){
      try{
        const registry=registryFor(doc);
        if(registry){
          try{for(const item of registry){const name=Array.isArray(item)?item[0]:item;if(String(name||'')===NAME)active++;}}catch{}
        }
      }catch{}
      try{legacy+=doc.querySelectorAll('[data-r3-audio-reading-v11]').length;}catch{}
    }
    debug.activeRegistries=active;
    debug.legacyAttrs=legacy;
    return {activeRegistries:active,legacyAttrs:legacy};
  }

  function clear(){
    debug.clearCalls++;
    for(const doc of docs())scrubDoc(doc,{clearCustom:true});
    validate();
    return true;
  }

  function paint(range){
    try{
      if(!range){clear();return false;}
      const doc=range.startContainer&&range.startContainer.ownerDocument;
      if(!doc){clear();return false;}
      clear();
      scrubDoc(doc,{clearCustom:false});
      ensureStyle(doc);
      const win=doc.defaultView;
      const registry=registryFor(doc);
      if(!registry||!win||typeof win.Highlight!=='function')return false;
      registry.set(NAME,new win.Highlight(range));
      debug.paintCalls++;
      debug.lastText=String(range.toString()||'').replace(/\\s+/g,' ').trim().slice(0,240);
      validate();
      return debug.activeRegistries===1&&debug.legacyAttrs===0;
    }catch(error){
      debug.lastError=String(error&&error.message||error||'highlight paint failed').slice(0,180);
      return false;
    }
  }

  window.__r3SentenceHighlightV44={NAME,debug,docs,scrubDoc,clear,paint,validate};
  window.addEventListener('pageshow',()=>setTimeout(clear,0));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(clear,0);});
  window.addEventListener('pagehide',clear,{once:true});
})();
</script>`;'''
if old_boot not in s34:
    raise SystemExit('v44: v43 boot marker missing')
s34 = s34.replace(old_boot, new_boot, 1)

start = s34.find('  function ensureFrameHooks(doc){')
end = s34.find('\n\n  function textTokensForElement(el){', start)
if start < 0 or end < 0:
    raise SystemExit('v44: ensureFrameHooks region missing')
s34 = s34[:start] + r'''  function ensureFrameHooks(doc){
    if(!doc)return;
    try{window.__r3SentenceHighlightV44?.scrubDoc?.(doc,{clearCustom:false});}catch{}
  }
''' + s34[end:]

start = s34.find('  function clearAllAudioHighlights(){')
end = s34.find('\n\n  async function syncWord(index,force=false){', start)
if start < 0 or end < 0:
    raise SystemExit('v44: highlight paint region missing')
s34 = s34[:start] + r'''  function clearAllAudioHighlights(){
    try{return Boolean(window.__r3SentenceHighlightV44?.clear?.());}catch{return false;}
  }

  function applyExactHighlight(range){
    try{return Boolean(window.__r3SentenceHighlightV44?.paint?.(range));}catch{return false;}
  }
''' + s34[end:]

old_ended = "  audio.addEventListener('ended',()=>{for(const doc of [...document.querySelectorAll('#viewer iframe')].map(f=>{try{return f.contentDocument;}catch{return null;}}).filter(Boolean)){try{doc.defaultView&&doc.defaultView.CSS&&doc.defaultView.CSS.highlights&&doc.defaultView.CSS.highlights.delete(highlightName);}catch{}}});"
new_ended = "  audio.addEventListener('ended',()=>{clearAllAudioHighlights();});"
if old_ended not in s34:
    raise SystemExit('v44: v34 ended cleanup marker missing')
s34 = s34.replace(old_ended, new_ended, 1)

old_clear_range = r'''  function clearRangeHighlight(){
    for(const doc of [...document.querySelectorAll('#viewer iframe')].map(f=>{try{return f.contentDocument;}catch{return null;}}).filter(Boolean)){
      try{doc.defaultView&&doc.defaultView.CSS&&doc.defaultView.CSS.highlights&&doc.defaultView.CSS.highlights.delete(highlightName);}catch{}
    }
  }
'''
new_clear_range = r'''  function clearRangeHighlight(){
    try{window.__r3SentenceHighlightV44?.clear?.();}catch{}
  }
'''
if old_clear_range not in s35:
    raise SystemExit('v44: v35 clearRangeHighlight marker missing')
s35 = s35.replace(old_clear_range, new_clear_range, 1)

# Strengthen runtime proof without creating another Worker wrapper/layer.
s35 = s35.replace(
    "headers.set('X-R3-Reader-Patch-Proof', 'v34+v35:ahead-prefetch+range-follow+single-audio-owner');",
    "headers.set('X-R3-Reader-Patch-Proof', 'v34+v35+v44:range-follow+single-audio+single-highlight-owner');",
    1,
)

checks34 = [
    'data-r3-sentence-highlight-owner-v44',
    "const NAME='r3-sentence-current-v44'",
    "if(typeof registry.clear==='function'){registry.clear();return;}",
    'debug.activeRegistries===1&&debug.legacyAttrs===0',
    'window.__r3SentenceHighlightV44?.paint?.(range)',
    'window.__r3SentenceHighlightV44?.clear?.()',
    'for(let step=0;step<5;step++)',
    'if(direction>0)await b.next();',
    'else await b.prev();',
]
for needle in checks34:
    if needle not in s34:
        raise SystemExit(f'v44: missing v34 marker: {needle}')

# v34 itself must no longer own a visual registry.
if 'win.CSS.highlights.set(highlightName' in s34:
    raise SystemExit('v44: legacy v34 visual registry owner remains')

checks35 = [
    'window.__r3SentenceHighlightV44?.clear?.()',
    'v34+v35+v44:range-follow+single-audio+single-highlight-owner',
]
for needle in checks35:
    if needle not in s35:
        raise SystemExit(f'v44: missing v35 marker: {needle}')

v34.write_text(s34, encoding='utf-8')
v35.write_text(s35, encoding='utf-8')
