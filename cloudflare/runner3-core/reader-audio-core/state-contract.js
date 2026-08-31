// Canonical persisted playback state contract for Reader Audio Core.
export function normalizePlaybackState(input = {}) {
  const out = {
    bookKey: String(input.bookKey || ""),
    chapter: String(input.chapter || ""),
    mediaId: String(input.mediaId || ""),
    time: Number.isFinite(Number(input.time)) ? Math.max(0, Number(input.time)) : 0,
    cfi: String(input.cfi || ""),
    playbackRate: Number.isFinite(Number(input.playbackRate)) ? Math.min(4, Math.max(0.5, Number(input.playbackRate))) : 1,
    playingIntent: Boolean(input.playingIntent),
  };
  return out;
}

export const PLAYBACK_STATE_VERSION = 1;
