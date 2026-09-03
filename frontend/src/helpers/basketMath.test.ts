import { describe, expect, it } from "vitest";

import {
  autofillPlan,
  eventWindowFields,
  rangeOwner,
  suggestStep,
} from "./basketMath";
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

describe("rangeOwner", () => {
  it("picks the row the marked interval was pinned around, not rank 1", () => {
    // Đúng cảnh trong báo cáo: mốc 1 ở khung 1939, mốc 2 ở 6916, và đoạn vừa
    // ghim là 5176→8657 — đoạn của mốc 2. Cách cũ luôn đo từ rows[0].
    const rows = [
      row({ id: 1, frames: [1939] }),
      row({ id: 2, frames: [6916] }),
    ];
    expect(rangeOwner(rows, { start: 5176, end: 8657 })?.id).toBe(2);
  });

  it("picks rank 1 back when the interval is the one pinned around it", () => {
    const rows = [
      row({ id: 1, frames: [1939] }),
      row({ id: 2, frames: [6916] }),
    ];
    expect(rangeOwner(rows, { start: 1410, end: 2469 })?.id).toBe(1);
  });

  it("returns null when no row sits inside the interval", () => {
    // Hai đầu vừa ghim nhưng chưa bấm Add Answer: chưa có dòng nào của đoạn
    // này. Thà không gợi ý còn hơn đo từ một mốc chẳng liên quan rồi ghi đè.
    const rows = [row({ id: 1, frames: [1939] })];
    expect(rangeOwner(rows, { start: 5176, end: 8657 })).toBeNull();
  });

  it("prefers the row nearest the middle when several sit inside", () => {
    // Điểm giữa là 3000. 2900 gần hơn 1200, dù 1200 đứng trước trong danh sách.
    const rows = [
      row({ id: 1, frames: [1200] }),
      row({ id: 2, frames: [2900] }),
    ];
    expect(rangeOwner(rows, { start: 1000, end: 5000 })?.id).toBe(2);
  });

  it("keeps the higher-ranked row when two are equally close", () => {
    const rows = [
      row({ id: 1, frames: [900] }),
      row({ id: 2, frames: [1100] }),
    ];
    expect(rangeOwner(rows, { start: 0, end: 2000 })?.id).toBe(1);
  });

  it("counts a row sitting exactly on an edge as inside", () => {
    const rows = [row({ id: 1, frames: [5176] })];
    expect(rangeOwner(rows, { start: 5176, end: 8657 })?.id).toBe(1);
  });

  it("reads the interval the same way whether it was pinned forwards or back", () => {
    const rows = [row({ id: 1, frames: [6916] })];
    expect(rangeOwner(rows, { start: 8657, end: 5176 })?.id).toBe(1);
  });

  it("has no owner for an empty basket", () => {
    expect(rangeOwner([], { start: 0, end: 100 })).toBeNull();
  });

  it("ignores a row with no frames rather than treating it as frame 0", () => {
    const rows = [row({ id: 1, frames: [] }), row({ id: 2, frames: [50] })];
    expect(rangeOwner(rows, { start: 0, end: 100 })?.id).toBe(2);
  });
});

describe("eventWindowFields", () => {
  it("turns each pinned event into a from/to pair of strings", () => {
    // Chuỗi vì đó là value của <input>: người dùng còn gõ đè lên được.
    const fields = eventWindowFields({
      0: { start: 3670, end: 3943 },
      2: { start: 5100, end: 5337 },
    });
    expect(fields.eventLo).toEqual({ 0: "3670", 2: "5100" });
    expect(fields.eventHi).toEqual({ 0: "3943", 2: "5337" });
  });

  it("reads an interval pinned backwards as the same interval", () => {
    // Bấm "Cuối" trước rồi mới bấm "Đầu" vẫn là cùng một đoạn video.
    const fields = eventWindowFields({ 0: { start: 3943, end: 3670 } });
    expect(fields.eventLo[0]).toBe("3670");
    expect(fields.eventHi[0]).toBe("3943");
  });

  it("drops an event whose two edges land on the same frame", () => {
    // Cửa sổ đóng ghi vào cũng chỉ ra đúng cái mặc định "hành động đứng yên",
    // nhưng lại làm ô đó trông như đã được xác nhận bằng tay.
    const fields = eventWindowFields({
      0: { start: 3670, end: 3943 },
      1: { start: 4200, end: 4200 },
    });
    expect(Object.keys(fields.eventLo)).toEqual(["0"]);
    expect(fields.eventHi[1]).toBeUndefined();
  });

  it("leaves unmarked events out entirely rather than inventing a window", () => {
    // Ghim E1 và E3, bỏ qua E2 và E4: hai mốc kia phải rơi về khung gốc trong
    // giỏ, không phải một khoảng do giao diện bịa ra.
    const fields = eventWindowFields({
      0: { start: 100, end: 200 },
      2: { start: 900, end: 950 },
    });
    expect(Object.keys(fields.eventLo).sort()).toEqual(["0", "2"]);
  });

  it("has nothing to say about a card where nothing was pinned", () => {
    expect(eventWindowFields({})).toEqual({ eventLo: {}, eventHi: {} });
  });

  it("skips a non-finite edge instead of writing NaN into the box", () => {
    const fields = eventWindowFields({ 0: { start: Number.NaN, end: 300 } });
    expect(fields.eventLo).toEqual({});
  });
});
