import { describe, expect, it } from "vitest";

import { autofillPlan } from "./basketMath";
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
