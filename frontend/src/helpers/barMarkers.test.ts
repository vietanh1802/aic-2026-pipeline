// frontend/src/helpers/barMarkers.test.ts

import { describe, expect, it } from "vitest";

import {
  candidateIntervals,
  mergeIntervals,
  MIN_BLOCK_PX,
  type Block,
  type Candidate,
} from "./candidateStrip";
import { LABEL_PX } from "./candidateStripView";
import { barPosition, barSeconds } from "./frameRange";
import {
  labelLeftPx,
  labelledMarkers,
  layoutMarkers,
  overlayVisible,
  secondsAtPointer,
} from "./barMarkers";

function block(start: number, end: number, score = 80, name = `B-${start}`): Block {
  return {
    start,
    end,
    frameCount: 1,
    bestScore: score,
    bestFrame: { name, frameIdx: Math.round(start * 30) },
    bestTimeS: (start + end) / 2,
  };
}

// Scene 46 of L25_V014 (29.97 fps): the realistic top 9 the strip tests use.
const SCENE_46 = [
  2837, 2948, 3060, 3172, 3284, 3395, 3507, 3619, 3731, 3843, 3954, 4066, 4178, 4290, 4402,
  4513, 4625, 4737, 4849, 4961, 5072, 5184, 5296, 5408, 5520, 5631,
];
const TOP_9: [number, number][] = [
  [0, 80], [1, 92], [2, 85], [5, 70], [6, 70], [10, 88], [14, 60], [15, 99], [25, 75],
];
const DURATION = 1591;
const WIDTH = 930;

function realBlocks(): Block[] {
  const candidates: Candidate[] = TOP_9.map(([position, score]) => ({
    name: `L25_V014-0046-${SCENE_46[position]}.jpg`,
    frameIdx: SCENE_46[position],
    timeS: SCENE_46[position] / 29.97,
    score,
  }));
  return mergeIntervals(candidateIntervals(candidates, DURATION));
}

describe("overlayVisible", () => {
  it("is true on the unzoomed bar of a known duration", () => {
    expect(overlayVisible({ low: 0, high: 1591 }, 1591)).toBe(true);
  });

  it("allows float noise of a millionth of a second, not more", () => {
    expect(overlayVisible({ low: 0, high: 1591 + 5e-7 }, 1591)).toBe(true);
    expect(overlayVisible({ low: 0, high: 1591 - 5e-7 }, 1591)).toBe(true);
    expect(overlayVisible({ low: 0, high: 1591 + 2e-6 }, 1591)).toBe(false);
  });

  it("is false on a zoomed bar (TRAKE with both ends pinned)", () => {
    expect(overlayVisible({ low: 50, high: 200 }, 1591)).toBe(false);
    // Starts at 0 but stops short of the end: still a zoom.
    expect(overlayVisible({ low: 0, high: 200 }, 1591)).toBe(false);
    // Starts late and ends at the end.
    expect(overlayVisible({ low: 50, high: 1591 }, 1591)).toBe(false);
  });

  it("is true when a zoom happens to span the whole video: that scale is the full one", () => {
    expect(overlayVisible({ low: 0, high: 1591 }, 1591)).toBe(true);
  });

  it("is false while the duration is unknown: the bar falls back to a 1 s scale", () => {
    expect(overlayVisible({ low: 0, high: 1 }, 0)).toBe(false);
  });

  it("is false for a stale duration after a switch: the bar still has the old length, the tag is 0", () => {
    expect(overlayVisible({ low: 0, high: 1591 }, 0)).toBe(false);
  });

  it("is false when the bar's length is another video's", () => {
    expect(overlayVisible({ low: 0, high: 1591 }, 1200)).toBe(false);
  });

  it.each([[Number.NaN], [-5], [0], [Number.POSITIVE_INFINITY]])(
    "is false for a tagged duration of %s",
    (tagged) => {
      expect(overlayVisible({ low: 0, high: 1591 }, tagged)).toBe(false);
    }
  );

  it("is false for a scale that is not a number", () => {
    expect(overlayVisible({ low: 0, high: Number.NaN }, 1591)).toBe(false);
    expect(overlayVisible({ low: Number.NaN, high: 1591 }, 1591)).toBe(false);
  });
});

