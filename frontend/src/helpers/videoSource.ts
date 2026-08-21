const env = (import.meta as { env?: Record<string, string | undefined> }).env;

/** The only video store. Empty in local dev, which disables playback there. */
const VIDEO_BASE_URL = env?.VITE_VIDEO_BASE_URL ?? "";

/**
 * Where a video plays from. Empty string when the store is not configured, so
 * callers can tell "no video here" apart from a broken URL.
 *
 * All 1,478 files are remuxed with `-movflags +faststart`, so the moov atom
 * sits ahead of the media data and a seek costs one range request. That is what
 * makes jumping straight to a frame cheap enough to do from a list.
 */
export function videoUrl(videoId: string): string {
  if (!VIDEO_BASE_URL || !videoId) {
    return "";
  }
  return `${VIDEO_BASE_URL.replace(/\/$/, "")}/${videoId}.mp4`;
}

/**
 * The same URL with a media fragment, so the browser opens at that second
 * instead of at zero and then seeking.
 */
export function videoUrlAt(videoId: string, seconds: number): string {
  const url = videoUrl(videoId);
  if (!url || !Number.isFinite(seconds) || seconds <= 0) {
    return url;
  }
  return `${url}#t=${seconds.toFixed(2)}`;
}
