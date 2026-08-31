export class PositionMapper {
  constructor(segments = []) {
    this.setSegments(segments);
  }

  setSegments(segments = []) {
    this.segments = Array.isArray(segments)
      ? segments
          .map((x, i) => ({
            index: Number.isFinite(Number(x.index)) ? Number(x.index) : i,
            start: Math.max(0, Number(x.start) || 0),
            end: Math.max(0, Number(x.end) || 0),
            cfi: String(x.cfi || ""),
            token: x.token == null ? "" : String(x.token),
          }))
          .filter((x) => x.end >= x.start)
          .sort((a, b) => a.start - b.start || a.index - b.index)
      : [];
  }

  at(time) {
    const t = Math.max(0, Number(time) || 0);
    if (!this.segments.length) return null;
    let lo = 0;
    let hi = this.segments.length - 1;
    let best = this.segments[0];
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const cur = this.segments[mid];
      if (cur.start <= t) {
        best = cur;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return best;
  }
}
