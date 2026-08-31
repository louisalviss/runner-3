import assert from 'node:assert/strict';
import { PositionMapper, ReaderFollower, normalizePlaybackState } from './index.js';

const state = normalizePlaybackState({ time: -2, playbackRate: 9, playingIntent: 1 });
assert.equal(state.time, 0);
assert.equal(state.playbackRate, 4);
assert.equal(state.playingIntent, true);

const mapper = new PositionMapper([
  { start: 0, end: 1, cfi: 'a', token: 'A' },
  { start: 1, end: 2, cfi: 'b', token: 'B' },
  { start: 2, end: 3, cfi: 'c', token: 'C' },
]);
assert.equal(mapper.at(0.5).cfi, 'a');
assert.equal(mapper.at(1.75).cfi, 'b');
assert.equal(mapper.at(9).cfi, 'c');

let concurrent = 0;
let maxConcurrent = 0;
const landed = [];
const follower = new ReaderFollower({
  isVisible: async () => false,
  displayCfi: async (cfi) => {
    concurrent += 1;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    await new Promise((r) => setTimeout(r, 15));
    landed.push(cfi);
    concurrent -= 1;
  },
});

await Promise.all([
  follower.follow({ cfi: 'a' }),
  follower.follow({ cfi: 'b' }),
  follower.follow({ cfi: 'c' }),
]);
assert.equal(maxConcurrent, 1);
assert.equal(landed.at(-1), 'c');
console.log('READER_AUDIO_CORE_SMOKE=PASS');
