/**
 * The frame a KIS or Q&A answer submits, given a marked interval on the video.
 *
 * The rules put the accepted answer inside a window `[s, e]` around the moment
 * itself, so the useful thing to pin while scrubbing is not one instant but the
 * two edges of the moment — the last frame before it and the first frame after.
 * The midpoint of those two is the best single guess the pair supports.
 *
 * Each edge is floored to a frame before averaging, not averaged in seconds,
 * so marking both edges at the same instant reproduces the old behaviour
 * exactly: `Math.floor(t * fps)`, the number this form has always submitted.
 */
export interface FrameRange {
  start: number;
  end: number;
  /** What goes in the CSV. */
  frame: number;
}

/**
 * Returns null when the video's fps is unknown, which happens for a video
 * missing from fps_map.json. Submitting was silently sending NaN in that case;
 * a null here lets the form disable the button and say so instead.
 */
export function frameRange(
  startSeconds: number,
  endSeconds: number,
  fps: number
): FrameRange | null {
  if (!Number.isFinite(fps) || fps <= 0) {
    return null;
  }
  if (!Number.isFinite(startSeconds) || !Number.isFinite(endSeconds)) {
    return null;
  }

  // Marking the end before the start is a normal thing to do while scrubbing
  // backwards. It describes the same interval, so read it as one.
  const low = Math.max(0, Math.min(startSeconds, endSeconds));
  const high = Math.max(0, Math.max(startSeconds, endSeconds));

  const start = Math.floor(low * fps);
  const end = Math.floor(high * fps);
  return { start, end, frame: Math.floor((start + end) / 2) };
}
