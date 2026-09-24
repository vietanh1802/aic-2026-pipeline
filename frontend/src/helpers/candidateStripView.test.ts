// frontend/src/helpers/candidateStripView.test.ts

import { describe, expect, it } from "vitest";

import type { OcrSearchResult, SearchResult } from "../types/api";
import {
  candidateIntervals,
  layoutBlocks,
  mergeIntervals,
  type Block,
  type BlockGroup,
  type Candidate,
} from "./candidateStrip";
import {
  LABEL_PX,
  activeBlockIndex,
  activeGroupIndex,
  candidatesForVideo,
  describeBlock,
  formatScore,
  isOcrResults,
  jumpOfBlock,
  labelledGroups,
  shortClock,
} from "./candidateStripView";

// Keyframes of scene 46 of L25_V014 (29.97 fps), from keyframe_metadata.json.
const SCENE_46 = [
  2837, 2948, 3060, 3172, 3284, 3395, 3507, 3619, 3731, 3843, 3954, 4066, 4178, 4290, 4402,
  4513, 4625, 4737, 4849, 4961, 5072, 5184, 5296, 5408, 5520, 5631,
];
const FPS = 29.97;

function result(video: string, frameIdx: number, distance: number, extra: Partial<SearchResult> = {}): SearchResult {
  const name = `${video}-0046-${frameIdx}.jpg`;
  return { frame: name, name, distance, url: "", video, frame_idx: frameIdx, ...extra };
}

/** Blocks for scene-46 frames picked by position, each with a score. */
function scene46Blocks(picks: [position: number, score: number][], duration = 1591): Block[] {
  const candidates: Candidate[] = picks.map(([position, score]) => ({
    name: `L25_V014-0046-${SCENE_46[position]}.jpg`,
    frameIdx: SCENE_46[position],
    timeS: SCENE_46[position] / FPS,
    score,
  }));
  return mergeIntervals(candidateIntervals(candidates, duration));
}

// The realistic top 9 of the helper tests: 5 blocks, of which the first four
// fall within 3 px of each other on a 1591 s video at 930 px.
const TOP_9: [number, number][] = [
  [0, 80], [1, 92], [2, 85], [5, 70], [6, 70], [10, 88], [14, 60], [15, 99], [25, 75],
];

function fakeGroup(leftPct: number, widthPct: number, score: number): BlockGroup {
  const block: Block = {
    start: 0, end: 1, frameCount: 1, bestScore: score,
    bestFrame: { name: `f${leftPct}`, frameIdx: 1 }, bestTimeS: 0.5,
  };
  return {
    members: [block], best: block, frameCount: 1,
    leftPct, widthPct, hitLeftPct: leftPct, hitWidthPct: widthPct,
  };
}

describe("isOcrResults", () => {
  it("is false for a visual list and for an empty one", () => {
    expect(isOcrResults([result("L25_V014", 2837, 90)])).toBe(false);
    expect(isOcrResults([])).toBe(false);
  });

  it("is true when the results carry a matched-word count", () => {
    const ocr: OcrSearchResult = { ...result("L25_V014", 2837, 1005), matched_words: 5, total_words: 5 };
    expect(isOcrResults([ocr])).toBe(true);
  });
});

