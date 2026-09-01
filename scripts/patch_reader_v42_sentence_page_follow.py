from pathlib import Path

# trigger v42
p = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js')
s = p.read_text(encoding='utf-8')


def replace_region(source: str, start: str, end: str, replacement: str, label: str) -> str:
    a = source.find(start)
    if a < 0:
        raise SystemExit(f'{label}: start marker missing')
    b = source.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f'{label}: end marker missing')
    return source[:a] + replacement + source[b:]

phrase = r'''  function phraseRange(index){
    const center=nearestMappedIndex(index);
    if(center<0)return null;
    const wordRange=mappedWords[center];
    if(!wordRange)return null;
    try{
      const doc=wordRange.startContainer.ownerDocument;
      const startNode=wordRange.startContainer.nodeType===1?wordRange.startContainer:wordRange.startContainer.parentElement;
      const block=startNode&&startNode.closest?startNode.closest('p,li,h1,h2,h3,h4,h5,h6,blockquote'):null;
      if(!block)return wordRange;
      const text=String(block.textContent||'');
      if(!text.trim())return wordRange;
      let centerOffset=0,foundCenter=false;
      const walker=doc.createTreeWalker(block,NodeFilter.SHOW_TEXT);
      let node;
      while((node=walker.nextNode())){
        if(node===wordRange.startContainer){centerOffset+=wordRange.startOffset;foundCenter=true;break;}
        centerOffset+=String(node.nodeValue||'').length;
      }
      if(!foundCenter)return wordRange;

      // Deterministic sentence boundaries. Safari/Intl.Segmenter can return a
      // surprisingly large segment for translated EPUB punctuation/markup.
      let sentenceStart=0;
      for(let i=Math.min(text.length-1,Math.max(0,centerOffset-1));i>=0;i--){
        if(/[.!?…]/.test(text[i]||'')){sentenceStart=i+1;break;}
      }
      let sentenceEnd=text.length;
      for(let i=Math.max(0,centerOffset);i<text.length;i++){
        if(/[.!?…]/.test(text[i]||'')){
          sentenceEnd=i+1;
          while(sentenceEnd<text.length&&/[\"'”’»)]/.test(text[sentenceEnd]||''))sentenceEnd++;
          break;
        }
      }
      while(sentenceStart<sentenceEnd&&/\s/.test(text[sentenceStart]||''))sentenceStart++;
      while(sentenceEnd>sentenceStart&&/\s/.test(text[sentenceEnd-1]||''))sentenceEnd--;
      if(sentenceEnd<=sentenceStart)return wordRange;

      let cursor=0,startFound=null,startOffset=0,endFound=null,endOffset=0;
      const walker2=doc.createTreeWalker(block,NodeFilter.SHOW_TEXT);
      while((node=walker2.nextNode())){
        const len=String(node.nodeValue||'').length;
        if(!startFound&&sentenceStart<=cursor+len){startFound=node;startOffset=Math.max(0,sentenceStart-cursor);}
        if(sentenceEnd<=cursor+len){endFound=node;endOffset=Math.max(0,sentenceEnd-cursor);break;}
        cursor+=len;
      }
      if(!startFound||!endFound)return wordRange;
      const range=doc.createRange();
      range.setStart(startFound,startOffset);
      range.setEnd(endFound,endOffset);
      return range;
    }catch{return wordRange;}
  }
'''

s = replace_region(
    s,
    '  function phraseRange(index){',
    '\n\n  function rangeVisible(range){',
    phrase,
    'phraseRange',
)

