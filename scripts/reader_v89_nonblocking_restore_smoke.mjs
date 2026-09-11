import fs from 'node:fs';
const path='cloudflare/runner3-core/artifact-library-reader-v82-patch.js';
const s=fs.readFileSync(path,'utf8');
const required=[
  'data-r3-nonblocking-restore-v89="1"',
  "restoreGuard: 'nonblocking-v89'",
  "html.r3-v82-stable.r3-restore-pending-v45 #viewer{visibility:visible!important;opacity:1!important}",
  "html.r3-v82-stable.r3-restore-pending-v45 #r3AudioDock{opacity:1!important;pointer-events:auto!important}",
  "html.r3-v82-stable.r3-restore-pending-v45 body::before,html.r3-v82-stable.r3-v82-restoring body::after{content:none!important;display:none!important;pointer-events:none!important}",
];
for(const marker of required)if(!s.includes(marker))throw new Error('V89_MISSING:'+marker);
if(s.includes("root.classList.add('r3-v82-restoring')"))throw new Error('V89_BLOCKING_CLASS_ARMED');
if(s.includes("body::after{content:'Đang mở đúng trang đọc…'"))throw new Error('V89_BLOCKING_AFTER_PRESENT');
console.log('READER_V89_NONBLOCKING_RESTORE_SMOKE=PASS');
