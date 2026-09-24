// frontend/src/helpers/groupResults.test.ts

import { describe, expect, it } from "vitest";

import type { SearchResult } from "../types/api";
import { filterByFocus } from "./focusFilter";
import {
  buildGridResults,
  groupResultsByVideo,
  pickedKind,
  type GroupInfoByFrame,
} from "./groupResults";

function frame(name: string, video: string | undefined, distance: number): SearchResult {
  return { frame: name, name, distance, url: "", video };
}

const names = (results: SearchResult[]) => results.map((r) => r.name);

describe("groupResultsByVideo", () => {
  it("shows each video once, in the order it first appears", () => {
    const { cards } = groupResultsByVideo([
      frame("A1", "A", 90),
      frame("B1", "B", 85),
      frame("A2", "A", 80),
      frame("C1", "C", 70),
      frame("B2", "B", 60),
    ]);
    expect(names(cards)).toEqual(["A1", "B1", "C1"]);
  });

  it("is the order of each video's best score when the list is sorted by score", () => {
    // What the ensemble returns: descending fused score. Cards then come out
    // best video first, which is what the grid shows today.
    const sorted = [
      frame("B1", "B", 99),
      frame("A1", "A", 97),
      frame("B2", "B", 95),
      frame("C1", "C", 93),
      frame("A2", "A", 90),
    ];
    const { cards } = groupResultsByVideo(sorted);
    expect(names(cards)).toEqual(["B1", "A1", "C1"]);
    expect(cards.map((c) => c.distance)).toEqual([99, 97, 93]);
  });

  it("shows the highest-scoring frame of the video", () => {
    // An unsorted list: the card holds the video's first slot but its best frame.
    const { cards } = groupResultsByVideo([
      frame("A1", "A", 80),
      frame("B1", "B", 85),
      frame("A2", "A", 95),
      frame("A3", "A", 90),
    ]);
    expect(names(cards)).toEqual(["A2", "B1"]);
  });

  it("gives a tie to the earlier frame in the list", () => {
    const { cards } = groupResultsByVideo([
      frame("A1", "A", 90),
      frame("A2", "A", 90),
      frame("A3", "A", 90),
    ]);
    expect(names(cards)).toEqual(["A1"]);
  });

  it("returns the original result objects, not copies", () => {
    const first = frame("A1", "A", 90);
    const { cards } = groupResultsByVideo([first, frame("A2", "A", 80)]);
    expect(cards[0]).toBe(first);
  });

  it("counts the frames of each video and lists their names in list order", () => {
    const { groupInfoByFrame } = groupResultsByVideo([
      frame("A1", "A", 80),
      frame("B1", "B", 85),
      frame("A2", "A", 95),
      frame("A3", "A", 90),
    ]);
    // Keyed by the frame the card shows.
    expect(groupInfoByFrame.get("A2")).toEqual({ count: 3, memberNames: ["A1", "A2", "A3"] });
    expect(groupInfoByFrame.get("B1")).toEqual({ count: 1, memberNames: ["B1"] });
    // The frames folded away are not keys.
    expect(groupInfoByFrame.has("A1")).toBe(false);
    expect(groupInfoByFrame.size).toBe(2);
  });

  it("gives a video with one frame count 1", () => {
    const { cards, groupInfoByFrame } = groupResultsByVideo([frame("A1", "A", 90)]);
    expect(names(cards)).toEqual(["A1"]);
    expect(groupInfoByFrame.get("A1")).toEqual({ count: 1, memberNames: ["A1"] });
  });

  it("is empty for an empty list", () => {
    const { cards, groupInfoByFrame } = groupResultsByVideo([]);
    expect(cards).toEqual([]);
    expect(groupInfoByFrame.size).toBe(0);
  });

  it("never merges frames whose video id cannot be read", () => {
    // No `video` field and a name that carries no video id: videoOf gives "".
    const unknown = [
      frame("mystery-1.jpg", undefined, 90),
      frame("mystery-2.jpg", undefined, 80),
      frame("other.jpg", "", 70),
    ];
    const { cards, groupInfoByFrame } = groupResultsByVideo([
      ...unknown,
      frame("A1", "A", 60),
      frame("A2", "A", 50),
    ]);
    expect(names(cards)).toEqual(["mystery-1.jpg", "mystery-2.jpg", "other.jpg", "A1"]);
    for (const card of cards.slice(0, 3)) {
      expect(groupInfoByFrame.get(card.name)?.count).toBe(1);
    }
    expect(groupInfoByFrame.get("A1")?.count).toBe(2);
  });

  it("reads the video from the name when the backend sent none", () => {
    const { cards } = groupResultsByVideo([
      frame("L25_V014-0046-2837.jpg", undefined, 90),
      frame("L25_V014-0046-2948.jpg", undefined, 95),
    ]);
    expect(names(cards)).toEqual(["L25_V014-0046-2948.jpg"]);
  });

  it("never lets a NaN distance win", () => {
    expect(names(groupResultsByVideo([frame("A1", "A", Number.NaN), frame("A2", "A", 50)]).cards)).toEqual(["A2"]);
    expect(names(groupResultsByVideo([frame("A1", "A", 50), frame("A2", "A", Number.NaN)]).cards)).toEqual(["A1"]);
    // Nothing to compare: the earlier frame stays.
    expect(names(groupResultsByVideo([frame("A1", "A", Number.NaN), frame("A2", "A", Number.NaN)]).cards)).toEqual(["A1"]);
  });

  it("keeps exactly the pinned videos when the pin filter runs first", () => {
    const list = [
      frame("A1", "A", 99),
      frame("B1", "B", 98),
      frame("A2", "A", 97),
      frame("C1", "C", 96),
      frame("B2", "B", 95),
      frame("C2", "C", 94),
    ];
    // The order App.tsx composes: shownResults (pin filter), then the grouping.
    const { cards, groupInfoByFrame } = groupResultsByVideo(filterByFocus(list, ["A", "C"]));
    expect(names(cards)).toEqual(["A1", "C1"]);
    // Counts are over what was shown, so B's frames are not in any group.
    expect(groupInfoByFrame.get("A1")?.memberNames).toEqual(["A1", "A2"]);
    expect(groupInfoByFrame.get("C1")?.memberNames).toEqual(["C1", "C2"]);
  });

  it("does not modify its input", () => {
    const list = [frame("A1", "A", 80), frame("B1", "B", 85), frame("A2", "A", 95)];
    const before = JSON.stringify(list);
    list.forEach(Object.freeze);
    Object.freeze(list);
    groupResultsByVideo(list);
    expect(JSON.stringify(list)).toBe(before);
  });

  it("groups 500 results in a fraction of a millisecond (bound: 20 ms)", () => {
    const videos = Array.from({ length: 60 }, (_, i) => `L25_V${String(i + 1).padStart(3, "0")}`);
    const list = Array.from({ length: 500 }, (_, i) =>
      frame(`f${i}`, videos[(i * 7) % videos.length], 100 - i * 0.05)
    );
    const started = performance.now();
    const { cards, groupInfoByFrame } = groupResultsByVideo(list);
    const elapsed = performance.now() - started;

    expect(cards).toHaveLength(60);
    expect([...groupInfoByFrame.values()].reduce((sum, g) => sum + g.count, 0)).toBe(500);
    expect(elapsed).toBeLessThan(20);
  });
});

