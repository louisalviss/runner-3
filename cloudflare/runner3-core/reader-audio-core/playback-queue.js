export class PlaybackQueue {
  constructor({ resolveNextReadable, prepare, activate } = {}) {
    this.resolveNextReadable = resolveNextReadable;
    this.prepare = prepare;
    this.activate = activate;
    this.next = null;
    this.preparing = null;
  }

  async prefetch(currentChapter) {
    if (this.preparing) return this.preparing;
    this.preparing = (async () => {
      const next = await this.resolveNextReadable?.(currentChapter);
      if (!next) return null;
      const prepared = await this.prepare?.(next);
      this.next = prepared || next;
      return this.next;
    })();
    try {
      return await this.preparing;
    } finally {
      this.preparing = null;
    }
  }

  async advance(currentChapter, { autoplay = true } = {}) {
    const next = this.next || await this.prefetch(currentChapter);
    this.next = null;
    if (!next) return null;
    await this.activate?.(next, { autoplay });
    this.prefetch(next.chapter || next.id).catch(() => {});
    return next;
  }
}
