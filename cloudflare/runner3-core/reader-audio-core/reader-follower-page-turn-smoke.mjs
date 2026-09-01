import assert from 'node:assert/strict';
import { ReaderFollower } from './reader-follower.js';

const events = [];
let visible = false;
const follower = new ReaderFollower({
  displayCfi: async (cfi) => {
    events.push(`display:${cfi}`);
    visible = true;
    return true;
  },
  isVisible: async () => visible,
  clearHighlight: () => events.push('clear'),
  highlight: (target) => events.push(`highlight:${target.cfi}`),
});

await follower.follow({ cfi: 'epubcfi(/6/4)' }, { force: true });
const displayIndex = events.indexOf('display:epubcfi(/6/4)');
const highlightIndex = events.indexOf('highlight:epubcfi(/6/4)');
assert.ok(displayIndex >= 0, 'page boundary must request display');
assert.ok(highlightIndex > displayIndex, 'highlight must be applied after relocation');

events.length = 0;
visible = true;
await follower.follow({ cfi: 'epubcfi(/6/5)' });
assert.equal(events.some((x) => x.startsWith('display:')), false, 'visible target must not trigger page movement');
assert.equal(events.at(-1), 'highlight:epubcfi(/6/5)');

console.log('READER_FOLLOWER_PAGE_TURN_SMOKE=PASS');
