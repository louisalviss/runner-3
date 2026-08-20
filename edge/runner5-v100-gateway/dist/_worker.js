// Runner5 isolated V100 candidate gateway.
// Candidate 6 preserves theme JavaScript and fixes the Inspiro first-paint
// header/layout mismatch structurally.

const LONG_CACHE_RE = /\.(?:js|mjs|css|woff2?|ttf|otf|eot|png|jpe?g|gif|webp|avif|svg|ico)(?:$|\?)/i;

class SearchButtonA11y {
  element(element) {
    if (!element.getAttribute('aria-label')) element.setAttribute('aria-label', 'Open search');
    if (!element.getAttribute('title')) element.setAttribute('title', 'Open search');
  }
}

class EntryHeadingA11y {
  element(element) {
    element.setAttribute('role', 'heading');
    element.setAttribute('aria-level', '2');
  }
}

class HeadEnhancer {
  element(element) {
    element.append('<meta name="description" content="Runner5 Restore Lab Demo — verified WordPress restore staging site for automated restore and performance validation.">',{html:true});
    element.append(`<style id="runner5-v100-critical">
      /* Inspiro adds .headroom and content padding after DOM ready. Start in the
         same geometry so there is no first-paint -> post-ready layout jump. */
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

class BundleCssInliner {
  constructor(css){ this.css=css||''; }
  element(element){ if(this.css) element.replace(`<style id="runner5-v100-bundle">${this.css.replace(/<\/style/gi,'<\\/style')}</style>`,{html:true}); }
}

function cloneWithHeaders(response,extra={}){
  const headers=new Headers(response.headers);for(const[k,v]of Object.entries(extra))headers.set(k,v);
  return new Response(response.body,{status:response.status,statusText:response.statusText,headers});
}

export default {
  async fetch(request,env){
    const url=new URL(request.url);
    if(url.pathname==='/__runner5/v100/health'){
      return Response.json({ok:true,gateway:'runner5-restore-gateway-v100',downstream:'runner5-restore-proxy',candidate:6},{headers:{'Cache-Control':'no-store','X-Robots-Tag':'noindex,nofollow'}});
    }
    if(!env.EDGE||typeof env.EDGE.fetch!=='function') return new Response('Runner5 V100 downstream unavailable',{status:503,headers:{'Cache-Control':'no-store'}});

    const htmlCandidate=request.method==='GET'&&!LONG_CACHE_RE.test(url.pathname)&&!url.pathname.startsWith('/wp-content/')&&!url.pathname.startsWith('/wp-includes/');
    const upstreamP=env.EDGE.fetch(request);
    const cssP=htmlCandidate?env.EDGE.fetch(new Request(new URL('/__edge/runner5.css',url.origin),{headers:{Accept:'text/css','User-Agent':'Runner5V100Candidate6/1.0'}})).catch(()=>null):Promise.resolve(null);
    const [upstream,cssResp]=await Promise.all([upstreamP,cssP]);

    if(request.method!=='POST'&&(LONG_CACHE_RE.test(url.pathname)||url.pathname.startsWith('/wp-content/')||url.pathname.startsWith('/wp-includes/'))){
      return cloneWithHeaders(upstream,{'Cache-Control':'public,max-age=31536000,immutable','X-Runner5-V100':'candidate-6-asset'});
    }
    const type=upstream.headers.get('Content-Type')||'';
    if(request.method==='HEAD'||upstream.status!==200||!/text\/html/i.test(type)) return upstream;

    let css='';if(cssResp&&cssResp.ok)css=await cssResp.text();
    const headers=new Headers(upstream.headers);headers.set('X-Runner5-V100','candidate-6');headers.set('Cache-Control','public,max-age=60,stale-while-revalidate=300');
    let response=new Response(upstream.body,{status:upstream.status,statusText:upstream.statusText,headers});
    let rewriter=new HTMLRewriter().on('head',new HeadEnhancer()).on('button.sb-search-button-open',new SearchButtonA11y()).on('h3.entry-title',new EntryHeadingA11y());
    if(css)rewriter=rewriter.on('link[href*="/__edge/runner5.css"]',new BundleCssInliner(css));
    return rewriter.transform(response);
  }
};
