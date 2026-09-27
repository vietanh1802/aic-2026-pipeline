/**
 * Filling all N slots of a TRAKE line in one press.
 *
 * The DP picks each event independently and sometimes bunches several of them
 * on the same second, or drops one on the wrong side of the action. Starting
 * from N moments spread evenly across the span the candidates cover is a
 * better place to correct from than starting from that.
 *
 * Positions are snapped to real keyframes so each cell has a still to judge by;
 * a video with no keyframe there falls back to the raw frame, which the card
 * already renders as a hand-pinned moment.
 */
import { nearestKeyframe, type KeyframeIndex } from "./keyframeIndex";

/** N positions from min to max inclusive, both ends on the ends. */
export function evenPositions(min: number, max: number, n: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || n <= 0) {
    return [];
  }
  const low = Math.min(min, max);
  const high = Math.max(min, max);
  if (n === 1) {
    return [low];
  }
  return Array.from({ length: n }, (_, index) =>
    Math.round(low + (index * (high - low)) / (n - 1))
  );
}

export interface SpreadPick {
  frameIdx: number;
  name: string;
  /** True when no keyframe was near enough to name, so there is no still. */
  byHand: boolean;
}

export function spreadTrakeSlots(
  video: string,
  min: number,
  max: number,
  n: number,
  index: KeyframeIndex
): SpreadPick[] {
  return evenPositions(min, max, n).map((position) => {
    const keyframe = nearestKeyframe(video, position, index);
    if (!keyframe) {
      // Same shape App.tsx uses when a moment is scrubbed to by hand.
      return {
        frameIdx: position,
        name: `${video} · frame ${position}`,
        byHand: true,
      };
    }
    return { frameIdx: keyframe.frameIdx, name: keyframe.name, byHand: false };
  });
}
