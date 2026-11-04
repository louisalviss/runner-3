import { webcrypto } from "node:crypto";
import { authorizeScoreCacheSeed, SCORE_CACHE_SEED_OIDC_AUDIENCE } from "../cloudflare/runner3-core/src/score-cache-seed-authorization.js";
const crypto=globalThis.crypto || webcrypto;
const now=Date.now(),sec=Math.floor(now/1000);
const {publicKey,privateKey}=await crypto.subtle.generateKey(
  {name:"RSASSA-PKCS1-v1_5",modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:"SHA-256"},
  true,["sign","verify"]);
const publicJwk=await crypto.subtle.exportKey("jwk",publicKey);
const jwks={keys:[{...publicJwk,kid:"testkid",alg:"RS256",use:"sig"}]};
const fakeFetch=async(url,options)=> {
  if (url!=="https://token.actions.githubusercontent.com/.well-known/jwks")throw Error("wrong JWKS");
  // Workers does NOT implement redirect:"error": this assertion guards
  // against reintroducing the production HTTP 403 regression.
  if(options?.redirect!=="manual")throw Error("UNSUPPORTED_WORKERS_REDIRECT_MODE");
  return {ok:true,json:async()=>jwks};
};
const claims={
  iss:"https://token.actions.githubusercontent.com",aud:SCORE_CACHE_SEED_OIDC_AUDIENCE,
  repository:"louisalviss/runner-3",repository_id:"1334745420",
  ref:"refs/heads/main",ref_type:"branch",
  workflow_ref:"louisalviss/runner-3/.github/workflows/content-intelligence-v4-guarded-materialize.yml@refs/heads/main",
  runner_environment:"github-hosted",event_name:"schedule",
  run_id:"12345",run_attempt:"1",iat:sec,nbf:sec-1,exp:sec+300,
};
const receipt={
  ok:true,checkedAtUtc:new Date(now).toISOString(),
  dateUtc:new Date(now).toISOString().slice(0,10),
  runId:"12345",runAttempt:"1",
  currentRowsRead:3000000,plannedReadRows:500000,projectedRowsRead:3500000,
  readSafeCeiling:4000000,
  currentRowsWritten:10000,plannedRows:25000,projectedRowsWritten:35000,safeCeiling:70000,
};
const b64=o=>Buffer.from(JSON.stringify(o)).toString("base64url");
async function jwt(payload, header={alg:"RS256",kid:"testkid",typ:"JWT"}) {
  const input=b64(header)+"."+b64(payload);
  const sig=await crypto.subtle.sign("RSASSA-PKCS1-v1_5",privateKey,new TextEncoder().encode(input));
  return input+"."+Buffer.from(sig).toString("base64url");
}
async function trial(c=claims,r=receipt,token=null) {
  const bearer=token||await jwt(c);
  const req={headers:new Headers({"X-Runner3-Seed-OIDC":bearer})};
  return authorizeScoreCacheSeed(req,{preflight_receipt:r},{now,fetchJwks:fakeFetch});
}
function expectDenied(r,label){if(r.ok)throw Error("unauthorized: "+label);}
let good=await trial();
if(!good.ok)throw Error("valid GH OIDC and preflight rejected: "+good.reason);
// Surface only coarse bounded stages; fail closed for actual network/parse
// failures without logging an OIDC token or exposing exception messages.
const transportError=await authorizeScoreCacheSeed(
  {headers:new Headers({"X-Runner3-Seed-OIDC":await jwt(claims)})},
  {preflight_receipt:receipt},{now,fetchJwks:async()=>{throw Error("PRIVATE_TRANSPORT_DETAIL");}});
if(transportError.ok || transportError.reason!=="oidc_jwks_fetch_failed")
  throw Error("JWKS transport failed open or exposed a raw exception");
const parseError=await authorizeScoreCacheSeed(
  {headers:new Headers({"X-Runner3-Seed-OIDC":await jwt(claims)})},
  {preflight_receipt:receipt},
  {now,fetchJwks:async()=>({ok:true,json:async()=>{throw Error("PRIVATE_JSON_DETAIL");}})});
if(parseError.ok || parseError.reason!=="oidc_jwks_parse_failed")
  throw Error("JWKS JSON failed open or exposed a raw exception");
const redirectJwks=await authorizeScoreCacheSeed(
  {headers:new Headers({"X-Runner3-Seed-OIDC":await jwt(claims)})},
  {preflight_receipt:receipt},
  {now,fetchJwks:async(url,opts)=>{
    if(url!=="https://token.actions.githubusercontent.com/.well-known/jwks" ||
       opts?.redirect!=="manual")throw Error("UNSAFE_JWKS_FETCH_OPTIONS");
    return {ok:false,status:302,headers:new Headers({location:"https://elsewhere.invalid/jwks"})};
  }});
if(redirectJwks.ok || redirectJwks.reason!=="oidc_jwks_unavailable")
  throw Error("redirecting JWKS endpoint must never be followed or authorized");
const missing=await authorizeScoreCacheSeed({headers:new Headers()}, {preflight_receipt:receipt},
  {now,fetchJwks:fakeFetch});
expectDenied(missing,"missing token");
expectDenied(await trial({...claims,workflow_ref:"other/workflow.yml@refs/heads/main"}),"wrong workflow");
expectDenied(await trial({...claims,repository_id:"other"}),"wrong repo");
expectDenied(await trial({...claims,ref:"refs/heads/feature"}),"wrong branch");
expectDenied(await trial({...claims,aud:"other"}),"wrong audience");
expectDenied(await trial({...claims,runner_environment:"self-hosted"}),"wrong runner");
expectDenied(await trial({...claims,event_name:"pull_request"}),"untrusted event");
expectDenied(await trial({...claims,iat:sec-900}),"stale OIDC");
expectDenied(await trial(claims,{...receipt,checkedAtUtc:new Date(now-150000).toISOString()}),"stale preflight");
expectDenied(await trial(claims,{...receipt,runId:"different"}),"wrong run");
expectDenied(await trial(claims,{...receipt,projectedRowsRead:4300000}),"quota exhausted");
expectDenied(await trial(claims,{...receipt,plannedReadRows:500}),"insufficient planned read");
expectDenied(await trial(claims,{...receipt,safeCeiling:80000}),"unsafe ceiling");
let forged=await jwt(claims);
const parts=forged.split(".");
parts[1]=b64({...claims,event_name:"workflow_dispatch"});
expectDenied(await trial(claims,receipt,parts.join(".")),"forged JWT");
expectDenied(await trial(claims,receipt,await jwt(claims,{alg:"HS256",kid:"testkid"})),"disallowed algorithm");
console.log("D1_SEED_SIGNED_PREFLIGHT_OIDC_PASS 20 cases");
