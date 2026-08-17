import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';

const APP='runner3-wp-a94b8fd2';
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
if(!account?.username || !account?.password) throw new Error('Wasmer account state incomplete');
const owner=account.username;
const dashboard=`https://wasmer.io/apps/${encodeURIComponent(owner)}/${APP}`;

const dir='/tmp/runner3-pntr-cleaner';
fs.rmSync(dir,{recursive:true,force:true});
fs.mkdirSync(dir,{recursive:true,mode:0o700});
const php=`<?php
/*
Plugin Name: Runner3 PNTR Bridge Cleaner
Description: Temporary targeted cleanup helper.
Version: 0.1.0
*/
if (!defined('ABSPATH')) { exit; }
function runner3_pntr_cleaner_run() {
    if (!is_admin()) return;
    require_once ABSPATH . 'wp-admin/includes/plugin.php';
    $plugins = get_plugins();
    $targets = [];
    foreach ($plugins as $file => $data) {
        $name = isset($data['Name']) ? (string)$data['Name'] : '';
        if (strpos($name, 'Runner3 PNTR Cookie Bridge') === 0) $targets[] = $file;
    }
    if ($targets) {
        deactivate_plugins($targets, true);
        delete_plugins($targets);
    }
    update_option('runner3_pntr_cleaner_last_count', count($targets), false);
}
add_action('admin_init', 'runner3_pntr_cleaner_run', 1);
add_action('init', function(){
    $p=parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
    if ($p !== '/pntr-cleaner-status') return;
    require_once ABSPATH . 'wp-admin/includes/plugin.php';
    $left=[];
    foreach (get_plugins() as $file=>$data) {
        $name=isset($data['Name'])?(string)$data['Name']:'';
        if (strpos($name,'Runner3 PNTR Cookie Bridge')===0) $left[]=$name;
    }
    nocache_headers();
    header('Content-Type: text/plain; charset=utf-8');
    echo 'LEFT='.count($left);
    exit;
},0);
`;
fs.writeFileSync(path.join(dir,'runner3-pntr-cleaner.php'),php,{mode:0o600});
execFileSync('zip',['-q','-r','/tmp/runner3-pntr-cleaner.zip','runner3-pntr-cleaner'],{cwd:'/tmp'});

const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
const body=async p=>clean(await p.locator('body').innerText().catch(()=>''));
async function login(p){
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await p.waitForTimeout(700);
  const ident=p.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await ident.count())) return false;
  await ident.fill(account.username||account.email);
  let b=p.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await ident.press('Enter');
  const pass=p.locator('input[type=password]').first();
  if(!(await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))) return false;
  await pass.fill(account.password);
  b=p.locator('button,input[type=submit]').filter({hasText:/log in|sign in|continue/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await pass.press('Enter');
  await p.waitForTimeout(3000);
  return !/\/login(?:[/?#]|$)/i.test(p.url());
}
async function wpAdmin(ctx,p){
  await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
  await p.waitForTimeout(1000);
  if(/\/login(?:[/?#]|$)/i.test(p.url()) || /log in|sign in/i.test((await body(p)).slice(0,500))){
    if(!(await login(p))) throw new Error('Wasmer login failed');
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
    await p.waitForTimeout(1000);
  }
  const a=p.getByText(/WordPress Admin/i).first();
  if(!(await a.count())) throw new Error('WordPress Admin control missing');
  const href=await a.getAttribute('href').catch(()=>null);
  if(href){
    const q=await ctx.newPage();
    await q.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000});
    await q.waitForTimeout(2200);
    if(/\/wp-admin/i.test(q.url())) return q;
    await q.close().catch(()=>{});
  }
  const pp=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null);
  await a.click().catch(()=>{});
  const pop=await pp;
  await p.waitForTimeout(2500);
  for(const q of [pop,...ctx.pages()].filter(Boolean)) if(/\/wp-admin/i.test(q.url())) return q;
  throw new Error('WordPress magic admin failed');
}

const state=fs.existsSync('/tmp/wasmer-browser-state.json')?'/tmp/wasmer-browser-state.json':undefined;
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:state,ignoreHTTPSErrors:true});
const page=await ctx.newPage();
try{
  const wp=await wpAdmin(ctx,page);
  const origin=new URL(wp.url()).origin;
  await wp.goto(`${origin}/wp-admin/plugin-install.php?tab=upload`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(700);
  let input=wp.locator('input[type=file]').first();
  if(!(await input.count())){
    const upload=wp.locator('button,a').filter({hasText:/Upload Plugin/i}).first();
    if(await upload.count()) await upload.click().catch(()=>{});
    await wp.waitForTimeout(400);
    input=wp.locator('input[type=file]').first();
  }
  if(!(await input.count())) throw new Error('Plugin upload input missing');
  await input.setInputFiles('/tmp/runner3-pntr-cleaner.zip');
  let install=wp.locator('input[type=submit],button').filter({hasText:/Install Now/i}).first();
  if(!(await install.count())) install=wp.locator('#install-plugin-submit').first();
  if(!(await install.count())) throw new Error('Install control missing');
  await install.click();
  await wp.waitForTimeout(4500);
  const txt=await body(wp);
  if(!/successfully installed|activate plugin|already exists/i.test(txt)) throw new Error('Cleaner install not confirmed');
  let activate=wp.locator('a,button').filter({hasText:/^Activate Plugin$/i}).first();
  if(await activate.count()){
    const href=await activate.getAttribute('href').catch(()=>null);
    if(href) await wp.goto(new URL(href,wp.url()).href,{waitUntil:'domcontentloaded',timeout:60000});
    else await activate.click();
    await wp.waitForTimeout(1800);
  }
  // Trigger admin_init cleanup once explicitly.
  await wp.goto(`${origin}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(1200);
  const r=await ctx.request.get('https://runner3wp.pntr.dev/pntr-cleaner-status',{failOnStatusCode:false,timeout:20000});
  const status=(await r.text().catch(()=>'' )).trim();
  console.log('CLEANER_STATUS_HTTP='+r.status());
  console.log('CLEANER_STATUS='+status);
  if(status!=='LEFT=0') throw new Error('Bridge plugins remain: '+status);
  console.log('PNTR_BRIDGES_REMOVED=true');
} finally {
  await browser.close().catch(()=>{});
  fs.rmSync(dir,{recursive:true,force:true});
  fs.rmSync('/tmp/runner3-pntr-cleaner.zip',{force:true});
}