geometry = r'''  function rangePageDirection(range){
    try{
      if(!range)return 0;
      const doc=range.startContainer&&range.startContainer.ownerDocument;
      const viewer=document.getElementById('viewer');
      if(!doc||!viewer)return 0;
      let frame=null;
      for(const candidate of document.querySelectorAll('#viewer iframe')){
        try{if(candidate.contentDocument===doc){frame=candidate;break;}}catch{}
      }
      if(!frame)return 0;
      const vr=viewer.getBoundingClientRect();
      const fr=frame.getBoundingClientRect();
      const rects=[...range.getClientRects()];
      if(!rects.length)return 0;
      let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
      for(const rect of rects){
        left=Math.min(left,fr.left+rect.left);
        right=Math.max(right,fr.left+rect.right);
        top=Math.min(top,fr.top+rect.top);
        bottom=Math.max(bottom,fr.top+rect.bottom);
      }
      if(left>=vr.right-3)return 1;
      if(right<=vr.left+3)return -1;
      if(top>=vr.bottom-3)return 1;
      if(bottom<=vr.top+3)return -1;
      return 0;
    }catch{return 0;}
  }

  function rangeVisible(range){
    try{
      if(!range)return false;
      const doc=range.startContainer&&range.startContainer.ownerDocument;
      const viewer=document.getElementById('viewer');
      if(!doc||!viewer)return false;
      let frame=null;
      for(const candidate of document.querySelectorAll('#viewer iframe')){
        try{if(candidate.contentDocument===doc){frame=candidate;break;}}catch{}
      }
      if(!frame)return false;
      const vr=viewer.getBoundingClientRect();
      const fr=frame.getBoundingClientRect();
      return [...range.getClientRects()].some(rect=>{
        const left=fr.left+rect.left,right=fr.left+rect.right,top=fr.top+rect.top,bottom=fr.top+rect.bottom;
        return right>vr.left+3&&left<vr.right-3&&bottom>vr.top+3&&top<vr.bottom-3;
      });
    }catch{return false;}
  }
'''

s = replace_region(
    s,
    '  function rangeVisible(range){',
    '\n\n  function clearAllAudioHighlights(){',
    geometry,
    'range geometry',
)

sync = r'''  async function syncWord(index,force=false){
    if(!timingWords.length)return false;
    buildWordMap(false);
    let center=nearestMappedIndex(index);
    let followRange=center>=0?mappedWords[center]:null;
    let range=phraseRange(index);
    if(!range||!followRange)return false;
    applyExactHighlight(range);

    let direction=rangePageDirection(followRange);
    if(!force&&direction===0&&rangeVisible(followRange))return true;
    if(Date.now()<suppressDisplayUntil)return true;
    const now=Date.now();
    if(!force&&now-lastFollowAt<260)return false;
    const b=bridge();
    if(!b)return false;
    lastFollowAt=now;
    debug.exactFollowCalls++;
    const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

    // Prefer page stepping. display(CFI) is only a fallback because on iOS
    // epub.js may accept display() without changing the visible column.
    if(direction&&((direction>0&&typeof b.next==='function')||(direction<0&&typeof b.prev==='function'))){
      for(let step=0;step<5;step++){
        try{
          if(direction>0)await b.next();
          else await b.prev();
        }catch{break;}
        await wait(75);
        if(rangeVisible(followRange)){
          buildWordMap(true);
          range=phraseRange(index);
          if(range)applyExactHighlight(range);
          try{if(typeof b.persist==='function')b.persist();}catch{}
          return true;
        }
        direction=rangePageDirection(followRange);
        if(!direction)break;
      }
    }

    center=nearestMappedIndex(index);
    followRange=center>=0?mappedWords[center]:followRange;
    let cfi='';
    try{if(followRange&&typeof b.cfiFromRange==='function')cfi=String(b.cfiFromRange(followRange)||'');}catch{}
    if(!cfi||typeof b.display!=='function')return false;
    try{
      await b.display(cfi);
      await wait(110);
      buildWordMap(true);
      range=phraseRange(index);
      if(range)applyExactHighlight(range);
      try{if(typeof b.persist==='function')b.persist();}catch{}
      return true;
    }catch{return false;}
  }
'''

s = replace_region(
    s,
    '  async function syncWord(index,force=false){',
    '\n\n  async function loadTimingForCurrent(){',
    sync,
    'syncWord',
)

if 'function rangePageDirection(range)' not in s:
    raise SystemExit('v42 direction marker missing')
if 'Deterministic sentence boundaries' not in s:
    raise SystemExit('v42 sentence marker missing')
if 'for(let step=0;step<5;step++)' not in s:
    raise SystemExit('v42 page-step marker missing')

p.write_text(s, encoding='utf-8')
