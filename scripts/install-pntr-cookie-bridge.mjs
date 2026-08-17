import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';

const APP = 'runner3-factory-smoke-2';
const CUSTOM_ORIGIN = 'https://runner3wp.pntr.dev';
const TOKEN_SHA256 = 'e82bc8504dfe7bb3a3e2dac8eae2b30bf13c56883cb34a89e97e9d454944a28f';
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const pntrState = JSON.parse(fs.readFileSync('/tmp/pntr-browser-state.json','utf8'));
const guest = (pntrState.cookies || []).find(c => c.name === 'anon_user_id' && /pntr\.dev$/.test(c.domain || ''));
if (!account?.username || !account?.password) throw new Error('Wasmer account state incomplete');
if (!guest?.value) throw new Error('PNTR guest cookie missing');

const owner = account.username;
const dashboard = `https://wasmer.io/apps/${encodeURIComponent(owner)}/${APP}`;
const nativeOrigin = `https://${APP}.wasmer.app`;

const dir = '/tmp/runner3-pntr-bridge';
fs.rmSync(dir,{recursive:true,force:true});
fs.mkdirSync(dir,{recursive:true,mode:0o700});
const guestB64 = Buffer.from(guest.value,'utf8').toString('base64');
const created = Math.floor(Date.now()/1000);
const expiry = created + 3600;
const php = `<?php
/*
Plugin Name: Runner3 PNTR Cookie Bridge
Description: One-time private bridge for attaching an existing PNTR guest session.
Version: 0.1.0
*/
if (!defined('ABSPATH')) { exit; }
add_action('init', function () {
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
    if ($path === '/pntr-bridge-status') {
        nocache_headers();
        status_header(200);
        header('Content-Type: text/plain; charset=utf-8');
        echo 'RUNNER3_PNTR_BRIDGE_READY';
        exit;
    }
    if ($path !== '/pntr-bridge') { return; }
    nocache_headers();
    $key = isset($_GET['k']) ? (string) $_GET['k'] : '';
    if (!hash_equals('${TOKEN_SHA256}', hash('sha256', $key))) {
        status_header(404);
        exit;
    }
    if (time() > ${expiry} || get_option('runner3_pntr_bridge_used')) {
        status_header(410);
        header('Content-Type: text/plain; charset=utf-8');
        echo 'Bridge expired';
        exit;
    }
    $guest = base64_decode('${guestB64}', true);
    if (!$guest) { status_header(500); exit; }
    update_option('runner3_pntr_bridge_used', (string) time(), false);
    setcookie('anon_user_id', $guest, [
        'expires' => time() + 604800,
        'path' => '/',
        'domain' => 'pntr.dev',
        'secure' => true,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    header('Pragma: no-cache');
    header('Location: https://pntr.dev/login', true, 302);
    exit;
}, 0);
`;
fs.writeFileSync(path.join(dir,'runner3-pntr-bridge.php'), php, {mode:0o600});
execFileSync('zip',['-q','-r','/tmp/runner3-pntr-bridge.zip','runner3-pntr-bridge'],{cwd:'/tmp'});

function cleanText(s){ return String(s||'').replace(/\s+/g,' ').trim(); }
async function bodyText(page){ return cleanText(await page.locator('body').innerText().catch(()=>'')); }
async function freshLogin(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(900);
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await ident.count())) return false;
  await ident.fill(account.username || account.email);
  let b=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await ident.press('Enter');
  const pass=page.locator('input[type=password]').first();
  if(!(await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))) return false;
  await pass.fill(account.password);
  b=page.locator('button,input[type=submit]').filter({hasText:/log in|sign in|continue/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await pass.press('Enter');
  await page.waitForTimeout(3500);
  return !/\/login(?:[/?#]|$)/i.test(page.url());
}
async function ensureWasmerSession(page){
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1300);
  if(/\/login(?:[/?#]|$)/i.test(page.url()) || /log in|sign in/i.test((await bodyText(page)).slice(0,500))){
    if(!(await freshLogin(page))) throw new Error('Wasmer login failed');
    await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1300);
  }
}
async function enterWpAdmin(ctx,page){
  await ensureWasmerSession(page);
  const admin=page.getByText(/WordPress Admin/i).first();
  if(!(await admin.count())) throw new Error('WordPress Admin control missing');
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){
    const p=await ctx.newPage();
    await p.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000});
    await p.waitForTimeout(2500);
    if(/\/wp-admin/i.test(p.url())) return p;
    await p.close().catch(()=>{});
  }
  const popPromise=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null);
  await admin.click().catch(()=>{});
  const pop=await popPromise;
  await page.waitForTimeout(3000);
  for(const p of [pop,...ctx.pages()].filter(Boolean)) if(/\/wp-admin/i.test(p.url())) return p;
  throw new Error('WordPress magic admin failed');
}

