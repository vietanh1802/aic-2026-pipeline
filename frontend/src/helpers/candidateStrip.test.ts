// frontend/src/helpers/candidateStrip.test.ts

import { describe, expect, it } from "vitest";

import { accuracyPercent } from "../components/FrameDisplay/accuracy";
import type { SearchResult } from "../types/api";
import {
  CANDIDATE_HALF_WINDOW_S,
  HIT_PX,
  MERGE_GAP_S,
  MIN_BLOCK_PX,
  candidateIntervals,
  groupByVideo,
  layoutBlocks,
  mergeIntervals,
  opacityForScore,
  scoreRange,
  type Candidate,
} from "./candidateStrip";
import { fpsOf } from "./frameIdentity";

// The 40 keyframes of scene 46 of L25_V014 (a static blackboard scene), copied
// from keyframe_metadata.json: 29.97 fps, 3.70 to 3.74 s apart, 145.5 s in all.
const SCENE_46 = [
  2837, 2948, 3060, 3172, 3284, 3395, 3507, 3619, 3731, 3843, 3954, 4066, 4178, 4290, 4402,
  4513, 4625, 4737, 4849, 4961, 5072, 5184, 5296, 5408, 5520, 5631, 5743, 5855, 5967, 6079,
  6190, 6302, 6414, 6526, 6638, 6749, 6861, 6973, 7085, 7197,
];
const FPS_V014 = 29.97;

function result(name: string, distance: number, extra: Partial<SearchResult> = {}): SearchResult {
  return { frame: name, name, distance, url: "", ...extra };
}

function candidate(name: string, timeS: number, score: number): Candidate {
  return { name, frameIdx: Math.round(timeS * 25), timeS, score };
}

/** Candidates for L25_V014 scene-46 frames picked by position, with a score each. */
function scene46(picks: [position: number, score: number][]): Candidate[] {
  return picks.map(([position, score]) => ({
    name: `L25_V014-0046-${SCENE_46[position]}.jpg`,
    frameIdx: SCENE_46[position],
    timeS: SCENE_46[position] / FPS_V014,
    score,
  }));
}

describe("constants", () => {
  it("are the values the design settled on", () => {
    expect(CANDIDATE_HALF_WINDOW_S).toBe(5);
    expect(MERGE_GAP_S).toBe(0);
    expect(MIN_BLOCK_PX).toBe(10);
    expect(HIT_PX).toBe(24);
  });
});

describe("groupByVideo", () => {
  it("guards the fps this file relies on", () => {
    expect(fpsOf("L25_V014")).toBe(FPS_V014);
    expect(fpsOf("L25_V008")).toBe(29.97);
  });

  it("keeps videos in the order they first appear, not sorted", () => {
    const groups = groupByVideo([
      result("L25_V014-0046-2837.jpg", 95, { frame_idx: 2837 }),
      result("L25_V008-0116-36128.jpg", 93, { frame_idx: 36128 }),
      result("L25_V014-0046-2948.jpg", 92, { frame_idx: 2948 }),
      result("L25_V001-0000-33.jpg", 90, { frame_idx: 33 }),
    ]);
    expect([...groups.keys()]).toEqual(["L25_V014", "L25_V008", "L25_V001"]);
    expect(groups.get("L25_V014")?.candidates.map((c) => c.frameIdx)).toEqual([2837, 2948]);
  });

  it("turns a result into name, frame, time and score", () => {
    const groups = groupByVideo([result("L25_V008-0116-36128.jpg", 91.2, { frame_idx: 36128 })]);
    const [only] = groups.get("L25_V008")?.candidates ?? [];
    expect(only.name).toBe("L25_V008-0116-36128.jpg");
    expect(only.frameIdx).toBe(36128);
    // 36128 / 29.97 = 1205.47 s = 20:05.47, the player's time (not 00:36).
    expect(only.timeS).toBeCloseTo(1205.472, 3);
    expect(only.score).toBe(91.2);
  });

  it("reads the frame from the name when the result has no frame_idx", () => {
    const groups = groupByVideo([result("L25_V014-0046-2837.jpg", 95)]);
    expect(groups.get("L25_V014")?.candidates[0].frameIdx).toBe(2837);
  });

  it("skips and counts frames it cannot place, without dropping the video", () => {
    const groups = groupByVideo([
      // A batch not in fps_map.json yet: no fps, so no time.
      // Was N001-V001 — the N batch is in fps_map.json since the 2026-09-25
      // dataset, so the fixture needs an id no mapping will ever carry.
      // result("N001-V001-0012-345.jpg", 90, { frame_idx: 345 }),
      // result("N001-V001-0013-400.jpg", 89, { frame_idx: 400 }),
      result("Z999-V001-0012-345.jpg", 90, { frame_idx: 345 }),
      result("Z999-V001-0013-400.jpg", 89, { frame_idx: 400 }),
      result("L25_V014-0046-2837.jpg", 88, { frame_idx: 2837 }),
      // A known video whose name and fields give no frame number.
      result("L25_V014-oops", 87, { video: "L25_V014" }),
    ]);
    // expect(groups.get("N001-V001")).toEqual({ candidates: [], skipped: 2 });
    expect(groups.get("Z999-V001")).toEqual({ candidates: [], skipped: 2 });
    expect(groups.get("L25_V014")?.candidates).toHaveLength(1);
    expect(groups.get("L25_V014")?.skipped).toBe(1);
  });

  it("is empty for no results", () => {
    expect(groupByVideo([]).size).toBe(0);
  });
});

