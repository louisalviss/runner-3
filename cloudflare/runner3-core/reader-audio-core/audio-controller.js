import { normalizePlaybackState } from './state-contract.js';

export class AudioController {
  constructor({ audio, loadState, saveState, onTick, onEnded } = {}) {
    if (!audio) throw new Error('AudioController requires audio');
    this.audio = audio;
    this.loadState = loadState;
    this.saveState = saveState;
    this.onTick = onTick;
    this.onEnded = onEnded;
    this.timer = null;
    this.state = normalizePlaybackState();
    this.bound = false;
    this.listeners = [];
  }

  bind() {
    if (this.bound) return this;
    this.bound = true;
    const on = (type, handler) => {
      this.audio.addEventListener(type, handler);
      this.listeners.push([type, handler]);
    };

    on('play', () => {
      this.state.playingIntent = true;
      this.persist();
      this.startClock();
    });
    on('pause', () => {
      if (!this.audio.ended) this.state.playingIntent = false;
      this.persist();
      this.stopClock();
    });
    on('ratechange', () => {
      this.state.playbackRate = normalizePlaybackState({ playbackRate: this.audio.playbackRate }).playbackRate;
      this.persist();
    });
    on('seeked', () => {
      this.tick(true);
      this.persist();
    });
    on('ended', async () => {
      this.stopClock();
      this.state.playingIntent = true;
      this.persist();
      const advanced = await this.onEnded?.(this.snapshot());
      if (!advanced) {
        this.state.playingIntent = false;
        this.persist();
      }
    });
    return this;
  }

  restore(context = {}) {
    const saved = normalizePlaybackState(this.loadState?.() || {});
    const definedContext = Object.fromEntries(Object.entries(context).filter(([, value]) => value !== undefined));
    this.state = normalizePlaybackState({ ...saved, ...definedContext });
    if (this.state.playbackRate) this.audio.playbackRate = this.state.playbackRate;
    if (this.state.time > 0) {
      const apply = () => {
        try { this.audio.currentTime = this.state.time; } catch {}
      };
      if (this.audio.readyState >= 1) apply();
      else this.audio.addEventListener('loadedmetadata', apply, { once: true });
    }
    return this.snapshot();
  }

  setMedia({ src, mediaId, chapter, cfi, time } = {}) {
    if (src && this.audio.src !== src) this.audio.src = src;
    const next = { ...this.state };
    if (mediaId !== undefined) next.mediaId = mediaId;
    if (chapter !== undefined) next.chapter = chapter;
    if (cfi !== undefined) next.cfi = cfi;
    if (time !== undefined) next.time = time;
    this.state = normalizePlaybackState(next);
    this.persist();
    return this.snapshot();
  }

  setPosition({ time, cfi } = {}, { persist = true } = {}) {
    if (Number.isFinite(Number(time))) this.state.time = Math.max(0, Number(time));
    if (cfi !== undefined) this.state.cfi = String(cfi || '');
    if (persist) this.persist();
    return this.snapshot();
  }

  async play() {
    this.bind();
    this.state.playingIntent = true;
    this.persist();
    try {
      await this.audio.play();
    } catch (error) {
      this.state.playingIntent = false;
      this.persist();
      throw error;
    }
    return this.snapshot();
  }

  pause() {
    this.audio.pause();
    if (this.audio.paused) {
      this.state.playingIntent = false;
      this.persist();
      this.stopClock();
    }
    return this.snapshot();
  }

  setRate(rate) {
    const playbackRate = normalizePlaybackState({ playbackRate: rate }).playbackRate;
    this.audio.playbackRate = playbackRate;
    this.state.playbackRate = playbackRate;
    this.persist();
    return this.snapshot();
  }

  seek(time, { cfi } = {}) {
    const nextTime = Math.max(0, Number(time) || 0);
    try { this.audio.currentTime = nextTime; } catch {}
    this.state.time = nextTime;
    if (cfi !== undefined) this.state.cfi = String(cfi || '');
    this.tick(true);
    this.persist();
    return this.snapshot();
  }

  startClock() {
    if (this.timer) return this.timer;
    this.timer = setInterval(() => this.tick(false), 75);
    return this.timer;
  }

  stopClock() {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null;
  }

  tick(force = false) {
    this.state.time = Math.max(0, Number(this.audio.currentTime) || 0);
    this.state.playbackRate = normalizePlaybackState({ playbackRate: this.audio.playbackRate }).playbackRate;
    this.onTick?.(this.snapshot(), { force });
    return this.snapshot();
  }

  persist() {
    this.saveState?.(this.snapshot());
  }

  snapshot() {
    return normalizePlaybackState(this.state);
  }

  destroy() {
    this.stopClock();
    for (const [type, handler] of this.listeners) this.audio.removeEventListener(type, handler);
    this.listeners = [];
    this.bound = false;
  }
}
