import { describe, expect, it } from "vitest";

import type { SearchResult } from "../types/api";
import { filterByFocus, videoOf } from "./focusFilter";

function result(frame: string, video?: string): SearchResult {
  return { frame, distance: 90, url: "", name: frame, video };
}

const RESULTS: SearchResult[] = [
  result("L21_V001-0000-10.jpg"),
  result("L21_V002-0003-99.jpg"),
  result("K19_V001-0000-29.jpg"),
  result("L21_V001-0004-500.jpg"),
];

describe("videoOf", () => {
  it("prefers the field the backend sends", () => {
    expect(videoOf(result("L21_V001-0000-10.jpg", "L21_V009"))).toBe("L21_V009");
  });

  it("falls back to the filename when the field is absent", () => {
    expect(videoOf(result("L21_V001-0000-10.jpg"))).toBe("L21_V001");
  });
});

describe("filterByFocus", () => {
  it("returns everything when nothing is focused", () => {
    expect(filterByFocus(RESULTS, [])).toHaveLength(4);
  });

  it("keeps only the focused video", () => {
    const kept = filterByFocus(RESULTS, ["L21_V001"]);
    expect(kept.map((r) => r.frame)).toEqual([
      "L21_V001-0000-10.jpg",
      "L21_V001-0004-500.jpg",
    ]);
  });

  it("keeps several focused videos at once", () => {
    expect(filterByFocus(RESULTS, ["L21_V002", "K19_V001"])).toHaveLength(2);
  });

  it("preserves the incoming order, which is the ranking", () => {
    const kept = filterByFocus(RESULTS, ["K19_V001", "L21_V001"]);
    expect(kept.map((r) => r.frame)).toEqual([
      "L21_V001-0000-10.jpg",
      "K19_V001-0000-29.jpg",
      "L21_V001-0004-500.jpg",
    ]);
  });

  // Filtering to a video with no hits must look like a filter, not a broken
  // search — which is what the "X/Y (đang lọc)" label in the header is for.
  it("returns nothing when the focused video has no results", () => {
    expect(filterByFocus(RESULTS, ["L30_V999"])).toEqual([]);
  });

  it("does not mutate the input", () => {
    const before = [...RESULTS];
    filterByFocus(RESULTS, ["L21_V001"]);
    expect(RESULTS).toEqual(before);
  });
});