describe("candidateIntervals", () => {
  it("is 5 s either side of the frame", () => {
    const [interval] = candidateIntervals([candidate("a", 100, 90)], 1800);
    expect(interval.start).toBe(95);
    expect(interval.end).toBe(105);
  });

  it("clamps the start at 0", () => {
    const [interval] = candidateIntervals([candidate("a", 2, 90)], 1800);
    expect(interval).toMatchObject({ start: 0, end: 7 });
  });

  it("clamps the end at the duration", () => {
    const [interval] = candidateIntervals([candidate("a", 1798, 90)], 1800);
    expect(interval).toMatchObject({ start: 1793, end: 1800 });
  });

  it("collapses a frame past the end of the video onto the end", () => {
    const [interval] = candidateIntervals([candidate("a", 1900, 90)], 1800);
    expect(interval).toMatchObject({ start: 1800, end: 1800 });
  });

  it.each([[undefined], [null], [0], [Number.NaN], [Number.POSITIVE_INFINITY], [-5]])(
    "does not clamp the end when the duration is %s",
    (duration) => {
      const [interval] = candidateIntervals([candidate("a", 1900, 90)], duration);
      expect(interval).toMatchObject({ start: 1895, end: 1905 });
    }
  );

  it("is empty for no candidates", () => {
    expect(candidateIntervals([], 1800)).toEqual([]);
  });
});

describe("mergeIntervals", () => {
  const merge = (candidates: Candidate[]) => mergeIntervals(candidateIntervals(candidates, 1800));

  it("is empty for no intervals", () => {
    expect(merge([])).toEqual([]);
  });

  it("gives one block for one candidate", () => {
    expect(merge([candidate("a", 100, 90)])).toEqual([
      {
        start: 95,
        end: 105,
        frameCount: 1,
        bestScore: 90,
        bestFrame: { name: "a", frameIdx: 2500 },
        bestTimeS: 100,
      },
    ]);
  });

  it("merges intervals that overlap", () => {
    const blocks = merge([candidate("a", 100, 90), candidate("b", 106, 80)]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ start: 95, end: 111, frameCount: 2 });
  });

  it("merges intervals that touch (end equals start)", () => {
    // 10 s apart: [95, 105] and [105, 115].
    const blocks = merge([candidate("a", 100, 90), candidate("b", 110, 80)]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ start: 95, end: 115, frameCount: 2 });
  });

  it("still merges when float error leaves a 1e-13 gap between two touching intervals", () => {
    const blocks = mergeIntervals([
      { start: 0, end: 0.3, candidate: candidate("a", 0.2, 90) },
      { start: 0.1 + 0.2, end: 5, candidate: candidate("b", 0.3, 80) },
    ]);
    expect(blocks).toHaveLength(1);
  });

  it("keeps blocks apart when a gap of 1 s separates them", () => {
    // 11 s apart: [95, 105] and [106, 116].
    const blocks = merge([candidate("a", 100, 90), candidate("b", 111, 80)]);
    expect(blocks).toHaveLength(2);
    expect(blocks.map((b) => [b.start, b.end])).toEqual([
      [95, 105],
      [106, 116],
    ]);
  });

  it("merges a chain even when its two ends do not touch", () => {
    const blocks = merge([
      candidate("a", 100, 90),
      candidate("c", 118, 70),
      candidate("b", 109, 80),
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ start: 95, end: 123, frameCount: 3 });
  });

  it("carries the best score and jumps to the best frame, not the middle", () => {
    const [block] = merge([
      candidate("low", 100, 80),
      candidate("best", 104, 95),
      candidate("mid", 108, 85),
    ]);
    expect(block.bestScore).toBe(95);
    expect(block.bestFrame.name).toBe("best");
    expect(block.bestTimeS).toBe(104);
    // Here the best frame happens to sit at the middle of [95, 113]. Where it
    // does not, the jump target must still be the frame, not the middle:
    const [edge] = merge([candidate("x", 100, 80), candidate("y", 108, 90)]);
    expect(edge.bestTimeS).toBe(108);
    expect((edge.start + edge.end) / 2).toBe(104);
  });

  it("breaks a tie on score by the earliest time", () => {
    const [block] = merge([candidate("late", 104, 90), candidate("early", 100, 90)]);
    expect(block.bestFrame.name).toBe("early");
    expect(block.bestTimeS).toBe(100);
  });

  it("gives the same blocks for any order of the input", () => {
    const candidates = [
      candidate("a", 100, 90),
      candidate("b", 104, 90),
      candidate("c", 111, 70),
      candidate("d", 300, 60),
      candidate("e", 305, 99),
      candidate("f", 500, 50),
    ];
    const expected = merge(candidates);
    expect(expected).toHaveLength(3);
    for (const order of [
      [5, 4, 3, 2, 1, 0],
      [2, 0, 4, 1, 5, 3],
      [3, 5, 1, 0, 2, 4],
    ]) {
      expect(merge(order.map((i) => candidates[i]))).toEqual(expected);
    }
  });

  it("does not change its input", () => {
    const intervals = candidateIntervals([candidate("b", 200, 80), candidate("a", 100, 90)], 1800);
    const before = JSON.stringify(intervals);
    mergeIntervals(intervals);
    expect(JSON.stringify(intervals)).toBe(before);
  });
});

