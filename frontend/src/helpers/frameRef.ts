// frontend/src/helpers/frameRef.ts

/**
 * Reading "which frame do you mean" out of whatever a teammate pasted.
 *
 * Three things get pasted in practice: a video and a frame with a space
 * between them, the same with a dash, and a whole keyframe filename copied off
 * a result tile. All three are the video id followed by one or two numbers, so
 * they parse as one rule rather than three.
 */
// Old acceptance, kept for the record: only the L and K batches, underscore only.
// const VIDEO = /^[LK]\d{2}_V\d{3}/;

/**
 * What a video id looks like: one batch letter, two or three digits, an
 * underscore OR a hyphen, then V and three digits. Old ids (L26_V194, K01_V003)
 * still match; new batches look like M01_V001, N001-V001 or S01-V001.
 *
 * Only accepted here, never normalised: the id stays exactly as written
 * because it is the key into fps_map.json and the video store, and rewriting
 * "N001-V001" to "N001_V001" would silently look up a video that is not there.
 * Case-sensitive on purpose, as before: "l01_v001" is a typo, not a video.
 *
 * The single source for every parser in the frontend. A wider or narrower
 * batch scheme is changed here and nowhere else.
 */
const VIDEO_ID_CORE = "[A-Z]\\d{2,3}[_-]V\\d{3}";
/** A whole string that is one video id. */
export const VIDEO_ID_PATTERN = new RegExp(`^${VIDEO_ID_CORE}$`);
/** A video id at the START of a string, captured; what follows is ignored. */
export const VIDEO_ID_PREFIX = new RegExp(`^(${VIDEO_ID_CORE})`);

export interface FrameRef {
  videoId: string;
  frameIdx: number;
}

/** Null for anything that is not one of the three forms. */
export function parseFrameRef(input: string): FrameRef | null {
  // A fractional frame is a mistake, not a rounding job, so strip only a real
  // file extension: letters, not digits.
  const text = input.trim().replace(/\.[a-z]+$/i, "");
  const match = VIDEO_ID_PREFIX.exec(text);
  if (!match) {
    return null;
  }
  const videoId = match[0];

  const rest = text.slice(videoId.length).replace(/^[\s\-_]+/, "");
  const parts = rest.split(/[\s\-_]+/).filter((part) => part !== "");
  // One number is the frame; two are scene and frame, and the frame is the one
  // that matters. Three would be a filename shape nobody writes.
  if (parts.length === 0 || parts.length > 2) {
    return null;
  }
  if (!parts.every((part) => /^\d+$/.test(part))) {
    return null;
  }

  return { videoId, frameIdx: Number(parts[parts.length - 1]) };
}

/** A keyframe filename taken apart. */
export interface ParsedFrameName {
  videoId: string;
  /**
   * "scene-frame" exactly as written, zero padding kept ("0012-004707"): the
   * popup shows it as the frame id, and 0012-004707 is not 0012-4707.
   */
  frameId: string;
  sceneId: number;
  frameIdx: number;
}

/**
 * Takes a keyframe name apart READING FROM THE RIGHT: the last two
 * hyphen-separated parts are the scene and the frame, everything before them is
 * the video id.
 *
 * From the left is what this replaces ("split on the first hyphen"), which only
 * works while a video id contains no hyphen: N001-V001-0012-345.jpg would come
 * out as video "N001". Reading from the right does not care what the id looks
 * like, and the id is then checked against VIDEO_ID_PATTERN.
 *
 * A directory part ("/static/images/") and a letters-only extension are
 * dropped; digits are never taken for an extension, since "36128" ends a name.
 * Null for anything that is not a frame name, so the caller decides the
 * fallback instead of getting a half-parsed guess.
 */
export function parseFrameName(name: string): ParsedFrameName | null {
  const base = name.trim().split(/[\\/]/).pop() ?? "";
  const parts = base.replace(/\.[A-Za-z]+$/, "").split("-");
  if (parts.length < 3) {
    return null;
  }
  const scene = parts[parts.length - 2];
  const frame = parts[parts.length - 1];
  if (!/^\d+$/.test(scene) || !/^\d+$/.test(frame)) {
    return null;
  }
  const videoId = parts.slice(0, -2).join("-");
  if (!VIDEO_ID_PATTERN.test(videoId)) {
    return null;
  }
  return {
    videoId,
    frameId: `${scene}-${frame}`,
    sceneId: Number(scene),
    frameIdx: Number(frame),
  };
}