describe("layoutMarkers", () => {
  it("gives one marker per block: no union across the gaps the strip's clusters merge", () => {
    const blocks = realBlocks();
    const markers = layoutMarkers(blocks, DURATION, WIDTH);
    expect(blocks).toHaveLength(5);
    expect(markers).toHaveLength(5);
    expect(new Set(markers.map((m) => m.block))).toEqual(new Set(blocks));
  });

  it("draws every marker at least MIN_BLOCK_PX wide on the 1591 s video at 930 px", () => {
    for (const marker of layoutMarkers(realBlocks(), DURATION, WIDTH)) {
      expect((marker.widthPct / 100) * WIDTH).toBeGreaterThanOrEqual(MIN_BLOCK_PX - 1e-9);
    }
  });

  it("centres a marker on its block", () => {
    // 100 s to 110 s of a 1000 s video on a 1000 px bar: 10 px, already minimum.
    const [marker] = layoutMarkers([block(100, 110)], 1000, 1000);
    expect(marker.leftPct).toBeCloseTo(10, 9);
    expect(marker.widthPct).toBeCloseTo(1, 9);
    // 1 s wide (1 px): widened to 10 px around its centre 100.5.
    const [thin] = layoutMarkers([block(100, 101)], 1000, 1000);
    expect(thin.leftPct).toBeCloseTo(9.55, 9);
    expect(thin.widthPct).toBeCloseTo(1, 9);
  });

  it("keeps a block wider than the minimum at its own width", () => {
    const [wide] = layoutMarkers([block(200, 300)], 1000, 1000);
    expect(wide.leftPct).toBeCloseTo(20, 9);
    expect(wide.widthPct).toBeCloseTo(10, 9);
  });

  it("clamps a block at the start of the video to the bar's left edge", () => {
    const [marker] = layoutMarkers([block(0, 2)], 1000, 1000);
    expect(marker.leftPct).toBe(0);
    expect(marker.widthPct).toBeCloseTo(1, 9);
  });

  it("clamps a block at the end of the video to the bar's right edge", () => {
    const [marker] = layoutMarkers([block(998, 1000)], 1000, 1000);
    expect(marker.leftPct + marker.widthPct).toBeCloseTo(100, 9);
  });

  it("widens a zero-length block (a frame past the end) to the minimum", () => {
    const [marker] = layoutMarkers([block(1000, 1000)], 1000, 1000);
    expect(marker.widthPct).toBeCloseTo(1, 9);
    expect(marker.leftPct + marker.widthPct).toBeCloseTo(100, 9);
  });

  it("never lets a marker exceed a bar narrower than the minimum", () => {
    const [marker] = layoutMarkers([block(100, 101)], 1000, 6);
    expect(marker.leftPct).toBe(0);
    expect(marker.widthPct).toBe(100);
  });

  it("scales in percent: the same blocks on a half-width bar keep their position", () => {
    const wide = layoutMarkers([block(100, 400)], 1000, 1000)[0];
    const narrow = layoutMarkers([block(100, 400)], 1000, 500)[0];
    expect(narrow.leftPct).toBeCloseTo(wide.leftPct, 9);
    expect(narrow.widthPct).toBeCloseTo(wide.widthPct, 9);
  });

  it("keeps overlapping blocks as two markers, best score last (on top)", () => {
    const markers = layoutMarkers([block(100, 150, 90, "good"), block(120, 170, 60, "weak")], 1000, 1000);
    expect(markers.map((m) => m.block.bestFrame.name)).toEqual(["weak", "good"]);
    expect(markers[0].leftPct + markers[0].widthPct).toBeGreaterThan(markers[1].leftPct);
  });

  it("orders equal scores left to right", () => {
    const markers = layoutMarkers([block(500, 510, 70, "right"), block(100, 110, 70, "left")], 1000, 1000);
    expect(markers.map((m) => m.block.bestFrame.name)).toEqual(["left", "right"]);
  });

  it.each([[0], [-1], [Number.NaN], [Number.POSITIVE_INFINITY], [null], [undefined]])(
    "is empty for a duration of %s",
    (duration) => {
      expect(layoutMarkers([block(1, 2)], duration as number, 930)).toEqual([]);
    }
  );

  it.each([[0], [-10], [Number.NaN]])("is empty for a width of %s", (width) => {
    expect(layoutMarkers([block(1, 2)], 1000, width)).toEqual([]);
  });

  it("is empty for no blocks, and skips a block whose times are not numbers", () => {
    expect(layoutMarkers([], 1000, 930)).toEqual([]);
    expect(layoutMarkers([block(Number.NaN, 5), block(1, 2)], 1000, 930)).toHaveLength(1);
  });

  it("places a marker where the bar's own geometry would put the block's centre", () => {
    const [marker] = layoutMarkers([block(300, 600)], 1000, 1000);
    const centre = marker.leftPct + marker.widthPct / 2;
    expect(centre).toBeCloseTo(barPosition(450, 0, 1000) * 100, 9);
  });
});