describe("L25_V014 scene 46, a static scene 3.7 s between frames", () => {
  it("guards the data", () => {
    expect(SCENE_46).toHaveLength(40);
    expect((SCENE_46[39] - SCENE_46[0]) / FPS_V014).toBeCloseTo(145.48, 1);
  });

  it("merges 9 neighbouring frames into ONE block of 9", () => {
    const first9 = scene46(SCENE_46.slice(0, 9).map((_, position) => [position, 90]));
    const blocks = mergeIntervals(candidateIntervals(first9, 1591));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].frameCount).toBe(9);
    expect(blocks[0].start).toBeCloseTo(89.66, 2);
    expect(blocks[0].end).toBeCloseTo(129.49, 2);
  });

  it("keeps every third frame apart: they are 11.2 s apart, 1.2 s short of touching", () => {
    const thirds = scene46([0, 3, 6, 9, 12, 15, 18, 21, 24].map((position) => [position, 90]));
    expect(mergeIntervals(candidateIntervals(thirds, 1591))).toHaveLength(9);
  });

  it("turns a realistic top-9 into 5 blocks and jumps to each block's best frame", () => {
    // Positions 0-2 and 14-15 are neighbours; 5-6 tie on score.
    const picks = scene46([
      [0, 80], [1, 92], [2, 85], [5, 70], [6, 70], [10, 88], [14, 60], [15, 99], [25, 75],
    ]);
    const blocks = mergeIntervals(candidateIntervals(picks, 1591));
    expect(blocks.map((b) => b.frameCount)).toEqual([3, 2, 1, 2, 1]);
    expect(blocks.map((b) => b.bestFrame.frameIdx)).toEqual([2948, 3395, 3954, 4513, 5631]);
    expect(blocks.map((b) => b.bestScore)).toEqual([92, 70, 88, 99, 75]);
    expect(blocks[1].bestTimeS).toBeCloseTo(3395 / FPS_V014, 6);
  });
});

