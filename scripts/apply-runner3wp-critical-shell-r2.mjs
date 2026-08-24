import fs from 'node:fs';

const path = 'scripts/build-wordpress-edge-snapshot.mjs';
let s = fs.readFileSync(path, 'utf8');
const anchor = 'function optimizeFcpHtml(html) {';
if (!s.includes(anchor)) throw new Error('optimizeFcpHtml anchor missing');

const helpers = String.raw`function cssBlocks(css) {
  const out = [];
  let i = 0;
  while (i < css.length) {
    while (i < css.length && /\s/.test(css[i])) i++;
    if (i >= css.length) break;
    const open = css.indexOf('{', i);
    if (open < 0) break;
    const prelude = css.slice(i, open).trim();
    let depth = 1;
    let j = open + 1;
    for (; j < css.length && depth; j++) {
      if (css[j] === '{') depth++;
      else if (css[j] === '}') depth--;
    }
    if (depth) break;
    out.push({ prelude, body: css.slice(open + 1, j - 1) });
    i = j;
  }
  return out;
}

function criticalSelector(prelude) {
  const p = prelude.replace(/\/\*[\s\S]*?\*\//g, '').trim();
  if (!p) return false;
  if (/^:root\b/.test(p) || /^(?:\*|html\b|body\b|a\b|img\b)/.test(p)) return true;
  if (p === '.home') return true;
  return /\.(?:wrap|kicker|site-header|header-row|brand(?:-dot)?|nav|header-meta|signal-stage(?:__[\w-]+)?|signal-title(?:__[\w-]+)?|signal-orbit(?:__[\w-]+)?)(?![\w-])/.test(p);
}

function filterCriticalCss(css) {
  let out = '';
  for (const block of cssBlocks(css)) {
    const p = block.prelude.replace(/\/\*[\s\S]*?\*\//g, '').trim();
    if (/^@(?:media|supports)\b/.test(p)) {
      const inner = filterCriticalCss(block.body);
      if (inner.trim()) out += p + '{' + inner + '}\n';
    } else if (/^@keyframes\s+signal-spin\b/.test(p) || criticalSelector(block.prelude)) {
      out += block.prelude + '{' + block.body + '}\n';
    }
  }
  return out.trim();
}

`;
s = s.replace(anchor, helpers + anchor);

const oldCritical = [
  '  const baseCritical = criticalCss.slice(rootStart, editionStart).trim();',
  '  const signalCritical = criticalCss.slice(signalStart).trim();',
  '  const criticalSubset = `${baseCritical}\\n\\n${signalCritical}`;',
  '  const criticalCopy = `<style id="runner3-v2-critical-css" data-runner3-v2-critical="r1">\\n${criticalSubset}\\n</style>`;',
].join('\n');
const newCritical = [
  '  const criticalSubset = filterCriticalCss(criticalCss);',
  '  if (!criticalSubset || Buffer.byteLength(criticalSubset) > 9200) {',
  '    return { html, deferredStyleCount: 0, deferredStyleBytes: 0, criticalCopyBytes: 0, headSavedBytes: 0 };',
  '  }',
  '  const criticalCopy = `<style id="runner3-v2-critical-css" data-runner3-v2-critical="r2">\\n${criticalSubset}\\n</style>`;',
].join('\n');
if (!s.includes(oldCritical)) throw new Error('R1 critical block missing');
s = s.replace(oldCritical, newCritical);

const oldDeferred = [
  '  const deferredCss = `\\n<!-- runner3-v2-original-css-order -->\\n${deferred.map(({ tag }) => tag.trim()).join(\'\\n\')}\\n`;',
  "  const bodyClose = withCritical.lastIndexOf('</body>');",
  '  const optimized = bodyClose >= 0',
  '    ? `${withCritical.slice(0, bodyClose)}${deferredCss}${withCritical.slice(bodyClose)}`',
  '    : `${withCritical}${deferredCss}`;',
].join('\n');
const newDeferred = [
  "  const deferredMarkup = deferred.map(({ tag }) => tag.trim()).join('\\n');",
  '  const deferredCss = `\\n<!-- runner3-v2-original-css-order -->\\n<template id="runner3-v2-deferred-css">${deferredMarkup}</template>\\n<script data-runner3-v2-css-loader="r2">(()=>{const a=()=>{const t=document.getElementById(\'runner3-v2-deferred-css\');if(t){document.head.append(t.content.cloneNode(true));t.remove();}};requestAnimationFrame(()=>requestAnimationFrame(a));})();</script>\\n`;',
  "  const bodyClose = withCritical.lastIndexOf('</body>');",
  '  const optimized = bodyClose >= 0',
  '    ? `${withCritical.slice(0, bodyClose)}${deferredCss}${withCritical.slice(bodyClose)}`',
  '    : `${withCritical}${deferredCss}`;',
].join('\n');
if (!s.includes(oldDeferred)) throw new Error('R1 deferred block missing');
s = s.replace(oldDeferred, newDeferred);

fs.writeFileSync(path, s);
console.log(JSON.stringify({ status: 'patched-r2-final', path }, null, 2));