describe("labelledMarkers", () => {
  const at = (centrePx: number, score: number, name: string, widthPx = 1000) => {
    const [marker] = layoutMarkers([block(centrePx - 5, centrePx + 5, score, name)], widthPx, widthPx);
    return marker;
  };

  it("labels every marker that has room", () => {
    // One px beyond the minimum gap: the centres come out of percent maths, and a
    // gap of exactly LABEL_PX can land at 33.999999999999996.
    const a = at(100, 90, "a");
    const b = at(100 + LABEL_PX + 1, 80, "b");
    expect(labelledMarkers([a, b], 1000)).toEqual(new Set([a, b]));
  });

  it("skips the weaker of two markers closer than a label", () => {
    const strong = at(100, 90, "strong");
    const weak = at(100 + LABEL_PX - 1, 80, "weak");
    expect(labelledMarkers([weak, strong], 1000)).toEqual(new Set([strong]));
  });

  it("checks against the labels already given out, not only the neighbour", () => {
    const a = at(100, 99, "a");
    const b = at(120, 90, "b"); // too close to a
    const c = at(140, 80, "c"); // 40 px from a: fits, and b never took a place
    expect(labelledMarkers([a, b, c], 1000)).toEqual(new Set([a, c]));
  });

  it("breaks a score tie in favour of the left one", () => {
    const left = at(100, 70, "left");
    const right = at(110, 70, "right");
    expect(labelledMarkers([right, left], 1000)).toEqual(new Set([left]));
  });

  it("is empty for no markers or an unknown width", () => {
    expect(labelledMarkers([], 1000).size).toBe(0);
    expect(labelledMarkers([at(100, 90, "a")], 0).size).toBe(0);
  });

  it("labels at least the best marker on the real 1591 s video at 930 px", () => {
    const markers = layoutMarkers(realBlocks(), DURATION, WIDTH);
    const labelled = labelledMarkers(markers, WIDTH);
    const best = markers[markers.length - 1];
    expect(best.block.bestScore).toBe(99);
    expect(labelled.has(best)).toBe(true);
  });
});

describe("labelLeftPx", () => {
  const marker = (start: number, end: number) => layoutMarkers([block(start, end)], 1000, 1000)[0];

  it("centres the label over the marker", () => {
    // Marker centre at 500 px.
    expect(labelLeftPx(marker(495, 505), 1000)).toBeCloseTo(500 - LABEL_PX / 2, 9);
  });

  it("keeps the label inside the bar at both ends", () => {
    expect(labelLeftPx(marker(0, 2), 1000)).toBe(0);
    expect(labelLeftPx(marker(998, 1000), 1000)).toBe(1000 - LABEL_PX);
  });

  it("never goes negative on a bar narrower than a label", () => {
    expect(labelLeftPx(marker(0, 2), 20)).toBe(0);
  });
});

describe("secondsAtPointer", () => {
  it("gives the low edge at the left and the high edge at the right", () => {
    expect(secondsAtPointer(200, 200, 930, 0, 1591)).toBe(0);
    expect(secondsAtPointer(1130, 200, 930, 0, 1591)).toBe(1591);
  });

  it("gives the middle in the middle: 465 px into a 930 px bar of a 1591 s video", () => {
    expect(secondsAtPointer(665, 200, 930, 0, 1591)).toBeCloseTo(795.5, 9);
  });

  it("clamps a pointer outside the bar", () => {
    expect(secondsAtPointer(100, 200, 930, 0, 1591)).toBe(0);
    expect(secondsAtPointer(5000, 200, 930, 0, 1591)).toBe(1591);
  });

  it("follows a zoomed scale", () => {
    expect(secondsAtPointer(600, 0, 1000, 50, 200)).toBeCloseTo(50 + 0.6 * 150, 9);
  });

  it("is the same expression the bar's click uses, for every pointer position", () => {
    for (const clientX of [-40, 0, 1, 137.5, 465, 929.9, 930, 1200]) {
      const click = barSeconds((clientX - 0) / 930, 0, 1591);
      expect(secondsAtPointer(clientX, 0, 930, 0, 1591)).toBe(click);
    }
  });

  it.each([
    ["zero width", 300, 100, 0],
    ["a NaN pointer", Number.NaN, 100, 930],
    ["an infinite pointer", Number.POSITIVE_INFINITY, 100, 930],
    ["a NaN rect", 300, Number.NaN, 930],
  ])("answers the low edge, not NaN, for %s", (_name, clientX, rectLeft, rectWidth) => {
    const seconds = secondsAtPointer(clientX, rectLeft, rectWidth, 0, 1591);
    expect(Number.isNaN(seconds)).toBe(false);
    expect(seconds).toBe(0);
  });
});
