import { patchReaderV82 } from '../cloudflare/runner3-core/artifact-library-reader-v82-stable-shell-entry.js';
const html=patchReaderV82('<!doctype html><html><head></head><body class="r3-audio-ui"><div id="viewer"></div></body></html>');
for(const marker of [
  "r3-v90-home",
  "r3-v90-browser",
  "layoutOwner: 'v90'",
  "owner: 'layout-convergence-v90'",
  "r3-v90-browser body.r3-audio-ui.r3-audio-expanded #viewer{bottom:210px!important}",
  "r3-v90-home body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}",
  "top:calc(max(env(safe-area-inset-top,0px),44px) + 8px)!important",
  "set(viewer, 'top', top)",
  "set(viewer, 'bottom', bottom)",
  "apply('body-class', true)",
]) if(!html.includes(marker))throw new Error('missing v90 marker '+marker);
if(html.includes('html.r3-v82-home #viewer{top:calc(max(env(safe-area-inset-top,0px),44px) + 54px)'))throw new Error('legacy v82 home 98px top reserve still owns layout');
console.log('READER_V90_LAYOUT_CONVERGENCE_SMOKE=PASS bytes='+html.length);
