// frontend/src/components/VideoPopUp/CandidateStrip.render.test.ts

/**
 * Smoke test of CandidateStrip's markup, with react-dom/server.
 *
 * vitest here runs in node with no DOM, so this renders to a string: what it can
 * see is the FIRST render - which elements exist, in what order, with which
 * labels and styles. Effects do not run, so there is no ResizeObserver and the
 * track's measured width stays 0: the blocks are tested by rendering BlockLayer
 * directly with a layout computed at a chosen width. Clicking, focus, real
 * seeking and the resize path need a browser.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

// zustand v5 answers a server render from the store's INITIAL state, so setState
// would be invisible here. Stand-in hooks with the two fields the strip reads.
const mocks = vi.hoisted(() => ({
  results: [] as unknown[],
  searchType: "ensemble" as string,
}));
vi.mock("../../store/useSearchStore", () => ({
  useSearchStore: (selector: (state: { results: unknown[] }) => unknown) =>
    selector({ results: mocks.results }),
}));
vi.mock("../../store/queryStore", () => ({
  useQueryStore: (selector: (state: { searchType: string }) => unknown) =>
    selector({ searchType: mocks.searchType }),
}));

import {
  candidateIntervals,
  layoutBlocks,
  mergeIntervals,
  type Candidate,
} from "../../helpers/candidateStrip";
import { labelledGroups } from "../../helpers/candidateStripView";
import type { SearchResult } from "../../types/api";
import CandidateStrip, { BlockLayer } from "./CandidateStrip";

// Scene 46 of L25_V014 (29.97 fps): the realistic top 9 of the helper tests.
const SCENE_46 = [
  2837, 2948, 3060, 3172, 3284, 3395, 3507, 3619, 3731, 3843, 3954, 4066, 4178, 4290, 4402,
  4513, 4625, 4737, 4849, 4961, 5072, 5184, 5296, 5408, 5520, 5631,
];
const TOP_9: [number, number][] = [
  [0, 80], [1, 92], [2, 85], [5, 70], [6, 70], [10, 88], [14, 60], [15, 99], [25, 75],
];

function resultAt(position: number, score: number, video = "L25_V014"): SearchResult {
  const frameIdx = SCENE_46[position];
  const name = `${video}-0046-${frameIdx}.jpg`;
  return { frame: name, name, distance: score, url: "", video, frame_idx: frameIdx };
}

const text = (markup: string) => markup.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();

function render(props: Partial<Parameters<typeof CandidateStrip>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(CandidateStrip, {
      videoId: "L25_V014",
      durationS: 1591,
      currentTimeS: 100,
      onJump: () => undefined,
      ...props,
    })
  );
}

beforeEach(() => {
  mocks.results = [
    ...TOP_9.map(([position, score]) => resultAt(position, score)),
    resultAt(0, 97, "L25_V008"),
  ];
  mocks.searchType = "ensemble";
});

describe("CandidateStrip renders nothing when there is nothing to show", () => {
  it("has no results for this video", () => {
    mocks.results = [resultAt(0, 97, "L25_V008")];
    expect(render()).toBe("");
  });

  it("has no results at all", () => {
    mocks.results = [];
    expect(render()).toBe("");
  });

  it("is hidden, as on a TRAKE popup", () => {
    expect(render({ hidden: true })).toBe("");
  });

  it.each(["trake", "temporal"])("is on the %s route, whose results are not the store's", (type) => {
    mocks.searchType = type;
    expect(render()).toBe("");
  });

  it("holds OCR results, whose distance is a word count", () => {
    mocks.results = [{ ...resultAt(0, 1005), total_words: 5 } as SearchResult];
    expect(render()).toBe("");
  });

  it("is on the single-model route: it still shows (its results are frames)", () => {
    mocks.searchType = "single";
    expect(render()).not.toBe("");
  });
});

describe("CandidateStrip with candidates", () => {
  it("says how many frames and blocks there are", () => {
    expect(text(render())).toContain("Candidates in this video 9 frames in 5 blocks");
  });

  it("lists one chip per block, in time order, with time, score and frame count", () => {
    const markup = render();
    const labels = [...markup.matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1]);
    expect(labels).toEqual([
      "Jump to 01:38, 3 frames, best 92.0%",
      "Jump to 01:53, 2 frames, best 70.0%",
      "Jump to 02:11, 1 frame, best 88.0%",
      "Jump to 02:30, 2 frames, best 99.0%",
      "Jump to 03:07, 1 frame, best 75.0%",
    ]);
    // Three adjacent spans; the gap between them is CSS, not a space.
    expect(text(markup)).toContain("01:3892.0%3 frames");
  });

  it("marks the chip the playhead is in", () => {
    const markup = render({ currentTimeS: 131.9 });
    expect(markup.match(/aria-current="true"/g)).toHaveLength(1);
    expect(markup).toMatch(/aria-current="true"[^>]*title="Jump to 02:11/);
  });

  it("marks no chip when the playhead is outside every block", () => {
    expect(render({ currentTimeS: 1000 })).not.toContain("aria-current");
  });

  it("shows only the chips, no track and no playhead, before the duration is known", () => {
    const markup = render({ durationS: 0 });
    expect(markup).not.toContain("isolate");
    expect(markup.match(/<button/g)).toHaveLength(5);
  });

  it("draws the track once the duration is known", () => {
    expect(render()).toContain("isolate");
  });
});

describe("CandidateStrip with showTrack false (the blocks are on the lower bar)", () => {
  const chipButtons = (markup: string) => markup.match(/<button[^>]*>[\s\S]*?<\/button>/g) ?? [];

  it("is the same as the default when showTrack is left out or true", () => {
    expect(render({ showTrack: true })).toBe(render());
    expect(render({ showTrack: undefined })).toBe(render());
  });

  it("keeps the header line", () => {
    expect(text(render({ showTrack: false }))).toContain(
      "Candidates in this video 9 frames in 5 blocks"
    );
  });

  it("keeps every chip, in time order, with the same labels as with the track", () => {
    const markup = render({ showTrack: false });
    const labels = [...markup.matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1]);
    expect(labels).toEqual([
      "Jump to 01:38, 3 frames, best 92.0%",
      "Jump to 01:53, 2 frames, best 70.0%",
      "Jump to 02:11, 1 frame, best 88.0%",
      "Jump to 02:30, 2 frames, best 99.0%",
      "Jump to 03:07, 1 frame, best 75.0%",
    ]);
    expect(chipButtons(markup)).toEqual(chipButtons(render({ showTrack: true })));
    expect(chipButtons(markup)).toHaveLength(5);
  });

  it("draws no track, no playhead and no note about clusters", () => {
    const markup = render({ showTrack: false });
    expect(markup).not.toContain("isolate");
    expect(markup).not.toContain("h-9");
    expect(markup).not.toContain("bg-proto-dark");
    expect(markup).not.toContain("share one button on the bar");
    // The track is exactly what the default adds on top of the header and chips.
    expect(render({ showTrack: true })).toContain("isolate");
  });

  it("still marks the chip the playhead is in", () => {
    const markup = render({ showTrack: false, currentTimeS: 131.9 });
    expect(markup.match(/aria-current="true"/g)).toHaveLength(1);
    expect(markup).toMatch(/aria-current="true"[^>]*title="Jump to 02:11/);
  });

  it("shows the chips before the duration is known, like the default", () => {
    expect(chipButtons(render({ showTrack: false, durationS: 0 }))).toHaveLength(5);
  });

  it("still renders nothing under every condition that hides the strip", () => {
    mocks.results = [];
    expect(render({ showTrack: false })).toBe("");
    mocks.results = [resultAt(0, 97, "L25_V008")];
    expect(render({ showTrack: false })).toBe("");
    expect(render({ showTrack: false, hidden: true })).toBe("");
    mocks.results = [{ ...resultAt(0, 1005), total_words: 5 } as SearchResult];
    expect(render({ showTrack: false })).toBe("");
    for (const type of ["trake", "temporal"]) {
      mocks.results = [resultAt(0, 80)];
      mocks.searchType = type;
      expect(render({ showTrack: false })).toBe("");
    }
  });
});

describe("BlockLayer", () => {
  const candidates: Candidate[] = TOP_9.map(([position, score]) => ({
    name: `L25_V014-0046-${SCENE_46[position]}.jpg`,
    frameIdx: SCENE_46[position],
    timeS: SCENE_46[position] / 29.97,
    score,
  }));
  const blocks = mergeIntervals(candidateIntervals(candidates, 1591));
  // Render order: ascending best score. At 930 px the first four blocks are a
  // cluster (best 99) and the last one stands alone (best 75).
  const groups = layoutBlocks(blocks, 1591, 930);
  const cluster = groups.find((g) => g.members.length === 4)!;
  const single = groups.find((g) => g.members.length === 1)!;

  function renderLayer(activeGroup = cluster, labelled = labelledGroups(groups, 930)): string {
    return renderToStaticMarkup(
      createElement(BlockLayer, {
        groups,
        activeGroup,
        labelled,
        scoreLow: 60,
        scoreHigh: 99,
        widthPx: 930,
        videoId: "L25_V014",
        onJumpBlock: () => undefined,
      })
    );
  }

  it("guards the fixture: a cluster and a lone block", () => {
    expect(groups).toHaveLength(2);
    expect(groups[0]).toBe(single);
    expect(groups[1]).toBe(cluster);
  });

  it("puts the buttons in TIME order even though the layout is in score order", () => {
    const labels = [...renderLayer().matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1]);
    expect(labels).toEqual([
      "Jump to 02:30, 8 frames, 4 blocks, best 99.0%",
      "Jump to 03:07, 1 frame, best 75.0%",
    ]);
  });

  it("stacks the better score on top with z-index", () => {
    const markup = renderLayer();
    expect(markup).toMatch(/title="Jump to 02:30[^"]*"[^>]*style="[^"]*z-index:2"/);
    expect(markup).toMatch(/title="Jump to 03:07[^"]*"[^>]*style="[^"]*z-index:1"/);
  });

  it("gives every button its hit box and puts the ring on the active group only", () => {
    const markup = renderLayer();
    expect(markup.match(/aria-current="true"/g)).toHaveLength(1);
    // The always-on focus ring is "focus-visible:ring-2 ..."; the selection ring
    // is the plain one, on the active group's block only.
    expect(markup.match(/ ring-2 ring-proto-primary/g)).toHaveLength(1);
    for (const group of groups) {
      expect(markup).toContain(`left:${group.hitLeftPct}%;width:${group.hitWidthPct}%`);
    }
  });

  it("fades the block by score on its own layer", () => {
    const markup = renderLayer();
    // Best score in the range is fully opaque, the lone 75 is not.
    expect(markup).toContain("opacity:1");
    expect(markup).toMatch(/opacity:0\.\d+/);
  });

  it("prints a score label only for the groups it was told fit", () => {
    // In time order: the cluster (99.0%), then the lone block (75.0%).
    expect(text(renderLayer(cluster, new Set(groups)))).toBe("99.0%75.0%");
    const onlyBest = text(renderLayer(cluster, new Set([cluster])));
    expect(onlyBest).toBe("99.0%");
    expect(text(renderLayer(cluster, new Set()))).toBe("");
  });
});
