import { chromium } from 'playwright-core';
import fs from 'fs';
const st = JSON.parse(fs.readFileSync('/tmp/pntr-browser-state.json','utf8'));
const real = (st.cookies||[]).find(c=>c.name==='anon_user_id' && /pntr\.dev$/.test(c.domain||''));
if(!real?.value) throw new Error('guest cookie missing');
const browser = await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
async function probe(order){
  const ctx = await browser.newContext();
  const fake='00000000-0000-4000-8000-000000000000';
  for(const item of order){
    if(item==='host') await ctx.addCookies([{name:'anon_user_id',value:fake,url:'https://pntr.dev/',path:'/',secure:true,httpOnly:true,sameSite:'Lax'}]);
    if(item==='domain') await ctx.addCookies([{name:'anon_user_id',value:real.value,domain:'.pntr.dev',path:'/',secure:true,httpOnly:true,sameSite:'Lax',expires:Math.floor(Date.now()/1000)+3600}]);
  }
  const r=await ctx.request.get('https://pntr.dev/api/subdomains',{failOnStatusCode:false,timeout:30000});
  const t=await r.text();
  const cookies=await ctx.cookies('https://pntr.dev/');
  console.log(`ORDER_${order.join('_').toUpperCase()}_HTTP=${r.status()} TARGET_VISIBLE=${t.toLowerCase().includes('runner3wp.pntr.dev')} COOKIE_COUNT=${cookies.filter(c=>c.name==='anon_user_id').length}`);
  await ctx.close();
}
await probe(['host','domain']);
await probe(['domain','host']);
await browser.close();
