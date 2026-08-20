import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';

const slug = process.env.WP_SITE_SLUG || 'runner3-speed-site3-realistic';
const site = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl).replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const mediaDir = process.env.SITE3_MEDIA_DIR || '/tmp/runner3-site3-media';
const out = '/tmp/runner3-speed-site3-seed.json';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const result = {
  status: 'STARTING',
  siteUrl: `${base}/`,
  theme: null,
  plugins: {},
  starterImport: {
    required: false,
    status: 'skipped',
    reason: 'deterministic_rest_seed_is_canonical'
  },
  pages: [],
  posts: [],
  media: [],
  menu: null,
  homeId: null,
  blogId: null,
  verify: null,
  detail: null,
  updatedAt: new Date().toISOString()
};
const save = () => {
  result.updatedAt = new Date().toISOString();
  fs.writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
};
const onLogin = page => /\/login(?:[/?#]|$)/i.test(page.url());

async function login(page) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
      if (!onLogin(page)) return;
      const ident = page.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
      await ident.waitFor({ state: 'visible', timeout: 15000 });
      await ident.fill(account.username || account.email);
      await ident.press('Enter');
      const pass = page.locator('input[type=password]').first();
      await pass.waitFor({ state: 'visible', timeout: 20000 });
      await pass.fill(account.password);
      await pass.press('Enter');
      await sleep(2200);
      if (!onLogin(page)) return;
    } catch {}
    await sleep(1000 * attempt);
  }
  throw new Error('wasmer_login_failed');
}

async function pollAdmin(ctx, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    for (const page of ctx.pages()) {
      if (page.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(page.url()) && !/wp-login\.php/i.test(page.url())) return page;
    }
    await sleep(500);
  }
  return null;
}

async function enterAdmin(ctx, page) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
    await sleep(900);
    let control = page.getByText(/WordPress Admin/i).first();
    if (await control.isVisible().catch(() => false)) {
      const href = await control.getAttribute('href').catch(() => null);
      if (href) {
        const wp = await ctx.newPage();
        await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        const found = await pollAdmin(ctx, 18000);
        if (found) return found;
      }
      await control.click({ noWaitAfter: true }).catch(() => {});
      const found = await pollAdmin(ctx, 22000);
      if (found) return found;
    }
  }
  throw new Error('magic_admin_failed');
}

