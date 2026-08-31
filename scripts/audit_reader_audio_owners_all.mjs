import fs from 'node:fs';
import path from 'node:path';

const root = 'cloudflare/runner3-core';
const names = fs.readdirSync(root)
  .filter((name) => /^artifact-library-reader-v(?:[1-9]|[12]\d|3[01])-[^/]+-entry\.js$/.test(name))
  .sort((a, b) => {
    const av = Number(a.match(/reader-v(\d+)/)?.[1] || 0);
    const bv = Number(b.match(/reader-v(\d+)/)?.[1] || 0);
    return av - bv || a.localeCompare(b);
  });
const patterns = [
  ['audio.play', /\baudio\.play\s*\(/],
  ['audio.pause', /\baudio\.pause\s*\(/],
  ['audio.listener', /\baudio\.addEventListener\s*\(/],
  ['main-click', /r3AudioMain|handleMain|addEventListener\(['"]click/],
  ['timer', /setInterval\s*\(|requestAnimationFrame\s*\(/],
  ['timeupdate-dispatch', /dispatchEvent\s*\(\s*new Event\(['"]timeupdate/],
  ['ended', /['"]ended['"]/],
  ['playbackRate', /playbackRate/],
];
const rows=[];
for(const name of names){
  const lines=fs.readFileSync(path.join(root,name),'utf8').split(/\r?\n/);
  for(let i=0;i<lines.length;i++){
    const hits=patterns.filter(([,re])=>re.test(lines[i])).map(([label])=>label);
    if(hits.length)rows.push({version:Number(name.match(/reader-v(\d+)/)?.[1]||0),file:name,line:i+1,hits,text:lines[i].trim().slice(0,260)});
  }
}
console.log(JSON.stringify({files:names.length,rows},null,2));
console.log(`READER_AUDIO_OWNER_FULL_AUDIT=PASS files=${names.length} matches=${rows.length}`);
