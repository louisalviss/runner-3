// trigger corrected PNTR guest flow 2026-08-24
import { chromium } from 'playwright';
import fs from 'fs';
import crypto from 'crypto';

const cfToken=process.env.CLOUDFLARE_API_TOKEN;
const cfAccount=process.env.CLOUDFLARE_ACCOUNT_ID;
const project=process.env.CF_PROJECT||'runner3-download-gateway';
const pagesTarget=`${project}.pages.dev`;
const candidates=['dl3','dlrunner3','r3download','runner3dl'];
const expectedSize=13951503;
const expectedSha='9e72a0ab7e8ae1f31b8c1086efdffa6b4842aff114e8ea1fc7162501571fb537';
const base='https://pntr.dev';

const browser=await chromium.launch({headless:true});
const context=await browser.newContext();
const page=await context.newPage();
await page.goto(base+'/dashboard',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});

async function api(path,method='GET',data=undefined){
  const opts={method,failOnStatusCode:false};
  if(data!==undefined){ opts.data=data; opts.headers={'Content-Type':'application/json'}; }
  const r=await context.request.fetch(base+path,opts);
  let body=null; try{body=await r.json();}catch{body=await r.text();}
  return {status:r.status(),body};
}

let subs=await api('/api/subdomains');
if(subs.status===401){
  const anon=await api('/api/auth/anonymous','POST');
  if(!anon.status || anon.status>=300) throw new Error('pntr_anonymous_auth_failed:'+anon.status);
  subs=await api('/api/subdomains');
}
if(subs.status!==200) throw new Error('pntr_guest_session_failed:'+subs.status);

const domains=await api('/api/domains');
if(domains.status!==200) throw new Error('pntr_domains_failed:'+domains.status);
const domainList=Array.isArray(domains.body)?domains.body:(domains.body?.domains||domains.body?.data||domains.body?.result||[]);
const pntr=domainList.find(x=>String(x?.name||x?.domain||x?.hostname||x?.full_domain||'').toLowerCase().includes('pntr.dev')) || domainList[0];
const domainId=pntr?.id||pntr?.domain_id;
if(!domainId) throw new Error('pntr_domain_id_missing');

let chosen='',sub=null;
for(const name of candidates){
  const ck=await api(`/api/check/${encodeURIComponent(domainId)}/${encodeURIComponent(name)}`);
  if(ck.status!==200 || ck.body?.available!==true) continue;
  const cr=await api('/api/subdomains','POST',{name,domain_id:domainId,description:'Runner3 direct download'});
  if([200,201].includes(cr.status)){
    sub=cr.body?.subdomain||cr.body?.data||cr.body?.result||cr.body;
    chosen=name; break;
  }
}
if(!chosen) throw new Error('pntr_no_candidate_registered');
const fqdn=`${chosen}.pntr.dev`;
let subId=sub?.id||sub?.subdomain_id;
if(!subId){
  const ls=await api('/api/subdomains');
  const arr=Array.isArray(ls.body)?ls.body:(ls.body?.subdomains||ls.body?.data||ls.body?.result||[]);
  const x=arr.find(v=>String(v?.full_domain||v?.fqdn||v?.hostname||'')===fqdn || v?.name===chosen);
  subId=x?.id||x?.subdomain_id;
}
if(!subId) throw new Error('pntr_subdomain_id_missing');

const cfBase=`https://api.cloudflare.com/client/v4/accounts/${cfAccount}/pages/projects/${project}/domains`;
const cfHeaders={Authorization:`Bearer ${cfToken}`,'Content-Type':'application/json'};
let cfList=await fetch(cfBase,{headers:cfHeaders}).then(r=>r.json());
if(!cfList.success) throw new Error('cf_pages_domain_list_failed');
let current=(cfList.result||[]).find(x=>x.name===fqdn);
if(!current){
  const r=await fetch(cfBase,{method:'POST',headers:cfHeaders,body:JSON.stringify({name:fqdn})});
  const j=await r.json();
  if(!j.success) throw new Error('cf_pages_domain_create_failed:'+JSON.stringify(j.errors||[]));
  current=j.result;
}

const rec=await api(`/api/subdomains/${encodeURIComponent(subId)}/records`,'POST',{record_type:'CNAME',record_value:pagesTarget});
if(![200,201].includes(rec.status)) throw new Error('pntr_cname_failed:'+rec.status+':'+JSON.stringify(rec.body).slice(0,400));

fs.mkdirSync('/tmp/pntr-download',{recursive:true});
await context.storageState({path:'/tmp/pntr-download/storage-state.json'});
await browser.close();

let domainStatus=null,http=0,disp='',ctype='',size=0,sha='';
for(let i=0;i<24;i++){
  const j=await fetch(cfBase+'/'+encodeURIComponent(fqdn),{headers:cfHeaders}).then(r=>r.json()).catch(()=>null);
  domainStatus=j?.result?.status||domainStatus;
  try{
    const r=await fetch(`https://${fqdn}/%40LinkFilesBot.apk`,{redirect:'manual'});
    http=r.status; disp=r.headers.get('content-disposition')||''; ctype=r.headers.get('content-type')||'';
    if(http===200){
      const b=Buffer.from(await r.arrayBuffer()); size=b.length; sha=crypto.createHash('sha256').update(b).digest('hex');
      if(size===expectedSize&&sha===expectedSha&&/^attachment/i.test(disp)) break;
    }
  }catch{}
  await new Promise(r=>setTimeout(r,5000));
}
const verified=http===200&&size===expectedSize&&sha===expectedSha&&/^attachment/i.test(disp);
const out={checkedAt:new Date().toISOString(),hostname:fqdn,pagesTarget,customDomainStatus:domainStatus,directUrl:`https://${fqdn}/%40LinkFilesBot.apk`,httpCode:http,contentDisposition:disp,contentType:ctype,size,sha256:sha,verified,workerHostnameHidden:true,oldDomainUntouched:'runner3wp.pntr.dev'};
fs.writeFileSync('/tmp/pntr-download/status.json',JSON.stringify(out,null,2)+'\n');
console.log(JSON.stringify(out,null,2));
if(!verified) process.exit(2);
