import fs from 'node:fs';
import assert from 'node:assert/strict';
const source=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v35-continuity-single-owner-entry.js','utf8');
const m=source.match(/const V81_PAGINATION_OWNER = `([\s\S]*?)`;\n\nconst V35_PLAYER_CHAPTERS/);
assert.ok(m,'v81 runtime template missing');
const scripts=[...m[1].matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length,1,'expected one v81 runtime script');
const js=scripts[0][1];
new Function(js);
const classes=new Set();
Object.defineProperty(globalThis,'navigator',{value:{standalone:false,userAgent:'Mock',platform:'Linux',maxTouchPoints:0},configurable:true});
globalThis.document={
  documentElement:{classList:{add:x=>classes.add(x)}},
};
const chapters=Array.from({length:1498},(_,i)=>({index:i,href:`OEBPS/page-${i}.html`,label:`Chương ${i+1}`}));
const heading={textContent:'Chương 1145'};
const doc={querySelector:()=>heading,title:'Chương 1145'};
const bridge={
  chapters:async()=>chapters,
  chapterInfo:async()=>({index:0,total:chapters.length,chapter:chapters[0],chapters}),
  contents:()=>[{document:doc}],
  current:()=>({start:{href:'OEBPS/page-1144.html'}}),
  displayChapter:async()=>true,
  stepChapter:async()=>true,
  next:async()=>true,
  prev:async()=>true,
};
globalThis.window={matchMedia:()=>({matches:false}),r3ReaderBridge:bridge};
new Function(js)();
const info=await bridge.chapterInfo();
assert.equal(info.index,1144,'chapter 1145 must resolve to zero-based 1144');
assert.equal(info.total,1498);
assert.match(String(info.r3Source),/^heading-/);
assert.equal(window.__r3PaginationOwnerV81.owner,'single-pagination-owner-v81');
console.log('READER_V81_PAGINATION_OWNER_SMOKE=PASS index='+info.index+' total='+info.total+' source='+info.r3Source);
