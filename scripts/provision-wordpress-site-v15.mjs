import { chromium } from 'playwright-core';
import fs from 'fs';

const requestPath = process.env.SITE_FACTORY_REQUEST;
if (!requestPath || !fs.existsSync(requestPath)) throw new Error('SITE_FACTORY_REQUEST missing');
const cfg = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
for (const k of ['site_name','site_slug','app_name','domain_mode']) if (!cfg[k]) throw new Error(`request missing ${k}`);
if (cfg.domain_mode !== 'wasmer') throw new Error('provision-only bridge supports domain_mode=wasmer');
if (!/^[a-z0-9][a-z0-9-]{2,62}$/.test(cfg.app_name)) throw new Error('invalid app_name');

let account = {};
if (fs.existsSync('/tmp/wasmer-account.json')) account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const username = account.username || process.env.WASMER_USERNAME || '';
const password = account.password || process.env.WASMER_PASSWORD || '';
const statusPath = `/tmp/site-factory-v15-${cfg.site_slug}.json`;
const state = { status:'starting', stage:'init', siteName:cfg.site_name, siteSlug:cfg.site_slug, appName:cfg.app_name, domainMode:cfg.domain_mode, siteUrl:null, dashboardUrl:null, httpCode:null, wpAdminReachable:false, wpApiReachable:false, reusedExistingApp:false, detail:null, updatedAt:new Date().toISOString() };
const save=()=>{state.updatedAt=new Date().toISOString();fs.writeFileSync(statusPath,JSON.stringify(state,null,2));};
const stage=s=>{state.stage=s;save();};
const finish=(status,detail=null)=>{state.status=status;state.detail=detail;save();};
const text=async p=>(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
const block=async p=>{const t=(await text(p)).toLowerCase();if(/recaptcha|hcaptcha|turnstile|verify you are human|captcha/.test(t))return'captcha';if(/credit card|payment method|billing information|card details/.test(t))return'payment';if(/limit reached|quota|upgrade your plan|usage limit/.test(t))return'quota';return null;};
save();
if(!username||!password){finish('BLOCKED','wasmer_auth_missing');process.exit(20);}
const owner=username;
const dashboard=a=>`https://wasmer.io/apps/${encodeURIComponent(owner)}/${encodeURIComponent(a)}`;
const nativeUrl=a=>`https://${a}.wasmer.app/`;
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});
const page=await ctx.newPage();

async function login(){stage('wasmer_login');await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});const id=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();if(!(await id.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false)))throw new Error('login_identifier_missing');await id.fill(username);await id.press('Enter').catch(()=>{});const pass=page.locator('input[type=password]').first();if(!(await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false)))throw new Error('login_password_missing');await pass.fill(password);await pass.press('Enter').catch(()=>{});await page.waitForTimeout(4000);const b=await block(page);if(b)throw new Error(`provider_block:${b}:login`);if(/\/login(?:[/?#]|$)/i.test(page.url()))throw new Error('wasmer_login_failed');}
async function exists(app){stage('check_existing_app');await page.goto(dashboard(app),{waitUntil:'domcontentloaded',timeout:60000});for(let i=0;i<6;i++){await page.waitForTimeout(900);const t=(await text(page)).toLowerCase();if(page.url().includes(`/apps/${owner}/${app}`)&&/wordpress|settings|domains|deployments|ready/.test(t))return true;if(/page not found|404|does not exist|could not be found/.test(t))return false;}return false;}
async function preflight(){stage('capacity_preflight');await page.goto('https://wasmer.io/apps',{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);await page.waitForTimeout(1200);const b=await block(page);if(b==='quota'||b==='payment')throw new Error(`provider_block:${b}:capacity_preflight`);}
async function create(){await preflight();stage('create_app');await page.goto('https://wasmer.io/apps/create?template=wordpress-starter',{waitUntil:'domcontentloaded',timeout:60000});await page.waitForTimeout(1800);let b=await block(page);if(b)throw new Error(`provider_block:${b}:create_entry`);const inputs=page.locator('input[name*=name i],input[placeholder*=name i],input[type=text]');let target=null;for(let i=0;i<await inputs.count();i++){const el=inputs.nth(i);if(!(await el.isVisible().catch(()=>false)))continue;const hint=`${await el.getAttribute('name')||''} ${await el.getAttribute('placeholder')||''}`;if(/user|email|search/i.test(hint))continue;target=el;break;}if(!target)throw new Error('app_name_input_missing');await target.fill(cfg.app_name);let deploy=page.locator('button').filter({hasText:/Deploy now/i}).first();if(!(await deploy.count()))deploy=page.getByText(/Deploy now/i).first();if(!(await deploy.count()))throw new Error('deploy_button_missing');await deploy.click();for(let i=0;i<72;i++){await page.waitForTimeout(2500);b=await block(page);if(b)throw new Error(`provider_block:${b}:after_deploy`);const r=await ctx.request.get(nativeUrl(cfg.app_name),{timeout:5000,failOnStatusCode:false}).catch(()=>null);if(r&&r.status()>0&&r.status()<500&&r.status()!==404)return;}throw new Error('deploy_unconfirmed');}
async function waitReady(){stage('wait_wordpress_ready');for(let i=0;i<48;i++){await page.goto(dashboard(cfg.app_name),{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);await page.waitForTimeout(1000);const b=await block(page);if(b)throw new Error(`provider_block:${b}:dashboard`);if(await page.getByText(/WordPress Admin/i).first().isVisible().catch(()=>false))return true;await page.waitForTimeout(1500);}return false;}
async function verify(){stage('verify_wordpress');state.siteUrl=nativeUrl(cfg.app_name);state.dashboardUrl=dashboard(cfg.app_name);const home=await ctx.request.get(state.siteUrl,{timeout:10000,failOnStatusCode:false}).catch(()=>null);state.httpCode=home?.status()??null;const api=await ctx.request.get(new URL('/wp-json/',state.siteUrl).href,{timeout:10000,failOnStatusCode:false}).catch(()=>null);state.wpApiReachable=!!api&&api.status()>=200&&api.status()<400;await page.goto(state.dashboardUrl,{waitUntil:'domcontentloaded',timeout:60000});state.wpAdminReachable=await page.getByText(/WordPress Admin/i).first().isVisible().catch(()=>false);save();if(!state.httpCode||state.httpCode>=500||!state.wpAdminReachable||!state.wpApiReachable)throw new Error('wordpress_readiness_failed');}
try{await login();if(await exists(cfg.app_name)){state.reusedExistingApp=true;save();}else await create();if(!(await waitReady()))throw new Error('app_not_ready_timeout');await verify();finish('COMPLETE');state.stage='complete';save();console.log(JSON.stringify(state,null,2));}catch(e){const msg=String(e?.message||e);finish(/^provider_block:/.test(msg)||/captcha|payment|quota|authorization/i.test(msg)?'BLOCKED':'FAILED',msg);console.error(msg);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
