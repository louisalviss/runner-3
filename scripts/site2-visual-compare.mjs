#!/usr/bin/env node

import fs from 'node:fs';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';

const baselinePath=process.env.BASELINE_SCREENSHOT||'/tmp/site2-baseline.png';
const candidatePath=process.env.CANDIDATE_SCREENSHOT||'/tmp/site2-candidate.png';
const diffPath=process.env.DIFF_SCREENSHOT||'/tmp/site2-diff.png';
const out=process.env.VISUAL_COMPARE_OUT||'/tmp/site2-visual-compare.json';
const maxRatio=Number(process.env.MAX_VISUAL_DIFF_RATIO||'0.002');

const a=PNG.sync.read(fs.readFileSync(baselinePath));
const b=PNG.sync.read(fs.readFileSync(candidatePath));
if(a.width!==b.width||a.height!==b.height) throw new Error(`screenshot dimensions differ ${a.width}x${a.height} vs ${b.width}x${b.height}`);
const diff=new PNG({width:a.width,height:a.height});
const changed=pixelmatch(a.data,b.data,diff.data,a.width,a.height,{threshold:0.12,includeAA:false});
const pixels=a.width*a.height;
const ratio=changed/pixels;
fs.writeFileSync(diffPath,PNG.sync.write(diff));
const result={status:ratio<=maxRatio?'PASS':'FAIL',changedPixels:changed,totalPixels:pixels,diffRatio:ratio,maxDiffRatio:maxRatio,width:a.width,height:a.height,diffPath};
fs.writeFileSync(out,`${JSON.stringify(result,null,2)}\n`);
console.log(JSON.stringify(result,null,2));
if(result.status!=='PASS') process.exitCode=1;
