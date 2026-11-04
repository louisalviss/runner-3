// Zero-network, zero-write contract test for private R2-backed Library.
import {webcrypto} from "node:crypto";
if(!globalThis.crypto)globalThis.crypto=webcrypto;
import app from "../cloudflare/runner3-core/artifact-library-simple-entry.js";
import fs from "node:fs";
const assert=(x,m)=>{if(!x)throw Error(m);};
const token="test-token",u="https://local.invalid/artifact-library/api/list";
const cookie=async ()=>{
  const d=await crypto.subtle.digest("SHA-256",
    new TextEncoder().encode("runner3-artifact-library-v1:"+token));
  return "r3_artifact_library="+[...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,"0")).join("");
};
let calls=0;
const entries=[
 {key:"core/ebook/a/final/a-v1.epub",size:12,uploaded:new Date("2026-11-01T00:00:00Z"),customMetadata:{title:"Old"}},
 {key:"core/ebook/a/final/a-v2.epub",size:13,uploaded:new Date("2026-11-02T00:00:00Z"),customMetadata:{title:"Verified A",creator:"Author A"}},
 {key:"core/ebook/b/final/b-v1.epub",size:21,uploaded:new Date("2026-11-03T00:00:00Z")},
 {key:"core/ebook/c/draft/c.epub",size:15,uploaded:new Date("2026-11-03T00:00:00Z")}
];
const env={RUNNER3_CORE_TOKEN:token,ARTIFACTS:{async list(o){
 calls++;assert(o.prefix==="core/ebook/"&&o.include?.includes("customMetadata"),"missing metadata include");
 return {objects:entries,truncated:false};
}}};
let result=await app.fetch(new Request(u),env);
assert(result.status===401 && calls===0,"unauthenticated R2 listing");
const auth={headers:{cookie:await cookie()}};
result=await app.fetch(new Request(u,auth),env);
assert(result.status===200,"authenticated R2 listing");const data=await result.json();
assert(data.ok&&data.canonical_latest_per_scope&&data.objects.length===2,"final scope dedupe");
const a=data.objects.find(x=>x.scope==="a"),b=data.objects.find(x=>x.scope==="b");
assert(a.title==="Verified A"&&a.creator==="Author A"&&a.display_title==="Verified A"&&a.size===13,"verified R2 metadata");
assert(b.title===null&&b.creator===null&&b.display_title==="B"&&b.metadata_source==="scope_fallback","fallback must not invent metadata");
assert(calls===1,"unbounded normal pagination");
let n=0;
const cap={...env,ARTIFACTS:{async list(){n++;return {objects:[],truncated:true,cursor:String(n)};}}};
result=await app.fetch(new Request(u,auth),cap);
assert(result.status===503 && n===25,"R2 page cap");
const ui=fs.readFileSync("cloudflare/runner3-core/artifact-library-simple-entry.js","utf8");
assert(ui.includes("const titleFor=b=>b.title||titleMap[b.scope]||b.display_title||"),"UI ignores R2 title");
console.log("EBOOK_R2_LIBRARY_CONTRACT_PASS: 6 cases");
