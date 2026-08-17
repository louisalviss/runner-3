import fs from 'fs';

const requestPath = process.env.WP_CONTROL_REQUEST;
if (!requestPath || !fs.existsSync(requestPath)) throw new Error('WP_CONTROL_REQUEST missing');
if (!fs.existsSync('/tmp/wp-control.json')) throw new Error('decrypted WordPress control credential missing');

const req = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
const cred = JSON.parse(fs.readFileSync('/tmp/wp-control.json', 'utf8'));
const base = String(cred.siteUrl || '').replace(/\/$/, '');
const slug = req.site_slug || cred.siteSlug;
const action = req.action;
const payload = req.payload || {};
if (!base || !cred.username || !cred.applicationPassword) throw new Error('WordPress control credential incomplete');
if (!action) throw new Error('request action missing');

const auth = 'Basic ' + Buffer.from(`${cred.username}:${cred.applicationPassword}`).toString('base64');
async function api(path, { method='GET', body=null, headers={} } = {}) {
  if (!String(path).startsWith('/wp-json/')) throw new Error('REST path must start with /wp-json/');
  const opts = { method, headers: { Authorization: auth, Accept: 'application/json', ...headers } };
  if (body !== null) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(base + path, opts);
  const text = await r.text();
  let data; try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text.slice(0, 2000) }; }
  if (!r.ok) throw new Error(`WP REST ${method} ${path} failed ${r.status}: ${JSON.stringify(data).slice(0,600)}`);
  return { status: r.status, data };
}

let result;
switch (action) {
  case 'inspect': {
    const me = await api('/wp-json/wp/v2/users/me?context=edit');
    const settings = await api('/wp-json/wp/v2/settings');
    const plugins = await api('/wp-json/wp/v2/plugins?context=edit&per_page=100').catch(e => ({ status: null, data: { unavailable: e.message } }));
    result = { me: me.data, settings: settings.data, plugins: plugins.data };
    break;
  }
  case 'create_post': result = (await api('/wp-json/wp/v2/posts', { method: 'POST', body: payload })).data; break;
  case 'update_post': {
    if (!payload.id) throw new Error('payload.id required');
    const { id, ...body } = payload; result = (await api(`/wp-json/wp/v2/posts/${id}`, { method: 'POST', body })).data; break;
  }
  case 'delete_post': {
    if (!payload.id) throw new Error('payload.id required');
    result = (await api(`/wp-json/wp/v2/posts/${payload.id}?force=${payload.force ? 'true' : 'false'}`, { method: 'DELETE' })).data; break;
  }
  case 'create_page': result = (await api('/wp-json/wp/v2/pages', { method: 'POST', body: payload })).data; break;
  case 'update_page': {
    if (!payload.id) throw new Error('payload.id required');
    const { id, ...body } = payload; result = (await api(`/wp-json/wp/v2/pages/${id}`, { method: 'POST', body })).data; break;
  }
  case 'delete_page': {
    if (!payload.id) throw new Error('payload.id required');
    result = (await api(`/wp-json/wp/v2/pages/${payload.id}?force=${payload.force ? 'true' : 'false'}`, { method: 'DELETE' })).data; break;
  }
  case 'update_settings': result = (await api('/wp-json/wp/v2/settings', { method: 'POST', body: payload })).data; break;
  case 'install_plugin': {
    if (!payload.slug) throw new Error('payload.slug required');
    result = (await api('/wp-json/wp/v2/plugins', { method: 'POST', body: { slug: payload.slug, status: payload.status || 'active' } })).data; break;
  }
  case 'set_plugin_status': {
    if (!payload.plugin || !payload.status) throw new Error('payload.plugin and payload.status required');
    result = (await api(`/wp-json/wp/v2/plugins/${encodeURIComponent(payload.plugin)}`, { method: 'POST', body: { status: payload.status } })).data; break;
  }
  case 'delete_plugin': {
    if (!payload.plugin) throw new Error('payload.plugin required');
    result = (await api(`/wp-json/wp/v2/plugins/${encodeURIComponent(payload.plugin)}`, { method: 'DELETE' })).data; break;
  }
  case 'rest': {
    const path = String(payload.path || '');
    const method = String(payload.method || 'GET').toUpperCase();
    result = (await api(path, { method, body: payload.body ?? null })).data; break;
  }
  default: throw new Error(`unsupported action: ${action}`);
}

const safe = {
  status: 'ok', siteSlug: slug, action,
  summary: Array.isArray(result) ? { type: 'array', count: result.length } : { type: typeof result, id: result?.id ?? null, slug: result?.slug ?? null, status: result?.status ?? null },
  result,
  updatedAt: new Date().toISOString()
};
const out = `/tmp/wp-control-result-${slug}.json`;
fs.writeFileSync(out, JSON.stringify(safe, null, 2));
console.log(`WP_CONTROL_OK site=${slug} action=${action}`);
