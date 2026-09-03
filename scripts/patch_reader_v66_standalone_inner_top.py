from pathlib import Path

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
text = V2.read_text(encoding='utf-8')

MARKER = '__r3StandaloneInnerTopV66'
if MARKER in text:
    print('READER_V66_STANDALONE_INNER_TOP=ALREADY_APPLIED')
    raise SystemExit(0)

render_anchor = "      rendition=book.renderTo('viewer',{width:'100%',height:'100%',spread:'none',flow:'paginated',manager:'default'});\n      registerThemes();applyReaderSettings();"
if render_anchor not in text:
    raise SystemExit('V66_RENDER_ANCHOR_MISSING')

helper_anchor = "  function bindEpubContents(){\n"
if helper_anchor not in text:
    raise SystemExit('V66_BIND_CONTENTS_ANCHOR_MISSING')

helper = r'''  function r3StandaloneIphoneV66(){
    try{return Boolean(/iPhone|iPod/i.test(String(navigator.userAgent||''))&&((window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true));}catch{return false;}
  }
  function r3PxV66(value){const n=parseFloat(String(value||'0'));return Number.isFinite(n)?n:0;}
  function r3NormalizeStandaloneInnerTopV66(contents,reason=''){
    try{
      if(!r3StandaloneIphoneV66())return false;
      const doc=contents&&contents.document||contents;
      if(!doc||!doc.documentElement||!doc.body)return false;
      const root=doc.documentElement,body=doc.body,win=doc.defaultView;
      const state=window.__r3StandaloneInnerTopV66||(window.__r3StandaloneInnerTopV66={owner:'standalone-inner-top-v66',calls:0,applied:0,lastReason:'',lastBefore:null,lastAfter:null});
      state.calls++;state.lastReason=String(reason||'');

      let chain=[],node=body;
      for(let depth=0;depth<5;depth++){
        const child=[...(node.children||[])].find(el=>{
          const tag=String(el.tagName||'').toLowerCase();
          if(!tag||['script','style','link','meta'].includes(tag))return false;
          try{const cs=win&&win.getComputedStyle?win.getComputedStyle(el):null;return !cs||cs.display!=='none'&&cs.visibility!=='hidden';}catch{return true;}
        });
        if(!child)break;
        chain.push(child);node=child;
      }
      const target=chain.length?chain[chain.length-1]:body;
      let before=null;
      try{before=Math.round(Number(target.getBoundingClientRect().top||0)*10)/10;}catch{}
      state.lastBefore=before;

      // The outer standalone viewport already owns the status-bar safe area.
      // Reapply this after EPUB author styles settle so a chapter stylesheet
      // cannot restore the duplicate top margin after the early content hook.
      root.style.setProperty('margin-top','0','important');
      root.style.setProperty('padding-top','0','important');
      body.style.setProperty('margin-top','0','important');
      body.style.setProperty('padding-top','8px','important');
      for(const el of chain){
        try{
          const cs=win&&win.getComputedStyle?win.getComputedStyle(el):null;
          if(!cs)continue;
          if(r3PxV66(cs.marginTop)>4)el.style.setProperty('margin-top','0','important');
          if(r3PxV66(cs.paddingTop)>12)el.style.setProperty('padding-top','0','important');
        }catch{}
      }
      root.dataset.r3StandaloneInnerTopV66='1';
      state.applied++;
      try{state.lastAfter=Math.round(Number(target.getBoundingClientRect().top||0)*10)/10;}catch{}
      return true;
    }catch{return false;}
  }

'''
text = text.replace(helper_anchor, helper + helper_anchor, 1)

render_patch = "      rendition=book.renderTo('viewer',{width:'100%',height:'100%',spread:'none',flow:'paginated',manager:'default'});\n      try{if(r3StandaloneIphoneV66()&&rendition&&rendition.hooks&&rendition.hooks.content&&typeof rendition.hooks.content.register==='function')rendition.hooks.content.register(contents=>r3NormalizeStandaloneInnerTopV66(contents,'content-hook'));}catch{}\n      registerThemes();applyReaderSettings();"
text = text.replace(render_anchor, render_patch, 1)

bind_old = "    contents.forEach(c=>{try{bindGestureTarget(c.document,()=>c.window?.innerWidth||c.document?.documentElement?.clientWidth||window.innerWidth);}catch{}});"
bind_new = "    contents.forEach(c=>{try{if(r3StandaloneIphoneV66()){r3NormalizeStandaloneInnerTopV66(c,'bind-rendered');setTimeout(()=>r3NormalizeStandaloneInnerTopV66(c,'bind-settle-80'),80);setTimeout(()=>r3NormalizeStandaloneInnerTopV66(c,'bind-settle-240'),240);}bindGestureTarget(c.document,()=>c.window?.innerWidth||c.document?.documentElement?.clientWidth||window.innerWidth);}catch{}});"
if bind_old not in text:
    raise SystemExit('V66_BIND_LINE_MISSING')
text = text.replace(bind_old, bind_new, 1)

for required in [
    '__r3StandaloneInnerTopV66',
    "owner:'standalone-inner-top-v66'",
    "body.style.setProperty('padding-top','8px','important')",
    "rendition.hooks.content.register(contents=>r3NormalizeStandaloneInnerTopV66(contents,'content-hook'))",
    "r3NormalizeStandaloneInnerTopV66(c,'bind-rendered')",
    "r3NormalizeStandaloneInnerTopV66(c,'bind-settle-80')",
    "r3NormalizeStandaloneInnerTopV66(c,'bind-settle-240')",
    "root.dataset.r3StandaloneInnerTopV66='1'",
]:
    if required not in text:
        raise SystemExit('V66_REQUIRED_MARKER_MISSING:' + required)

V2.write_text(text, encoding='utf-8')
print('READER_V66_STANDALONE_INNER_TOP=PASS')
