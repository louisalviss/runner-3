import fs from 'node:fs';
const v82=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v82-patch.js','utf8');
const shell=fs.readFileSync('cloudflare/runner3-core/artifact-library-reader-v82-stable-shell-entry.js','utf8');
if(!v82.includes("doc.documentElement.dataset.r3GestureOwnerV94 = '1'")) throw new Error('V94_DOC_MARKER_MISSING');
if(!v82.includes("typeof bridge.onRelocated === 'function'")) throw new Error('V94_RELOCATED_HOOK_MISSING');
if(!v82.includes('window.__r3FrameRebindOffV94 = off')) throw new Error('V94_RELOCATED_OFF_MISSING');
if(!v82.includes('await paint(); bindReaderFrames(); setTimeout(bindReaderFrames, 80); refreshChapterUi(bridge);')) throw new Error('V94_MOVE_REBIND_MISSING');
if(!shell.includes("X-R3-Reader-Frame-Bind', 'relocated-v94'")) throw new Error('V94_HEADER_MISSING');
console.log('READER_V94_FRAME_REBIND_SMOKE=PASS');
