from pathlib import Path

p = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')
s = p.read_text(encoding='utf-8')
old = """  function applyExactHighlight(range){
    if(!range)return;
    const doc=range.startContainer&&range.startContainer.ownerDocument;
    ensureFrameHooks(doc);
    try{
      const win=doc.defaultView;
      if(win&&win.CSS&&win.CSS.highlights&&typeof win.Highlight==='function'){
        win.CSS.highlights.set(highlightName,new win.Highlight(range));
      }
    }catch{}
  }
"""
new = """  function clearAllAudioHighlights(){
    const docs=new Set();
    for(const frame of document.querySelectorAll('#viewer iframe')){
      try{if(frame.contentDocument)docs.add(frame.contentDocument);}catch{}
    }
    try{
      for(const content of bridge()?.contents?.()||[]){
        const doc=content&&content.document;
        if(doc)docs.add(doc);
      }
    }catch{}
    if(activeDoc)docs.add(activeDoc);
    for(const doc of docs){
      try{doc.querySelectorAll('[data-r3-audio-reading-v11]').forEach(el=>el.removeAttribute('data-r3-audio-reading-v11'));}catch{}
      try{
        const registry=doc.defaultView&&doc.defaultView.CSS&&doc.defaultView.CSS.highlights;
        if(!registry)continue;
        registry.delete(highlightName);
        try{
          for(const item of registry){
            const name=Array.isArray(item)?item[0]:item;
            if(String(name||'').startsWith('r3-audio-'))registry.delete(name);
          }
        }catch{}
      }catch{}
    }
  }

  function applyExactHighlight(range){
    if(!range)return;
    const doc=range.startContainer&&range.startContainer.ownerDocument;
    if(!doc)return;
    clearAllAudioHighlights();
    ensureFrameHooks(doc);
    try{
      const win=doc.defaultView;
      if(win&&win.CSS&&win.CSS.highlights&&typeof win.Highlight==='function'){
        win.CSS.highlights.set(highlightName,new win.Highlight(range));
      }
    }catch{}
  }
"""
count = s.count(old)
if count != 1:
    raise SystemExit(f'applyExactHighlight marker expected 1, got {count}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('PATCH_V41=PASS')
