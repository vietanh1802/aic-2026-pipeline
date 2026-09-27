import { describe, expect, it } from "vitest";

import {
  keyframeName,
  nearestKeyframe,
  neighbourKeyframes,
  type KeyframeIndex,
} from "./keyframeIndex";

// [frame_idx, scene_id], sorted by frame_idx — the shape
// scripts/build_keyframe_index.py writes.
const INDEX: KeyframeIndex = {
  L21_V001: [
    [0, 0],
    [90, 0],
    [261, 1],
    [400, 2],
  ],
  K19_V001: [[29, 0]],
};

describe("keyframeName", () => {
  it("pads the scene id to four digits, like the files on disk", () => {
    expect(keyframeName("K19_V001", 0, 29)).toBe("K19_V001-0000-29");
    expect(keyframeName("L25_V085", 86, 30870)).toBe("L25_V085-0086-30870");
  });
});

describe("neighbourKeyframes", () => {
  it("returns the keyframes either side of a frame between two", () => {
    const { smaller, larger } = neighbourKeyframes("L21_V001", 200, INDEX);
    expect(smaller?.frameIdx).toBe(90);
    expect(larger?.frameIdx).toBe(261);
  });

  it("returns the same keyframe on both sides for an exact hit", () => {
    const { smaller, larger } = neighbourKeyframes("L21_V001", 261, INDEX);
    expect(smaller?.frameIdx).toBe(261);
    expect(larger?.frameIdx).toBe(261);
  });

  it("has no larger neighbour past the last keyframe", () => {
    const { smaller, larger } = neighbourKeyframes("L21_V001", 9999, INDEX);
    expect(smaller?.frameIdx).toBe(400);
    expect(larger).toBeNull();
  });

  it("has no smaller neighbour before the first keyframe", () => {
    // The first entry is frame 0, so ask below it.
    const { smaller, larger } = neighbourKeyframes("K19_V001", 5, INDEX);
    expect(smaller).toBeNull();
    expect(larger?.frameIdx).toBe(29);
  });

  it("returns nothing for a video that is not in the index", () => {
    expect(neighbourKeyframes("L99_V999", 10, INDEX)).toEqual({
      smaller: null,
      larger: null,
    });
  });
});

describe("nearestKeyframe", () => {
  it("picks the closer of the two neighbours", () => {
    expect(nearestKeyframe("L21_V001", 100, INDEX)?.frameIdx).toBe(90);
    expect(nearestKeyframe("L21_V001", 250, INDEX)?.frameIdx).toBe(261);
  });

  it("breaks a tie towards the earlier keyframe", () => {
    // 90 and 261 are 85.5 apart; 175 is nearer 90 by half a frame, 176 nearer
    // 261. Use the exact midpoint of 0 and 90.
    expect(nearestKeyframe("L21_V001", 45, INDEX)?.frameIdx).toBe(0);
  });

  it("falls back to the only side that exists", () => {
    expect(nearestKeyframe("L21_V001", 9999, INDEX)?.frameIdx).toBe(400);
    expect(nearestKeyframe("K19_V001", 0, INDEX)?.frameIdx).toBe(29);
  });

  it("carries the name the image URL needs", () => {
    expect(nearestKeyframe("L21_V001", 260, INDEX)?.name).toBe(
      "L21_V001-0001-261"
    );
  });

  it("returns null for an unknown video or a non-finite frame", () => {
    expect(nearestKeyframe("L99_V999", 10, INDEX)).toBeNull();
    expect(nearestKeyframe("L21_V001", Number.NaN, INDEX)).toBeNull();
  });
});
