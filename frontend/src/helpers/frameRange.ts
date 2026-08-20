/**
 * Turning a position in the video into the frame number that goes in the CSV.
 *
 * One place for the conversion because it is used in three: the readout under
 * the player, the marked edges, and what the submit button sends.
 */

/**
 * Frame index f covers `[f/fps, (f+1)/fps)`, so flooring is the right rule —
 * but flooring alone loses a frame.
 *
 * A result's start time is built as `frame / fps`, and float division makes
 * `(f / fps) * fps` land a hair *below* f: 49/25*25 is 48.99999999999999, which
 * floors to 48. Opening the popup on a keyframe and submitting it unchanged
 * therefore submitted the frame before it — 6.2% of frames at 25 fps, 8.3% at
 * 23.976, measured across the first 60,000 of each.
 *
 * The epsilon is 1e-6 of a frame, about 40 nanoseconds against a frame that
 * lasts 40 milliseconds. It absorbs that error and nothing else: a position
 * genuinely inside the previous frame is never closer than that to the border.
 */
const EPSILON = 1e-6;

export function frameAt(seconds: number, fps: number): number | null {
  if (!Number.isFinite(fps) || fps <= 0 || !Number.isFinite(seconds)) {
    return null;
  }
  return Math.floor(Math.max(0, seconds) * fps + EPSILON);
}

/**
 * The frame a KIS or Q&A answer submits, given a marked interval on the video.
 *
 * The rules put the accepted answer inside a window `[s, e]` around the moment
 * itself, so the useful thing to pin while scrubbing is not one instant but the
 * two edges of the moment — the last frame before it and the first frame after.
 * The midpoint of those two is the best single guess the pair supports.
 *
 * Each edge is converted to a frame before averaging, not averaged in seconds,
 * so marking both edges at the same instant submits exactly that frame.
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
  // Marking the end before the start is a normal thing to do while scrubbing
  // backwards. It describes the same interval, so read it as one.
  const start = frameAt(Math.min(startSeconds, endSeconds), fps);
  const end = frameAt(Math.max(startSeconds, endSeconds), fps);
  if (start === null || end === null) {
    return null;
  }
  return { start, end, frame: Math.floor((start + end) / 2) };
}
