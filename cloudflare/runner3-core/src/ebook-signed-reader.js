import { handleDelivery } from "./delivery.js";

const NOINDEX = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const H = { "X-Robots-Tag": NOINDEX, "Cache-Control": "private, no-store",
  "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff" };

export function parseSignedEpub(input, now = Math.floor(Date.now()/1000)) {
  const u = input instanceof URL ? input : new URL(input);
  let signed;
  // Queryless capability for mobile in-app browsers that rewrite or drop
  // "&"-separated query parameters. No owner session or D1 access is granted.
  if (u.pathname.startsWith("/artifact-library/r/")) {
    if (u.search || u.hash) return null;
    const segments = u.pathname.split("/").filter(Boolean);
    if (segments.length !== 6 || segments[0] !== "artifact-library" ||
        segments[1] !== "r") return null;
    let scope, name, exp, sig;
    try { [scope, name, exp, sig] = segments.slice(2).map(decodeURIComponent); }
    catch { return null; }
    if (!/^[\w.-]{1,180}$/.test(scope) ||
        !/^[^\/\\\u0000-\u001f]{1,180}\.epub$/i.test(name) ||
        !/^\d{10}$/.test(exp) || !/^[A-Za-z0-9_-]{43}$/.test(sig)) return null;
    signed = new URL("/delivery/ebook/" + encodeURIComponent(scope) +
      "/final/" + encodeURIComponent(name), u.origin);
    signed.searchParams.set("exp", exp);
    signed.searchParams.set("sig", sig);
  } else if (u.pathname === "/artifact-library/read-signed") {
  // Flat capability avoids a URL inside a URL, which some mobile clients
  // re-encode or truncate when opening a link.
  if (u.searchParams.size === 4 &&
      ["scope", "name", "exp", "sig"].every(k => u.searchParams.getAll(k).length === 1)) {
    const scope = u.searchParams.get("scope") || "";
    const name = u.searchParams.get("name") || "";
    if (!/^[\w.-]{1,180}$/.test(scope) ||
        !/^[^\/\\\u0000-\u001f]{1,180}\.epub$/i.test(name)) return null;
    signed = new URL("/delivery/ebook/" + encodeURIComponent(scope) +
      "/final/" + encodeURIComponent(name), u.origin);
    signed.searchParams.set("exp", u.searchParams.get("exp"));
    signed.searchParams.set("sig", u.searchParams.get("sig"));
  } else if (u.searchParams.size === 1 && u.searchParams.getAll("file").length === 1) {
    const file = u.searchParams.get("file");
    if (!file || file.length > 1700) return null;
    try { signed = new URL(file, u.origin); } catch { return null; }
  } else return null;
  } else return null;
  if (signed.origin !== u.origin || signed.username || signed.password || signed.hash ||
      signed.searchParams.size !== 2 || signed.searchParams.getAll("exp").length !== 1 ||
      signed.searchParams.getAll("sig").length !== 1) return null;
  let parts;
  try { parts = signed.pathname.split("/").filter(Boolean).map(decodeURIComponent); } catch { return null; }
  if (parts.length !== 5 || parts[0] !== "delivery" || parts[1] !== "ebook" ||
      parts[3] !== "final" || !/^[\w.-]{1,180}$/.test(parts[2]) ||
      !/^[^\/\\\u0000-\u001f]{1,180}\.epub$/i.test(parts[4])) return null;
  const expText = signed.searchParams.get("exp") || "";
  if (!/^\d{10}$/.test(expText) ||
      !/^[A-Za-z0-9_-]{43}$/.test(signed.searchParams.get("sig") || "")) return null;
  const exp = Number(expText);
  if (exp <= now || exp > now + 259260) return null;
  return { path: signed.pathname + signed.search,
    key: "core/ebook/" + parts[2] + "/final/" + parts[4], name: parts[4] };
}
function reply(body, status = 200, type = "text/html; charset=utf-8") {
  return new Response(body, { status, headers: { ...H, "Content-Type": type,
    "Content-Security-Policy": "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'" }});
}
const esc = x => String(x).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");

