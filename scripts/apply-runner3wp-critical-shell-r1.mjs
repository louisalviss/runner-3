import fs from 'node:fs';

const path = 'scripts/build-wordpress-edge-snapshot.mjs';
let source = fs.readFileSync(path, 'utf8');
const oldBlock = `  const criticalCopy = criticalOriginal
    .replace(/\\bid=(["'])runner3-critical-css\\1/i, 'id="runner3-v2-critical-css" data-runner3-v2-critical="1"')
    .trim();`;
const newBlock = `  const criticalMatch = criticalOriginal.match(/<style\\b[^>]*>([\\s\\S]*?)<\\/style>/i);
  const criticalCss = criticalMatch?.[1] || '';
  const rootStart = criticalCss.indexOf(':root {');
  const editionStart = criticalCss.indexOf('.edition-hero {', rootStart);
  const signalStart = criticalCss.indexOf('/* OFFSET / SIGNAL — front-page art direction */', rootStart);
  if (rootStart < 0 || editionStart <= rootStart || signalStart <= editionStart) {
    return { html, deferredStyleCount: 0, deferredStyleBytes: 0, criticalCopyBytes: 0, headSavedBytes: 0 };
  }
  const baseCritical = criticalCss.slice(rootStart, editionStart).trim();
  const signalCritical = criticalCss.slice(signalStart).trim();
  const criticalSubset = \`\${baseCritical}\\n\\n\${signalCritical}\`;
  const criticalCopy = \`<style id="runner3-v2-critical-css" data-runner3-v2-critical="r1">\\n\${criticalSubset}\\n</style>\`;`;
if (!source.includes(oldBlock)) throw new Error('Expected criticalCopy block not found; refusing blind patch');
source = source.replace(oldBlock, newBlock);
fs.writeFileSync(path, source);
console.log(JSON.stringify({status:'patched',path,oldBytes:Buffer.byteLength(oldBlock),newBytes:Buffer.byteLength(newBlock)},null,2));
