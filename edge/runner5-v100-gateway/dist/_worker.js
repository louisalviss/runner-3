// Runner5 isolated V100 candidate gateway.
// Keeps WordPress/restore untouched; transforms only public output from the
// proven runner5-restore-proxy service binding.

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
    element.append(
      '<meta name="description" content="Runner5 Restore Lab Demo — verified WordPress restore staging site for automated restore and performance validation.">',
      { html: true },
    );
    element.append(
      `<style id="runner5-v100-a11y">
        .entry-meta .entry-author,
        .entry-meta .entry-date,
        .entry-meta time.entry-date { color:#595959 !important; }
        #colophon .site-info .copyright > span,
        #colophon .site-info .copyright > span a { color:#f5f5f5 !important; }
      </style>`,
      { html: true },
    );
  }
}

class BundleCssInliner {
  constructor(css) { this.css = css; }
  element(element) {
    if (!this.css) return;
    const safe = this.css.replace(/<\/style/gi, '<\\/style');
    element.replace(`<style id="runner5-v100-bundle">${safe}</style>`, { html: true });
  }
}

function cloneWithHeaders(response, extra = {}) {
  const headers = new Headers(response.headers);
  for (const [k, v] of Object.entries(extra)) headers.set(k, v);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/__runner5/v100/health') {
      return Response.json({ ok: true, gateway: 'runner5-restore-gateway-v100', downstream: 'runner5-restore-proxy', candidate: 2 }, {
        headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
      });
    }
    if (!env.EDGE || typeof env.EDGE.fetch !== 'function') {
      return new Response('Runner5 V100 downstream unavailable', { status: 503, headers: { 'Cache-Control': 'no-store' } });
    }

    const downstreamPromise = env.EDGE.fetch(request);
    const likelyHtml = request.method === 'GET' && !LONG_CACHE_RE.test(url.pathname) && !url.pathname.startsWith('/wp-content/') && !url.pathname.startsWith('/wp-includes/');
    const cssPromise = likelyHtml
      ? env.EDGE.fetch(new Request(new URL('/__edge/runner5.css', url.origin), { headers: { Accept: 'text/css', 'User-Agent': 'Runner5V100CssInline/1.0' } })).catch(() => null)
      : Promise.resolve(null);

    const [downstream, cssResponse] = await Promise.all([downstreamPromise, cssPromise]);
    const type = downstream.headers.get('Content-Type') || '';

    // Give immutable public assets a long browser cache. The WordPress origin and
    // private/admin responses are still controlled by the downstream worker.
    if (request.method !== 'POST' && (LONG_CACHE_RE.test(url.pathname) || url.pathname.startsWith('/wp-content/') || url.pathname.startsWith('/wp-includes/'))) {
      return cloneWithHeaders(downstream, {
        'Cache-Control': 'public, max-age=31536000, immutable',
        'X-Runner5-V100': 'candidate-2-asset',
      });
    }

    if (request.method === 'HEAD' || !/text\/html/i.test(type) || downstream.status !== 200) return downstream;

    let bundleCss = '';
    if (cssResponse && cssResponse.ok) bundleCss = await cssResponse.text();

    const headers = new Headers(downstream.headers);
    headers.set('X-Runner5-V100', 'candidate-2');
    let response = new Response(downstream.body, { status: downstream.status, statusText: downstream.statusText, headers });
    let rewriter = new HTMLRewriter()
      .on('head', new HeadEnhancer())
      .on('button.sb-search-button-open', new SearchButtonA11y())
      .on('h3.entry-title', new EntryHeadingA11y());
    if (bundleCss) rewriter = rewriter.on('link[href*="/__edge/runner5.css"]', new BundleCssInliner(bundleCss));
    return rewriter.transform(response);
  },
};
