import http from 'node:http';
import vm from 'node:vm';
import { once } from 'node:events';
import { webkit } from 'playwright';

const app=(await import('../cloudflare/runner3-core/artifact-library-simple-entry.js?webkit-v66')).default;
const SAMPLE_KEY='core/ebook/webkit-smoke/final/WebKit-Smoke.epub';
let brokenAsset=false;
let manageBodies=[];

function toRequest(req,base){
  const url=new URL(req.url,base);
  const headers=new Headers();
  for(const [k,v] of Object.entries(req.headers)){if(Array.isArray(v)){for(const item of v)headers.append(k,item)}else if(v!==undefined)headers.set(k,String(v))}
  const method=req.method||'GET';
  return new Request(url,{method,headers,body:(method==='GET'||method==='HEAD')?undefined:req,duplex:(method==='GET'||method==='HEAD')?undefined:'half'});
}
async function sendNode(res,response){
  res.statusCode=response.status;
  response.headers.forEach((v,k)=>res.setHeader(k,v));
  if(!response.body){res.end();return}
  const reader=response.body.getReader();
  while(true){const {done,value}=await reader.read();if(done)break;res.write(Buffer.from(value))}
  res.end();
}

const fakeEnv={
  ARTIFACTS:{
    async list(){return {objects:[{key:SAMPLE_KEY,size:12345,uploaded:new Date('2026-09-03T00:00:00Z')}],truncated:false}},
    async head(key){return key===SAMPLE_KEY?{key,size:12345,httpMetadata:{contentType:'application/epub+zip'},customMetadata:{}}:null},
    async get(){return null},
    async put(){},
    async delete(){},
  },
  RUNNER3_CORE_TOKEN:'webkit-v66-token',
};

async function assertInlineScriptsParse(){
  const response=await app.fetch(new Request('http://r3.local/artifact-library'),fakeEnv,{waitUntil(){}});
  const html=await response.text();
  const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]).filter(x=>x.trim());
  for(let i=0;i<scripts.length;i++){
    try{new vm.Script(scripts[i],{filename:'artifact-library-inline-'+(i+1)+'.js'})}
    catch(error){console.error('READER_V66_INLINE_SCRIPT_PARSE_FAIL index='+(i+1));console.error(String(error&&error.stack||error));throw error}
  }
  console.log('READER_V66_INLINE_SCRIPT_PARSE=PASS scripts='+scripts.length);
}
await assertInlineScriptsParse();

