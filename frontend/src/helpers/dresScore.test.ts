import { describe, expect, it } from "vitest";

import {
  clockTone,
  formatClock,
  isTrakeTask,
  liveClock,
  scoreIfCorrectNow,
} from "./dresScore";

describe("scoreIfCorrectNow", () => {
  it("follows the BTC formula", () => {
    expect(scoreIfCorrectNow(300, 0, 0)).toBe(100);
    expect(scoreIfCorrectNow(300, 150, 0)).toBe(75);
    expect(scoreIfCorrectNow(300, 300, 0)).toBe(50);
    // Ví dụ trong portal BTC: 03:50 còn lại của 5 phút = 70 giây đã trôi.
    expect(scoreIfCorrectNow(300, 70, 0)).toBeCloseTo(88.33, 2);
  });

  it("takes 10 points per wrong submission and never goes negative", () => {
    expect(scoreIfCorrectNow(300, 150, 2)).toBe(55);
    expect(scoreIfCorrectNow(300, 300, 6)).toBe(0);
  });

  it("clamps time outside the task window", () => {
    expect(scoreIfCorrectNow(240, 999, 0)).toBe(50);
    expect(scoreIfCorrectNow(240, -5, 0)).toBe(100);
  });

  it("has no score without a duration", () => {
    expect(scoreIfCorrectNow(null, 10, 0)).toBeNull();
    expect(scoreIfCorrectNow(0, 10, 0)).toBeNull();
  });
});

describe("liveClock", () => {
  const clock = { time_left: 100, time_elapsed: 200, source: "dres" as const };

  it("keeps counting between polls", () => {
    expect(liveClock(clock, 1_000, 3_500)).toEqual({ timeLeft: 97.5, elapsed: 202.5 });
  });

  it("stops at zero", () => {
    expect(liveClock(clock, 0, 500_000).timeLeft).toBe(0);
  });

  it("keeps an unknown time_left unknown", () => {
    expect(liveClock({ ...clock, time_left: null }, 0, 1_000).timeLeft).toBeNull();
  });
});

describe("clockTone", () => {
  it("goes green → yellow at half time → red near the end", () => {
    expect(clockTone(200, 300)).toBe("green");
    expect(clockTone(150, 300)).toBe("yellow");
    expect(clockTone(30, 300)).toBe("red");
    expect(clockTone(0, 300)).toBe("red");
  });

  it("uses only the red mark when the duration is unknown", () => {
    expect(clockTone(100, null)).toBe("green");
    expect(clockTone(10, null)).toBe("red");
    expect(clockTone(null, 300)).toBe("green");
  });
});

describe("formatClock", () => {
  it("rounds up so the last second still shows", () => {
    expect(formatClock(230)).toBe("03:50");
    expect(formatClock(0.4)).toBe("00:01");
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(-3)).toBe("00:00");
  });
});

describe("isTrakeTask", () => {
  it("matches TRAKE in either field, any case", () => {
    expect(isTrakeTask("TRAKE", "")).toBe(true);
    expect(isTrakeTask("temporal", "Trake-group")).toBe(true);
    expect(isTrakeTask("KIS", "Textual KIS")).toBe(false);
  });
});
