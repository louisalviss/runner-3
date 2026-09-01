import fs from 'node:fs';

const path='cloudflare/runner3-core/audio-entry.js';
const source=fs.readFileSync(path,'utf8');
const required=[
  'import { handleAudioMedia } from "./src/audio-media.js";',
  'import { handleEbookReaderAudio } from "./src/ebook-reader-audio.js";',
  'const ebookAudioResponse = await handleEbookReaderAudio(request, env);',
  'if (ebookAudioResponse) return ebookAudioResponse;',
  'const app = await loadReaderApp();',
];
for (const marker of required) {
  if (!source.includes(marker)) throw new Error(`MISSING:${marker}`);
}
const ebookIndex=source.indexOf('handleEbookReaderAudio(request, env)');
const readerIndex=source.indexOf('const app = await loadReaderApp()');
if (!(ebookIndex >= 0 && readerIndex > ebookIndex)) throw new Error('EBOOK_AUDIO_NOT_FAST_PATHED');
console.log('EBOOK_AUDIO_FAST_PATH_SOURCE=PASS');
