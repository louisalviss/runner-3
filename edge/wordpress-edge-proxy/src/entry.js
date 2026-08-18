import worker from './index.js';

export default {
  async fetch(request, env, ctx) {
    const response = await worker.fetch(request, env, ctx);
    const contentType = response.headers.get('Content-Type') || '';

    // Keep the public edge surface intentionally out of search indexes while
    // preserving crawlability so bots can actually observe the noindex directive.
    if (/text\/html/i.test(contentType)) {
      const headers = new Headers(response.headers);
      headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet');
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    }

    return response;
  },
};
