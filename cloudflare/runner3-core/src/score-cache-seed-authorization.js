// Trust boundary for an expensive, one-time legacy cache seed.
// Verifies a short-lived GitHub Actions OIDC signature and signed workflow
// identity, plus a current, bound account-wide D1 quota-preflight receipt.
// No authorization fallback: an ordinary RUNNER3_CORE_TOKEN is insufficient.
export const SCORE_CACHE_SEED_OIDC_AUDIENCE = "runner3-d1-score-cache-seed-v1";
const ISSUER = "https://token.actions.githubusercontent.com";
const JWKS = ISSUER + "/.well-known/jwks";
const WORKFLOW_REF = "louisalviss/runner-3/.github/workflows/content-intelligence-v4-guarded-materialize.yml@refs/heads/main";
const REPO_ID = "1334745420";
const MAX_RECEIPT_AGE_MS = 120000;

function fromBase64Url(s) {
  if (typeof s !== "string" || !/^[A-Za-z0-9_-]+$/.test(s) || s.length>12000) throw Error("bad_jwt_encoding");
  const padded=s.replace(/-/g,"+").replace(/_/g,"/");
  const raw=atob(padded+"=".repeat((4-padded.length%4)%4));
  return Uint8Array.from(raw,(c)=>c.charCodeAt(0));
}
function jwtJson(s) {
  return JSON.parse(new TextDecoder().decode(fromBase64Url(s)));
}
function nonnegativeInteger(n) {
  return Number.isSafeInteger(n) && n>=0;
}
function validateReceipt(r,p,now) {
  if (!r || typeof r!=="object" || r.ok!==true) return false;
  const t=Date.parse(r.checkedAtUtc);
  if (!Number.isFinite(t) || t>now+30000 || now-t>MAX_RECEIPT_AGE_MS) return false;
  const utcDate=new Date(now).toISOString().slice(0,10);
  if (r.dateUtc!==utcDate || r.dateUtc!==new Date(t).toISOString().slice(0,10)) return false;
  if (String(r.runId)!==String(p.run_id) || String(r.runAttempt)!==String(p.run_attempt)) return false;
  for (const name of ["currentRowsRead","projectedRowsRead","readSafeCeiling","currentRowsWritten",
    "plannedRows","plannedReadRows","projectedRowsWritten","safeCeiling"]) {
    if (!nonnegativeInteger(r[name])) return false;
  }
  return r.plannedRows>=25000 && r.plannedReadRows>=500000
    && r.safeCeiling>0 && r.safeCeiling<=70000
    && r.readSafeCeiling>0 && r.readSafeCeiling<=4000000
    && r.projectedRowsWritten===r.currentRowsWritten+r.plannedRows
    && r.projectedRowsRead===r.currentRowsRead+r.plannedReadRows
    && r.projectedRowsWritten<=r.safeCeiling && r.projectedRowsRead<=r.readSafeCeiling;
}

/** @returns {{ok:boolean,reason:string}} */
export async function authorizeScoreCacheSeed(request, body, {
  now=Date.now(), fetchJwks=globalThis.fetch,
}={}) {
  const deny=(reason)=>({ok:false,reason});
  // Report a fixed operation stage, not exception messages, tokens, headers,
  // remote responses or JWKS bytes. Each failure still denies authorization.
  let phase="token_decode";
  try {
    const token=request?.headers?.get("X-Runner3-Seed-OIDC");
    if (!token || token.length>12000) return deny("oidc_missing");
    const parts=token.split(".");
    if (parts.length!==3) return deny("oidc_format");
    const header=jwtJson(parts[0]),claims=jwtJson(parts[1]);
    if (header.alg!=="RS256" || typeof header.kid!=="string" || !header.kid || header.kid.length>250) return deny("oidc_header");
    const sec=Math.floor(now/1000);
    if (claims.iss!==ISSUER || claims.aud!==SCORE_CACHE_SEED_OIDC_AUDIENCE ||
        claims.repository!=="louisalviss/runner-3" ||
        String(claims.repository_id)!==REPO_ID ||
        claims.ref!=="refs/heads/main" || claims.ref_type!=="branch" ||
        claims.workflow_ref!==WORKFLOW_REF ||
        claims.runner_environment!=="github-hosted" ||
        !["schedule","workflow_dispatch"].includes(claims.event_name) ||
        !/^[0-9]+$/.test(String(claims.run_id||"")) ||
        !/^[0-9]+$/.test(String(claims.run_attempt||""))) return deny("oidc_workflow_identity");
    if (!nonnegativeInteger(claims.iat) || !nonnegativeInteger(claims.nbf) ||
        !nonnegativeInteger(claims.exp) ||
        claims.iat>sec+30 || sec-claims.iat>300 ||
        claims.nbf>sec+30 || claims.exp<=sec || claims.exp>claims.iat+1200) return deny("oidc_expired");
    if (!validateReceipt(body?.preflight_receipt,claims,now)) return deny("preflight_invalid");

    // Only GitHub's fixed, verified OIDC JWKS host is consulted.
    phase="jwks_fetch";
    // Cloudflare Workers rejects redirect:"error" at Request construction.
    // Manual mode returns 3xx to us without contacting a redirect target;
    // response.ok below fails closed for every redirect/non-2xx response.
    const response=await fetchJwks(JWKS,{redirect:"manual",signal:AbortSignal.timeout(4000)});
    if (!response?.ok) return deny("oidc_jwks_unavailable");
    phase="jwks_parse";
    const jwks=await response.json();
    const key=(Array.isArray(jwks?.keys)?jwks.keys:[]).find(k=>
      k.kid===header.kid && k.kty==="RSA" &&
      (k.alg===undefined || k.alg==="RS256") && k.use!=="enc");
    if (!key) return deny("oidc_key_not_found");
    phase="key_import";
    const publicKey=await crypto.subtle.importKey(
      "jwk",key,{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["verify"]);
    phase="signature_verify";
    const valid=await crypto.subtle.verify("RSASSA-PKCS1-v1_5",publicKey,
      fromBase64Url(parts[2]),new TextEncoder().encode(parts[0]+"."+parts[1]));
    return valid?{ok:true,reason:"github_oidc_preflight_valid"}:deny("oidc_signature");
  } catch {
    return deny("oidc_"+phase+"_failed");
  }
}