const server=http.createServer(async(req,res)=>{
  const base='http://127.0.0.1:'+server.address().port;
  try{
    const url=new URL(req.url,base);
    if(url.pathname==='/artifact-library/assets/manage-v66.js'&&brokenAsset){
      res.writeHead(200,{'content-type':'application/javascript; charset=utf-8','cache-control':'no-store'});
      res.end('function(){ this is intentionally invalid javascript');
      return;
    }
    if(url.pathname==='/artifact-library/api/list'){
      res.writeHead(200,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
      res.end(JSON.stringify({ok:true,prefix:'core/ebook/',final_only:true,canonical_latest_per_scope:true,objects:[{key:SAMPLE_KEY,size:12345,uploaded:'2026-09-03T00:00:00.000Z',scope:'webkit-smoke'}]}));
      return;
    }
    if(url.pathname==='/artifact-library/api/progress'){
      res.writeHead(200,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
      res.end(JSON.stringify({ok:true,items:[]}));
      return;
    }
    if(url.pathname==='/artifact-library/api/manage'&&req.method==='POST'){
      let body='';for await(const chunk of req)body+=chunk;
      let data={};try{data=JSON.parse(body)}catch{}
      manageBodies.push(data);
      const newKey='core/ebook/webkit-smoke/final/'+encodeURIComponent(String(data.name||'Renamed Book')).replace(/%20/g,'-')+'.epub';
      res.writeHead(200,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
      res.end(JSON.stringify({ok:true,action:data.action||'rename',key:data.key||SAMPLE_KEY,new_key:newKey,title:data.name||'Renamed Book'}));
      return;
    }
    if(url.pathname.startsWith('/artifact-library/api/')){
      res.writeHead(200,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
      res.end(JSON.stringify({ok:true,items:[],books:{},objects:[]}));
      return;
    }
    const response=await app.fetch(toRequest(req,base),fakeEnv,{waitUntil(){}});
    await sendNode(res,response);
  }catch(error){res.statusCode=500;res.setHeader('content-type','text/plain');res.end(String(error&&error.stack||error))}
});
server.listen(0,'127.0.0.1');
await once(server,'listening');
const origin='http://127.0.0.1:'+server.address().port;

async function waitForBookOrDiagnose(page,errors,consoleLines,label){
  try{
    await page.waitForSelector('article.book',{timeout:7000});
  }catch(error){
    const body=(await page.locator('body').innerText().catch(()=>'' )).slice(0,1800).replace(/\s+/g,' ').trim();
    const html=(await page.content().catch(()=>'' )).slice(0,3000).replace(/\s+/g,' ');
    const asset=await page.evaluate(()=>({ready:window.__R3_MANAGE_UI_V66===true,assetError:window.__R3_MANAGE_UI_V66_ERROR||'',href:location.href})).catch(()=>({}));
    throw new Error(label+'_NO_BOOK; asset='+JSON.stringify(asset)+'; pageErrors='+JSON.stringify(errors)+'; console='+JSON.stringify(consoleLines)+'; body='+body+'; html='+html+'; original='+String(error));
  }
}

const browser=await webkit.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];
  const dialogs=[];
  const consoleLines=[];
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',msg=>{if(msg.type()==='error'||msg.type()==='warning')consoleLines.push(msg.type()+':'+msg.text())});
  page.on('dialog',async dialog=>{dialogs.push(dialog.type()+':'+dialog.message());await dialog.dismiss()});
  await page.goto(origin+'/artifact-library',{waitUntil:'networkidle'});
  await waitForBookOrDiagnose(page,errors,consoleLines,'WEBKIT_MAIN');
  const bodyText=(await page.locator('body').innerText()).trim();
  if(bodyText.length<10)throw new Error('WEBKIT_LIBRARY_BODY_BLANK');
  const assetReady=await page.evaluate(()=>window.__R3_MANAGE_UI_V66===true);
  if(!assetReady)throw new Error('WEBKIT_V66_ASSET_NOT_READY');
  await page.locator('.r3-manage-v65').first().click();
  await page.waitForSelector('#r3-manage-layer-v66');
  if(!(await page.getByText('Tùy chọn sách',{exact:true}).isVisible()))throw new Error('WEBKIT_MENU_NOT_VISIBLE');
  await page.getByRole('button',{name:'Đổi tên',exact:true}).click();
  const input=page.locator('.r3-manage-input-v66');
  await input.waitFor();
  await input.fill('Renamed WebKit Book');
  await page.getByRole('button',{name:'Lưu',exact:true}).click();
  await page.waitForLoadState('domcontentloaded');
  if(!manageBodies.some(x=>x&&x.action==='rename'&&x.key===SAMPLE_KEY&&x.name==='Renamed WebKit Book'))throw new Error('WEBKIT_RENAME_REQUEST_MISSING');
  if(dialogs.length)throw new Error('WEBKIT_LEGACY_DIALOG_LEAK:'+dialogs.join('|'));
  if(errors.length)throw new Error('WEBKIT_PAGEERROR:'+errors.join('|'));
  console.log('READER_V66_WEBKIT_REAL_UI=PASS');

  brokenAsset=true;
  const failPage=await browser.newPage({viewport:{width:390,height:844}});
  const failErrors=[];
  const failConsole=[];
  failPage.on('pageerror',error=>failErrors.push(String(error)));
  failPage.on('console',msg=>{if(msg.type()==='error'||msg.type()==='warning')failConsole.push(msg.type()+':'+msg.text())});
  await failPage.goto(origin+'/artifact-library',{waitUntil:'networkidle'});
  await waitForBookOrDiagnose(failPage,failErrors,failConsole,'WEBKIT_BROKEN_ASSET');
  const failBody=(await failPage.locator('body').innerText()).trim();
  if(failBody.length<10)throw new Error('WEBKIT_BROKEN_ASSET_BLANKED_LIBRARY');
  const fallbackVisible=await failPage.locator('.r3-manage-v65').first().isVisible();
  if(!fallbackVisible)throw new Error('WEBKIT_BROKEN_ASSET_REMOVED_FALLBACK');
  if(!failErrors.length)throw new Error('WEBKIT_BROKEN_ASSET_DID_NOT_EXECUTE_FAILURE_PATH');
  console.log('READER_V66_BROKEN_ASSET_ISOLATION=PASS');
}finally{
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
