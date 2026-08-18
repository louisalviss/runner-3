const ALLOWED_MODELS = new Set([
  '@cf/openai/gpt-oss-120b',
  '@cf/openai/gpt-oss-20b',
]);

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

export default {
  async fetch(request, env) {
    if (!env.AUTOCONTENT_PROXY_KEY) {
      return json({ success: false, error: 'proxy_not_configured' }, 503);
    }

    const auth = request.headers.get('authorization') || '';
    if (auth !== `Bearer ${env.AUTOCONTENT_PROXY_KEY}`) {
      return json({ success: false, error: 'unauthorized' }, 401);
    }

    if (request.method !== 'POST') {
      return json({ success: false, error: 'method_not_allowed' }, 405);
    }

    const contentLength = Number(request.headers.get('content-length') || 0);
    if (contentLength > 700_000) {
      return json({ success: false, error: 'payload_too_large' }, 413);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ success: false, error: 'invalid_json' }, 400);
    }

    const model = String(body.model || '@cf/openai/gpt-oss-120b');
    if (!ALLOWED_MODELS.has(model)) {
      return json({ success: false, error: 'model_not_allowed' }, 400);
    }

    const messages = Array.isArray(body.messages) ? body.messages : [];
    if (!messages.length || messages.length > 40) {
      return json({ success: false, error: 'invalid_messages' }, 400);
    }

    const input = {
      messages,
      temperature: Math.min(1, Math.max(0, Number(body.temperature ?? 0.2))),
      max_tokens: Math.min(6000, Math.max(16, Number(body.max_tokens ?? 5000))),
    };

    try {
      const result = await env.AI.run(model, input);
      return json({ success: true, model, result });
    } catch (error) {
      return json({
        success: false,
        error: 'workers_ai_failed',
        detail: String(error?.message || error).slice(0, 800),
      }, 502);
    }
  },
};
