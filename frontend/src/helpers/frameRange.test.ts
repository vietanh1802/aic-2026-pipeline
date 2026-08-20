import { describe, expect, it } from "vitest";

import { frameRange } from "./frameRange";

describe("frameRange", () => {
  it("submits the midpoint of the two marked edges", () => {
    // 100.0s and 104.0s at 25 fps -> frames 2500 and 2600 -> 2550.
    expect(frameRange(100, 104, 25)).toEqual({
      start: 2500,
      end: 2600,
      frame: 2550,
    });
  });

  it("reproduces the old single-instant behaviour when both edges match", () => {
    // The form has always submitted Math.floor(startAt * fps). Leaving the
    // edges untouched must not change one existing answer.
    const startAt = 1024.36;
    const fps = 25;
    expect(frameRange(startAt, startAt, fps)?.frame).toBe(
      Math.floor(startAt * fps)
    );
  });

  it("reads an interval marked backwards as the same interval", () => {
    expect(frameRange(104, 100, 25)).toEqual(frameRange(100, 104, 25));
  });

  it("floors to whole frames rather than averaging seconds", () => {
    // 1.00s and 1.06s at 25 fps are frames 25 and 26; the midpoint is 25, not
    // the 25.75 that averaging the seconds first would round up to 26.
    expect(frameRange(1.0, 1.06, 25)?.frame).toBe(25);
  });

  it("never returns a negative frame", () => {
    expect(frameRange(-3, 2, 25)?.start).toBe(0);
  });

  it("returns null when the fps is unknown", () => {
    // fps_map.json has no entry for the video: frame_detect arrives undefined
    // and every arithmetic result downstream is NaN.
    expect(frameRange(100, 104, Number.NaN)).toBeNull();
    expect(frameRange(100, 104, 0)).toBeNull();
  });

  it("returns null when a marker is not a number", () => {
    expect(frameRange(Number.NaN, 104, 25)).toBeNull();
  });
});
