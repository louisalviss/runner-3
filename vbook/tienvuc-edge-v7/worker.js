function hexToBytes(hex) {
  var clean = String(hex || '');
  var out = new Uint8Array(clean.length / 2);
  for (var i = 0; i < out.length; i++) out[i] = parseInt(clean.substr(i * 2, 2), 16);
  return out;
}

async function decryptChapter(cipherHex) {
  var text = String(cipherHex || '').trim();
  if (!/^[0-9a-f]+$/i.test(text) || text.length < 64 || text.length % 2) throw new Error('BAD_CIPHER');
  var keyBytes = new TextEncoder().encode('2bd40f62d20c1c49237a109d491974eb');
  var iv = hexToBytes(text.slice(0, 32));
  var cipher = hexToBytes(text.slice(32));
  var key = await crypto.subtle.importKey('raw', keyBytes, { name: 'AES-CBC' }, false, ['decrypt']);
  var plain = await crypto.subtle.decrypt({ name: 'AES-CBC', iv: iv }, key, cipher);
  return new TextDecoder('utf-8', { fatal: false }).decode(plain);
}

function reply(body, status, type) {
  return new Response(body, { status: status, headers: {
    'content-type': type || 'text/plain; charset=utf-8',
    'cache-control': 'no-store, private, max-age=0',
    'x-content-type-options': 'nosniff'
  }});
}
export default {
  async fetch(request) {
    try {
      var u = new URL(request.url);
      if (u.pathname === '/health') return reply('ok', 200);
      if (u.pathname !== '/chapter' || request.method !== 'GET') return reply('not found', 404);
      var slug = u.searchParams.get('slug') || '';
      var num = u.searchParams.get('num') || '';
      if (!/^[0-9a-z-]+$/.test(slug) || !/^\d+$/.test(num)) return reply('bad request', 400);
      var upstream = 'https://tienvuc.me/api/reading/' + encodeURIComponent(slug) + '/chapters/' + encodeURIComponent(num) + '/content';
      var headers = { 'User-Agent': 'Mozilla/5.0 VBook-TienVuc-Proxy/2.0' };
      var auth = request.headers.get('authorization') || '';
      if (auth) headers.authorization = auth;
      var r = await fetch(upstream, { method: 'GET', headers: headers, redirect: 'follow' });
      if (!r.ok) return reply('upstream ' + r.status, r.status);
      var content = await decryptChapter(await r.text());
      if (!content) return reply('decrypt empty', 502);
      if (content.indexOf('Đây là chương VIP') !== -1) return reply(auth ? 'vip not purchased or auth expired' : 'vip auth required', 402);
      return reply(content, 200, 'text/html; charset=utf-8');
    } catch (e) {
      return reply('proxy error', 502);
    }
  }
};
