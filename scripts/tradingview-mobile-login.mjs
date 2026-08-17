import http from 'node:http';
import fs from 'node:fs';
import { URLSearchParams } from 'node:url';
import { chromium } from 'playwright-core';

const token = process.env.LOGIN_TOKEN;
if (!token) throw new Error('LOGIN_TOKEN missing');
const profileDir = '/tmp/tv-profile';
const confirmFile = '/tmp/tv-session-confirmed';
const port = 8787;
let context;
let page;
let state = { stage: 'login', message: 'Nhập email và mật khẩu TradingView.' };

const esc = (s='') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const html = () => `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta charset="utf-8"><title>TradingView Login</title><style>body{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:#f5f5f7;margin:0;color:#111}.wrap{max-width:520px;margin:0 auto;padding:24px 18px 40px}.card{background:#fff;border-radius:18px;padding:20px;box-shadow:0 6px 24px rgba(0,0,0,.08)}h1{font-size:24px;margin:0 0 8px}p{font-size:15px;line-height:1.45;color:#555}label{display:block;font-size:13px;font-weight:600;margin:14px 0 6px}input{width:100%;box-sizing:border-box;font-size:17px;padding:13px 12px;border:1px solid #ccc;border-radius:12px;background:#fff}button{width:100%;margin-top:18px;padding:14px;border:0;border-radius:12px;background:#111;color:#fff;font-size:17px;font-weight:700}.msg{padding:12px;border-radius:12px;background:#f0f2f5;margin:12px 0;font-size:14px}.ok{background:#e9f8ee}.bad{background:#fff0f0}.note{font-size:12px;color:#777;margin-top:16px}</style></head><body><div class="wrap"><div class="card"><h1>TradingView</h1><div class="msg ${state.stage==='done'?'ok':state.stage==='error'?'bad':''}">${esc(state.message)}</div>${state.stage==='login'?`<form method="post" action="/${token}/login"><label>Email / username</label><input name="user" autocomplete="username" autocapitalize="none" required><label>Mật khẩu TradingView</label><input name="pass" type="password" autocomplete="current-password" required><button type="submit">Đăng nhập</button></form>`:''}${state.stage==='otp'?`<form method="post" action="/${token}/otp"><label>Mã 2FA</label><input name="otp" inputmode="numeric" autocomplete="one-time-code" required><button type="submit">Xác nhận 2FA</button></form>`:''}<div class="note">Không nhập mật khẩu Google. Chỉ dùng mật khẩu riêng của TradingView.</div></div></div></body></html>`;

async function ensureBrowser() {
  if (context) return;
  const execs = ['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser'];
  const executablePath = execs.find(fs.existsSync);
  if (!executablePath) throw new Error('Chrome/Chromium not found');
  fs.mkdirSync(profileDir,{recursive:true});
  context = await chromium.launchPersistentContext(profileDir,{executablePath,headless:false,viewport:{width:1280,height:800},args:['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled']});
  page = context.pages()[0] || await context.newPage();
}

async function fillAny(selectors, value) {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    if (await loc.count()) {
      try { if (await loc.isVisible()) { await loc.fill(value); return true; } } catch {}
    }
  }
  return false;
}

async function clickAny(selectors) {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    if (await loc.count()) {
      try { if (await loc.isVisible()) { await loc.click(); return true; } } catch {}
    }
  }
  return false;
}

async function detectOtp() {
  const sels = ['input[autocomplete="one-time-code"]','input[name*="code" i]','input[name*="otp" i]','input[inputmode="numeric"]'];
  for (const s of sels) { const l=page.locator(s).first(); if(await l.count()){ try{if(await l.isVisible()) return true;}catch{}} }
  const body=(await page.locator('body').innerText().catch(()=>'' )).toLowerCase();
  return body.includes('two-factor') || body.includes('verification code') || body.includes('2fa');
}

async function detectCaptcha() {
  const body=(await page.locator('body').innerText().catch(()=>'' )).toLowerCase();
  const frames=page.frames().map(f=>f.url()).join(' ').toLowerCase();
  return body.includes('captcha') || frames.includes('recaptcha') || frames.includes('hcaptcha');
}

