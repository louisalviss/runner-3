import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

// Triggered after correcting the Wasmer installer path used by the static deploy workflow.
const dir=process.env.WASMER_DIR || '/tmp/wasmer-cli';
const wasmer=process.env.WASMER_BIN || `${dir}/bin/wasmer`;
const state=process.env.WASMER_BROWSER_STATE || '/tmp/wasmer-browser-state.json';
if(!fs.existsSync(wasmer)) throw new Error(`wasmer_binary_missing:${wasmer}`);
if(!fs.existsSync(state)) throw new Error(`browser_state_missing:${state}`);
fs.mkdirSync(dir,{recursive:true});

const child=spawn(wasmer,['login','--wasmer-dir',dir],{
  env:{...process.env,BROWSER:'true',NO_COLOR:'1'},
  stdio:['ignore','pipe','pipe'],
});
let log='';let authUrl=null;
const onChunk=(chunk)=>{
  const s=chunk.toString();log+=s;process.stdout.write(s);
  const m=log.match(/https:\/\/wasmer\.io\/auth\/cli\?[^\s'"<>]+/i);
  if(m&&!authUrl) authUrl=m[0].replace(/[),.;]+$/,'');
};
child.stdout.on('data',onChunk);child.stderr.on('data',onChunk);
const exitP=new Promise((resolve)=>child.on('exit',(code,signal)=>resolve({code,signal})));

const deadline=Date.now()+30000;
while(!authUrl&&Date.now()<deadline){await new Promise(r=>setTimeout(r,250));}
if(!authUrl){child.kill('SIGTERM');throw new Error(`wasmer_login_auth_url_missing:${log.slice(-2000)}`);}
console.log('WASMER_AUTH_URL_DISCOVERED');

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
try{
  const ctx=await browser.newContext({storageState:state,ignoreHTTPSErrors:true});
  const page=await ctx.newPage();
  await page.goto(authUrl,{waitUntil:'domcontentloaded',timeout:60000});
  for(let i=0;i<30;i++){
    const body=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
    if(/success|authenticated|authorized|you can close|login complete/i.test(body)){console.log('WASMER_CLI_BROWSER_AUTH_SUCCESS');break;}
    const btn=page.getByRole('button',{name:/authorize|allow|approve|continue|log in|sign in/i}).first();
    if(await btn.count()&&await btn.isVisible().catch(()=>false)){await btn.click({noWaitAfter:true}).catch(()=>{});}
    const link=page.getByRole('link',{name:/authorize|allow|approve|continue/i}).first();
    if(await link.count()&&await link.isVisible().catch(()=>false)){await link.click({noWaitAfter:true}).catch(()=>{});}
    await page.waitForTimeout(1000);
  }
}finally{await browser.close().catch(()=>{});}

const timeoutP=new Promise((resolve)=>setTimeout(()=>resolve({code:null,signal:'timeout'}),45000));
const res=await Promise.race([exitP,timeoutP]);
if(res.code===null){child.kill('SIGTERM');throw new Error('wasmer_login_timeout');}
if(res.code!==0) throw new Error(`wasmer_login_failed:${res.code}:${log.slice(-2000)}`);
console.log('WASMER_CLI_LOGIN_OK');
