import worker from './index.js';

const R2_ORIGIN = 'https://pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const R2_HOST = 'pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';

class HeadResourceHints {
  element(element) {
    // Start the R2 DNS/TLS connection before the browser reaches the hero preload.
    // Images themselves remain direct R2 URLs; no transform/proxy layer is involved.
    element.prepend(
      `<link rel="dns-prefetch" href="//${R2_HOST}"><link rel="preconnect" href="${R2_ORIGIN}" crossorigin>`,
      { html: true },
    );
  }
}

export default {
  async fetch(request, env, ctx) {
    const response = await worker.fetch(request, env, ctx);
    const contentType = response.headers.get('Content-Type') || '';

    // Keep the public edge surface intentionally out of search indexes while
    // preserving crawlability so bots can actually observe the noindex directive.
    if (/text\/html/i.test(contentType)) {
      const headers = new Headers(response.headers);
      headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet');
      // The HTTP Link hint is visible as soon as response headers arrive; the HTML
      // hint below is a compatible fallback and appears before the existing LCP preload.
      headers.append('Link', `<${R2_ORIGIN}>; rel=preconnect; crossorigin`);
      let htmlResponse = new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
      if (request.method.toUpperCase() !== 'HEAD') {
        htmlResponse = new HTMLRewriter().on('head', new HeadResourceHints()).transform(htmlResponse);
      }
      return htmlResponse;
    }

    return response;
  },
};
