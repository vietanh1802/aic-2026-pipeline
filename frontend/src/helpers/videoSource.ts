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

/**
 * Where keyframe stills come from.
 *
 * Not the API base. In the deployed setup the API answers on
 * https://aic-api.umaga.fun while the images live on
 * https://aic-frames.umaga.fun — `AIC_IMAGE_BASE_URL` in docker-compose.yml,
 * mirrored here so the client composes the same URL the backend does. The
 * default matches preprocess.py's: the API's own /static mount, which is what
 * `npm run dev` proxies.
 */
const IMAGE_BASE_URL =
  env?.VITE_IMAGE_BASE_URL ??
  `${env?.VITE_API_BASE_URL ?? "http://localhost:8000"}/static`;

/**
 * The composition rule, separated from the configuration so it can be tested.
 *
 * Both mappings were checked when the images were seeded: a single flat
 * `images/` prefix, no subdirectories, so name → path needs no lookup table.
 */
export function buildKeyframeUrl(base: string, name: string): string {
  if (!name) {
    return "";
  }
  const file = name.endsWith(".jpg") ? name : `${name}.jpg`;
  return `${base.replace(/\/+$/, "")}/images/${file}`;
}

/** The image for a keyframe basename, e.g. "L25_V085-0086-30870". */
export function keyframeUrl(name: string): string {
  return buildKeyframeUrl(IMAGE_BASE_URL, name);
}
