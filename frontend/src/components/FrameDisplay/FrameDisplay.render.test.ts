// frontend/src/components/FrameDisplay/FrameDisplay.render.test.ts

/**
 * Markup of the results grid with and without the one-card-per-video option,
 * rendered to a string with react-dom/server (vitest runs in node, no DOM).
 *
 * The stores are NOT mocked here: zustand v5 answers a server render from the
 * store's initial state (no annotations, empty filters), which is exactly what
 * these cards need. Only the first render is visible - effects, clicks and the
 * scroll-to-picked-card do not run.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { groupResultsByVideo } from "../../helpers/groupResults";
import type { SearchResult } from "../../types/api";
import FrameDisplay from "./index";
import GroupBadge from "./GroupBadge";

function frame(name: string, video: string, distance: number): SearchResult {
  return {
    frame: name,
    name,
    url: `http://localhost:8000/static/images/${name}`,
    distance,
    video,
    timestamp: "00:01:00.000",
    has_image: true,
  };
}

// Three frames of A (A2 scores best, so its card shows A2), one of B.
const LIST = [
  frame("A1.jpg", "A", 80),
  frame("B1.jpg", "B", 85),
  frame("A2.jpg", "A", 95),
  frame("A3.jpg", "A", 90),
];
const { cards, groupInfoByFrame } = groupResultsByVideo(LIST);

function render(extra: Record<string, unknown> = {}, results: SearchResult[] = LIST): string {
  return renderToStaticMarkup(
    createElement(FrameDisplay, {
      results,
      maxDistance: 100,
      isLoading: false,
      onClick: () => undefined,
      ...extra,
    } as never)
  );
}

const badges = (markup: string) => [...markup.matchAll(/>(\d+) khung</g)].map((m) => m[1]);

describe("GroupBadge", () => {
  it("says how many frames the card stands for", () => {
    const markup = renderToStaticMarkup(createElement(GroupBadge, { count: 3 }));
    expect(markup).toContain(">3 khung<");
    expect(markup).toContain("Video này có 3 khung trong kết quả. Mở video để xem các khung khác.");
  });

  it.each([[1], [0], [-2]])("renders nothing for a count of %i", (count) => {
    expect(renderToStaticMarkup(createElement(GroupBadge, { count }))).toBe("");
  });
});

describe("FrameDisplay without groupInfoByFrame (the option off)", () => {
  it("has no badge and no picked-frame label", () => {
    const markup = render();
    expect(badges(markup)).toEqual([]);
    expect(markup).not.toContain("khung bạn đã chọn");
  });

  it("looks the same whether the prop is absent, undefined or an empty map", () => {
    const absent = render();
    expect(render({ groupInfoByFrame: undefined })).toBe(absent);
    expect(render({ groupInfoByFrame: new Map() })).toBe(absent);
  });

  it("keeps the old ring rule: only the card whose own frame is picked", () => {
    const own = render({ highlightFrame: "A2.jpg" });
    expect(own).toContain("khung bạn đã chọn");
    // A frame of the same video that is not shown on any card is not ringed.
    const other = render({ highlightFrame: "A9.jpg" });
    expect(other).not.toContain("khung bạn đã chọn");
  });
});

describe("FrameDisplay with groupInfoByFrame (one card per video)", () => {
  it("shows the badge only on the card that stands for several frames", () => {
    const markup = render({ groupInfoByFrame }, cards);
    // Card A stands for 3 frames; card B for 1, so no badge on it.
    expect(badges(markup)).toEqual(["3"]);
  });

  it("does not print the folded frames' names, only the card's own", () => {
    const markup = render({ groupInfoByFrame }, cards);
    expect(markup).toContain("A2.jpg");
    expect(markup).not.toContain(">A1.jpg<");
    expect(markup).not.toContain(">A3.jpg<");
  });

  it("rings the card whose own frame is picked, with the usual label", () => {
    const markup = render({ groupInfoByFrame, highlightFrame: "A2.jpg" }, cards);
    expect(markup).toContain("khung bạn đã chọn<");
    expect(markup).not.toContain("nằm trong video này");
  });

  it("rings the card whose group HIDES the picked frame, and says so", () => {
    // A1 is folded into A's card; the ring must still land on that card.
    const markup = render({ groupInfoByFrame, highlightFrame: "A1.jpg" }, cards);
    expect(markup).toContain("khung bạn đã chọn nằm trong video này");
    expect(markup.match(/ring-4/g)).toHaveLength(1);
  });

  it("names who picked it when the hidden frame was copied from a teammate", () => {
    const markup = render(
      { groupInfoByFrame, highlightFrame: "A3.jpg", highlightLabel: "An" },
      cards
    );
    expect(markup).toContain("An bấm vào một khung của video này");
  });

  it("does not ring the card of another video", () => {
    const markup = render({ groupInfoByFrame, highlightFrame: "B1.jpg" }, cards);
    // Exactly one ring, on B's card, and not the hidden-frame wording.
    expect(markup.match(/ring-4/g)).toHaveLength(1);
    expect(markup).not.toContain("nằm trong video này");
  });

  it("keeps the pin state per video: the pin button follows the video, not the frame", () => {
    const markup = render(
      { groupInfoByFrame, onToggleFocus: () => undefined, focusVideos: ["A"] },
      cards
    );
    // Card A is pinned (its title flips to the unpin wording), card B is not.
    expect(markup.match(/Bỏ lọc video này/g)).toHaveLength(1);
    expect(markup.match(/Chỉ xem video này/g)).toHaveLength(1);
  });
});
