const fs=require('fs'), path=require('path'), crypto=require('crypto');
const root='/tmp/vbook-audit/roots';
const backup='/tmp/vbook-audit/enc-backup';
fs.mkdirSync(backup,{recursive:true});
function keyFor(meta){
  let md=crypto.createHash('md5').update('com.vbook.app'+String(meta.source||'')+String(meta.author||'')).digest('hex').replace(/^0+/,'')||'0';
  return crypto.createHash('sha256').update(md).digest();
}
function decrypt(raw,key){
  raw=raw.trim().replaceAll('x0P1Xx','+').replaceAll('x0P2Xx','/').replaceAll('x0P3Xx','=');
  let d=crypto.createDecipheriv('aes-256-cbc',key,Buffer.alloc(16,0));
  return Buffer.concat([d.update(Buffer.from(raw,'base64')),d.final()]).toString('utf8');
}
let stats={plugins:0,files:0,ok:0,fail:0,already:0};
for(const id of fs.readdirSync(root)){
  const dir=path.join(root,id); let p=path.join(dir,'plugin.json'); if(!fs.existsSync(p)) continue;
  let m; try{m=JSON.parse(fs.readFileSync(p,'utf8'))}catch{continue}
  if(!(m.metadata&&m.metadata.encrypt===true)) continue; stats.plugins++;
  let k=keyFor(m.metadata); let src=path.join(dir,'src'); if(!fs.existsSync(src)) continue;
  for(const f of fs.readdirSync(src).filter(x=>x.endsWith('.js'))){ stats.files++; let fp=path.join(src,f), raw=fs.readFileSync(fp,'utf8');
    if(/\bfunction\s+execute\b|\bload\s*\(/.test(raw)){stats.already++;continue}
    try{let out=decrypt(raw,k); if(!(/[\x09\x0a\x0d\x20-\x7e\u0080-\uffff]{20}/.test(out))) throw Error('not text');
      let bd=path.join(backup,id,'src');fs.mkdirSync(bd,{recursive:true});fs.writeFileSync(path.join(bd,f),raw);fs.writeFileSync(fp,out);stats.ok++;
    }catch(e){stats.fail++; console.log('FAIL',id,m.metadata.name,f,e.message)}
  }
}
console.log(JSON.stringify(stats));
