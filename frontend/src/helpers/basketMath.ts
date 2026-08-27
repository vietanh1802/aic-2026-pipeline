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
