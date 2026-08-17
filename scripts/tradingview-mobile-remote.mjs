import http from 'node:http';
import fs from 'node:fs';
import { WebSocketServer } from 'ws';
import { chromium } from 'playwright-core';

const PORT = 7070;
const SAVE_FILE = '/tmp/tv-storage-state.json';
const DONE_FILE = '/tmp/tv-auth-done';
const executableCandidates = ['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath = executableCandidates.find(fs.existsSync);
if (!executablePath) throw new Error('Chrome/Chromium not found');

const browser = await chromium.launch({executablePath, headless:false, args:['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled','--window-size=430,850']});
const context = await browser.newContext({viewport:{width:430,height:850}});
let page = await context.newPage();
let cdp = null;
let frameW = 430, frameH = 850;
const clients = new Set();

async function attach(p){
  if (!p || p.isClosed()) return;
  page = p;
  try { if (cdp) await cdp.detach(); } catch {}
  cdp = await context.newCDPSession(page);
  await cdp.send('Page.enable');
  await cdp.send('Page.startScreencast',{format:'jpeg',quality:82,maxWidth:860,maxHeight:1700,everyNthFrame:1});
  cdp.on('Page.screencastFrame', async ev => {
    frameW = Math.max(1, Math.round(ev.metadata.deviceWidth || 430));
    frameH = Math.max(1, Math.round(ev.metadata.deviceHeight || 850));
    let url=''; try { url=page.url(); } catch {}
    const msg = JSON.stringify({t:'frame',data:ev.data,w:frameW,h:frameH,url});
    for (const ws of clients) if (ws.readyState===1) ws.send(msg);
    try { await cdp.send('Page.screencastFrameAck',{sessionId:ev.sessionId}); } catch {}
  });
  p.once('close', async()=>{
    const survivors=context.pages().filter(x=>!x.isClosed());
    if (survivors.length) await attach(survivors[survivors.length-1]);
  });
}
context.on('page', p => attach(p));
await attach(page);
await page.goto('https://www.tradingview.com/accounts/signin/',{waitUntil:'domcontentloaded',timeout:90000});
console.log('TV_MOBILE_REMOTE_READY');

const html = `<!doctype html><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no"><style>
*{box-sizing:border-box}body{margin:0;background:#0b0e11;color:white;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}#top{position:sticky;top:0;z-index:4;background:#111827;padding:8px;display:flex;gap:7px;align-items:center}button,input{font-size:16px;border:0;border-radius:9px;padding:10px}button{background:#2563eb;color:white;font-weight:700}#save{background:#16a34a}.grow{flex:1}#screen{display:block;width:100%;height:auto;touch-action:none;background:#111}#url{font-size:11px;color:#9ca3af;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:4px 8px;background:#111827}#kbd{position:sticky;bottom:0;z-index:4;background:#111827;padding:8px;display:flex;gap:6px}#text{min-width:0;background:white;color:black}.note{font-size:12px;color:#cbd5e1;padding:5px 8px}</style><div id=top><button id=back>‹</button><button id=reload>↻</button><button id=login class=grow>TradingView login</button><button id=save>SAVE</button></div><div id=url></div><img id=screen><div class=note>Tap trực tiếp lên màn hình. Nếu Google mở trang mới, giao diện sẽ tự chuyển sang đó. Sau khi TradingView đã đăng nhập, bấm SAVE.</div><div id=kbd><input id=text class=grow placeholder="Nhập text…"><button id=send>Send</button><button id=enter>Enter</button></div><script>
const s=document.getElementById('screen'),u=document.getElementById('url'),q=document.getElementById('text');let W=430,H=850;const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws'+location.search);ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.t==='frame'){W=m.w;H=m.h;s.src='data:image/jpeg;base64,'+m.data;u.textContent=m.url||''}if(m.t==='saved'){document.body.innerHTML='<div style="padding:32px;font:600 20px -apple-system;color:white;background:#0b0e11;min-height:100vh">Đã lưu session TradingView. Bạn có thể đóng trang này.</div>'}};function send(o){if(ws.readyState===1)ws.send(JSON.stringify(o))}s.onclick=e=>{const r=s.getBoundingClientRect();send({t:'tap',x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height})};document.getElementById('back').onclick=()=>send({t:'back'});document.getElementById('reload').onclick=()=>send({t:'reload'});document.getElementById('login').onclick=()=>send({t:'login'});document.getElementById('send').onclick=()=>{send({t:'text',v:q.value});q.value=''};document.getElementById('enter').onclick=()=>send({t:'enter'});document.getElementById('save').onclick=()=>send({t:'save'});q.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();document.getElementById('send').click();send({t:'enter'})}});
</script>`;

const server=http.createServer((req,res)=>{res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store'});res.end(html)});
const wss=new WebSocketServer({server,path:'/ws'});
wss.on('connection',ws=>{clients.add(ws);ws.on('close',()=>clients.delete(ws));ws.on('message',async raw=>{try{const m=JSON.parse(String(raw));if(!cdp)return;if(m.t==='tap'){await cdp.send('Input.dispatchMouseEvent',{type:'mousePressed',x:m.x,y:m.y,button:'left',clickCount:1});await cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:m.x,y:m.y,button:'left',clickCount:1})}else if(m.t==='text'){await cdp.send('Input.insertText',{text:String(m.v||'')})}else if(m.t==='enter'){await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13})}else if(m.t==='back'){await page.goBack({waitUntil:'domcontentloaded',timeout:30000}).catch(()=>{})}else if(m.t==='reload'){await page.reload({waitUntil:'domcontentloaded',timeout:30000}).catch(()=>{})}else if(m.t==='login'){await page.goto('https://www.tradingview.com/accounts/signin/',{waitUntil:'domcontentloaded',timeout:90000})}else if(m.t==='save'){const state=await context.storageState();const filtered={cookies:state.cookies.filter(c=>{const d=(c.domain||'').replace(/^\./,'').toLowerCase();return d==='tradingview.com'||d.endsWith('.tradingview.com')}),origins:state.origins.filter(o=>{try{const h=new URL(o.origin).hostname.toLowerCase();return h==='tradingview.com'||h.endsWith('.tradingview.com')}catch{return false}})};fs.writeFileSync(SAVE_FILE,JSON.stringify(filtered),{mode:0o600});fs.writeFileSync(DONE_FILE,new Date().toISOString(),{mode:0o600});ws.send(JSON.stringify({t:'saved'}));setTimeout(async()=>{await browser.close();process.exit(0)},1200)}}catch(e){console.error('ws error',e.message)}})});
server.listen(PORT,'127.0.0.1',()=>console.log('TV_MOBILE_HTTP_READY'));
