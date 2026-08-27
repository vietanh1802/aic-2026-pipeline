import { describe, expect, it } from "vitest";

import { autofillPlan, suggestStep } from "./basketMath";
import type { AnswerRow } from "../api/answers";

// Minimal rows: only `origin` and `frames[0]` matter to this arithmetic. The
// rest of AnswerRow is filled with placeholders so the type checks.
function row(overrides: Partial<AnswerRow> & { frames: number[] }): AnswerRow {
  return {
    id: 1,
    task_id: 1,
    rank: 1,
    video_id: "L01_V001",
    answer_text: null,
    origin: "manual",
    created_by: null,
    updated_by: null,
    updated_at: "",
    version: 1,
    ...overrides,
  };
}

describe("autofillPlan", () => {
  it("has no anchor and nothing to cover when the basket is empty", () => {
    const plan = autofillPlan([], 100, 25);
    expect(plan).toEqual({
      anchor: null,
      autoCount: 0,
      needed: 100,
      span: 0,
      from: 0,
      to: 0,
    });
  });

  it("needs nothing once the basket is already full", () => {
    const rows = Array.from({ length: 100 }, (_, i) =>
      row({ id: i + 1, frames: [1000 + i] })
    );
    const plan = autofillPlan(rows, 100, 25);
    expect(plan.needed).toBe(0);
    // needed 0 -> ceil(0/2) * step -> span 0, so coverage collapses to the
    // anchor's own frame.
    expect(plan.span).toBe(0);
    expect(plan.from).toBe(1000);
    expect(plan.to).toBe(1000);
  });

  it("spans an odd `needed` by rounding the half up (Math.ceil)", () => {
    // rowsPerQuery 100, 7 rows already in -> needed 93 -> ceil(93/2) = 47.
    const rows = Array.from({ length: 7 }, (_, i) =>
      row({ id: i + 1, frames: [5000 + i] })
    );
    const plan = autofillPlan(rows, 100, 10);
    expect(plan.needed).toBe(93);
    expect(plan.span).toBe(470); // 47 * 10
    expect(plan.from).toBe(5000 - 470);
    expect(plan.to).toBe(5000 + 470);
  });

  it("counts only auto-origin rows toward autoCount", () => {
    const rows = [
      row({ id: 1, frames: [100], origin: "manual" }),
      row({ id: 2, frames: [101], origin: "auto" }),
      row({ id: 3, frames: [102], origin: "auto" }),
    ];
    const plan = autofillPlan(rows, 100, 25);
    expect(plan.autoCount).toBe(2);
  });

  it("clamps `from` at 0 rather than going negative near frame 0", () => {
    const rows = [row({ id: 1, frames: [10] })];
    // needed = 99 -> ceil(99/2) = 50 -> span = 50 * 25 = 1250, far past the
    // anchor's own frame 10.
    const plan = autofillPlan(rows, 100, 25);
    expect(plan.span).toBe(1250);
    expect(plan.from).toBe(0);
    expect(plan.to).toBe(10 + 1250);
  });

  it("works with a step of 1", () => {
    const rows = [row({ id: 1, frames: [500] })];
    // needed = 99 -> ceil(99/2) = 50 -> span = 50 * 1 = 50.
    const plan = autofillPlan(rows, 100, 1);
    expect(plan.span).toBe(50);
    expect(plan.from).toBe(450);
    expect(plan.to).toBe(550);
  });

  it("picks the first row as the anchor", () => {
    const rows = [
      row({ id: 1, frames: [42] }),
      row({ id: 2, frames: [999] }),
    ];
    const plan = autofillPlan(rows, 100, 25);
    expect(plan.anchor).toEqual(rows[0]);
  });
});

describe("suggestStep", () => {
  it("matches the user's hand-computed case: anchor 26253, 25642→26864, needed 93", () => {
    // halfWidth = max(26253-25642, 26864-26253) = max(611, 611) = 611.
    // steps = ceil(93/2) = 47. 611/47 = 13.0000... -> 13.
    const step = suggestStep(26253, { start: 25642, end: 26864 }, 93);
    expect(step).toBe(13);
  });

  it("uses the farther edge, not the average, when the anchor sits off-centre", () => {
    // anchor 100 in [90, 150]: distances are 10 and 50 -> halfWidth 50 (the
    // max), not 30 (the average of 10 and 50).
    const step = suggestStep(100, { start: 90, end: 150 }, 9);
    // steps = ceil(9/2) = 5. 50/5 = 10.
    expect(step).toBe(10);
  });

  it("reads a reversed range (start > end) the same as the forward one", () => {
    const forward = suggestStep(100, { start: 90, end: 150 }, 9);
    const reversed = suggestStep(100, { start: 150, end: 90 }, 9);
    expect(reversed).toBe(forward);
  });

  it("returns null when needed is 0 — there is nothing left to spread", () => {
    const step = suggestStep(26253, { start: 25642, end: 26864 }, 0);
    expect(step).toBeNull();
  });

  it("still suggests something when needed is 1", () => {
    // steps = ceil(1/2) = 1. halfWidth 10 / 1 = 10.
    const step = suggestStep(1000, { start: 990, end: 1010 }, 1);
    expect(step).toBe(10);
  });

  it("clamps at 2000 for a huge interval", () => {
    // steps = ceil(1/2) = 1. halfWidth 50000 far exceeds the API's ceiling.
    const step = suggestStep(0, { start: -50000, end: 50000 }, 1);
    expect(step).toBe(2000);
  });

  it("clamps up to 1 for a tiny interval rather than rounding down to 0", () => {
    // steps = ceil(9/2) = 5. halfWidth 1 / 5 = 0.2, which rounds to 0 — but 0
    // is not a usable step, so it clamps up to 1 instead.
    const step = suggestStep(1000, { start: 999, end: 1000 }, 9);
    expect(step).toBe(1);
  });

  it("returns null when halfWidth is 0 — the anchor sits exactly on a single-frame interval", () => {
    const step = suggestStep(500, { start: 500, end: 500 }, 93);
    expect(step).toBeNull();
  });

  it("returns null for a non-finite input", () => {
    expect(suggestStep(Number.NaN, { start: 0, end: 100 }, 9)).toBeNull();
    expect(suggestStep(50, { start: 0, end: 100 }, Number.POSITIVE_INFINITY)).toBeNull();
  });
});
