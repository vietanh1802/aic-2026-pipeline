// frontend/src/components/VideoPopUp/CandidateMarkers.render.test.ts

/**
 * Markup of the candidate markers on the lower bar, with react-dom/server.
 *
 * vitest here runs in node with no DOM, so this renders to a string and sees only
 * the FIRST render: effects do not run, so there is no ResizeObserver (the
 * measured width stays 0, hence no marker in CandidateMarkers itself) and no
 * pointer listeners (the hover state stays null). What that leaves is tested
 * directly: the gating through the overlay root, the marker layer rendered at a
 * chosen width, and the hover view rendered with a chosen second. The pointer
 * events themselves, and the real width, need a browser.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

// zustand v5 answers a server render from the store's INITIAL state, so setState
// would be invisible here. Stand-in hooks with the two fields the overlay reads.
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

import { labelledMarkers, layoutMarkers } from "../../helpers/barMarkers";
import {
  candidateIntervals,
  mergeIntervals,
  opacityForScore,
  scoreRange,
  type Candidate,
} from "../../helpers/candidateStrip";
import { formatScore } from "../../helpers/candidateStripView";
import type { SearchResult } from "../../types/api";
import CandidateMarkers, { HoverView, MarkerLayer } from "./CandidateMarkers";
import CandidateStrip from "./CandidateStrip";

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
const FULL = { low: 0, high: DURATION };

function resultAt(position: number, score: number, video = "L25_V014"): SearchResult {
  const frameIdx = SCENE_46[position];
  const name = `${video}-0046-${frameIdx}.jpg`;
  return { frame: name, name, distance: score, url: "", video, frame_idx: frameIdx };
}

const text = (markup: string) => markup.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

function render(props: Partial<Parameters<typeof CandidateMarkers>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(CandidateMarkers, {
      videoId: "L25_V014",
      stripDuration: DURATION,
      scale: FULL,
      ...props,
    })
  );
}

// The default scene: this video's top 9 plus one frame of another video, frame route.
function resetMocks() {
  mocks.results = [
    ...TOP_9.map(([position, score]) => resultAt(position, score)),
    resultAt(0, 97, "L25_V008"),
  ];
  mocks.searchType = "ensemble";
}

beforeEach(resetMocks);

describe("CandidateMarkers draws nothing unless everything allows it", () => {
  const drawn = (markup: string) => markup.includes("data-candidate-markers");

  it("is drawn on the unzoomed bar of a known duration", () => {
    expect(drawn(render())).toBe(true);
  });

  it("is drawn when a zoom happens to span the whole video", () => {
    expect(drawn(render({ scale: { low: 0, high: DURATION } }))).toBe(true);
  });

  it("is hidden when the bar is zoomed (TRAKE range pinned)", () => {
    expect(render({ scale: { low: 50, high: 200 } })).toBe("");
    expect(render({ scale: { low: 0, high: 200 } })).toBe("");
  });

  it("is hidden while the duration is unknown", () => {
    // The bar falls back to a 1 s scale and the tagged duration is 0.
    expect(render({ stripDuration: 0, scale: { low: 0, high: 1 } })).toBe("");
  });

  it("is hidden for a stale duration: the bar still has the previous video's length", () => {
    expect(render({ stripDuration: 0, scale: FULL })).toBe("");
    // Tag from another video's length.
    expect(render({ stripDuration: 1200, scale: FULL })).toBe("");
  });

  it("is hidden when told to (a TRAKE slot)", () => {
    expect(render({ hidden: true })).toBe("");
  });

  it.each(["trake", "temporal"])("is hidden on the %s route, whose results are not the store's", (type) => {
    mocks.searchType = type;
    expect(render()).toBe("");
  });

  it("is drawn on the single-model route: its results are frames too", () => {
    mocks.searchType = "single";
    expect(drawn(render())).toBe(true);
  });

  it("is hidden for OCR results, whose distance is a word count", () => {
    mocks.results = [{ ...resultAt(0, 1005), total_words: 5 } as SearchResult];
    expect(render()).toBe("");
  });

  it("is hidden when this video is not in the results (Go to frame, basket, badge)", () => {
    mocks.results = [resultAt(0, 97, "L25_V008")];
    expect(render()).toBe("");
  });

  it("is hidden with no results at all", () => {
    mocks.results = [];
    expect(render()).toBe("");
  });

  it("agrees with the upper strip about which of these hide it", () => {
    // The strip shows its chips exactly when the overlay root is drawn, for the
    // conditions they share.
    const cases: [string, () => void][] = [
      ["frame route", () => undefined],
      ["trake route", () => { mocks.searchType = "trake"; }],
      ["temporal route", () => { mocks.searchType = "temporal"; }],
      ["video absent", () => { mocks.results = [resultAt(0, 97, "L25_V008")]; }],
      ["no results", () => { mocks.results = []; }],
      ["ocr results", () => { mocks.results = [{ ...resultAt(0, 1005), total_words: 5 } as SearchResult]; }],
    ];
    for (const [name, arrange] of cases) {
      resetMocks();
      arrange();
      const strip = renderToStaticMarkup(
        createElement(CandidateStrip, {
          videoId: "L25_V014",
          durationS: DURATION,
          currentTimeS: 0,
          onJump: () => undefined,
        })
      );
      expect([name, drawn(render())]).toEqual([name, strip !== ""]);
    }
  });
});

describe("the overlay root", () => {
  it("is decorative, pointer-transparent and fills the bar", () => {
    const markup = render();
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain("pointer-events-none");
    expect(markup).toContain("absolute inset-0");
  });

  it("has no focusable or clickable element, so the tab order does not change", () => {
    const markup = render();
    expect(markup).not.toMatch(/<(button|a|input|select|textarea)\b/);
    expect(markup).not.toContain("tabindex");
    expect(markup).not.toContain("onclick");
  });
});

describe("MarkerLayer", () => {
  const candidates: Candidate[] = TOP_9.map(([position, score]) => ({
    name: `L25_V014-0046-${SCENE_46[position]}.jpg`,
    frameIdx: SCENE_46[position],
    timeS: SCENE_46[position] / 29.97,
    score,
  }));
  const blocks = mergeIntervals(candidateIntervals(candidates, DURATION));
  const markers = layoutMarkers(blocks, DURATION, WIDTH);
  const { low, high } = scoreRange(TOP_9.map(([, score]) => ({ distance: score })));

  function renderLayer(labelled = labelledMarkers(markers, WIDTH), list = markers): string {
    return renderToStaticMarkup(
      createElement(MarkerLayer, {
        markers: list,
        labelled,
        scoreLow: low,
        scoreHigh: high,
        widthPx: WIDTH,
      })
    );
  }

  it("guards the fixture: five blocks, none merged into a cluster", () => {
    expect(blocks).toHaveLength(5);
    expect(markers).toHaveLength(5);
  });

  it("draws one marker per block at its own position and width, in percent", () => {
    const markup = renderLayer();
    expect(markup.match(/data-marker=""/g)).toHaveLength(5);
    for (const marker of markers) {
      expect(markup).toContain(`left:${marker.leftPct}%;width:${marker.widthPct}%`);
    }
  });

  it("gives every marker at least 10 px at this bar width", () => {
    for (const marker of markers) {
      expect((marker.widthPct / 100) * WIDTH).toBeGreaterThanOrEqual(10 - 1e-9);
    }
  });

  it("fades each marker with the strip's own rule: the best fully opaque, the weaker less", () => {
    const markup = renderLayer();
    const opacities = markers.map((marker) => opacityForScore(marker.block.bestScore, low, high));
    // The 60-score frame is merged into the block whose best is 99, so the weakest
    // DRAWN marker is the 70 block.
    expect(Math.max(...opacities)).toBe(1);
    expect(Math.min(...opacities)).toBeLessThan(1);
    for (const [index, marker] of markers.entries()) {
      expect(markup).toContain(
        `left:${marker.leftPct}%;width:${marker.widthPct}%;opacity:${opacities[index]}`
      );
    }
  });

  it("paints the better score later, so it ends up on top where markers overlap", () => {
    const markup = renderLayer();
    const lefts = [...markup.matchAll(/data-marker=""[^>]*style="left:([\d.]+)%/g)].map((m) => Number(m[1]));
    expect(lefts).toEqual(markers.map((marker) => marker.leftPct));
    // Render order is ascending score, and the best block is the last one drawn.
    expect(markers[markers.length - 1].block.bestScore).toBe(99);
  });

  it("makes every element pointer-transparent and aria-hidden", () => {
    const markup = renderLayer(new Set(markers));
    const tags = markup.match(/<span\b[^>]*>/g) ?? [];
    expect(tags.length).toBe(10); // 5 markers + 5 labels
    for (const tag of tags) {
      expect(tag).toContain("pointer-events-none");
      expect(tag).toContain('aria-hidden="true"');
    }
    expect(markup).not.toMatch(/<(button|a|input)\b/);
    expect(markup).not.toContain("tabindex");
  });

  it("prints a score label only for the markers it was told fit", () => {
    expect(text(renderLayer(new Set(markers)))).toBe(
      markers.map((marker) => formatScore(marker.block.bestScore)).join(" ")
    );
    const best = markers[markers.length - 1];
    expect(text(renderLayer(new Set([best])))).toBe("99.0%");
    expect(text(renderLayer(new Set()))).toBe("");
  });

  it("culls labels that would print on top of each other", () => {
    // Real layout at 930 px: the labelled set is a subset of the markers.
    const labelled = labelledMarkers(markers, WIDTH);
    expect(labelled.size).toBeGreaterThan(0);
    expect(labelled.size).toBeLessThanOrEqual(markers.length);
    expect(renderLayer(labelled).match(/data-marker-label=""/g) ?? []).toHaveLength(labelled.size);
    // A crowded bar (150 px for the same video) labels fewer.
    const narrow = layoutMarkers(blocks, DURATION, 150);
    expect(labelledMarkers(narrow, 150).size).toBeLessThan(narrow.length);
  });

  it("keeps a label inside the bar", () => {
    const markup = renderLayer(new Set(markers));
    for (const [, left] of markup.matchAll(/data-marker-label=""[^>]*style="left:([\d.]+)px;width:34px"/g)) {
      expect(Number(left)).toBeGreaterThanOrEqual(0);
      expect(Number(left)).toBeLessThanOrEqual(WIDTH - 34);
    }
  });

  it("prints the scores with the format of the chips in the upper strip", () => {
    const strip = renderToStaticMarkup(
      createElement(CandidateStrip, {
        videoId: "L25_V014",
        durationS: DURATION,
        currentTimeS: 0,
        onJump: () => undefined,
      })
    );
    const chipScores = [...strip.matchAll(/font-bold text-proto-primary-active">(\d+\.\d%)</g)].map(
      (m) => m[1]
    );
    const labelScores = [...renderLayer(new Set(markers)).matchAll(/leading-3 text-proto-ink"[^>]*>(\d+\.\d%)</g)].map(
      (m) => m[1]
    );
    expect(chipScores.length).toBe(5);
    expect(labelScores.slice().sort()).toEqual(chipScores.slice().sort());
  });

  it("draws nothing for no markers", () => {
    expect(renderLayer(new Set(), [])).toBe("");
  });
});

describe("HoverView", () => {
  const view = (seconds: number | null, scale = FULL) =>
    renderToStaticMarkup(createElement(HoverView, { seconds, scale }));

  it("draws nothing while the pointer is off the bar", () => {
    expect(view(null)).toBe("");
  });

  it("puts a thin line and the time at the pointer's position", () => {
    const markup = view(795.5);
    expect(markup).toContain("data-hover-line");
    expect(markup).toContain("data-hover-label");
    expect(text(markup)).toBe("13:15");
    expect(markup.match(/left:50%/g)).toHaveLength(2);
  });

  it("reads the time as M:SS, and H:MM:SS from one hour", () => {
    expect(text(view(59, { low: 0, high: 7200 }))).toBe("0:59");
    expect(text(view(3600, { low: 0, high: 7200 }))).toBe("1:00:00");
    expect(text(view(3725, { low: 0, high: 7200 }))).toBe("1:02:05");
  });

  it("clamps the line to the bar", () => {
    expect(view(-5)).toContain("left:0%");
    expect(view(9999)).toContain("left:100%");
  });

  it("is pointer-transparent and aria-hidden", () => {
    const tags = view(100).match(/<span\b[^>]*>/g) ?? [];
    expect(tags).toHaveLength(2);
    for (const tag of tags) {
      expect(tag).toContain("pointer-events-none");
      expect(tag).toContain('aria-hidden="true"');
    }
  });
});
