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
