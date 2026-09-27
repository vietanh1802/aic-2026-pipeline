import { describe, expect, it } from "vitest";

import {
  barPosition,
  barSeconds,
  frameAt,
  frameRange,
  spreadFrames,
} from "./frameRange";

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

describe("barPosition / barSeconds", () => {
  // Thanh dưới video có HAI thang: cả video, hoặc đúng đoạn đã ghim khi câu
  // TRAKE đã chốt hai đầu và đang chọn khung bên trong.

  it("maps a timestamp onto the full-video scale", () => {
    expect(barPosition(0, 0, 600)).toBe(0);
    expect(barPosition(300, 0, 600)).toBe(0.5);
    expect(barPosition(600, 0, 600)).toBe(1);
  });

  it("stretches a pinned window across the whole bar", () => {
    // Đoạn 146.8s -> 157.7s (khung 3670 -> 3943 ở 25 fps) trong video 600s.
    // Trên thang cả video nó chiếm 1.8% bề rộng; thu về thì trải kín.
    expect(barPosition(146.8, 146.8, 157.72)).toBe(0);
    expect(barPosition(157.72, 146.8, 157.72)).toBe(1);
    expect(barPosition(152.26, 146.8, 157.72)).toBeCloseTo(0.5, 6);
  });

  it("gives a click far more reach once the window is zoomed", () => {
    // Cùng một cú bấm lệch 1% bề rộng thanh:
    const wholeVideo = barSeconds(0.51, 0, 600) - barSeconds(0.5, 0, 600);
    const zoomed = barSeconds(0.51, 146.8, 157.72) - barSeconds(0.5, 146.8, 157.72);
    expect(wholeVideo).toBeCloseTo(6, 5);      // 6 giây = 150 khung
    expect(zoomed).toBeCloseTo(0.1092, 4);     // 0.1 giây = ~3 khung
    expect(zoomed).toBeLessThan(wholeVideo);
  });

  it("is its own inverse — the line and the click agree", () => {
    // Lệch nhau thì vạch đầu phát đứng một chỗ còn cú bấm nhảy sang chỗ khác.
    for (const [low, high] of [[0, 600], [146.8, 157.72]] as const) {
      for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
        const seconds = barSeconds(fraction, low, high);
        expect(barPosition(seconds, low, high)).toBeCloseTo(fraction, 9);
      }
    }
  });

  it("clamps a playhead that sits outside the window to the nearest edge", () => {
    // Tua bằng điều khiển của trình phát ra ngoài đoạn đã ghim. Vạch dính ở
    // mép còn hơn vẽ ra ngoài thanh.
    expect(barPosition(100, 146.8, 157.72)).toBe(0);
    expect(barPosition(400, 146.8, 157.72)).toBe(1);
  });

  it("clamps a click that lands outside the bar", () => {
    expect(barSeconds(-0.3, 146.8, 157.72)).toBe(146.8);
    expect(barSeconds(1.4, 146.8, 157.72)).toBe(157.72);
  });

  it("does not divide by zero when the window has no width", () => {
    // Hai đầu ghim trùng nhau, hoặc video chưa nạp xong metadata.
    expect(barPosition(5, 10, 10)).toBe(0);
    expect(barSeconds(0.5, 10, 10)).toBe(10);
  });

  it("survives a non-finite input rather than writing NaN% into the style", () => {
    expect(barPosition(Number.NaN, 0, 600)).toBe(0);
    expect(barSeconds(Number.NaN, 0, 600)).toBe(0);
    expect(barPosition(5, 0, Number.NaN)).toBe(0);
  });
});
