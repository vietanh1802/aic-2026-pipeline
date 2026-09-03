import type { AnswerRow } from "../api/answers";

/**
 * The autofill arithmetic, lifted out of `AnswerBasket` so `BasketBody` can
 * share it between the dialog and the popup panel without duplicating it.
 */
export interface AutofillPlan {
  anchor: AnswerRow | null;
  autoCount: number;
  needed: number;
  span: number;
  /** Coverage lower bound in frames, clamped at 0. 0 when there is no anchor. */
  from: number;
  /** Coverage upper bound in frames. 0 when there is no anchor. */
  to: number;
}

/** Frames, as marked on the video. */
export interface MarkedRange {
  start: number;
  end: number;
}

/**
 * The step that makes autofill's spread exactly blanket a marked interval.
 *
 * Autofill covers `anchor ± span` where `span = ceil(needed / 2) * step`.
 * Solving that for the step that makes `span` reach the interval's farther
 * edge gives `halfWidth / steps`, where `halfWidth` is the anchor's distance
 * to whichever edge is farther — not the interval's own half-width, so an
 * off-centre anchor still gets fully covered rather than covered on average.
 *
 * Returns null when there is nothing to suggest: no rows are needed, an
 * input is not finite, or the anchor sits exactly on a single-frame interval
 * (`halfWidth` 0 — any positive step already covers it).
 */
export function suggestStep(
  anchorFrame: number,
  range: MarkedRange,
  needed: number
): number | null {
  if (
    !Number.isFinite(anchorFrame) ||
    !Number.isFinite(range.start) ||
    !Number.isFinite(range.end) ||
    !Number.isFinite(needed) ||
    needed <= 0
  ) {
    return null;
  }

  const halfWidth = Math.max(
    anchorFrame - Math.min(range.start, range.end),
    Math.max(range.start, range.end) - anchorFrame
  );
  if (halfWidth === 0) {
    return null;
  }

  const steps = Math.ceil(needed / 2);
  return Math.min(2000, Math.max(1, Math.round(halfWidth / steps)));
}

/**
 * Mốc mà một đoạn ghim đầu–cuối đang nói tới.
 *
 * Chỉ có MỘT `markedRange` tại một thời điểm — nó là dải ghim của video đang
 * mở — nhưng giỏ thì có nhiều mốc. Trước đây bước tự tính luôn đo từ khung của
 * dòng HẠNG 1, nên ghim đoạn thứ hai quanh khung 6916 lại đo khoảng cách từ
 * 1939 tới mép đoạn: ra một con số không phủ đúng đoạn nào cả, rồi con số đó
 * đè lên mọi mốc.
 *
 * Chủ của đoạn là dòng ghim tay có khung nằm TRONG đoạn — người dùng ghim hai
 * đầu rồi mới bấm Add Answer, nên dòng vừa sinh ra chắc chắn nằm trong đó.
 * Nhiều dòng cùng nằm trong thì lấy dòng gần GIỮA đoạn nhất: khung "sẽ nộp"
 * của dải ghim chính là điểm giữa, nên dòng sinh ra từ đoạn này gần nó nhất.
 *
 * Trả null khi không dòng nào nằm trong đoạn — lúc đó thà không gợi ý gì còn
 * hơn gợi ý một con số đo từ một mốc chẳng liên quan.
 */
export function rangeOwner(
  rows: AnswerRow[],
  range: MarkedRange
): AnswerRow | null {
  const low = Math.min(range.start, range.end);
  const high = Math.max(range.start, range.end);
  const middle = (low + high) / 2;

  let owner: AnswerRow | null = null;
  let bestGap = Infinity;
  for (const row of rows) {
    const frame = row.frames[0];
    if (!Number.isFinite(frame) || frame < low || frame > high) {
      continue;
    }
    const gap = Math.abs(frame - middle);
    // `<` chứ không phải `<=`: hoà thì giữ dòng đứng trước, tức thứ hạng cao
    // hơn — một luật cố định để cùng một giỏ luôn ra cùng một chủ.
    if (gap < bestGap) {
      owner = row;
      bestGap = gap;
    }
  }
  return owner;
}

/**
 * Hai đầu đã ghim cho từng mốc TRAKE, quy về đúng hình dạng hai ô "từ … đến …"
 * của bảng Điền tự động (`AutofillTuning.eventLo` / `eventHi`).
 *
 * Chuỗi chứ không phải số vì đó là giá trị của một `<input>`: người dùng còn
 * gõ đè lên được, và một ô đang xoá dở là chuỗi rỗng chứ không phải NaN.
 *
 * Bỏ qua mốc có hai đầu TRÙNG nhau. Cửa sổ đóng ghi vào cũng chỉ ra đúng cái
 * mặc định — "hành động này đứng yên" — nhưng lại làm ô đó trông như đã được
 * xác nhận bằng tay. `anyWindowOpen()` trong giỏ cũng đọc theo luật `hi > lo`
 * ấy để quyết định có gửi `event_ranges` hay không.
 */
export function eventWindowFields(marks: Record<number, MarkedRange>): {
  eventLo: Record<number, string>;
  eventHi: Record<number, string>;
} {
  const eventLo: Record<number, string> = {};
  const eventHi: Record<number, string> = {};
  for (const [key, mark] of Object.entries(marks)) {
    const position = Number(key);
    const low = Math.min(mark.start, mark.end);
    const high = Math.max(mark.start, mark.end);
    // Ghim ngược — bấm Cuối trước rồi mới bấm Đầu — vẫn là cùng một đoạn.
    if (!Number.isFinite(low) || !Number.isFinite(high) || low === high) {
      continue;
    }
    eventLo[position] = String(low);
    eventHi[position] = String(high);
  }
  return { eventLo, eventHi };
}

export function autofillPlan(
  rows: AnswerRow[],
  rowsPerQuery: number,
  step: number
): AutofillPlan {
  const anchor = rows[0] ?? null;
  const autoCount = rows.filter((row) => row.origin === "auto").length;
  const needed = Math.max(0, rowsPerQuery - rows.length);
  const span = Math.ceil(needed / 2) * step;

  if (!anchor) {
    return { anchor: null, autoCount, needed, span: 0, from: 0, to: 0 };
  }

  return {
    anchor,
    autoCount,
    needed,
    span,
    from: Math.max(0, anchor.frames[0] - span),
    to: anchor.frames[0] + span,
  };
}
