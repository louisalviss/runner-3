#!/usr/bin/env node

import fs from 'node:fs';
import { chromium } from 'playwright-core';

const target = (process.env.SITE2_URL || 'https://runner3-wp-a94b8fd2.wasmer.app').replace(/\/$/, '');
const out = process.env.SETUP_OUT || '/tmp/site2-realistic-setup.json';
const templateName = process.env.STARTER_TEMPLATE_NAME || 'Generic eCommerce';
const legacySlug = process.env.LEGACY_FIXTURE_PLUGIN_SLUG || 'runner3-site2-fixture-v2';
let token = String(process.env.WASMER_TOKEN || '').replace(/[\r\n]/g, '').trim();
if (!token) throw new Error('WASMER_TOKEN is required');
if (!token.startsWith('wap_')) token = `wap_${token}`;

const expectedHost = new URL(target).host;
const liveconfigUrl = `${target}/?rest_route=/wasmer/v1/liveconfig`;

function sanitize(value) {
  return String(value || '').replaceAll(token, '[REDACTED]').replace(/magiclogin=[^&\s"']+/gi, 'magiclogin=[REDACTED]');
}

async function readLiveconfig() {
  const response = await fetch(`${liveconfigUrl}&_=${Date.now()}`, { headers:{'cache-control':'no-cache'}, redirect:'follow' });
  if (!response.ok) throw new Error(`liveconfig returned HTTP ${response.status}`);
  const data = await response.json();
  const wpUrl = data?.wordpress?.url;
  if (!wpUrl || new URL(wpUrl).host !== expectedHost) throw new Error(`target guard failed: ${wpUrl}`);
  return data;
}

function countValue(v) {
  if (v && typeof v === 'object' && 'count' in v) return Number(v.count || 0);
  return Number(v || 0);
}

function compactLiveconfig(data) {
  const plugins = Array.isArray(data?.wordpress?.plugins) ? data.wordpress.plugins : [];
  const themes = Array.isArray(data?.wordpress?.themes) ? data.wordpress.themes : [];
  return {
    wordpress_version:data?.wordpress?.version ?? null,
    url:data?.wordpress?.url ?? null,
    posts:countValue(data?.wordpress?.posts),
    pages:countValue(data?.wordpress?.pages),
    active_theme:themes.find((x) => x.status === 'active')?.name ?? null,
    active_plugins:plugins.filter((x) => ['active','active-network','must-use'].includes(x.status)).map((x) => x.name),
  };
}

async function gotoAdminHref(page, locator) {
  const href = await locator.getAttribute('href');
  if (!href) throw new Error('WordPress admin action link has no href');
  const resolved = new URL(href, `${target}/wp-admin/`);
  if (resolved.host !== expectedHost || !resolved.pathname.startsWith('/wp-admin/')) throw new Error('admin target guard failed');
  await page.goto(resolved.href, { waitUntil:'domcontentloaded', timeout:120000 });
}

async function login(page) {
  const magicUrl = `${target}/?rest_route=/wasmer/v1/magiclogin&magiclogin=${encodeURIComponent(token)}`;
  await page.goto(magicUrl, { waitUntil:'domcontentloaded', timeout:90000 });
  if (new URL(page.url()).host !== expectedHost || !page.url().includes('/wp-admin')) throw new Error('Wasmer magic-login failed');
}

async function cleanupLegacyFixture(page) {
  const result = { found:false, reset:false, inactive:false };
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  let row = page.locator('tr').filter({ has:page.locator(`a[href*="${legacySlug}"]`) }).first();
  if (!(await row.count())) return result;
  result.found = true;
  const activate = row.getByRole('link', { name:/^Activate$/i });
  if (await activate.count()) await gotoAdminHref(page, activate.first());
  await page.goto(`${target}/wp-admin/tools.php?page=runner3-site2-fixture`, { waitUntil:'domcontentloaded', timeout:60000 });
  const reset = page.locator('input[name="runner3_reset"]');
  if (await reset.count()) {
    await reset.click();
    await page.waitForLoadState('domcontentloaded', { timeout:180000 }).catch(() => {});
    await page.getByText('RUNNER3_RESET_DONE').waitFor({ state:'visible', timeout:180000 });
    result.reset = true;
  }
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  row = page.locator('tr').filter({ has:page.locator(`a[href*="${legacySlug}"]`) }).first();
  if (await row.count()) {
    const deactivate = row.getByRole('link', { name:/^Deactivate$/i });
    if (await deactivate.count()) await gotoAdminHref(page, deactivate.first());
  }
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  row = page.locator('tr').filter({ has:page.locator(`a[href*="${legacySlug}"]`) }).first();
  if (await row.count()) result.inactive = !(await row.getByRole('link', { name:/^Deactivate$/i }).count());
  return result;
}

async function ensureAstra(page) {
  await page.goto(`${target}/wp-admin/themes.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  let card = page.locator('.theme[data-slug="astra"]').first();
  if (!(await card.count())) {
    await page.goto(`${target}/wp-admin/theme-install.php?search=astra`, { waitUntil:'domcontentloaded', timeout:60000 });
    const installCard = page.locator('.theme[data-slug="astra"]').first();
    await installCard.waitFor({ state:'visible', timeout:30000 });
    const install = installCard.locator('.install-now').first();
    if (await install.count()) {
      await install.click();
      await page.waitForFunction(() => {
        const c=document.querySelector('.theme[data-slug="astra"]');
        return !!c && !c.querySelector('.install-now');
      }, { timeout:120000 }).catch(() => {});
    }
  }
  await page.goto(`${target}/wp-admin/themes.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  card = page.locator('.theme[data-slug="astra"]').first();
  if (!(await card.count())) throw new Error('Astra theme missing after install check');
  const activate = card.locator('a.activate').first();
  if (await activate.count()) await gotoAdminHref(page, activate);
  const live = compactLiveconfig(await readLiveconfig());
  if (live.active_theme !== 'astra') throw new Error(`Astra activation failed: ${live.active_theme}`);
}

async function ensureStarterTemplates(page) {
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  let row = page.locator('tr[data-slug="astra-sites"], tr').filter({ has:page.locator('a[href*="astra-sites"]') }).first();
  if (!(await row.count())) {
    await page.goto(`${target}/wp-admin/plugin-install.php?s=Starter%20Templates&tab=search&type=term`, { waitUntil:'domcontentloaded', timeout:90000 });
    const card = page.locator('.plugin-card-astra-sites').first();
    await card.waitFor({ state:'visible', timeout:45000 });
    const install = card.locator('a.install-now').first();
    if (await install.count()) { await install.click(); await page.waitForTimeout(8000); }
  }
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  row = page.locator('tr[data-slug="astra-sites"], tr').filter({ has:page.locator('a[href*="astra-sites"]') }).first();
  if (!(await row.count())) throw new Error('Starter Templates plugin missing');
  const activate = row.getByRole('link', { name:/^Activate$/i });
  if (await activate.count()) await gotoAdminHref(page, activate.first());
}

async function clickButton(page, regex, timeout=5000) {
  const started=Date.now();
  while (Date.now()-started<timeout) {
    const b=page.getByRole('button',{name:regex}).first();
    if (await b.count() && await b.isVisible().catch(()=>false)) { await b.click(); return true; }
    const l=page.getByRole('link',{name:regex}).first();
    if (await l.count() && await l.isVisible().catch(()=>false)) { await l.click(); return true; }
    await page.waitForTimeout(400);
  }
  return false;
}

function authBlocked(text) {
  return /sign in to zipwp|log in to zipwp|create.*zipwp.*account|continue with google/i.test(text || '');
}

async function importOfficialStarterTemplate(page) {
  await page.goto(`${target}/wp-admin/themes.php?page=starter-templates`, { waitUntil:'domcontentloaded', timeout:120000 });
  let body=await page.locator('body').innerText().catch(()=> '');
  if (authBlocked(body)) throw new Error('Starter Templates requires ZipWP authentication');
  await clickButton(page,/Build with Templates/i,12000);
  const classic=page.getByText(/Classic Starter Templates/i).first();
  if (await classic.count() && await classic.isVisible().catch(()=>false)) await classic.click();
  body=await page.locator('body').innerText().catch(()=> '');
  if (authBlocked(body)) throw new Error('Classic Starter Templates library requires ZipWP authentication');
  let search=page.locator('input[type="search"]').first();
  if (!(await search.count()) || !(await search.isVisible().catch(()=>false))) search=page.locator('input[placeholder*="Search" i]').first();
  if (!(await search.count())) throw new Error('Starter Templates search input not found');
  await search.fill(templateName);
  await page.waitForTimeout(2500);
  const exact=page.getByText(new RegExp(`^${templateName.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}$`,'i')).first();
  await exact.waitFor({ state:'visible', timeout:45000 });
  await exact.click();
  const builder=page.getByText(/Block Editor|Gutenberg|WordPress Editor/i).first();
  if (await builder.count() && await builder.isVisible().catch(()=>false)) await builder.click();
  const deadline=Date.now()+180000;
  let submitted=false;
  while (Date.now()<deadline) {
    body=await page.locator('body').innerText().catch(()=> '');
    if (authBlocked(body)) throw new Error('Starter Templates import requires ZipWP authentication');
    if (/view your website|your website is ready|successfully imported|import complete/i.test(body)) return {completed:true,source:'starter-templates-ui'};
    if (await clickButton(page,/Submit & Build My Website/i,1500)) { submitted=true; break; }
    const progressed=await clickButton(page,/Skip & Continue|^Continue$|Continue & Build|Start Importing|Build My Website/i,2500);
    if (!progressed) await page.waitForTimeout(900);
  }
  if (!submitted) throw new Error('Could not reach complete-site import submit action');
  const done=Date.now()+300000;
  while (Date.now()<done) {
    body=await page.locator('body').innerText().catch(()=> '');
    if (/view your website|your website is ready|successfully imported|import complete/i.test(body)) return {completed:true,source:'starter-templates-ui'};
    await page.waitForTimeout(1500);
  }
  throw new Error(`Starter Templates import did not confirm completion: ${body.slice(0,1200)}`);
}

async function verifyFrontend(page) {
  const checks={};
  for (const path of ['/','/shop/','/cart/','/checkout/','/about/','/contact/']) {
    const response=await page.goto(`${target}${path}?__official_demo_verify=${Date.now()}`, { waitUntil:'domcontentloaded', timeout:90000 });
    checks[path]={status:response?.status() ?? null,title:await page.title(),h1:(await page.locator('h1').first().textContent().catch(()=>''))?.trim()||''};
    if (!response || response.status()>=400) throw new Error(`frontend verification failed for ${path}`);
  }
  await page.goto(`${target}/shop/?__official_demo_products=${Date.now()}`, { waitUntil:'domcontentloaded', timeout:90000 });
  const productCards=await page.locator('li.product, .wc-block-product, .products .product').count();
  if (productCards<4) throw new Error(`expected official demo product cards, got ${productCards}`);
  checks.shop_product_cards=productCards;
  await page.goto(`${target}/?__official_demo_home=${Date.now()}`, { waitUntil:'domcontentloaded', timeout:90000 });
  const bodyText=(await page.locator('body').innerText()).trim();
  if (bodyText.length<800) throw new Error(`homepage is not a full demo; body text only ${bodyText.length} chars`);
  checks.home_body_chars=bodyText.length;
  checks.home_images=await page.locator('main img, #content img, .site-content img').count();
  return checks;
}

const result={target,fixture:'astra-starter-generic-ecommerce-02',source:'official Astra Starter Templates complete-site demo',template:templateName,started_at:new Date().toISOString(),status:'starting',before:null,after:null,legacy_cleanup:null,import:null,frontend:null};
let browser;
try {
  result.before=compactLiveconfig(await readLiveconfig());
  const executablePath=[process.env.CHROME_PATH,'/usr/bin/google-chrome-stable','/usr/bin/google-chrome','/usr/bin/chromium'].filter(Boolean).find((p)=>fs.existsSync(p));
  if (!executablePath) throw new Error('Chrome executable not found');
  browser=await chromium.launch({headless:true,executablePath,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  const context=await browser.newContext({viewport:{width:1440,height:1100}});
  const page=await context.newPage(); page.setDefaultTimeout(60000); page.setDefaultNavigationTimeout(120000);
  await login(page);
  result.legacy_cleanup=await cleanupLegacyFixture(page);
  await ensureAstra(page);
  await ensureStarterTemplates(page);
  result.import=await importOfficialStarterTemplate(page);
  result.frontend=await verifyFrontend(page);
  result.after=compactLiveconfig(await readLiveconfig());
  const plugins=new Set(result.after.active_plugins||[]);
  if (result.after.active_theme!=='astra') throw new Error(`expected Astra, got ${result.after.active_theme}`);
  if (!plugins.has('woocommerce')) throw new Error('WooCommerce is not active after official demo import');
  if (result.after.pages<3) throw new Error(`official demo produced too few pages: ${result.after.pages}`);
  result.status='ready'; result.completed_at=new Date().toISOString();
} catch (error) {
  result.status='failed'; result.error=sanitize(error?.stack||error?.message||error); result.completed_at=new Date().toISOString(); process.exitCode=1;
} finally {
  if (browser) await browser.close().catch(()=>{});
  fs.writeFileSync(out,`${JSON.stringify(result,null,2)}\n`);
  console.log(JSON.stringify({...result,error:result.error?sanitize(result.error):undefined},null,2));
}
