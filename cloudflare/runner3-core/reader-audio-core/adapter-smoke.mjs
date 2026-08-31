import assert from 'node:assert/strict';
import { ReaderAudioAdapter } from './reader-audio-adapter.js';

class FakeAudio extends EventTarget {
  constructor() {
    super();
    this.paused = true;
    this.ended = false;
    this.readyState = 1;
    this.currentTime = 0;
    this._src = '';
    this._playbackRate = 1;
    this.defaultPlaybackRate = 1;
  }
  get src() { return this._src; }
  set src(value) {
    this._src = String(value || '');
    // Model the browser behavior that exposed the live E2E regression:
    // selecting a new resource can drop the active playback rate.
    this._playbackRate = 1;
  }
  get playbackRate() { return this._playbackRate; }
  set playbackRate(value) {
    this._playbackRate = Number(value) || 1;
    this.dispatchEvent(new Event('ratechange'));
  }
  async play() {
    this.paused = false;
    this.ended = false;
    this.dispatchEvent(new Event('play'));
  }
  pause() {
    this.paused = true;
    this.dispatchEvent(new Event('pause'));
  }
  end() {
    this.paused = true;
    this.ended = true;
    this.dispatchEvent(new Event('ended'));
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const audio = new FakeAudio();
let persisted = {
  bookKey: 'book-1',
  chapter: '1',
  mediaId: 'm1',
  time: 1.25,
  cfi: 'b',
  playbackRate: 2,
  playingIntent: false,
};
const saves = [];
const landed = [];
let concurrent = 0;
let maxConcurrent = 0;

const segments1 = [
  { start: 0, end: 1, cfi: 'a', token: 'A' },
  { start: 1, end: 2, cfi: 'b', token: 'B' },
  { start: 2, end: 3, cfi: 'c', token: 'C' },
];
const segments2 = [{ start: 0, end: 3, cfi: 'd', token: 'D' }];

const adapter = new ReaderAudioAdapter({
  audio,
  loadState: () => persisted,
  saveState: (state) => {
    persisted = state;
    saves.push(state);
  },
  isVisible: async () => false,
  displayCfi: async (cfi, options) => {
    concurrent += 1;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    await sleep(12);
    landed.push({ cfi, options });
    concurrent -= 1;
  },
  resolveNextReadable: async (chapter) => chapter === '1'
    ? { chapter: '2', mediaId: 'm2', src: 'two.mp3', segments: segments2, time: 0 }
    : null,
  prepareNext: async (next) => ({ ...next, prepared: true }),
  activateChapter: async (next) => next,
});

await adapter.mount({
  bookKey: 'book-1',
  chapter: '1',
  mediaId: 'm1',
  src: 'one.mp3',
  segments: segments1,
});
assert.equal(audio.currentTime, 1.25);
assert.equal(audio.playbackRate, 2, 'saved playback rate was lost when src changed');
assert.equal(audio.defaultPlaybackRate, 2, 'default playback rate did not follow canonical state');
assert.equal(adapter.snapshot().cfi, 'b');
assert.equal(landed.at(-1).cfi, 'b');
assert.equal(landed.at(-1).options.animate, false);

await adapter.play();
const clock = adapter.controller.timer;
assert.ok(clock, '75ms playback clock did not start');
assert.equal(adapter.controller.startClock(), clock, 'duplicate playback clock created');
adapter.setRate(2.5);
assert.equal(audio.playbackRate, 2.5);
assert.equal(audio.defaultPlaybackRate, 2.5);
assert.equal(adapter.snapshot().playbackRate, 2.5);

await adapter.seek(2.4);
assert.equal(audio.currentTime, 2.4);
assert.equal(adapter.snapshot().cfi, 'c');
assert.equal(landed.at(-1).cfi, 'c');

const autoFollow = adapter.follower.follow({ cfi: 'b' }, { force: true });
await sleep(1);
const manualFollow = adapter.navigate('manual-cfi');
await Promise.all([autoFollow, manualFollow]);
assert.equal(maxConcurrent, 1, 'Reader navigation overlapped');
assert.equal(landed.at(-1).cfi, 'manual-cfi', 'manual navigation did not win latest-target race');
assert.equal(adapter.snapshot().cfi, 'manual-cfi');

const prefetched = await adapter.prefetchNext();
assert.equal(prefetched.chapter, '2');
assert.equal(prefetched.prepared, true);
audio.end();
await sleep(35);
assert.equal(adapter.snapshot().chapter, '2');
assert.equal(adapter.snapshot().mediaId, 'm2');
assert.equal(audio.src, 'two.mp3');
assert.equal(audio.playbackRate, 2.5, 'chapter media swap lost playback rate');
assert.equal(adapter.snapshot().cfi, 'd');
assert.equal(adapter.snapshot().playingIntent, true);
assert.equal(audio.paused, false);
assert.equal(landed.at(-1).cfi, 'd');

adapter.pause();
assert.equal(adapter.snapshot().playingIntent, false);
assert.equal(adapter.controller.timer, null);
assert.ok(saves.length > 0);
adapter.destroy();

const finalAudio = new FakeAudio();
let finalState = {};
const finalAdapter = new ReaderAudioAdapter({
  audio: finalAudio,
  loadState: () => ({}),
  saveState: (state) => { finalState = state; },
  resolveNextReadable: async () => null,
});
await finalAdapter.mount({ bookKey: 'book-2', chapter: 'last', mediaId: 'last-media' });
await finalAdapter.play();
finalAudio.end();
await sleep(20);
assert.equal(finalState.playingIntent, false, 'ended state stayed playing when queue was exhausted');
finalAdapter.destroy();

console.log('READER_AUDIO_ADAPTER_SMOKE=PASS');
