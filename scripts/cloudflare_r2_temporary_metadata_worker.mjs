// Temporary, single-bucket signed R2 metadata-preserving migration endpoint.
// No credentials, registrar permissions, D1, or bucket enumeration.
const te=new TextEncoder();
function b64bytes(s) {
  if (typeof s!=="string" || s.length>9000000) throw new Error("b64_length");
  const bin=atob(s);const out=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++)out[i]=bin.charCodeAt(i);
  return out;
}
function hex(bytes){return Array.from(bytes,x=>x.toString(16).padStart(2,"0")).join("");}
const json=(v,status)=>new Response(JSON.stringify(v),{status,headers:{"content-type":"application/json","cache-control":"no-store"}});
export default {
  async fetch(request,env){
    if(request.method!=="POST" || new URL(request.url).pathname!=="/write")return json({ok:false},404);
    if(!env.STORAGE || !env.MIGRATION_PUB_SPKI_B64)return json({ok:false,error:"binding"},503);
    const len=Number(request.headers.get("content-length")||0);
    if(!Number.isFinite(len)||len<=0||len>8500000)return json({ok:false,error:"size"},413);
    const sig=request.headers.get("x-migration-signature")||"";
    if(!sig || sig.length>1000)return json({ok:false,error:"signature_required"},401);
    try{
      const raw=await request.arrayBuffer();
      if(raw.byteLength>8500000)return json({ok:false,error:"size"},413);
      const publicKey=await crypto.subtle.importKey(
        "spki",b64bytes(env.MIGRATION_PUB_SPKI_B64),
        {name:"RSA-PSS",hash:"SHA-256"},false,["verify"]
      );
      const verified=await crypto.subtle.verify(
        {name:"RSA-PSS",saltLength:32},publicKey,b64bytes(sig),raw
      );
      if(!verified)return json({ok:false,error:"signature_invalid"},401);
      const p=JSON.parse(new TextDecoder().decode(raw));
      if(p.v!==1 || p.bucket!=="runner3-telegram-bobvolman-raw" ||
        !Number.isSafeInteger(p.issued_ms) || Math.abs(Date.now()-p.issued_ms)>300000)
        return json({ok:false,error:"scope_or_time"},400);
      if(typeof p.key!=="string"||p.key.length<1||p.key.length>1024 ||
        p.key.startsWith("__migration_test__/"))return json({ok:false,error:"key"},400);
      const data=b64bytes(p.bytes_b64);
      if(data.length<=0||data.length>6000000||data.length!==p.size)
        return json({ok:false,error:"payload_size"},400);
      const hash=hex(new Uint8Array(await crypto.subtle.digest("SHA-256",data)));
      if(hash!==p.sha256)return json({ok:false,error:"sha256"},400);
      const meta=p.custom_metadata||{};
      if(typeof meta!=="object"||Array.isArray(meta)||Object.keys(meta).length>32 ||
        Object.entries(meta).some(([k,v])=>(typeof k!=="string"||typeof v!=="string"||k.length>128||v.length>1024)))
        return json({ok:false,error:"custom_metadata"},400);
      const http=p.http_metadata||{};
      const m={};
      for(const k of ["contentType","contentLanguage","contentDisposition","contentEncoding","cacheControl","cacheExpiry"])
        if(http[k]!=null)m[k]=http[k];
      const exists=await env.STORAGE.head(p.key);
      if(exists)return json({ok:false,error:"exists_no_overwrite"},409);
      const wrote=await env.STORAGE.put(p.key,data,{customMetadata:meta,httpMetadata:m});
      if(!wrote)return json({ok:false,error:"r2_put"},500);
      const check=await env.STORAGE.get(p.key);
      if(!check)return json({ok:false,error:"readback"},500);
      const after=new Uint8Array(await check.arrayBuffer());
      const afterHash=hex(new Uint8Array(await crypto.subtle.digest("SHA-256",after)));
      if(afterHash!==hash)return json({ok:false,error:"readback_hash"},500);
      for(const [k,v] of Object.entries(meta))
        if(check.customMetadata?.[k]!==v)return json({ok:false,error:"metadata_readback"},500);
      return json({ok:true,sha256:afterHash,bytes:after.length,custom_metadata_fields:Object.keys(meta).length},200);
    }catch(err){
      return json({ok:false,error:"internal"},500);
    }
  }
};
