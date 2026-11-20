import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { parsePermanentEpub, handlePermanentEpubReader } from "../cloudflare/runner3-core/src/ebook-signed-reader.js";
globalThis.crypto ||= webcrypto;
const origin="https://runner3-core.example.com";
const token="f".repeat(43);
const url=origin+"/r/"+token;
assert.equal(parsePermanentEpub(url)?.token,token);
assert.equal(parsePermanentEpub(url)?.path,"/delivery-permanent/"+token);
assert.equal(parsePermanentEpub(url+"?utm_source=chatgpt.com")?.token,token,"in-app browser tracking suffix accepted");
assert.equal(parsePermanentEpub(url+"?source=chatgpt")?.token,token,"common link opener suffix accepted");
assert.equal(parsePermanentEpub(url+"/")?.token,token,"trailing slash accepted");
assert.equal(parsePermanentEpub(url+"/?utm_source=chatgpt")?.token,token,"trailing slash and tracking accepted");
assert.equal(parsePermanentEpub(url+"#fragment")?.token,token,"fragment does not authorize a different token");
assert.equal(parsePermanentEpub(origin+"/r/../secret"),null,"path traversal forbidden");
assert.equal(parsePermanentEpub(origin+"/r/"+"a".repeat(42)),null,"short malformed token forbidden");
assert.equal(parsePermanentEpub(origin+"/r/"+token+"/extra"),null,"path suffix forbidden");
const artifact={project:"ebook",scope:"test-book",name:"final/Bataille-Foreword.vi.epub",key:"core/ebook/test-book/final/Bataille-Foreword.vi.epub"};
const state={lookup:0,head:0};
const env={
 DB:{prepare(sql){assert.match(sql,/SELECT project, scope, name, object_key FROM delivery_permalinks/);
   return {bind(hash){assert.match(hash,/^[a-f0-9]{64}$/);return {async first(){state.lookup++;return {...artifact,object_key:artifact.key}}}}}}},
 ARTIFACTS:{async head(key){assert.equal(key,artifact.key);state.head++;return {
   size:64000,httpEtag:"test",
   writeHttpMetadata(headers){headers.set("content-type","application/epub+zip")}
 }}}};
const good=await handlePermanentEpubReader(new Request(url),env);
assert.equal(good.status,200,"existing revocable capability works without PIN");
const tracked=await handlePermanentEpubReader(new Request(url+"?utm_source=chatgpt.com"),env);
assert.equal(tracked.status,200,"real iPhone/ChatGPT tracking variant still opens reader");
const slash=await handlePermanentEpubReader(new Request(url+"/"),env);
assert.equal(slash.status,200,"trailing slash still opens reader");
assert.match(await good.text(),/Bataille Foreword\.vi/);
assert.match(good.headers.get("X-Robots-Tag"),/noindex/);
assert.equal(good.headers.get("Referrer-Policy"),"no-referrer");
assert.ok(state.lookup>0 && state.head>0,"D1 SHA-token check and R2 HEAD were executed");
const invalid=await handlePermanentEpubReader(new Request(origin+"/r/bad"),env);
assert.equal(invalid.status,404);
const revokedEnv={...env,DB:{prepare(){return {bind(){return {async first(){return null}}}}}}};
const revoked=await handlePermanentEpubReader(new Request(url),revokedEnv);
assert.equal(revoked.status,404,"revoked/unknown capability is denied");
const badMethod=await handlePermanentEpubReader(new Request(url,{method:"POST"}),env);
assert.equal(badMethod.status,405,"no data mutations");
console.log("PERMANENT_READER_HMACLESS_D1_CAPABILITY_AND_REVOKE_PASS");
