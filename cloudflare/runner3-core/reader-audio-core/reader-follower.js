export class ReaderFollower {
  constructor({ displayCfi, isVisible, highlight, clearHighlight } = {}) {
    this.displayCfi = displayCfi;
    this.isVisible = isVisible;
    this.highlight = highlight;
    this.clearHighlight = clearHighlight;
    this.inFlight = null;
    this.pending = null;
  }

  async follow(target, { force = false } = {}) {
    if (!target || !target.cfi) return false;
    this.pending = { target, force };
    if (this.inFlight) return this.inFlight;
    this.inFlight = this.#drain();
    try {
      return await this.inFlight;
    } finally {
      this.inFlight = null;
    }
  }

  async #drain() {
    let moved = false;
    while (this.pending) {
      const job = this.pending;
      this.pending = null;
      this.clearHighlight?.();
      this.highlight?.(job.target);
      const visible = job.force ? false : Boolean(await this.isVisible?.(job.target));
      if (!visible && this.displayCfi) {
        await this.displayCfi(job.target.cfi, { animate: false });
        moved = true;
      }
    }
    return moved;
  }
}