async function login(user, pass) {
  await ensureBrowser();
  state={stage:'busy',message:'Đang đăng nhập TradingView...'};
  await page.goto('https://www.tradingview.com/accounts/signin/',{waitUntil:'domcontentloaded',timeout:90000});
  await page.waitForTimeout(1200);
  await clickAny(['button:has-text("Email")','[role="button"]:has-text("Email")','text=/^Email$/i']).catch(()=>{});
  await page.waitForTimeout(500);
  const u=await fillAny(['input[autocomplete="username"]','input[name="username"]','input[type="email"]','input[name*="email" i]'],user);
  const p=await fillAny(['input[autocomplete="current-password"]','input[type="password"]'],pass);
  if(!u||!p) throw new Error('Không tìm thấy form email/password của TradingView.');
  await clickAny(['button[type="submit"]','button:has-text("Sign in")','button:has-text("Log in")']);
  await page.waitForTimeout(3500);
  if(await detectCaptcha()) { state={stage:'error',message:'TradingView yêu cầu CAPTCHA. Flow tự động dừng để không bypass CAPTCHA.'}; return; }
  if(await detectOtp()) { state={stage:'otp',message:'TradingView yêu cầu mã 2FA. Nhập mã bên dưới.'}; return; }
  const pwdVisible = await page.locator('input[type="password"]').first().isVisible().catch(()=>false);
  if(pwdVisible) { state={stage:'error',message:'Đăng nhập chưa thành công. Kiểm tra email/username hoặc mật khẩu TradingView.'}; return; }
  await finish();
}

async function submitOtp(otp) {
  state={stage:'busy',message:'Đang xác nhận 2FA...'};
  const ok=await fillAny(['input[autocomplete="one-time-code"]','input[name*="code" i]','input[name*="otp" i]','input[inputmode="numeric"]'],otp);
  if(!ok){state={stage:'error',message:'Không tìm thấy ô nhập 2FA.'};return;}
  await clickAny(['button[type="submit"]','button:has-text("Verify")','button:has-text("Confirm")','button:has-text("Continue")']);
  await page.waitForTimeout(3000);
  if(await detectOtp()) {state={stage:'otp',message:'Mã 2FA chưa được chấp nhận. Nhập mã mới.'};return;}
  await finish();
}

async function finish() {
  await page.goto('https://www.tradingview.com/chart/',{waitUntil:'domcontentloaded',timeout:90000}).catch(()=>{});
  await page.waitForTimeout(2500);
  const cookies=await context.cookies('https://www.tradingview.com');
  if(cookies.length<2) { state={stage:'error',message:'Không xác nhận được session TradingView.'}; return; }
  state={stage:'done',message:'Đăng nhập thành công. Session đang được lưu mã hóa.'};
  await context.close();
  context=null; page=null;
  fs.writeFileSync(confirmFile,new Date().toISOString(),{mode:0o600});
}

function readBody(req){return new Promise((resolve,reject)=>{let d='';req.on('data',c=>{d+=c;if(d.length>8192){reject(new Error('too large'));req.destroy();}});req.on('end',()=>resolve(d));req.on('error',reject);});}

const server=http.createServer(async(req,res)=>{
  const path=req.url?.split('?')[0]||'/';
  if(!path.startsWith('/'+token)){res.writeHead(404);res.end('Not found');return;}
  try{
    if(req.method==='POST'&&path===`/${token}/login`){const b=new URLSearchParams(await readBody(req));await login(b.get('user')||'',b.get('pass')||'');}
    else if(req.method==='POST'&&path===`/${token}/otp`){const b=new URLSearchParams(await readBody(req));await submitOtp(b.get('otp')||'');}
  }catch(e){state={stage:'error',message:`Lỗi đăng nhập: ${e.message}`};}
  res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store'});res.end(html());
});
server.listen(port,'127.0.0.1',()=>console.log('TV_MOBILE_LOGIN_READY'));
