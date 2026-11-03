// Live, no-secrets GitHub Actions OIDC smoke. Never sends an OIDC token to
// D1/Workers and never prints it. Tests the actual issuer/JWKS/key/claims.
import { webcrypto } from "node:crypto";
import { authorizeScoreCacheSeed, SCORE_CACHE_SEED_OIDC_AUDIENCE } from
  "../cloudflare/runner3-core/src/score-cache-seed-authorization.js";

const crypto = globalThis.crypto || webcrypto;
const env = process.env;
function must(value,label) { if (!value) throw new Error("LIVE_OIDC_SMOKE_"+label); }
function jwtPart(encoded) {
  return JSON.parse(Buffer.from(encoded,"base64url").toString("utf8"));
}
async function json(url,opts={}) {
  const response=await fetch(url,{redirect:"error",signal:AbortSignal.timeout(10000),...opts});
  must(response.ok,"HTTP_"+response.status);
  return response.json();
}
must(env.GITHUB_REPOSITORY==="louisalviss/runner-3","REPO");
must(env.GITHUB_EVENT_NAME==="pull_request","EVENT");
must(env.RUNNER_ENVIRONMENT==="github-hosted","RUNNER");
must(env.ACTIONS_ID_TOKEN_REQUEST_URL && env.ACTIONS_ID_TOKEN_REQUEST_TOKEN,"RUNNER_OIDC_ENV");
const tokenUrl=new URL(env.ACTIONS_ID_TOKEN_REQUEST_URL);
must(tokenUrl.protocol==="https:","TOKEN_REQUEST_HTTPS");
tokenUrl.searchParams.set("audience",SCORE_CACHE_SEED_OIDC_AUDIENCE);
const result=await json(tokenUrl.toString(),{
  headers:{Authorization:"Bearer "+env.ACTIONS_ID_TOKEN_REQUEST_TOKEN,Accept:"application/json"},
});
const token=result?.value;
must(typeof token==="string" && token.split(".").length===3,"TOKEN_FORMAT");
const parts=token.split(".");
const header=jwtPart(parts[0]),claims=jwtPart(parts[1]);
must(header.alg==="RS256" && typeof header.kid==="string","TOKEN_HEADER");
const discovery=await json("https://token.actions.githubusercontent.com/.well-known/openid-configuration");
must(discovery.issuer==="https://token.actions.githubusercontent.com","ISSUER");
must(discovery.jwks_uri==="https://token.actions.githubusercontent.com/.well-known/jwks","JWKS_DISCOVERY");
const jwks=await json(discovery.jwks_uri);
const key=jwks.keys?.find(k=>k.kid===header.kid && k.kty==="RSA" && k.use!=="enc");
must(key,"JWKS_KEY_MISSING");
const imported=await crypto.subtle.importKey("jwk",key,
  {name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["verify"]);
const authentic=await crypto.subtle.verify("RSASSA-PKCS1-v1_5",imported,
  Buffer.from(parts[2],"base64url"),new TextEncoder().encode(parts[0]+"."+parts[1]));
must(authentic,"SIGNATURE_INVALID");
must(claims.iss===discovery.issuer,"SIGNED_ISSUER");
must(claims.aud===SCORE_CACHE_SEED_OIDC_AUDIENCE,"AUDIENCE");
must(claims.repository===env.GITHUB_REPOSITORY,"SIGNED_REPO");
must(String(claims.repository_id)==="1334745420","SIGNED_REPO_ID");
must(claims.event_name===env.GITHUB_EVENT_NAME,"SIGNED_EVENT");
must(String(claims.run_id)===env.GITHUB_RUN_ID,"SIGNED_RUN");
must(String(claims.run_attempt)===env.GITHUB_RUN_ATTEMPT,"SIGNED_ATTEMPT");
must(claims.ref===env.GITHUB_REF,"SIGNED_REF");
must(claims.runner_environment==="github-hosted","SIGNED_RUNNER");
must(typeof claims.workflow_ref==="string"
  && claims.workflow_ref.startsWith(env.GITHUB_REPOSITORY+
    "/.github/workflows/content-intelligence-v2-test.yml@"),"WORKFLOW_REF");
const now=Math.floor(Date.now()/1000);
must(Number.isInteger(claims.iat)&&Number.isInteger(claims.nbf)
  && Number.isInteger(claims.exp)&&claims.iat<=now+30
  && claims.nbf<=now+30 && claims.exp>now,"TIME_CLAIMS");

// A valid CI token must be rejected by the PRODUCTION authorizer because it
// comes from a pull_request regression workflow, not the main guarded workflow.
const receipt={
  ok:true,checkedAtUtc:new Date().toISOString(),
  dateUtc:new Date().toISOString().slice(0,10),
  runId:claims.run_id,runAttempt:claims.run_attempt,
  currentRowsRead:1000,plannedReadRows:500000,projectedRowsRead:501000,
  readSafeCeiling:4000000,
  currentRowsWritten:1000,plannedRows:25000,projectedRowsWritten:26000,safeCeiling:70000,
};
const decision=await authorizeScoreCacheSeed(
  {headers:new Headers({"X-Runner3-Seed-OIDC":token})},
  {preflight_receipt:receipt});
must(decision.ok===false && decision.reason==="oidc_workflow_identity",
     "PULL_REQUEST_NOT_DENIED");
console.log("LIVE_GITHUB_OIDC_SIGNATURE_PASS");
console.log("LIVE_OIDC_CLAIMS_PASS");
console.log("PRODUCTION_SEED_REJECTS_PR_TOKEN_PASS");
// No JWT or bearer token ever printed.
