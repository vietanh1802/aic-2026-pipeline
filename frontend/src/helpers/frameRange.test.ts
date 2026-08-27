import { describe, expect, it } from "vitest";

import { frameAt, frameRange, spreadFrames } from "./frameRange";

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

describe("spreadFrames", () => {
  it("emits the edges first, then the middle, then the quarters", () => {
    // Rank order is submission order, and R@1..R@100 is what is scored, so the
    // most defensible guesses have to come out first.
    expect(spreadFrames(0, 8, 9)).toEqual([0, 8, 4, 2, 6, 1, 3, 5, 7]);
  });

  it("stops at k", () => {
    expect(spreadFrames(0, 1000, 5)).toEqual([0, 1000, 500, 250, 750]);
  });

  it("shrinks to the frames that exist rather than padding", () => {
    // Three frames in the interval and five asked for: three rows, not five.
    expect(spreadFrames(100, 102, 5)).toEqual([100, 102, 101]);
  });

  it("returns one frame when both edges are the same", () => {
    expect(spreadFrames(500, 500, 7)).toEqual([500]);
  });

  it("returns just the edges for k = 2", () => {
    expect(spreadFrames(10, 20, 2)).toEqual([10, 20]);
  });

  it("returns just the start for k = 1", () => {
    expect(spreadFrames(10, 20, 1)).toEqual([10]);
  });

  it("returns nothing for k of zero or less", () => {
    expect(spreadFrames(10, 20, 0)).toEqual([]);
    expect(spreadFrames(10, 20, -3)).toEqual([]);
  });

  it("reads a reversed interval as the same interval", () => {
    expect(spreadFrames(20, 10, 5)).toEqual(spreadFrames(10, 20, 5));
  });

  it("never repeats a frame", () => {
    const frames = spreadFrames(0, 4, 20);
    expect(new Set(frames).size).toBe(frames.length);
  });

  it("returns nothing when an edge is not a number", () => {
    expect(spreadFrames(Number.NaN, 20, 5)).toEqual([]);
  });
});
