import { r3StableRuntimeV82 } from '../cloudflare/runner3-core/artifact-library-reader-v82-stable-shell-entry.js';

const cfi='epubcfi(/6/2294!/4/2/4/12/1:278)';
const store=new Map();
const classes=new Set(['r3-restore-pending-v45']);
const fakeHeading={textContent:'Chương 1145'};
const fakeDoc={title:'Chương 1145',querySelector:sel=>/h1|h2|h3|chapter-title/.test(sel)?fakeHeading:null};
const fakeFrame={contentDocument:fakeDoc};
const listeners=new Map();
const body={dataset:{nav:'swipe'},classList:{toggle(){},contains(){return false}},appendChild(){}};
const documentElement={classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)}};
const viewer={};
const element=()=>({style:{setProperty(){}},setAttribute(){},addEventListener(){},classList:{contains(){return false}},options:[],disabled:false,textContent:'',value:''});

globalThis.window=globalThis;
Object.defineProperty(globalThis,'navigator',{value:{standalone:false},configurable:true});
globalThis.location={search:'?key='+encodeURIComponent('core/ebook/tha-nu-phu-thuy-kia-ra-nhi-muc-1lwhn39/final/Book.epub')};
globalThis.document={
  documentElement,body,
  querySelectorAll(sel){if(sel==='#viewer iframe')return [fakeFrame];if(sel==='.r3-hit-zone')return [];return [];},
  getElementById(id){if(id==='viewer')return viewer;if(id==='r3GestureLayer')return null;return element();},
  createElement(){return element();},
  addEventListener(type,fn){listeners.set(type,fn);},
};
globalThis.localStorage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,String(v))};
globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);
const realSetInterval=globalThis.setInterval;
globalThis.setInterval=()=>0;
globalThis.fetch=async()=>new Response(JSON.stringify({ok:true,progress:{key:'x',percent:76,cfi,updated_at:1789080981889,last_open_at:1789080981889}}),{status:200,headers:{'content-type':'application/json'}});

globalThis.__R3_BASE_READER_BOOT_DONE=true;
let rawNextCalls=0;
let currentCfi='epubcfi(/6/2294!/4/2/4/2/1:0)';
let displayed='';
const chapters=Array.from({length:1498},(_,i)=>({index:i,href:`OEBPS/page-${i}.html`,label:`Chương ${i+1}`}));
globalThis.r3ReaderBridge={
  async chapters(){return chapters;},
  async chapterInfo(){return {index:0,total:1498,chapter:chapters[0],chapters};},
  current(){return {start:{cfi:currentCfi,href:'OEBPS/page-1144.html'}};},
  async display(target){displayed=String(target);currentCfi=String(target);return true;},
  async next(){rawNextCalls++;await new Promise(r=>setTimeout(r,35));currentCfi+='n';return true;},
  async prev(){return true;},
};

r3StableRuntimeV82();
await new Promise(r=>setTimeout(r,520));
const info=await globalThis.r3ReaderBridge.chapterInfo();
if(info.index!==1144||info.total!==1498||info.r3Source!=='heading-label')throw new Error('chapter identity mismatch '+JSON.stringify(info));
if(displayed!==cfi)throw new Error('server CFI not restored: '+displayed);
const key='r3-reader-position:core/ebook/tha-nu-phu-thuy-kia-ra-nhi-muc-1lwhn39/final/Book.epub';
if(store.get(key)!==cfi)throw new Error('canonical local CFI mismatch key='+key+' got='+String(store.get(key))+' debug='+JSON.stringify(globalThis.__r3StableRuntimeV82));
await Promise.all([globalThis.r3ReaderBridge.next(),globalThis.r3ReaderBridge.next()]);
if(rawNextCalls!==1)throw new Error('double navigation was not serialized: '+rawNextCalls);
if(classes.has('r3-restore-pending-v45'))throw new Error('restore shield still active');
if(globalThis.__r3StableRuntimeV82?.restoreGuard!=='fail-safe-v88')throw new Error('v88 runtime restore guard missing');
if(globalThis.__r3StableRuntimeV82?.restoreReleasedBy!=='restore-complete')throw new Error('restore completion release proof missing: '+JSON.stringify(globalThis.__r3StableRuntimeV82));
console.log(`READER_V82_RUNTIME_SMOKE=PASS index=${info.index} total=${info.total} source=${info.r3Source} nextCalls=${rawNextCalls}`);
globalThis.setInterval=realSetInterval;