async function nonce(wp) {
  await wp.goto(`${base}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(500);
  let value = await wp.evaluate(() => globalThis.wpApiSettings?.nonce || globalThis.wp?.apiSettings?.nonce || null).catch(() => null);
  if (!value) {
    const html = await wp.content();
    const match = html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);
    if (match) value = match[1];
  }
  if (!value) throw new Error('wp_rest_nonce_missing');
  return value;
}

async function api(ctx, n, endpoint, { method = 'GET', json = null, headers = {} } = {}) {
  const requestHeaders = { 'X-WP-Nonce': n, Accept: 'application/json', ...headers };
  let data;
  if (json !== null) {
    requestHeaders['Content-Type'] = 'application/json';
    data = JSON.stringify(json);
  }
  const response = await ctx.request.fetch(`${base}/wp-json${endpoint}`, {
    method,
    headers: requestHeaders,
    data,
    timeout: 120000,
    failOnStatusCode: false
  });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  if (!response.ok()) throw new Error(`api_${method}_${endpoint}:${response.status()}:${String(text).slice(0, 260)}`);
  return body;
}

async function ensureTheme(wp, themeSlug, themeName) {
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  let active = wp.locator(`.theme.active[data-slug="${themeSlug}"]`).first();
  if (await active.count()) {
    result.theme = themeSlug;
    return;
  }

  let card = wp.locator(`.theme[data-slug="${themeSlug}"]`).first();
  if (!(await card.count())) {
    await wp.goto(`${base}/wp-admin/theme-install.php?search=${encodeURIComponent(themeSlug)}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(1400);
    let install = wp.locator(`a[href*="action=install-theme"][href*="theme=${themeSlug}"],a.theme-install[href*="${themeSlug}"]`).first();
    let href = await install.getAttribute('href').catch(() => null);
    if (!href) {
      const html = await wp.content();
      const re = new RegExp(`href=["']([^"']*(?:action=install-theme[^"']*theme=${themeSlug}|theme=${themeSlug}[^"']*action=install-theme)[^"']*)["']`, 'i');
      const match = html.match(re);
      if (match) href = match[1].replaceAll('&amp;', '&');
    }
    if (!href) throw new Error(`${themeSlug}_install_url_missing`);
    await wp.goto(new URL(href, base).href, { waitUntil: 'domcontentloaded', timeout: 120000 });
    await sleep(1200);
  }

  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  card = wp.locator(`.theme[data-slug="${themeSlug}"]`).first();
  if (!(await card.count())) throw new Error(`${themeSlug}_not_installed`);
  active = wp.locator(`.theme.active[data-slug="${themeSlug}"]`).first();
  if (!(await active.count())) {
    const activate = card.locator('a.activate,a[href*="action=activate"]').first();
    const href = await activate.getAttribute('href').catch(() => null);
    if (!href) throw new Error(`${themeSlug}_activate_url_missing`);
    await wp.goto(new URL(href, base).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  }

  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  active = wp.locator(`.theme.active[data-slug="${themeSlug}"]`).first();
  if (!(await active.count())) throw new Error(`${themeName}_activation_failed`);
  result.theme = themeSlug;
}

async function listPlugins(ctx, n) {
  return api(ctx, n, '/wp/v2/plugins?context=edit');
}

async function ensurePlugin(ctx, n, pluginSlug, prefix) {
  const plugins = await listPlugins(ctx, n);
  let plugin = Array.isArray(plugins) ? plugins.find(item => String(item.plugin || '').startsWith(prefix)) : null;
  if (!plugin) plugin = await api(ctx, n, '/wp/v2/plugins', { method: 'POST', json: { slug: pluginSlug, status: 'active' } });
  else if (plugin.status !== 'active') plugin = await api(ctx, n, `/wp/v2/plugins/${encodeURIComponent(plugin.plugin)}`, { method: 'POST', json: { status: 'active' } });
  return plugin;
}

async function removePlugin(ctx, n, prefix) {
  const plugins = await listPlugins(ctx, n);
  const plugin = Array.isArray(plugins) ? plugins.find(item => String(item.plugin || '').startsWith(prefix)) : null;
  if (!plugin) return false;
  if (plugin.status === 'active') {
    await api(ctx, n, `/wp/v2/plugins/${encodeURIComponent(plugin.plugin)}`, { method: 'POST', json: { status: 'inactive' } });
  }
  await api(ctx, n, `/wp/v2/plugins/${encodeURIComponent(plugin.plugin)}`, { method: 'DELETE' });
  return true;
}

async function deleteCollection(ctx, n, type) {
  const items = await api(ctx, n, `/wp/v2/${type}?per_page=100&context=edit`);
  if (!Array.isArray(items)) return 0;
  for (const item of items) {
    await api(ctx, n, `/wp/v2/${type}/${item.id}?force=true`, { method: 'DELETE' });
  }
  return items.length;
}

async function resetContent(ctx, n) {
  await deleteCollection(ctx, n, 'menu-items').catch(() => 0);
  await deleteCollection(ctx, n, 'menus').catch(() => 0);
  await deleteCollection(ctx, n, 'posts');
  await deleteCollection(ctx, n, 'pages');
  await deleteCollection(ctx, n, 'media');
}

async function uploadMedia(ctx, n, file, title) {
  const bytes = fs.readFileSync(file);
  const response = await ctx.request.fetch(`${base}/wp-json/wp/v2/media`, {
    method: 'POST',
    headers: {
      'X-WP-Nonce': n,
      'Content-Type': 'image/jpeg',
      'Content-Disposition': `attachment; filename="${path.basename(file)}"`,
      Accept: 'application/json'
    },
    data: bytes,
    timeout: 120000,
    failOnStatusCode: false
  });
  const text = await response.text();
  if (!response.ok()) throw new Error(`media_upload_${response.status()}:${text.slice(0, 240)}`);
  const media = JSON.parse(text);
  await api(ctx, n, `/wp/v2/media/${media.id}`, {
    method: 'POST',
    json: { title, alt_text: title, caption: `${title} — Runner3 deterministic Blocksy benchmark` }
  });
  return { id: media.id, source_url: media.source_url, alt_text: title };
}

async function createPost(ctx, n, type, title, postSlug, content, extra = {}) {
  return api(ctx, n, `/wp/v2/${type}`, {
    method: 'POST',
    json: { title, slug: postSlug, content, status: 'publish', comment_status: 'closed', ...extra }
  });
}

const esc = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const image = (media, priority = false) => `<figure class="wp-block-image size-full"><img src="${esc(media.source_url)}" alt="${esc(media.alt_text)}" class="wp-image-${media.id}" width="1600" height="1000" ${priority ? 'fetchpriority="high"' : 'loading="lazy"'} decoding="async"></figure>`;

function homeHtml(media) {
  const links = [['Home','/'],['Services','/services/'],['Projects','/projects/'],['Journal','/blog/'],['About','/about/'],['Contact','/contact/']];
  return `<div class="runner3-benchmark-home">
<nav class="runner3-benchmark-local-nav" aria-label="Benchmark navigation">${links.map(([label, href]) => `<a href="${href}">${label}</a>`).join(' · ')}</nav>
<section data-r3-section="hero" style="max-width:1180px;margin:auto;padding:28px 24px 64px"><p style="letter-spacing:.12em;text-transform:uppercase;font-weight:700">Northline Studio</p><h1 style="font-size:clamp(42px,7vw,86px);line-height:1.02;margin:.2em 0">Build spaces that work harder.</h1><p style="font-size:21px;max-width:760px">Architecture, construction and interior delivery for growing businesses. Strategy, design and build managed as one practical system.</p>${image(media[0], true)}</section>
<section data-r3-section="projects" style="max-width:1180px;margin:auto;padding:56px 24px"><h2>Selected projects</h2><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px">${media.slice(1,7).map((item, i) => `<article>${image(item)}<h3>${['Harbor House','Foundry Offices','Mesa Retail','West End Loft','North Works','Civic Courtyard'][i]}</h3><p>Full-scope design, material coordination and delivery with a focus on durability and clear operating costs.</p></article>`).join('')}</div></section>
<section data-r3-section="services" style="max-width:1180px;margin:auto;padding:56px 24px"><h2>What we do</h2><div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:28px"><div><h3>Architecture</h3><p>Briefing, planning, documentation and approvals.</p></div><div><h3>Interiors</h3><p>Workplace, hospitality and residential interiors.</p></div><div><h3>Construction</h3><p>Cost control, procurement, site delivery and handover.</p></div></div></section>
<section data-r3-section="process" style="max-width:1180px;margin:auto;padding:56px 24px"><h2>A practical delivery process</h2><ol><li>Define constraints and success criteria.</li><li>Develop the design against cost and programme.</li><li>Coordinate procurement and construction.</li><li>Commission, document and hand over.</li></ol>${image(media[7])}</section>
<section data-r3-section="evidence" style="max-width:1180px;margin:auto;padding:56px 24px"><h2>Built for measurable outcomes</h2><div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px"><article><strong>18</strong><p>Local project assets.</p></article><article><strong>18</strong><p>Editorial posts with featured images.</p></article><article><strong>8</strong><p>Core business pages.</p></article></div></section>
<section data-r3-section="cta" style="max-width:1180px;margin:auto;padding:56px 24px">${image(media[8])}<blockquote style="font-size:28px;line-height:1.35;margin:34px 0">A good project should feel simpler after we arrive, not more complicated.</blockquote><p><a href="/contact/">Start a project →</a></p></section>
</div>`;
}

function pageHtml(title, media, a, b) {
  return `<section data-r3-section="page-${esc(title.toLowerCase().replace(/[^a-z0-9]+/g, '-'))}" style="max-width:1180px;margin:auto;padding:56px 24px"><h1>${esc(title)}</h1><p style="font-size:20px;max-width:760px">A complete benchmark page with local media, long-form content, cards and project imagery.</p>${image(media[a])}<h2>Approach</h2><p>We work from measurable constraints: site, budget, programme, maintenance and user needs. Each decision is documented so design intent survives procurement and construction.</p><div style="display:grid;grid-template-columns:1fr 1fr;gap:28px">${image(media[b])}<div><h2>Delivery</h2><p>Concept design, developed design, tender documentation, procurement support, construction administration and final handover.</p><ul><li>Clear scope and milestones</li><li>Material and cost reviews</li><li>Weekly project reporting</li><li>Commissioning and close-out</li></ul></div></div></section>`;
}

async function buildMenu(ctx, n, pages) {
  const rawLocations = await api(ctx, n, '/wp/v2/menu-locations?context=edit');
  const entries = Array.isArray(rawLocations)
    ? rawLocations.map(item => [item.slug || item.name, item])
    : Object.entries(rawLocations || {});
  const preferred = entries.find(([key, value]) => /primary|main|header|menu[_ -]?1/i.test(`${key} ${value?.name || ''}`)) || entries[0];
  if (!preferred) throw new Error('blocksy_menu_location_missing');
  const location = preferred[0];
  const menu = await api(ctx, n, '/wp/v2/menus', {
    method: 'POST',
    json: { name: 'Runner3 Benchmark Primary', slug: 'runner3-benchmark-primary', locations: [location], auto_add: false }
  });
  const target = pages.filter(page => ['home','services','projects','blog','about','contact'].includes(page.slug));
  for (let i = 0; i < target.length; i++) {
    const page = target[i];
    await api(ctx, n, '/wp/v2/menu-items', {
      method: 'POST',
      json: {
        title: page.title,
        type: 'post_type',
        status: 'publish',
        object: 'page',
        object_id: page.id,
        menu_order: i + 1,
        menus: menu.id
      }
    });
  }
  const assigned = await api(ctx, n, `/wp/v2/menus/${menu.id}?context=edit`);
  if (!Array.isArray(assigned.locations) || !assigned.locations.includes(location)) {
    await api(ctx, n, `/wp/v2/menus/${menu.id}`, { method: 'POST', json: { locations: [location] } });
  }
  return { id: menu.id, location, items: target.length };
}

async function setReadingSettings(ctx, n, wp, homeId, blogId) {
  try {
    await api(ctx, n, '/wp/v2/settings', {
      method: 'POST',
      json: {
        title: 'Northline Studio — Runner3 Benchmark',
        description: 'Deterministic Blocksy + Elementor performance fixture',
        show_on_front: 'page',
        page_on_front: homeId,
        page_for_posts: blogId,
        posts_per_page: 10
      }
    });
    return 'rest';
  } catch {
    await wp.goto(`${base}/wp-admin/options-reading.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const staticRadio = wp.locator('input[name="show_on_front"][value="page"]').first();
    if (await staticRadio.count()) await staticRadio.check();
    const homeSelect = wp.locator('select[name="page_on_front"]').first();
    if (await homeSelect.count()) await homeSelect.selectOption(String(homeId));
    const blogSelect = wp.locator('select[name="page_for_posts"]').first();
    if (await blogSelect.count()) await blogSelect.selectOption(String(blogId));
    const submit = wp.locator('#submit,input[type=submit]').first();
    if (!(await submit.count())) throw new Error('reading_settings_submit_missing');
    await submit.click();
    await wp.waitForLoadState('domcontentloaded').catch(() => {});
    return 'admin-ui';
  }
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();

try {
  await login(page);
  const wp = await enterAdmin(ctx, page);
  await ensureTheme(wp, 'blocksy', 'Blocksy');
  const n = await nonce(wp);

  for (const prefix of ['runner3-speed/', 'astra-sites/', 'ultimate-addons-for-gutenberg/', 'sureforms/']) {
    await removePlugin(ctx, n, prefix).catch(error => {
      if (prefix === 'runner3-speed/') throw error;
    });
  }
  const elementor = await ensurePlugin(ctx, n, 'elementor', 'elementor/');
  result.plugins.elementor = elementor.status || 'active';
  if (result.plugins.elementor !== 'active') throw new Error('elementor_not_active');

  await resetContent(ctx, n);
  save();

  const files = fs.readdirSync(mediaDir).filter(name => /\.jpe?g$/i.test(name)).sort();
  if (files.length < 18) throw new Error(`fixture_media_missing:${files.length}`);
  for (let i = 0; i < 18; i++) {
    result.media.push(await uploadMedia(ctx, n, path.join(mediaDir, files[i]), `Northline project ${i + 1}`));
    save();
  }

  const pageSpecs = [
    ['Home', 'home', homeHtml(result.media)],
    ['About', 'about', pageHtml('About Northline', result.media, 9, 2)],
    ['Services', 'services', pageHtml('Services', result.media, 10, 3)],
    ['Projects', 'projects', pageHtml('Projects', result.media, 11, 4)],
    ['Journal', 'blog', pageHtml('Journal', result.media, 12, 5)],
    ['Contact', 'contact', pageHtml('Contact', result.media, 13, 6)],
    ['Team', 'team', pageHtml('Team', result.media, 14, 7)],
    ['FAQ', 'faq', pageHtml('Frequently Asked Questions', result.media, 15, 8)]
  ];
  for (const [title, pageSlug, content] of pageSpecs) {
    const created = await createPost(ctx, n, 'pages', title, pageSlug, content);
    const row = { id: created.id, title, slug: pageSlug };
    result.pages.push(row);
    if (pageSlug === 'home') result.homeId = created.id;
    if (pageSlug === 'blog') result.blogId = created.id;
    save();
  }

  const titles = [
    'How to budget a commercial fit-out', 'Choosing durable materials', 'Planning approvals without surprises',
    'What makes a good project brief', 'Five lessons from adaptive reuse', 'Lighting for productive workplaces',
    'Reducing operational energy', 'Procurement: where projects lose time', 'Designing for maintenance',
    'When to renovate and when to rebuild', 'A practical handover checklist', 'Post-occupancy reviews that matter',
    'Coordinating consultants without delay', 'Designing flexible workplace layouts', 'Material lead times to track early',
    'What clients should expect at tender', 'Managing variations during construction', 'Closing out a project cleanly'
  ];
  for (let i = 0; i < titles.length; i++) {
    const media = result.media[i];
    const content = `<p>Good project decisions come from clear constraints and useful evidence.</p>${image(media)}<h2>${esc(titles[i])}</h2><p>This benchmark article intentionally includes substantial text and a local featured image so archive and single-post rendering behave like a normal business WordPress site.</p><p>Scope, programme, cost, approvals, procurement and maintenance are reviewed together. That reduces late-stage changes and keeps the operating impact visible.</p><h3>Practical checklist</h3><ul><li>Confirm scope.</li><li>Confirm dependencies.</li><li>Record decisions.</li><li>Review cost and programme impact.</li></ul>`;
    const created = await createPost(ctx, n, 'posts', titles[i], `northline-journal-${i + 1}`, content, {
      featured_media: media.id,
      excerpt: 'Practical notes from design, construction and project delivery.'
    });
    result.posts.push({ id: created.id, title: titles[i], slug: `northline-journal-${i + 1}`, featured_media: media.id });
    save();
  }

  result.menu = await buildMenu(ctx, n, result.pages);
  result.readingSettings = await setReadingSettings(ctx, n, wp, result.homeId, result.blogId);

  const [homeResponse, pages, posts, media] = await Promise.all([
    fetch(`${base}/?fixture=${Date.now()}`, { headers: { 'Cache-Control': 'no-cache' } }),
    fetch(`${base}/wp-json/wp/v2/pages?per_page=100&_fields=id,slug`).then(response => response.json()),
    fetch(`${base}/wp-json/wp/v2/posts?per_page=100&_fields=id,slug,featured_media`).then(response => response.json()),
    fetch(`${base}/wp-json/wp/v2/media?per_page=100&_fields=id,source_url`).then(response => response.json())
  ]);
  const home = await homeResponse.text();
  const seededPageSlugs = new Set(result.pages.map(item => item.slug));
  const seededPostSlugs = new Set(result.posts.map(item => item.slug));
  const verify = {
    http: homeResponse.status,
    blocksy: /\bct-(?:container|header|footer|panel)|themes\/blocksy\//i.test(home),
    images: (home.match(/<img\b/gi) || []).length,
    navLinks: (home.match(/<nav[\s\S]*?<\/nav>/gi) || []).join('').match(/<a\b/gi)?.length || 0,
    sections: (home.match(/data-r3-section=/g) || []).length,
    pages: Array.isArray(pages) ? pages.filter(item => seededPageSlugs.has(item.slug)).length : 0,
    posts: Array.isArray(posts) ? posts.filter(item => seededPostSlugs.has(item.slug)).length : 0,
    featuredPosts: Array.isArray(posts) ? posts.filter(item => seededPostSlugs.has(item.slug) && Number(item.featured_media) > 0).length : 0,
    media: Array.isArray(media) ? media.filter(item => String(item.source_url || '').startsWith(base)).length : 0
  };
  result.verify = verify;
  if (verify.http !== 200) throw new Error(`homepage_http_${verify.http}`);
  if (!verify.blocksy) throw new Error('blocksy_public_marker_missing');
  if (verify.pages !== 8 || verify.posts !== 18 || verify.featuredPosts !== 18 || verify.media !== 18) throw new Error(`deterministic_counts_invalid:${JSON.stringify(verify)}`);
  if (verify.images < 8 || verify.navLinks < 5 || verify.sections < 6) throw new Error(`homepage_richness_invalid:${JSON.stringify(verify)}`);
  if (!result.menu || result.menu.items < 5) throw new Error('primary_menu_invalid');

  const pluginsAfter = await listPlugins(ctx, n);
  const r3 = Array.isArray(pluginsAfter) ? pluginsAfter.find(item => String(item.plugin || '').startsWith('runner3-speed/')) : null;
  if (r3) throw new Error('runner3_speed_present_after_clean_seed');

  result.status = 'READY';
  save();
} catch (error) {
  result.status = 'FAILED';
  result.detail = String(error?.stack || error);
  save();
  console.error(result.detail);
  process.exitCode = 1;
} finally {
  await browser.close();
}

console.log(JSON.stringify(result, null, 2));
