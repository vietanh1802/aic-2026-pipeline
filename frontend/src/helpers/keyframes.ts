/**
 * The real keyframe index, bound to the lookup in keyframeIndex.ts.
 *
 * The one module that imports the multi-megabyte JSON, so a unit test can use
 * the pure functions without pulling it in.
 */
import INDEX from "../mapping/keyframe_index.json";
import {
  nearestKeyframe,
  neighbourKeyframes,
  type Keyframe,
  type KeyframeIndex,
} from "./keyframeIndex";
import { spreadTrakeSlots, type SpreadPick } from "./trakeSpread";

const KEYFRAMES = INDEX as unknown as KeyframeIndex;

export function nearestKeyframeFor(
  video: string,
  frameIdx: number
): Keyframe | null {
  return nearestKeyframe(video, frameIdx, KEYFRAMES);
}

export function neighbourKeyframesFor(
  video: string,
  frameIdx: number
): { smaller: Keyframe | null; larger: Keyframe | null } {
  return neighbourKeyframes(video, frameIdx, KEYFRAMES);
}

export { KEYFRAMES };

export function spreadTrakeSlotsFor(
  video: string,
  min: number,
  max: number,
  n: number
): SpreadPick[] {
  return spreadTrakeSlots(video, min, max, n, KEYFRAMES);
}
