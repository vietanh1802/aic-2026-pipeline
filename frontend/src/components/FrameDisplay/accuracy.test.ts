import { describe, expect, it } from "vitest";

import { accuracyColor, accuracyPercent } from "./accuracy";

describe("accuracyPercent", () => {
  it("puts the best result at 100 and the worst at 0", () => {
    // A real ensemble response spans roughly 86 to 100, so raw distance
    // compresses into a single shade. Normalising against the set is what
    // makes the spread visible.
    expect(accuracyPercent(100, 86.15, 100)).toBe(100);
    expect(accuracyPercent(86.15, 86.15, 100)).toBe(0);
  });

  it("scales linearly in between", () => {
    expect(accuracyPercent(93.075, 86.15, 100)).toBeCloseTo(50, 5);
  });

  it("treats a single-result set as a full score", () => {
    expect(accuracyPercent(97, 97, 97)).toBe(100);
  });

  it("clamps values outside the observed range", () => {
    expect(accuracyPercent(120, 86.15, 100)).toBe(100);
    expect(accuracyPercent(10, 86.15, 100)).toBe(0);
  });
});

describe("accuracyColor", () => {
  it("is green at the top", () => {
    expect(accuracyColor(100)).toBe("rgb(0,255,0)");
  });

  it("is red at the bottom", () => {
    expect(accuracyColor(0)).toBe("rgb(255,0,0)");
  });

  it("is yellow in the middle", () => {
    expect(accuracyColor(50)).toBe("rgb(255,255,0)");
  });

  it("stays inside the green half above the midpoint", () => {
    expect(accuracyColor(75)).toBe("rgb(128,255,0)");
  });
});