describe("buildGridResults", () => {
  const list = [frame("A1", "A", 90), frame("A2", "A", 80), frame("B1", "B", 70)];

  it("returns the same array and no group info when the option is off", () => {
    const grid = buildGridResults(list, false, true);
    // The off path is the code that ran before the option existed: the same
    // array, and no key at all for FrameDisplay to receive.
    expect(grid.cards).toBe(list);
    expect(grid.groupInfoByFrame).toBeUndefined();
    expect(Object.keys(grid)).toEqual(["cards"]);
  });

  it("returns the same array when the route must not be grouped, even with the option on", () => {
    const grid = buildGridResults(list, true, false);
    expect(grid.cards).toBe(list);
    expect(Object.keys(grid)).toEqual(["cards"]);
  });

  it("groups when the option is on and the route allows it", () => {
    const grid = buildGridResults(list, true, true);
    expect(names(grid.cards)).toEqual(["A1", "B1"]);
    expect(grid.groupInfoByFrame?.get("A1")?.count).toBe(2);
  });

  it("is a new array only when it groups", () => {
    expect(buildGridResults(list, true, true).cards).not.toBe(list);
    expect(buildGridResults([], true, true).cards).toEqual([]);
  });
});

describe("pickedKind", () => {
  const { cards, groupInfoByFrame } = groupResultsByVideo([
    frame("A1", "A", 90),
    frame("B1", "B", 85),
    frame("A2", "A", 80),
  ]);
  const [cardA, cardB] = cards;

  it("is null when nothing is picked", () => {
    expect(pickedKind(cardA, undefined, groupInfoByFrame)).toBeNull();
    expect(pickedKind(cardA, undefined)).toBeNull();
  });

  it("is 'own' when the card's own frame is the picked one", () => {
    expect(pickedKind(cardA, "A1", groupInfoByFrame)).toBe("own");
    expect(pickedKind(cardA, "A1")).toBe("own");
  });

  it("is 'hidden' when the picked frame is another frame folded into the card", () => {
    expect(pickedKind(cardA, "A2", groupInfoByFrame)).toBe("hidden");
  });

  it("is null for a frame of another video, or one that is not in any group", () => {
    expect(pickedKind(cardA, "B1", groupInfoByFrame)).toBeNull();
    expect(pickedKind(cardB, "A2", groupInfoByFrame)).toBeNull();
    expect(pickedKind(cardA, "nothing", groupInfoByFrame)).toBeNull();
  });

  it("without group info is exactly the old rule: only the card's own frame", () => {
    expect(pickedKind(cardA, "A2")).toBeNull();
    expect(pickedKind(cardA, "A2", undefined)).toBeNull();
  });

  it("is null when the card has no entry in the map", () => {
    const empty: GroupInfoByFrame = new Map();
    expect(pickedKind(cardA, "A2", empty)).toBeNull();
  });
});
