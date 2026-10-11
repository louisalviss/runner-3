// Isolated public GET-only R2 website.
export default { async fetch(request, env) {
 if (!["GET","HEAD"].includes(request.method)) return new Response("Method not allowed",{status:405});
 const raw = new URL(request.url).pathname;
 let name;try{name=decodeURIComponent(raw.slice(1))||"index.html"}catch{return new Response("Bad URL",{status:400})}
 if(name.includes("..")||name.includes("\\")|| !/^(?:index\.html|chapter-\d+\.html|manifest\.json|assets\/[A-Za-z0-9._-]+\.(?:webp|png|jpg|jpeg|svg))$/.test(name)) return new Response("Not found",{status:404});
 const obj=await env.ASSETS.get(name); if(!obj)return new Response("Not found",{status:404});
 const ctype=obj.httpMetadata?.contentType||(name.endsWith(".html")?"text/html; charset=utf-8":"image/webp");
 const h=new Headers({"Content-Type":ctype,"Cache-Control":name.endsWith(".html")?"public, max-age=180":"public, max-age=3600","X-Content-Type-Options":"nosniff"});
 return new Response(request.method==="HEAD"?null:obj.body,{status:200,headers:h});
}};
