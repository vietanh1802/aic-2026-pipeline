import { describe, expect, it } from "vitest";

import type { KeyframeIndex } from "./keyframeIndex";
import { evenPositions, spreadTrakeSlots } from "./trakeSpread";

const INDEX: KeyframeIndex = {
  L21_V001: [
    [0, 0],
    [100, 1],
    [200, 2],
    [300, 3],
    [400, 4],
  ],
};

describe("evenPositions", () => {
  it("puts the ends on the ends and spaces the rest evenly", () => {
    expect(evenPositions(0, 400, 5)).toEqual([0, 100, 200, 300, 400]);
  });

  it("rounds rather than truncating", () => {
    // 0 + 1·(10/3) = 3.33 -> 3; 0 + 2·(10/3) = 6.67 -> 7.
    expect(evenPositions(0, 10, 4)).toEqual([0, 3, 7, 10]);
  });

  it("returns the single position for n = 1", () => {
    expect(evenPositions(40, 90, 1)).toEqual([40]);
  });

  it("returns n copies when the span is a point", () => {
    // Every candidate on one frame is degenerate, but N slots still need N
    // values — dropping duplicates here would leave slots empty.
    expect(evenPositions(70, 70, 3)).toEqual([70, 70, 70]);
  });

  it("reads a reversed span as the same span", () => {
    expect(evenPositions(400, 0, 5)).toEqual(evenPositions(0, 400, 5));
  });

  it("returns nothing for n of zero or a non-finite bound", () => {
    expect(evenPositions(0, 400, 0)).toEqual([]);
    expect(evenPositions(Number.NaN, 400, 3)).toEqual([]);
  });
});

describe("spreadTrakeSlots", () => {
  it("snaps every position to the nearest real keyframe", () => {
    const picks = spreadTrakeSlots("L21_V001", 0, 400, 5, INDEX);
    expect(picks.map((p) => p.frameIdx)).toEqual([0, 100, 200, 300, 400]);
    expect(picks.every((p) => p.byHand === false)).toBe(true);
  });

  it("carries the keyframe name so the cell can show a still", () => {
    const picks = spreadTrakeSlots("L21_V001", 0, 400, 3, INDEX);
    expect(picks.map((p) => p.name)).toEqual([
      "L21_V001-0000-0",
      "L21_V001-0002-200",
      "L21_V001-0004-400",
    ]);
  });

  it("snaps an off-keyframe position to the closest one", () => {
    // 0, 133, 267, 400 -> 100, 300 for the two middles.
    expect(spreadTrakeSlots("L21_V001", 0, 400, 4, INDEX).map((p) => p.frameIdx))
      .toEqual([0, 100, 300, 400]);
  });

  it("falls back to the raw frame when the video has no keyframes", () => {
    const picks = spreadTrakeSlots("L99_V999", 0, 400, 3, INDEX);
    expect(picks.map((p) => p.frameIdx)).toEqual([0, 200, 400]);
    expect(picks.every((p) => p.byHand === true)).toBe(true);
    expect(picks[0].name).toBe("L99_V999 · frame 0");
  });

  it("returns nothing for n of zero", () => {
    expect(spreadTrakeSlots("L21_V001", 0, 400, 0, INDEX)).toEqual([]);
  });
});
