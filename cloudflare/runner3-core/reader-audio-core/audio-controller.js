import { normalizePlaybackState } from './state-contract.js';

export class AudioController {
  constructor({ audio, loadState, saveState, onTick, onEnded, persistIntervalMs = 1000 } = {}) {
    if (!audio) throw new Error('AudioController requires audio');
    this.audio = audio;
    this.loadState = loadState;
    this.saveState = saveState;
    this.onTick = onTick;
    this.onEnded = onEnded;
    this.persistIntervalMs = Math.max(250, Number(persistIntervalMs) || 1000);
    this.lastClockPersistAt = 0;
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

  applyPlaybackRate() {
    const playbackRate = normalizePlaybackState({ playbackRate: this.state.playbackRate }).playbackRate;
    try { this.audio.defaultPlaybackRate = playbackRate; } catch {}
    try { this.audio.playbackRate = playbackRate; } catch {}
    this.state.playbackRate = playbackRate;
    return playbackRate;
  }

  restore(context = {}) {
    const saved = normalizePlaybackState(this.loadState?.() || {});
    const definedContext = Object.fromEntries(Object.entries(context).filter(([, value]) => value !== undefined));
    this.state = normalizePlaybackState({ ...saved, ...definedContext });
    this.applyPlaybackRate();
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
    this.applyPlaybackRate();
    this.persist();
    return this.snapshot();
  }

  setPosition({ time, cfi } = {}, { persist = true } = {}) {
    if (Number.isFinite(Number(time))) this.state.time = Math.max(0, Number(time));
    if (cfi !== undefined) this.state.cfi = String(cfi || '');
    if (persist) this.persist();
    return this.snapshot();
  }

  async waitUntilReady(timeoutMs = 5000) {
    if (this.audio.readyState >= 1) return true;
    try { this.audio.load?.(); } catch {}
    return await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (ok, error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.audio.removeEventListener('loadedmetadata', onReady);
        this.audio.removeEventListener('canplay', onReady);
        this.audio.removeEventListener('error', onError);
        if (ok) resolve(true);
        else reject(error || new Error('AUDIO_MEDIA_NOT_READY'));
      };
      const onReady = () => finish(true);
      const onError = () => finish(false, this.audio.error || new Error('AUDIO_MEDIA_ERROR'));
      const timer = setTimeout(() => finish(false, new Error('AUDIO_MEDIA_READY_TIMEOUT')), Math.max(250, Number(timeoutMs) || 5000));
      this.audio.addEventListener('loadedmetadata', onReady, { once: true });
      this.audio.addEventListener('canplay', onReady, { once: true });
      this.audio.addEventListener('error', onError, { once: true });
    });
  }

  async play() {
    this.bind();
    this.state.playingIntent = true;
    this.persist();
    try {
      await this.waitUntilReady();
      this.applyPlaybackRate();
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
    this.state.playbackRate = playbackRate;
    this.applyPlaybackRate();
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
    this.lastClockPersistAt = Date.now();
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
    const now = Date.now();
    if (force || now - this.lastClockPersistAt >= this.persistIntervalMs) {
      this.lastClockPersistAt = now;
      this.persist();
    }
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
