import { beforeEach, describe, expect, it } from "vitest";

import { filterByFocus } from "../helpers/focusFilter";
import type { SearchResult } from "../types/api";
import { useSearchStore } from "./useSearchStore";

// Store là singleton, nên mỗi test phải bắt đầu từ bàn trống.
beforeEach(() => {
  useSearchStore.setState({ focusVideos: [], showOnlyPinned: false });
});

function result(frame: string, video: string): SearchResult {
  return { frame, distance: 90, url: "", name: frame, video };
}

const RESULTS: SearchResult[] = [
  result("A-0000-1.jpg", "A"),
  result("B-0000-1.jpg", "B"),
  result("C-0000-1.jpg", "C"),
];

// The composition App.tsx actually renders: shownResults only narrows down
// when showOnlyPinned is on -- see the shownResults useMemo around App.tsx:621.
function shownResults(results: SearchResult[]): SearchResult[] {
  const { focusVideos, showOnlyPinned } = useSearchStore.getState();
  return showOnlyPinned ? filterByFocus(results, focusVideos) : results;
}

describe("focusVideos / showOnlyPinned", () => {
  it(
    "pinning a second video no longer removes it before it can be pinned " +
      "-- the actual regression: filterByFocus used to run the moment " +
      "focusVideos was non-empty, so video B's card (and its pin button) " +
      "vanished from shownResults right after video A was pinned, and there " +
      "was never a card left on screen to pin B from",
    () => {
      const { toggleFocusVideo } = useSearchStore.getState();

      toggleFocusVideo("A");
      // Video B's card must still be there to click its pin button at all.
      expect(shownResults(RESULTS).map((r) => r.video)).toEqual(["A", "B", "C"]);

      toggleFocusVideo("B");
      expect(useSearchStore.getState().focusVideos).toEqual(["A", "B"]);
      // Pinning a second video still must not have narrowed the grid.
      expect(shownResults(RESULTS).map((r) => r.video)).toEqual(["A", "B", "C"]);
    }
  );

  it("showOnlyPinned narrows the grid to exactly the pinned videos, same as the old always-on behavior", () => {
    const { toggleFocusVideo, toggleShowOnlyPinned } = useSearchStore.getState();

    toggleFocusVideo("A");
    toggleFocusVideo("C");
    toggleShowOnlyPinned();

    expect(useSearchStore.getState().showOnlyPinned).toBe(true);
    expect(shownResults(RESULTS).map((r) => r.video)).toEqual(["A", "C"]);
  });

  it("defaults to showing everything unfiltered", () => {
    expect(useSearchStore.getState().showOnlyPinned).toBe(false);
    expect(useSearchStore.getState().focusVideos).toEqual([]);
    expect(shownResults(RESULTS)).toEqual(RESULTS);
  });

  it("clearFocus resets both the pin list and the narrowing toggle, so the grid never gets stuck filtered-to-nothing", () => {
    const { toggleFocusVideo, toggleShowOnlyPinned, clearFocus } =
      useSearchStore.getState();

    toggleFocusVideo("A");
    toggleShowOnlyPinned();
    expect(shownResults(RESULTS).map((r) => r.video)).toEqual(["A"]);

    clearFocus();

    expect(useSearchStore.getState().focusVideos).toEqual([]);
    expect(useSearchStore.getState().showOnlyPinned).toBe(false);
    expect(shownResults(RESULTS)).toEqual(RESULTS);
  });
});
