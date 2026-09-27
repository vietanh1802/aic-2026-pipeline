/**
 * Finding the keyframe nearest a frame number, and naming its image file.
 *
 * The index is passed in rather than imported, for two reasons: the real one
 * is several megabytes and has no business inside a unit test, and TRAKE's
 * even-spread needs the same arithmetic against a fixture.
 *
 * Built by scripts/build_keyframe_index.py. The pairs of one video are sorted
 * by frame index, which is what makes the binary search below legal.
 */

/** `[frame_idx, scene_id]`. */
export type KeyframePair = [number, number];

export type KeyframeIndex = Record<string, KeyframePair[]>;

export interface Keyframe {
  video: string;
  frameIdx: number;
  sceneId: number;
  /** Image basename without the extension: "L25_V085-0086-30870". */
  name: string;
}

/**
 * The filename the images were seeded under: video, scene id padded to four
 * digits, frame index unpadded. Verified against all 868,524 entries of
 * keyframe_metadata.json by the generator.
 */
export function keyframeName(
  video: string,
  sceneId: number,
  frameIdx: number
): string {
  return `${video}-${String(sceneId).padStart(4, "0")}-${frameIdx}`;
}

/** Position of the last pair at or below `target`, or -1. */
function floorIndex(pairs: KeyframePair[], target: number): number {
  let low = 0;
  let high = pairs.length - 1;
  let found = -1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    if (pairs[mid][0] <= target) {
      found = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return found;
}

function at(
  video: string,
  pairs: KeyframePair[],
  position: number
): Keyframe | null {
  const pair = pairs[position];
  if (!pair) {
    return null;
  }
  return {
    video,
    frameIdx: pair[0],
    sceneId: pair[1],
    name: keyframeName(video, pair[1], pair[0]),
  };
}

export function neighbourKeyframes(
  video: string,
  frameIdx: number,
  index: KeyframeIndex
): { smaller: Keyframe | null; larger: Keyframe | null } {
  const pairs = index[video];
  if (!pairs || pairs.length === 0 || !Number.isFinite(frameIdx)) {
    return { smaller: null, larger: null };
  }
  const position = floorIndex(pairs, frameIdx);
  const smaller = at(video, pairs, position);
  // An exact hit is its own upper neighbour, so a caller asking for both edges
  // of a frame that is itself a keyframe gets that frame twice rather than the
  // next one along.
  const larger =
    smaller && smaller.frameIdx === frameIdx
      ? smaller
      : at(video, pairs, position + 1);
  return { smaller, larger };
}

/** Ties go to the earlier keyframe. */
export function nearestKeyframe(
  video: string,
  frameIdx: number,
  index: KeyframeIndex
): Keyframe | null {
  const { smaller, larger } = neighbourKeyframes(video, frameIdx, index);
  if (!smaller) {
    return larger;
  }
  if (!larger) {
    return smaller;
  }
  return frameIdx - smaller.frameIdx <= larger.frameIdx - frameIdx
    ? smaller
    : larger;
}
