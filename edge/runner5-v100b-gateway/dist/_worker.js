// Runner5 V100B: isolated production-faithful optimization candidate.
// No WordPress mutation. Preserve all theme JS/features; fix first-paint layout.

const ASSET_RE = /\.(?:js|mjs|css|woff2?|ttf|otf|eot|png|jpe?g|gif|webp|avif|svg|ico)(?:$|\?)/i;

class A11ySearch {
  element(el) {
    if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', 'Open search');
    if (!el.getAttribute('title')) el.setAttribute('title', 'Open search');
  }
}
class HeadingFix {
  element(el) { el.setAttribute('role', 'heading'); el.setAttribute('aria-level', '2'); }
}
class HeadFix {
  element(el) {
    el.append('<meta name="description" content="Runner5 Restore Lab Demo — verified WordPress restore staging site for automated restore and performance validation.">',{html:true});
    el.append(`<style id="runner5-v100b-critical">
      /* Match Inspiro's post-ready Headroom state before first paint. */
      .site-header {
        position:fixed !important;
        top:0 !important;
        width:100% !important;
        z-index:1000 !important;
      }
      body.home.blog:not(.has-header-image):not(.has-header-video) #content {
        padding-top:105px !important;
      }
      .entry-meta .entry-author,
      .entry-meta .entry-date,
      .entry-meta time.entry-date { color:#595959 !important; }
      #colophon .site-info .copyright > span,
      #colophon .site-info .copyright > span a { color:#f5f5f5 !important; }
    </style>`,{html:true});
  }
}
class CssInline {
  constructor(css){this.css=css||'';}
  element(el){ if(this.css) el.replace(`<style id="runner5-v100b-bundle">${this.css.replace(/<\/style/gi,'<\\/style')}</style>`,{html:true}); }
}
function withHeaders(r,extra){const h=new Headers(r.headers);for(const[k,v]of Object.entries(extra))h.set(k,v);return new Response(r.body,{status:r.status,statusText:r.statusText,headers:h});}

export default {
  async fetch(request,env){
    const url=new URL(request.url);
    if(url.pathname==='/__runner5/v100b/health') return Response.json({ok:true,gateway:'runner5-v100b',candidate:6,downstream:'runner5-restore-proxy'},{headers:{'Cache-Control':'no-store','X-Robots-Tag':'noindex,nofollow'}});
    if(!env.EDGE||typeof env.EDGE.fetch!=='function') return new Response('downstream unavailable',{status:503});

    const isHtmlCandidate=request.method==='GET'&&!ASSET_RE.test(url.pathname)&&!url.pathname.startsWith('/wp-content/')&&!url.pathname.startsWith('/wp-includes/');
    const upstreamP=env.EDGE.fetch(request);
    const cssP=isHtmlCandidate?env.EDGE.fetch(new Request(new URL('/__edge/runner5.css',url.origin),{headers:{Accept:'text/css','User-Agent':'Runner5V100B/1.0'}})).catch(()=>null):Promise.resolve(null);
    const [upstream,cssResp]=await Promise.all([upstreamP,cssP]);

    if(request.method!=='POST'&&(ASSET_RE.test(url.pathname)||url.pathname.startsWith('/wp-content/')||url.pathname.startsWith('/wp-includes/'))){
      return withHeaders(upstream,{'Cache-Control':'public,max-age=31536000,immutable','X-Runner5-V100B':'candidate-6-asset'});
    }
    const ct=upstream.headers.get('Content-Type')||'';
    if(request.method==='HEAD'||upstream.status!==200||!/text\/html/i.test(ct)) return upstream;

    let css=''; if(cssResp&&cssResp.ok) css=await cssResp.text();
    const h=new Headers(upstream.headers); h.set('X-Runner5-V100B','candidate-6'); h.set('Cache-Control','public,max-age=60,stale-while-revalidate=300');
    let response=new Response(upstream.body,{status:upstream.status,statusText:upstream.statusText,headers:h});
    let rw=new HTMLRewriter().on('head',new HeadFix()).on('button.sb-search-button-open',new A11ySearch()).on('h3.entry-title',new HeadingFix());
    if(css) rw=rw.on('link[href*="/__edge/runner5.css"]',new CssInline(css));
    return rw.transform(response);
  }
};
