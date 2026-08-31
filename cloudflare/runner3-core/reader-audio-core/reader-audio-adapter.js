import { AudioController } from './audio-controller.js';
import { PositionMapper } from './position-mapper.js';
import { ReaderFollower } from './reader-follower.js';
import { PlaybackQueue } from './playback-queue.js';

const defined = (input = {}) => Object.fromEntries(Object.entries(input).filter(([, value]) => value !== undefined));

export class ReaderAudioAdapter {
  constructor({
    audio,
    loadState,
    saveState,
    displayCfi,
    isVisible,
    highlight,
    clearHighlight,
    resolveNextReadable,
    prepareNext,
    activateChapter,
    continuous = true,
    prefetchOnMount = true,
    prefetchAfterAdvance = true,
    onState,
    onTarget,
  } = {}) {
    if (!audio) throw new Error('ReaderAudioAdapter requires audio');
    this.audio = audio;
    this.continuous = Boolean(continuous);
    this.prefetchOnMount = Boolean(prefetchOnMount);
    this.onState = onState;
    this.onTarget = onTarget;
    this.activateChapter = activateChapter;
    this.mapper = new PositionMapper();
    this.follower = new ReaderFollower({ displayCfi, isVisible, highlight, clearHighlight });
    this.queue = new PlaybackQueue({
      resolveNextReadable,
      prepare: prepareNext,
      activate: (next, options) => this.#activatePrepared(next, options),
      prefetchAfterAdvance,
    });
    this.controller = new AudioController({
      audio,
      loadState,
      saveState: (state) => {
        saveState?.(state);
        this.onState?.(state);
      },
      onTick: (state, meta) => this.#syncMappedTarget(state, meta),
      onEnded: (state) => this.#handleEnded(state),
    });
  }

  bind() {
    this.controller.bind();
    return this;
  }

  setSegments(segments = []) {
    this.mapper.setSegments(segments);
    return this;
  }

  async mount(context = {}) {
    this.bind();
    if (context.segments) this.setSegments(context.segments);
    const restoreContext = defined({
      bookKey: context.bookKey,
      chapter: context.chapter,
      mediaId: context.mediaId,
      time: context.time,
      cfi: context.cfi,
      playbackRate: context.playbackRate,
      playingIntent: context.playingIntent,
    });
    const state = this.controller.restore(restoreContext);
    this.controller.setMedia(defined({
      src: context.src,
      mediaId: state.mediaId || context.mediaId,
      chapter: state.chapter || context.chapter,
      cfi: state.cfi || context.cfi,
      time: state.time,
    }));
    await this.#syncMappedTarget(this.controller.snapshot(), { force: true });
    if (this.prefetchOnMount && state.chapter) this.queue.prefetch(state.chapter).catch(() => {});
    if (state.playingIntent && context.autoplay !== false) await this.controller.play();
    return this.snapshot();
  }

  async play() {
    return this.controller.play();
  }

  pause() {
    return this.controller.pause();
  }

  setRate(rate) {
    return this.controller.setRate(rate);
  }

  async seek(time) {
    const target = this.mapper.at(time);
    const state = this.controller.seek(time, { cfi: target?.cfi });
    if (target) await this.follower.follow(target, { force: true });
    return state;
  }

  async navigate(cfi, { time, target } = {}) {
    const manualTarget = target || { cfi: String(cfi || '') };
    if (!manualTarget.cfi) return false;
    this.controller.setPosition({ time, cfi: manualTarget.cfi });
    await this.follower.follow(manualTarget, { force: true });
    return true;
  }

  prefetchNext() {
    return this.queue.prefetch(this.controller.snapshot().chapter);
  }

  advance({ autoplay = true } = {}) {
    return this.queue.advance(this.controller.snapshot().chapter, { autoplay });
  }

  setContinuous(enabled) {
    this.continuous = Boolean(enabled);
  }

  persist() {
    this.controller.persist();
    return this.snapshot();
  }

  snapshot() {
    return this.controller.snapshot();
  }

  destroy() {
    this.controller.destroy();
  }

  async #syncMappedTarget(state, { force = false } = {}) {
    const target = this.mapper.at(state.time);
    if (!target) return null;
    this.controller.setPosition({ time: state.time, cfi: target.cfi }, { persist: false });
    this.onTarget?.(target, this.controller.snapshot());
    await this.follower.follow(target, { force });
    return target;
  }

  async #handleEnded(state) {
    if (!this.continuous) return false;
    const next = await this.queue.advance(state.chapter, { autoplay: true });
    return Boolean(next);
  }

  async #activatePrepared(next, { autoplay = true } = {}) {
    const activated = (await this.activateChapter?.(next, { autoplay: false })) || next;
    if (activated.segments) this.setSegments(activated.segments);
    const state = this.controller.setMedia(defined({
      src: activated.src,
      mediaId: activated.mediaId,
      chapter: activated.chapter || activated.id,
      cfi: activated.cfi,
      time: activated.time ?? 0,
    }));
    await this.#syncMappedTarget(state, { force: true });
    if (autoplay) await this.controller.play();
    return activated;
  }
}
