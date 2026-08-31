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
  }

  bind() {
    if (this.bound) return;
    this.bound = true;
    this.audio.addEventListener('play', () => {
      this.state.playingIntent = true;
      this.persist();
      this.startClock();
    });
    this.audio.addEventListener('pause', () => {
      if (!this.audio.ended) this.state.playingIntent = false;
      this.persist();
      this.stopClock();
    });
    this.audio.addEventListener('ratechange', () => {
      this.state.playbackRate = this.audio.playbackRate || 1;
      this.persist();
    });
    this.audio.addEventListener('seeked', () => this.tick(true));
    this.audio.addEventListener('ended', async () => {
      this.stopClock();
      this.state.playingIntent = true;
      this.persist();
      await this.onEnded?.(this.snapshot());
    });
  }

  restore(context = {}) {
    const saved = normalizePlaybackState(this.loadState?.() || {});
    this.state = normalizePlaybackState({ ...saved, ...context });
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

  setMedia({ src, mediaId, chapter, cfi, time = 0 } = {}) {
    if (src && this.audio.src !== src) this.audio.src = src;
    this.state = normalizePlaybackState({ ...this.state, mediaId, chapter, cfi, time });
    this.persist();
  }

  setPosition({ time, cfi } = {}) {
    if (Number.isFinite(Number(time))) this.state.time = Math.max(0, Number(time));
    if (cfi) this.state.cfi = String(cfi);
    this.persist();
  }

  startClock() {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(false), 75);
  }

  stopClock() {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null;
  }

  tick(force = false) {
    this.state.time = Math.max(0, Number(this.audio.currentTime) || 0);
    this.state.playbackRate = Number(this.audio.playbackRate) || 1;
    this.onTick?.(this.snapshot(), { force });
  }

  persist() {
    this.saveState?.(this.snapshot());
  }

  snapshot() {
    return normalizePlaybackState(this.state);
  }
}