function page(item) {
  const title = item.name.replace(/\.epub$/i,"").replace(/[-_]+/g," ");
  const html = '<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' +
  '<meta name="robots" content="noindex,nofollow,noarchive"><title>__TITLE__</title>' +
  '<style>:root{--bg:#f7f5ef;--fg:#29241e;--panel:#eee7d9}*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden;background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,sans-serif}body{position:fixed;inset:0;height:100dvh}body.dark{--bg:#101216;--fg:#ebedef;--panel:#252a30}#viewer{position:absolute;inset:0 5vw;overflow:hidden}#loading{position:absolute;inset:0;display:grid;place-items:center;padding:30px;text-align:center;font-size:14px;z-index:2;pointer-events:none}.bar{position:fixed;left:0;right:0;z-index:15;display:flex;align-items:center;gap:8px;background:var(--panel);padding:10px 15px;opacity:0;pointer-events:none}body.controls .bar{opacity:1;pointer-events:auto}.top{top:0;padding-top:max(10px,env(safe-area-inset-top))}.bottom{bottom:0;padding-bottom:max(10px,env(safe-area-inset-bottom));justify-content:space-between}button{border:0;border-radius:10px;padding:10px 14px;font:inherit;color:var(--fg);background:var(--bg)}.name{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:13px}.hit{position:fixed;top:14%;bottom:14%;z-index:10;background:transparent;color:transparent;padding:0;font-size:0}#prev{left:0;width:28vw}#next{right:0;width:28vw}#menu{left:28vw;width:44vw}#settings{position:fixed;z-index:20;bottom:70px;right:12px;background:var(--panel);padding:16px;border-radius:12px;display:none}#settings.open{display:block}</style>' +
  '<script src="/artifact-library/vendor/jszip.min.js"></script><script src="/artifact-library/vendor/epub.min.js"></script></head><body>' +
  '<div id="viewer"></div><div id="loading">Đang mở sách…</div>' +
  '<button class="hit" id="prev" aria-label="Trang trước"></button><button class="hit" id="menu" aria-label="Điều khiển"></button><button class="hit" id="next" aria-label="Trang sau"></button>' +
  '<div class="bar top"><span class="name">__TITLE__</span><button id="gear">Aa</button></div><div class="bar bottom"><button id="back">‹</button><span>Đọc không cần PIN</span><button id="forward">›</button></div>' +
  '<div id="settings"><div><button id="small">A−</button><button id="large">A+</button></div><button id="theme">Sáng / Tối</button><button id="close">Đóng</button></div>' +
  '<script>const src=__SRC__, key=__KEY__;(()=>{"use strict";const $=x=>document.getElementById(x);let reader=null,font=100;const body=document.body;' +
  'try{font=Number(localStorage.getItem("signed-reader-font")||100);if(localStorage.getItem("signed-reader-theme")==="dark")body.classList.add("dark")}catch{};font=Math.max(70,Math.min(180,font));' +
  'const go=d=>{if(reader)(d>0?reader.next():reader.prev())};$("prev").onclick=()=>go(-1);$("next").onclick=()=>go(1);$("back").onclick=()=>go(-1);$("forward").onclick=()=>go(1);$("menu").onclick=()=>body.classList.toggle("controls");' +
  '$("gear").onclick=()=>{$("settings").classList.toggle("open");body.classList.add("controls")};$("close").onclick=()=>$("settings").classList.remove("open");' +
  'const size=n=>{font=Math.max(70,Math.min(180,n));try{localStorage.setItem("signed-reader-font",font)}catch{};if(reader)reader.themes.fontSize(font+"%")};$("small").onclick=()=>size(font-10);$("large").onclick=()=>size(font+10);' +
  '$("theme").onclick=()=>{body.classList.toggle("dark");try{localStorage.setItem("signed-reader-theme",body.classList.contains("dark")?"dark":"light")}catch{};if(reader)reader.themes.select(body.classList.contains("dark")?"dark":"light")};' +
  'document.addEventListener("keydown",e=>{if(e.key==="ArrowLeft")go(-1);if(e.key==="ArrowRight")go(1)});' +
  '(async()=>{try{if(typeof window.ePub!=="function")throw Error("Không tải được bộ đọc EPUB");const r=await fetch(src,{cache:"no-store",credentials:"omit",referrerPolicy:"no-referrer"});if(!r.ok)throw Error(r.status===410?"Link đã hết hạn":"Không mở được EPUB: HTTP "+r.status);' +
  'const bytes=await r.arrayBuffer();if(bytes.byteLength<100||bytes.byteLength>80*1024*1024)throw Error("EPUB không hợp lệ");const book=ePub(bytes);reader=book.renderTo("viewer",{width:"100%",height:"100%",flow:"paginated",spread:"none"});' +
  'reader.themes.register("light",{body:{color:"#29241e",background:"#f7f5ef"}});reader.themes.register("dark",{body:{color:"#ebedef",background:"#101216"}});reader.themes.select(body.classList.contains("dark")?"dark":"light");reader.themes.fontSize(font+"%");' +
  'reader.on("relocated",l=>{const c=l&&l.start&&l.start.cfi;if(c)try{localStorage.setItem("signed-reader-position:"+key,c)}catch{}});let pos="";try{pos=localStorage.getItem("signed-reader-position:"+key)||""}catch{};try{await reader.display(pos||undefined)}catch{await reader.display()};$("loading").style.display="none";' +
  '}catch(e){$("loading").textContent=String(e&&e.message||e)}})()})();</script></body></html>';
  return html.replaceAll("__TITLE__",esc(title)).replace("__SRC__",JSON.stringify(item.path).replaceAll("<","\\u003c"))
    .replace("__KEY__",JSON.stringify(item.key).replaceAll("<","\\u003c"));
}


