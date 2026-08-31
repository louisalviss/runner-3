import assert from 'node:assert/strict';
import { DomSegmentBuilder, PositionMapper } from './index.js';

const blocks = [
  { textContent: 'Xin chào thế giới' },
  { textContent: 'Đây là đoạn thứ hai' },
  { textContent: 'Kết thúc chương' },
];
const words = [
  { text: 'Xin', startMs: 0, durationMs: 100 },
  { text: 'chào', startMs: 120, durationMs: 100 },
  { text: 'thế', startMs: 240, durationMs: 100 },
  { text: 'giới', startMs: 360, durationMs: 100 },
  { text: 'Đây', startMs: 600, durationMs: 100 },
  { text: 'là', startMs: 720, durationMs: 100 },
  { text: 'đoạn', startMs: 840, durationMs: 100 },
  { text: 'thứ', startMs: 960, durationMs: 100 },
  { text: 'hai', startMs: 1080, durationMs: 100 },
  { text: 'Kết', startMs: 1400, durationMs: 100 },
  { text: 'thúc', startMs: 1520, durationMs: 100 },
  { text: 'chương', startMs: 1640, durationMs: 100 },
];

const built = new DomSegmentBuilder({ minCoverage: 0.9 }).build({
  timingWords: words,
  blocks,
  cfiFromNode: (node) => `cfi-${blocks.indexOf(node)}`,
});
assert.equal(built.segments.length, 3);
assert.equal(built.coverage, 1);
assert.equal(built.segments[0].cfi, 'cfi-0');
assert.equal(built.segments[1].start, 0.6);
assert.equal(built.segments[2].cfi, 'cfi-2');
assert.equal(built.nodeByCfi.get('cfi-1'), blocks[1]);

const mapper = new PositionMapper(built.segments);
assert.equal(mapper.at(0.3).cfi, 'cfi-0');
assert.equal(mapper.at(0.9).cfi, 'cfi-1');
assert.equal(mapper.at(1.7).cfi, 'cfi-2');
console.log('READER_AUDIO_DOM_SEGMENT_BUILDER_SMOKE=PASS');