describe("candidatesForVideo", () => {
  it("returns only the frames of that video, best rank first", () => {
    const results = [
      result("L25_V008", 36128, 95),
      result("L25_V014", 2948, 92),
      result("L25_V008", 100, 91),
      result("L25_V014", 2837, 80),
    ];
    const candidates = candidatesForVideo(results, "L25_V014");
    expect(candidates.map((c) => c.frameIdx)).toEqual([2948, 2837]);
    expect(candidates.map((c) => c.score)).toEqual([92, 80]);
    expect(candidates[0].timeS).toBeCloseTo(2948 / FPS, 9);
  });

  it("reads the FULL list: a frame ranked 250th is still a candidate", () => {
    const filler = Array.from({ length: 249 }, (_, i) => result("L25_V008", 1000 + i, 99 - i * 0.01));
    const results = [...filler, result("L25_V014", 2837, 60)];
    expect(results).toHaveLength(250);
    expect(candidatesForVideo(results, "L25_V014")).toHaveLength(1);
  });

  it("is empty for a video that is not in the results", () => {
    expect(candidatesForVideo([result("L25_V008", 36128, 95)], "L25_V014")).toEqual([]);
  });

  it("is empty for an empty video id and for no results", () => {
    expect(candidatesForVideo([result("L25_V014", 2837, 90)], "")).toEqual([]);
    expect(candidatesForVideo([], "L25_V014")).toEqual([]);
  });

  it("is empty for the OCR route, whose distance is a word count", () => {
    const ocr: OcrSearchResult = { ...result("L25_V014", 2837, 1005), total_words: 5 };
    expect(candidatesForVideo([ocr], "L25_V014")).toEqual([]);
  });

  it("leaves out frames it cannot place in time", () => {
    // A video with no fps in fps_map.json has no timeline.
    expect(candidatesForVideo([result("ZZ99_V999", 5, 90)], "ZZ99_V999")).toEqual([]);
  });
});

describe("which block the playhead is in", () => {
  const blocks = scene46Blocks(TOP_9);

  it("guards the fixture: 5 blocks, none touching the next", () => {
    expect(blocks).toHaveLength(5);
    for (let i = 1; i < blocks.length; i++) {
      expect(blocks[i].start).toBeGreaterThan(blocks[i - 1].end);
    }
  });

  it("finds the block around the playhead", () => {
    expect(activeBlockIndex(blocks, 98)).toBe(0);
    expect(activeBlockIndex(blocks, 131.9)).toBe(2);
    expect(activeBlockIndex(blocks, 187.9)).toBe(4);
  });

  it("counts both edges of a block as inside", () => {
    for (const [index, block] of blocks.entries()) {
      expect(activeBlockIndex(blocks, block.start)).toBe(index);
      expect(activeBlockIndex(blocks, block.end)).toBe(index);
    }
  });

  it("is outside just past either edge and in the gap between two blocks", () => {
    expect(activeBlockIndex(blocks, blocks[0].start - 0.001)).toBe(-1);
    expect(activeBlockIndex(blocks, blocks[4].end + 0.001)).toBe(-1);
    // 107.1 to 108.3 s is the 1.2 s between block 0 and block 1.
    expect(activeBlockIndex(blocks, (blocks[0].end + blocks[1].start) / 2)).toBe(-1);
  });

  it("is -1 for a playhead outside every block, and for no blocks", () => {
    expect(activeBlockIndex(blocks, 0)).toBe(-1);
    expect(activeBlockIndex(blocks, 1500)).toBe(-1);
    expect(activeBlockIndex([], 100)).toBe(-1);
    expect(activeGroupIndex([], 100)).toBe(-1);
  });

  it("selects a whole cluster when the playhead is in any of its blocks, not in the gaps", () => {
    const groups = layoutBlocks(blocks, 1591, 930);
    // Blocks 0-3 are one cluster on the bar; block 4 stands alone.
    expect(groups).toHaveLength(2);
    const cluster = groups.findIndex((g) => g.members.length === 4);
    expect(cluster).toBeGreaterThanOrEqual(0);
    expect(activeGroupIndex(groups, 98)).toBe(cluster);
    expect(activeGroupIndex(groups, 150)).toBe(cluster);
    expect(activeGroupIndex(groups, (blocks[0].end + blocks[1].start) / 2)).toBe(-1);
    expect(activeGroupIndex(groups, 187.9)).toBe(1 - cluster);
    expect(activeGroupIndex(groups, 1000)).toBe(-1);
  });
});

