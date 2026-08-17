const HTML_HEADERS = { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' };
const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };

function esc(s='') {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function page(title, body) {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title><style>body{font-family:system-ui,-apple-system,sans-serif;max-width:680px;margin:48px auto;padding:0 18px;line-height:1.5}input,button{font:inherit;padding:12px;border-radius:10px;border:1px solid #bbb}input{width:100%;box-sizing:border-box;margin:6px 0 14px}button{cursor:pointer;font-weight:650}.ok{padding:14px;border:1px solid #9c9;border-radius:12px;background:#f4fff4}.bad{padding:14px;border:1px solid #c99;border-radius:12px;background:#fff5f5}code{word-break:break-all}</style></head><body>${body}</body></html>`;
}

function ua(username) {
  return `web:runner3-reddit-reader:v1.0 (by /u/${username})`;
}

async function refreshAccess(env, creds) {
  const auth = btoa(`${creds.client_id}:`);
  const form = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: creds.refresh_token });
  const r = await fetch('https://www.reddit.com/api/v1/access_token', {
    method: 'POST',
    headers: {
      'authorization': `Basic ${auth}`,
      'content-type': 'application/x-www-form-urlencoded',
      'user-agent': ua(creds.username),
    },
    body: form,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.access_token) throw new Error(`refresh_failed:${r.status}:${JSON.stringify(data).slice(0,300)}`);
  return data.access_token;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = url.origin;

    if (url.pathname === '/health') {
      return new Response(JSON.stringify({ ok: true, service: 'runner3-reddit-oauth' }), { headers: JSON_HEADERS });
    }

    if (url.pathname === '/') {
      const hasCreds = !!(await env.AUTH_KV.get('reddit:credentials'));
      return new Response(page('Runner3 Reddit OAuth', `
        <h1>Runner3 Reddit OAuth</h1>
        <p>${hasCreds ? '<b>Đã có Reddit refresh token trong KV.</b>' : 'Chưa authorize Reddit.'}</p>
        <p>Tạo Reddit app loại <b>installed app</b> với Redirect URI chính xác:</p>
        <p><code>${esc(origin + '/callback')}</code></p>
        <form action="/start" method="get">
          <label>Reddit Client ID</label><input name="client_id" autocomplete="off" required placeholder="client id dưới tên app">
          <label>Reddit username</label><input name="username" autocomplete="off" required placeholder="username không có /u/">
          <button type="submit">Authorize Reddit</button>
        </form>
        <p><a href="/status">Kiểm tra trạng thái</a></p>
      `), { headers: HTML_HEADERS });
    }

    if (url.pathname === '/start') {
      const clientId = (url.searchParams.get('client_id') || '').trim();
      const username = (url.searchParams.get('username') || '').trim().replace(/^\/u\//, '');
      if (!/^[A-Za-z0-9_-]{5,80}$/.test(clientId) || !/^[A-Za-z0-9_-]{3,30}$/.test(username)) {
        return new Response(page('Invalid input', '<div class="bad">Client ID hoặc username không hợp lệ.</div>'), { status: 400, headers: HTML_HEADERS });
      }
      const state = crypto.randomUUID().replaceAll('-', '');
      await env.AUTH_KV.put(`state:${state}`, JSON.stringify({ client_id: clientId, username, created_at: Date.now() }), { expirationTtl: 600 });
      const auth = new URL('https://www.reddit.com/api/v1/authorize');
      auth.searchParams.set('client_id', clientId);
      auth.searchParams.set('response_type', 'code');
      auth.searchParams.set('state', state);
      auth.searchParams.set('redirect_uri', `${origin}/callback`);
      auth.searchParams.set('duration', 'permanent');
      auth.searchParams.set('scope', 'read identity');
      return Response.redirect(auth.toString(), 302);
    }

    if (url.pathname === '/callback') {
      const state = url.searchParams.get('state') || '';
      const code = url.searchParams.get('code') || '';
      const error = url.searchParams.get('error') || '';
      const raw = state ? await env.AUTH_KV.get(`state:${state}`) : null;
      if (error) return new Response(page('Reddit OAuth denied', `<div class="bad">Reddit trả lỗi: ${esc(error)}</div>`), { status: 400, headers: HTML_HEADERS });
      if (!raw || !code) return new Response(page('Invalid OAuth callback', '<div class="bad">State/code không hợp lệ hoặc đã hết hạn.</div>'), { status: 400, headers: HTML_HEADERS });
      const pending = JSON.parse(raw);
      const redirectUri = `${origin}/callback`;
      const auth = btoa(`${pending.client_id}:`);
      const form = new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: redirectUri });
      const tr = await fetch('https://www.reddit.com/api/v1/access_token', {
        method: 'POST',
        headers: {
          'authorization': `Basic ${auth}`,
          'content-type': 'application/x-www-form-urlencoded',
          'user-agent': ua(pending.username),
        },
        body: form,
      });
      const td = await tr.json().catch(() => ({}));
      if (!tr.ok || !td.refresh_token) {
        return new Response(page('Token exchange failed', `<div class="bad">Token exchange thất bại (${tr.status}). Không lưu credential.</div>`), { status: 502, headers: HTML_HEADERS });
      }
      const creds = {
        client_id: pending.client_id,
        username: pending.username,
        refresh_token: td.refresh_token,
        scope: td.scope || 'read identity',
        stored_at: new Date().toISOString(),
      };
      await env.AUTH_KV.put('reddit:credentials', JSON.stringify(creds));
      await env.AUTH_KV.delete(`state:${state}`);
      return new Response(page('Reddit connected', `<div class="ok"><h2>Authorize thành công</h2><p>Refresh token đã được lưu trong Cloudflare KV, không ghi vào GitHub repo hay log.</p><p><a href="/status">Verify Reddit connection</a></p></div>`), { headers: HTML_HEADERS });
    }

    if (url.pathname === '/status') {
      const raw = await env.AUTH_KV.get('reddit:credentials');
      if (!raw) return new Response(page('Not connected', '<div class="bad">Chưa có Reddit credential.</div>'), { status: 404, headers: HTML_HEADERS });
      try {
        const creds = JSON.parse(raw);
        const access = await refreshAccess(env, creds);
        const me = await fetch('https://oauth.reddit.com/api/v1/me', {
          headers: { 'authorization': `bearer ${access}`, 'user-agent': ua(creds.username) },
        });
        const md = await me.json().catch(() => ({}));
        if (!me.ok) throw new Error(`me_failed:${me.status}`);
        return new Response(page('Connected', `<div class="ok"><h2>Reddit OAuth hoạt động</h2><p>Account: <b>${esc(md.name || creds.username)}</b></p><p>Scope: <code>${esc(creds.scope)}</code></p><p>Stored: ${esc(creds.stored_at || '')}</p></div>`), { headers: HTML_HEADERS });
      } catch (e) {
        return new Response(page('Connection failed', `<div class="bad">Credential tồn tại nhưng verify thất bại: ${esc(String(e.message || e))}</div>`), { status: 502, headers: HTML_HEADERS });
      }
    }

    return new Response('Not found', { status: 404 });
  }
};
