import { describe, expect, it } from "vitest";

import { frameAt, frameRange } from "./frameRange";

describe("frameAt", () => {
  it("survives the frame -> seconds -> frame round trip", () => {
    // A result's start time is built as frame / fps and handed back here.
    // Plain flooring lost a frame on 6.2% of these at 25 fps, because
    // (49 / 25) * 25 is 48.99999999999999.
    for (const fps of [25, 30, 24, 29.97, 23.976]) {
      for (let frame = 0; frame < 4000; frame += 1) {
        const milliseconds = (frame / fps) * 1000;
        expect(frameAt(milliseconds / 1000, fps)).toBe(frame);
      }
    }
  });

  it("still floors a position that is genuinely inside a frame", () => {
    // Halfway through frame 100 at 25 fps is still frame 100.
    expect(frameAt(100 / 25 + 0.02, 25)).toBe(100);
    // And a whole frame earlier is frame 99.
    expect(frameAt(100 / 25 - 0.04, 25)).toBe(99);
  });

  it("returns null when the fps is unknown", () => {
    expect(frameAt(10, Number.NaN)).toBeNull();
    expect(frameAt(10, 0)).toBeNull();
  });
});

describe("frameRange", () => {
  it("submits the midpoint of the two marked edges", () => {
    // 100.0s and 104.0s at 25 fps -> frames 2500 and 2600 -> 2550.
    expect(frameRange(100, 104, 25)).toEqual({
      start: 2500,
      end: 2600,
      frame: 2550,
    });
  });

  it("submits exactly the marked frame when both edges match", () => {
    const seconds = 19470 / 25;
    expect(frameRange(seconds, seconds, 25)).toEqual({
      start: 19470,
      end: 19470,
      frame: 19470,
    });
  });

  it("reads an interval marked backwards as the same interval", () => {
    expect(frameRange(104, 100, 25)).toEqual(frameRange(100, 104, 25));
  });

  it("converts to frames before averaging, not after", () => {
    // 1.00s and 1.06s at 25 fps are frames 25 and 26; the midpoint is 25, not
    // the 25.75 that averaging the seconds first would round up to 26.
    expect(frameRange(1.0, 1.06, 25)?.frame).toBe(25);
  });

  it("never returns a negative frame", () => {
    expect(frameRange(-3, 2, 25)?.start).toBe(0);
  });

  it("returns null when the fps is unknown", () => {
    expect(frameRange(100, 104, Number.NaN)).toBeNull();
    expect(frameRange(100, 104, 0)).toBeNull();
  });

  it("returns null when a marker is not a number", () => {
    expect(frameRange(Number.NaN, 104, 25)).toBeNull();
  });
});
