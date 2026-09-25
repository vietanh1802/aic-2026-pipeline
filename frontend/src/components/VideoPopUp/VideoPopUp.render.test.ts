// frontend/src/components/VideoPopUp/VideoPopUp.render.test.ts

/**
 * Wiring of the popup, with react-dom/server: the candidate strip is mounted
 * without its own track and the lower frame bar gets the marker overlay slot.
 *
 * Only the first render is visible and the player has not reported a duration,
 * so the tagged duration is 0 and no marker can be drawn here; what this proves
 * is which props the popup passes. Markers on screen, the hover line and real
 * clicks need a browser.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

// zustand v5 answers a server render from the store's INITIAL state, so setState
// would be invisible here: stand-in hooks with the fields the popup tree reads.
const mocks = vi.hoisted(() => ({
  results: [] as unknown[],
}));
vi.mock("../../store/useSearchStore", () => ({
  useSearchStore: Object.assign(
    (selector: (state: { results: unknown[] }) => unknown) => selector({ results: mocks.results }),
    { getState: () => ({ results: mocks.results }) }
  ),
}));
vi.mock("../../store/queryStore", () => ({
  useQueryStore: Object.assign(
    (selector: (state: { searchType: string }) => unknown) => selector({ searchType: "ensemble" }),
    { getState: () => ({ searchType: "ensemble" }) }
  ),
}));

import type { SearchResult } from "../../types/api";
import VideoPopup, { type TrakeSlot } from "./index";

const SCENE_46 = [2837, 2948, 3060, 3172, 3284, 3395, 3507, 3619, 3731];

function resultAt(position: number, score: number): SearchResult {
  const frameIdx = SCENE_46[position];
  const name = `L25_V014-0046-${frameIdx}.jpg`;
  return { frame: name, name, distance: score, url: "", video: "L25_V014", frame_idx: frameIdx };
}

function render(extra: { trakeSlot?: TrakeSlot | null } = {}): string {
  return renderToStaticMarkup(
    createElement(VideoPopup, {
      videoId: "L25_V014",
      frameId: "0046-2837",
      startAt: 94000,
      onClose: () => undefined,
      setStartAt: () => undefined,
      ...extra,
    })
  );
}

const HEADROOM = "has-[[data-candidate-markers]]:mt-4";

// videoUrl() is "" without the storage env var, so the player renders <video src="">
// and React says so on every render. Not what this file is about; swallow that one
// warning only, and let any other console error through.
beforeAll(() => {
  const original = console.error;
  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
    if (String(args[0]).includes("An empty string")) return;
    original(...args);
  });
});
afterAll(() => vi.restoreAllMocks());

describe("VideoPopup wiring of the candidate blocks", () => {
  mocks.results = [resultAt(0, 80), resultAt(1, 92), resultAt(2, 85)];

  it("mounts the strip with its header and chips but without its own track", () => {
    const markup = render();
    expect(markup).toContain("Candidates in this video");
    expect(markup).toContain('aria-label="Jump to ');
    // The strip's track is the only element with this class in the popup.
    expect(markup).not.toContain("relative isolate h-9");
  });

  it("gives the lower bar the marker overlay slot (its headroom class is only added with one)", () => {
    expect(render()).toContain(HEADROOM);
  });

  it("keeps the lower bar's own controls and click-to-seek target", () => {
    const markup = render();
    expect(markup).toContain("Bấm để tua");
    expect(markup).toContain("Khung hiện tại");
    expect(markup).toContain("Nộp");
  });

  it("hides the strip on a TRAKE slot as before, and still gives the bar its slot", () => {
    const slot: TrakeSlot = {
      cardKey: "card-1",
      index: 0,
      label: "event one",
      total: 2,
      onCommit: () => undefined,
    };
    const markup = render({ trakeSlot: slot });
    expect(markup).not.toContain("Candidates in this video");
    expect(markup).toContain(HEADROOM);
  });

  it("draws no marker yet: the player has not reported a duration", () => {
    // The attribute itself; the bar's headroom class only NAMES it.
    expect(render()).not.toContain('data-candidate-markers=""');
  });
});
