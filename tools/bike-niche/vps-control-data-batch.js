#!/usr/bin/env node
'use strict';
// Secure batch upload: one BWS credential load, one authorized MTProto session.
// Resume per-file checkpoint; never materialize credentials on disk here.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {TelegramClient,sessions}=require('/opt/telegram-mtproto/node_modules/teleproto');
const CHECKROOT='/opt/bike-niche-corpus/releases';
const STAGE='/var/lib/telegram-upload/bike-niche';
const TOPIC='/var/lib/telegram-audit/vps-control-topic-map.json';
const sleep=(n)=>new Promise(ok=>setTimeout(ok,n));
function checkString(s){ if(!s)throw Error('EMPTY_INPUT'); return String(s); }
function sha(file){
 const hash=crypto.createHash('sha256');
 const fd=fs.openSync(file,'r');const buf=Buffer.alloc(1024*1024);
 try{let n;while((n=fs.readSync(fd,buf,0,buf.length,null))>0)hash.update(buf.subarray(0,n));}
 finally{fs.closeSync(fd);}
 return hash.digest('hex');
}
function checkpoint(p,obj){
 const t=p+'.tmp.'+process.pid;
 fs.writeFileSync(t,JSON.stringify(obj,null,2),{mode:0o600});fs.renameSync(t,p);
}
function caption(base,archive,fullsha,part){
 return [base,'Archive: '+archive,'Part '+part.number+'/'+part.total,
   'Full SHA256: '+fullsha,'Part SHA256: '+part.sha256,
   'Restore: concatenate all numbered parts in order'].join('\n');
}
function msgId(m){return Number(m?.id||0)}
function waitSeconds(e){
 const n=Number(e?.seconds||String(e?.errorMessage||e?.message||'').match(/FLOOD_WAIT_(\d+)/)?.[1]||0);
 return Number.isFinite(n)&&n>0?n:0;
}
async function main(){
 const statepath=path.resolve(checkString(process.argv[2]));
 const base=checkString(process.argv[3]);
 if(!statepath.startsWith(CHECKROOT+path.sep) || path.basename(statepath)!=='telegram-part-state.json')throw Error('CHECKPOINT_OUTSIDE_ALLOWED_ROOT');
 const work=path.dirname(statepath);
 const state=JSON.parse(fs.readFileSync(statepath,'utf8'));
 const parts=state.parts||[];
 if(!parts.length || parts.length>3000)throw Error('INVALID_PART_COUNT');
 const archive=path.join(work,checkString(state.archive));
 if(!fs.existsSync(archive)||sha(archive)!==state.archive_sha256||fs.statSync(archive).size!==state.archive_bytes)throw Error('ARCHIVE_HASH_OR_SIZE_MISMATCH');
 const mapping=JSON.parse(fs.readFileSync(TOPIC,'utf8'));
 const forumId=checkString(mapping?.forum?.id),topicId=Number(mapping?.topics?.data);
 if(topicId!==1 || !forumId)throw Error('TOPIC_DATA_MAPPING_MISSING');
 if(!process.env.TG_STRING_SESSION||!process.env.TG_API_ID||!process.env.TG_API_HASH)throw Error('MT_PROTO_CREDENTIALS_MISSING');
 const client=new TelegramClient(new sessions.StringSession(process.env.TG_STRING_SESSION),Number(process.env.TG_API_ID),process.env.TG_API_HASH,{connectionRetries:5,autoReconnect:true});
 fs.mkdirSync(STAGE,{recursive:true,mode:0o700});
 await client.connect();
 try{
  if(!(await client.checkAuthorization()))throw Error('TG_UNAUTHORIZED');
  const dialogs=await client.getDialogs({limit:250});
  const peer=dialogs.find(x=>String(x?.entity?.id??'')===forumId)?.entity;
  if(!peer)throw Error('VPS_CONTROL_NOT_FOUND');
  // Reconcile messages sent shortly before a disconnect but not checkpointed.
  const recent=await client.getMessages(peer,{limit:300});
  const existing=new Map(recent.filter(x=>x?.media?.document).map(x=>[String(x.message||''),msgId(x)]));
  async function transmit(file,cap){
   if(existing.has(cap))return {id:existing.get(cap),reconciled:true};
   let last;
   for(let attempt=1;attempt<=5;attempt++){
    try{
     const result=await client.sendFile(peer,{file,caption:cap,forceDocument:true,silent:true,replyTo:topicId});
     const id=msgId(result);if(!id)throw Error('SEND_WITHOUT_ID');
     existing.set(cap,id);return {id,reconciled:false};
    }catch(e){
     last=e;
     if(attempt===5)break;
     const wait=waitSeconds(e);
     await sleep((wait?Math.min(wait+2,600):Math.min(6*Math.pow(2,attempt),80))*1000);
    }
   }
   throw Error('SEND_RETRIES_EXHAUSTED: '+String(last?.errorMessage||last?.message||last));
  }
  for(const part of parts){
   if(part?.number<1||part?.number>parts.length||part.total!==parts.length||!/^[a-z0-9._-]+$/i.test(part.name))throw Error('INVALID_PART_DESCRIPTOR');
   if(state.message_ids?.[part.name])continue;
   const src=path.join(work,'telegram_parts',part.name);
   if(path.dirname(src)!==path.join(work,'telegram_parts')||!fs.existsSync(src))throw Error('PART_MISSING');
   if(fs.statSync(src).size!==part.bytes||sha(src)!==part.sha256)throw Error('PART_HASH_MISMATCH: '+part.name);
   const stage=path.join(STAGE,part.name);
   fs.copyFileSync(src,stage);
   const cap=caption(base,state.archive,state.archive_sha256,part);
   try{
    const receipt=await transmit(stage,cap);
    state.message_ids=state.message_ids||{};
    state.message_ids[part.name]=receipt.id;
    checkpoint(statepath,state);
    console.log(JSON.stringify({part_sent:part.number,total:parts.length,message_id:receipt.id,reconciled:receipt.reconciled}));
   }finally{try{fs.unlinkSync(stage)}catch{}}
   await sleep(900);
  }
  const manifest=path.join(work,'telegram-parts-manifest.json');
  const receipt={
   archive:state.archive,archive_sha256:state.archive_sha256,archive_bytes:state.archive_bytes,
   part_bytes:state.part_bytes,parts:parts.map(p=>({...p,telegram_message_id:state.message_ids[p.name]})),
   reassemble_command:'cat '+state.archive+'.part-* > '+state.archive,r2_durable_master:true
  };
  checkpoint(manifest,receipt);
  if(!state.manifest_message_id){
   const cap=['BIKE NICHE — PARTS MANIFEST','Archive: '+state.archive,'Parts: '+parts.length,
    'SHA256: '+state.archive_sha256,'Follow numbered parts to restore .tar.zst'].join('\n');
   const stage=path.join(STAGE,path.basename(manifest));
   fs.copyFileSync(manifest,stage);
   try{
    const done=await transmit(stage,cap);
    state.manifest_message_id=done.id;checkpoint(statepath,state);
   }finally{try{fs.unlinkSync(stage)}catch{}}
  }
  console.log(JSON.stringify({ok:true,message_id:state.manifest_message_id,
   manifest_message_id:state.manifest_message_id,
   part_message_ids:parts.map(p=>state.message_ids[p.name]),
   part_count:parts.length,bytes:state.archive_bytes,topic:'Data',forum:'VPS Control'}));
 }finally{try{await client.disconnect()}catch{}}
}
main().catch(e=>{console.error(JSON.stringify({ok:false,error:String(e?.errorMessage||e?.message||e)}));process.exit(1)});