// Opaque, revocable bearer-capability link. The token is minted by the
// existing authenticated /delivery-permalinks endpoint and its SHA-256 digest
// is recorded in D1. Reader never receives the Library owner's cookie.
export function parsePermanentEpub(input) {
  const u = input instanceof URL ? input : new URL(input);
  // Browsers and link-openers may append analytics query parameters or a
  // trailing slash. Neither changes the 256-bit bearer token. Ignore them;
  // the D1-backed capability is still independently checked by delivery.js.
  const match = /^\/r\/([A-Za-z0-9_-]{43})\/?$/.exec(u.pathname);
  if (!match) return null;
  return {
    token: match[1],
    path: "/delivery-permanent/" + match[1],
    key: "public-epub:" + match[1],
    name: "EPUB",
  };
}

export async function handlePermanentEpubReader(request, env, url = new URL(request.url)) {
  if (request.method !== "GET") return reply("Method not allowed",405,"text/plain; charset=utf-8");
  const item = parsePermanentEpub(url);
  if (!item) return reply("Invalid book link",404,"text/plain; charset=utf-8");
  const ref = new URL(item.path,url.origin);
  // Existing HMAC-independent but unguessable D1-backed capability validation.
  // 404 on revoked/unknown tokens; no fallback to private owner session.
  const proof = await handleDelivery(new Request(ref,{method:"HEAD"}),env,ref);
  if (!proof || proof.status !== 200 ||
      !/application\/epub\+zip/i.test(proof.headers.get("content-type") || "")) {
    return reply("Book link unavailable or revoked",404,"text/plain; charset=utf-8");
  }
  const disposition = proof.headers.get("content-disposition") || "";
  const m = /filename="([^"\r\n]{1,180}\.epub)"/i.exec(disposition);
  if (m) item.name=m[1];
  return reply(page(item));
}

export async function handleSignedEpubReader(request, env, url = new URL(request.url)) {
  if (request.method !== "GET") return reply("Method not allowed",405,"text/plain; charset=utf-8");
  const item = parseSignedEpub(url);
  if (!item) return reply("Invalid or expired signed EPUB",403,"text/plain; charset=utf-8");
  const signedUrl = new URL(item.path,url.origin);
  const check = await handleDelivery(new Request(signedUrl,{method:"HEAD"}), env, signedUrl);
  if (!check || check.status !== 200) return reply("Signed EPUB not available",check?.status === 410 ? 410 : 403,"text/plain; charset=utf-8");
  return reply(page(item));
}