describe("labelledGroups", () => {
  const WIDTH = 930;

  it("labels every group when they are far enough apart", () => {
    const groups = [fakeGroup(10, 1, 80), fakeGroup(40, 1, 90), fakeGroup(80, 1, 70)];
    expect(labelledGroups(groups, WIDTH).size).toBe(3);
  });

  it("keeps only the better score when two labels would overlap", () => {
    // 2% of 930 px = 18.6 px apart, closer than LABEL_PX.
    const low = fakeGroup(10, 1, 80);
    const high = fakeGroup(12, 1, 95);
    const shown = labelledGroups([low, high], WIDTH);
    expect(shown.has(high)).toBe(true);
    expect(shown.has(low)).toBe(false);
  });

  it("uses the label width as the limit", () => {
    // Centres a hair more than LABEL_PX apart are both labelled (a hair, so the
    // percent round trip cannot land just under the limit).
    const gapPct = ((LABEL_PX + 0.01) / WIDTH) * 100;
    const a = fakeGroup(10, 0, 90);
    const b = fakeGroup(10 + gapPct, 0, 80);
    expect(labelledGroups([a, b], WIDTH).size).toBe(2);
  });

  it("chains: the best in a row of close groups wins, its neighbours yield", () => {
    const groups = [fakeGroup(10, 0, 70), fakeGroup(12, 0, 99), fakeGroup(14, 0, 80), fakeGroup(60, 0, 50)];
    const shown = labelledGroups(groups, WIDTH);
    expect(shown.has(groups[1])).toBe(true);
    expect(shown.has(groups[0])).toBe(false);
    expect(shown.has(groups[2])).toBe(false);
    expect(shown.has(groups[3])).toBe(true);
  });

  it("is empty for no groups", () => {
    expect(labelledGroups([], WIDTH).size).toBe(0);
  });
});

describe("wording", () => {
  it("shortens a clock to what a chip needs", () => {
    expect(shortClock("00:20:05.472")).toBe("20:05");
    expect(shortClock("00:00:00.120")).toBe("00:00");
    expect(shortClock("01:02:03.000")).toBe("1:02:03");
    expect(shortClock("")).toBe("");
  });

  it("prints a score the way the cards do", () => {
    expect(formatScore(94.2)).toBe("94.2%");
    expect(formatScore(100)).toBe("100.0%");
    expect(formatScore(86.14)).toBe("86.1%");
  });

  it("describes a block for a screen reader", () => {
    expect(describeBlock({ clock: "20:05", frames: 3, score: 94.2 })).toBe(
      "Jump to 20:05, 3 frames, best 94.2%"
    );
    expect(describeBlock({ clock: "20:05", frames: 1, score: 94.2 })).toBe(
      "Jump to 20:05, 1 frame, best 94.2%"
    );
    expect(describeBlock({ clock: "1:49", frames: 7, score: 99, blocks: 4 })).toBe(
      "Jump to 1:49, 7 frames, 4 blocks, best 99.0%"
    );
  });
});

describe("jumpOfBlock", () => {
  it("targets the best frame, not the middle of the block", () => {
    // Positions 0-2: the best score is on the middle frame (2948), and the
    // block spans 89.7 to 107.1 s, whose middle (98.4) is not a frame.
    const [block] = scene46Blocks([[0, 80], [1, 92], [2, 85]]);
    const jump = jumpOfBlock(block);
    expect(jump).toEqual({
      frameName: "L25_V014-0046-2948.jpg",
      frameIdx: 2948,
      timeS: 2948 / FPS,
    });
  });

  it("takes the edge frame when that one scores best", () => {
    const [block] = scene46Blocks([[0, 99], [1, 80], [2, 85]]);
    expect(jumpOfBlock(block).frameIdx).toBe(2837);
    expect(jumpOfBlock(block).timeS).not.toBeCloseTo((block.start + block.end) / 2, 1);
  });

  it("gives the earliest frame when scores tie", () => {
    const [block] = scene46Blocks([[1, 90], [0, 90]]);
    expect(jumpOfBlock(block).frameIdx).toBe(2837);
  });
});