describe("layoutBlocks", () => {
  const WIDTH = 930;
  const DURATION = 1800;
  const layout = (times: [time: number, score: number][], duration = DURATION, width = WIDTH) =>
    layoutBlocks(
      mergeIntervals(
        candidateIntervals(
          times.map(([time, score], i) => candidate(`c${i}`, time, score)),
          duration
        )
      ),
      duration,
      width
    );
  const px = (percent: number, width = WIDTH) => (percent / 100) * width;

  it("is empty when the duration, the width or the blocks are missing", () => {
    expect(layout([[100, 90]], 0)).toEqual([]);
    expect(layoutBlocks(mergeIntervals(candidateIntervals([candidate("a", 100, 90)])), undefined, WIDTH)).toEqual([]);
    expect(layout([[100, 90]], DURATION, 0)).toEqual([]);
    expect(layoutBlocks([], DURATION, WIDTH)).toEqual([]);
  });

  it("places a wide block exactly by percent, with no widening", () => {
    // 1000 s bar of 1000 px; a block from 100 to 300 s.
    const block = {
      start: 100, end: 300, frameCount: 4, bestScore: 90,
      bestFrame: { name: "a", frameIdx: 1 }, bestTimeS: 150,
    };
    const [group] = layoutBlocks([block], 1000, 1000);
    expect(group.leftPct).toBeCloseTo(10, 9);
    expect(group.widthPct).toBeCloseTo(20, 9);
    expect(group.hitWidthPct).toBeCloseTo(20, 9);
    expect(group.frameCount).toBe(4);
  });

  it("widens a 10 s block on a 30 min video from ~5 px to MIN_BLOCK_PX", () => {
    const [group] = layout([[900, 90]]);
    expect(px(group.widthPct)).toBeCloseTo(MIN_BLOCK_PX, 6);
    // Centred on the block: 900 s of 1800 s is the middle of the bar.
    expect(px(group.leftPct + group.widthPct / 2)).toBeCloseTo(WIDTH / 2, 6);
  });

  it("gives every block a hit area of at least HIT_PX", () => {
    const [group] = layout([[900, 90]]);
    expect(px(group.hitWidthPct)).toBeCloseTo(HIT_PX, 6);
    expect(group.hitLeftPct).toBeLessThan(group.leftPct);
  });

  it("keeps blocks at the two ends of the bar inside it", () => {
    const [first, last] = [...layout([[2, 90], [1798, 80]])].sort((a, b) => a.leftPct - b.leftPct);
    expect(first.leftPct).toBeCloseTo(0, 9);
    expect(first.hitLeftPct).toBeCloseTo(0, 9);
    expect(last.leftPct + last.widthPct).toBeCloseTo(100, 9);
    expect(last.hitLeftPct + last.hitWidthPct).toBeCloseTo(100, 9);
  });

  it("clusters blocks whose hit boxes would overlap, and lists the members", () => {
    // 30 s apart on a 30 min bar at 930 px: centres 15.5 px apart, hit boxes 24 px.
    const groups = layout([[900, 80], [930, 95]]);
    expect(groups).toHaveLength(1);
    expect(groups[0].members).toHaveLength(2);
    expect(groups[0].frameCount).toBe(2);
    // A click on the cluster goes to its best member.
    expect(groups[0].best.bestScore).toBe(95);
    expect(groups[0].best.bestTimeS).toBe(930);
    // Drawn as the union of the two drawn boxes.
    expect(px(groups[0].leftPct)).toBeCloseTo(460, 6);
    expect(px(groups[0].leftPct + groups[0].widthPct)).toBeCloseTo(485.5, 6);
  });

  it("keeps blocks apart once their hit boxes clear each other", () => {
    // 100 s apart: centres 51.7 px apart.
    const groups = layout([[900, 80], [1000, 95]]);
    expect(groups).toHaveLength(2);
    for (const group of groups) {
      expect(px(group.hitWidthPct)).toBeGreaterThanOrEqual(HIT_PX - 1e-9);
    }
  });

  it("renders in ascending score order so the best is drawn last, on top", () => {
    const groups = layout([[300, 90], [900, 70], [1500, 99], [1700, 80]]);
    expect(groups.map((g) => g.best.bestScore)).toEqual([70, 80, 90, 99]);
  });

  it("gives a 30 minute video at 930 px drawn blocks of at least 10 px whatever the input", () => {
    const groups = layout(
      Array.from({ length: 40 }, (_, i): [number, number] => [40 + i * 43, 60 + (i % 7) * 5])
    );
    expect(groups.length).toBeGreaterThan(1);
    for (const group of groups) {
      expect(px(group.widthPct)).toBeGreaterThanOrEqual(MIN_BLOCK_PX - 1e-9);
      expect(px(group.hitWidthPct)).toBeGreaterThanOrEqual(HIT_PX - 1e-9);
    }
  });

  it("never overlaps hit boxes, keeps every block, and stays inside the bar (random inputs)", () => {
    // mulberry32: a seeded generator, so a failure is reproducible.
    let seed = 20260924;
    const random = () => {
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    for (let round = 0; round < 200; round++) {
      const duration = 300 + random() * 3000;
      const width = 200 + random() * 1300;
      const count = 1 + Math.floor(random() * 60);
      const blocks = mergeIntervals(
        candidateIntervals(
          Array.from({ length: count }, (_, i) =>
            candidate(`c${i}`, random() * duration, 50 + random() * 50)
          ),
          duration
        )
      );
      const groups = layoutBlocks(blocks, duration, width);
      expect(groups.reduce((sum, g) => sum + g.members.length, 0)).toBe(blocks.length);
      const byPosition = [...groups].sort((a, b) => a.hitLeftPct - b.hitLeftPct);
      byPosition.forEach((group, i) => {
        expect(group.widthPct).toBeGreaterThanOrEqual((MIN_BLOCK_PX / width) * 100 - 1e-9);
        expect(group.hitWidthPct).toBeGreaterThanOrEqual((HIT_PX / width) * 100 - 1e-9);
        expect(group.leftPct).toBeGreaterThanOrEqual(-1e-9);
        expect(group.hitLeftPct).toBeGreaterThanOrEqual(-1e-9);
        expect(group.hitLeftPct + group.hitWidthPct).toBeLessThanOrEqual(100 + 1e-9);
        if (i > 0) {
          const previous = byPosition[i - 1];
          expect(group.hitLeftPct).toBeGreaterThanOrEqual(
            previous.hitLeftPct + previous.hitWidthPct - 1e-9
          );
        }
      });
    }
  });
});

describe("scoreRange and opacityForScore", () => {
  it("takes the range over the whole list it is given", () => {
    expect(scoreRange([{ distance: 91 }, { distance: 99.5 }, { distance: 84.2 }])).toEqual({
      low: 84.2,
      high: 99.5,
    });
  });

  it("is 0 to 0 for no results", () => {
    expect(scoreRange([])).toEqual({ low: 0, high: 0 });
  });

  it("maps the highest score to 1 and the lowest to 0.35", () => {
    expect(opacityForScore(99.5, 84.2, 99.5)).toBeCloseTo(1, 12);
    expect(opacityForScore(84.2, 84.2, 99.5)).toBeCloseTo(0.35, 12);
  });

  it("is linear in between", () => {
    expect(opacityForScore(87.5, 80, 95)).toBeCloseTo(0.675, 12);
  });

  it("uses the same normalisation as the card colour", () => {
    for (const score of [80, 83.3, 90, 94.9, 95]) {
      expect(opacityForScore(score, 80, 95)).toBeCloseTo(
        0.35 + 0.65 * (accuracyPercent(score, 80, 95) / 100),
        12
      );
    }
  });

  it("is 1 when every score is the same", () => {
    expect(opacityForScore(90, 90, 90)).toBe(1);
  });

  it("stays within 0.35 and 1 for a score outside the range", () => {
    expect(opacityForScore(120, 80, 95)).toBeCloseTo(1, 12);
    expect(opacityForScore(10, 80, 95)).toBeCloseTo(0.35, 12);
  });
});

describe("500 candidates", () => {
  it("group, merge and lay out in well under 50 ms", () => {
    const videos = ["L25_V001", "L25_V002", "L25_V003", "L25_V008", "L25_V014", "L26_V001"];
    let seed = 7;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) % 4294967296;
      return seed / 4294967296;
    };
    const results = Array.from({ length: 500 }, (_, i) => {
      const video = videos[Math.floor(random() * videos.length)];
      const frameIdx = Math.floor(random() * 40000);
      return result(`${video}-0001-${frameIdx}.jpg`, 100 - i * 0.02, { video, frame_idx: frameIdx });
    });
    for (const video of videos) {
      expect(fpsOf(video)).toBeGreaterThan(0);
    }

    const started = performance.now();
    const groups = groupByVideo(results);
    let blocksMade = 0;
    for (const { candidates } of groups.values()) {
      const blocks = mergeIntervals(candidateIntervals(candidates, 1600));
      blocksMade += layoutBlocks(blocks, 1600, 930).length;
    }
    const elapsed = performance.now() - started;

    expect([...groups.values()].reduce((sum, g) => sum + g.candidates.length, 0)).toBe(500);
    expect(blocksMade).toBeGreaterThan(0);
    expect(elapsed).toBeLessThan(50);
  });
});