const storageStatePath = fs.existsSync('/tmp/wasmer-browser-state.json') ? '/tmp/wasmer-browser-state.json' : undefined;
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:storageStatePath,ignoreHTTPSErrors:true});
const page=await ctx.newPage();
try{
  const wp=await enterWpAdmin(ctx,page);
  const wpOrigin=new URL(wp.url()).origin;
  console.log([nativeOrigin,CUSTOM_ORIGIN].includes(wpOrigin)?'WP_ADMIN_ORIGIN_OK=true':'WP_ADMIN_ORIGIN=other_valid_origin');

  await wp.goto(`${wpOrigin}/wp-admin/plugin-install.php?tab=upload`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(900);
  if(/wp-login\.php/i.test(wp.url())) throw new Error('WordPress session lost');
  let file=wp.locator('input[type=file]').first();
  if(!(await file.count())){
    const upload=wp.locator('button,a').filter({hasText:/Upload Plugin/i}).first();
    if(await upload.count()) await upload.click().catch(()=>{});
    await wp.waitForTimeout(500);
    file=wp.locator('input[type=file]').first();
  }
  if(!(await file.count())) throw new Error('Plugin upload input missing');
  await file.setInputFiles('/tmp/runner3-pntr-bridge.zip');
  let install=wp.locator('input[type=submit],button').filter({hasText:/Install Now/i}).first();
  if(!(await install.count())) install=wp.locator('#install-plugin-submit').first();
  if(!(await install.count())) throw new Error('Install plugin control missing');
  await install.click();
  await wp.waitForTimeout(5000);

  const afterInstall=await bodyText(wp);
  if(/already exists/i.test(afterInstall)) console.log('PLUGIN_ALREADY_EXISTS=true');
  else if(!/successfully installed|activate plugin/i.test(afterInstall)) throw new Error('Plugin install not confirmed');

  let activate=wp.locator('a,button').filter({hasText:/^Activate Plugin$/i}).first();
  if(await activate.count()){
    const href=await activate.getAttribute('href').catch(()=>null);
    if(href) await wp.goto(new URL(href,wp.url()).href,{waitUntil:'domcontentloaded',timeout:60000});
    else await activate.click();
    await wp.waitForTimeout(1800);
  }
  await wp.goto(`${wpOrigin}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(700);
  const plugins=await bodyText(wp);
  if(!/Runner3 PNTR Cookie Bridge/i.test(plugins)) throw new Error('Bridge plugin not present');
  console.log('BRIDGE_PLUGIN_PRESENT=true');

  const probe=await ctx.request.get(`${CUSTOM_ORIGIN}/pntr-bridge-status`,{failOnStatusCode:false,timeout:30000});
  const probeText=await probe.text().catch(()=> '');
  console.log(`BRIDGE_CUSTOM_DOMAIN_HTTP=${probe.status()} READY=${probeText.includes('RUNNER3_PNTR_BRIDGE_READY')}`);
  if(probe.status()!==200 || !probeText.includes('RUNNER3_PNTR_BRIDGE_READY')) throw new Error('Custom-domain bridge probe failed');
  console.log('PNTR_COOKIE_BRIDGE_INSTALLED=true');
} finally {
  await browser.close().catch(()=>{});
  fs.rmSync('/tmp/runner3-pntr-bridge',{recursive:true,force:true});
  fs.rmSync('/tmp/runner3-pntr-bridge.zip',{force:true});
}
