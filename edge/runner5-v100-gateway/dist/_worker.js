// Runner5 isolated V100 candidate gateway.
// Keeps WordPress/restore untouched; only transforms anonymous public HTML
// returned by the proven runner5-restore-proxy service binding.

class SearchButtonA11y {
  element(element) {
    if (!element.getAttribute('aria-label')) element.setAttribute('aria-label', 'Open search');
    if (!element.getAttribute('title')) element.setAttribute('title', 'Open search');
  }
}

class EntryHeadingA11y {
  element(element) {
    // Lighthouse sees these card titles as H3 directly after H1. Preserve visual
    // styling/tag while exposing the correct level to the accessibility tree.
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
        .entry-meta time.entry-date {
          color: #595959 !important;
        }
      </style>`,
      { html: true },
    );
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/__runner5/v100/health') {
      return Response.json({ ok: true, gateway: 'runner5-restore-gateway-v100', downstream: 'runner5-restore-proxy' }, {
        headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
      });
    }
    if (!env.EDGE || typeof env.EDGE.fetch !== 'function') {
      return new Response('Runner5 V100 downstream unavailable', { status: 503, headers: { 'Cache-Control': 'no-store' } });
    }

    const downstream = await env.EDGE.fetch(request);
    const type = downstream.headers.get('Content-Type') || '';
    if (request.method === 'HEAD' || !/text\/html/i.test(type) || downstream.status !== 200) return downstream;

    const headers = new Headers(downstream.headers);
    headers.set('X-Runner5-V100', 'candidate-1');
    let response = new Response(downstream.body, { status: downstream.status, statusText: downstream.statusText, headers });
    response = new HTMLRewriter()
      .on('head', new HeadEnhancer())
      .on('button.sb-search-button-open', new SearchButtonA11y())
      .on('h3.entry-title', new EntryHeadingA11y())
      .transform(response);
    return response;
  },
};
