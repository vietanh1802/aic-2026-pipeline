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
 * KHÔNG CÒN AI GỌI kể từ khi giỏ chuyển sang một bước chung (`uniformStep`).
 *
 * Giữ lại vì nó trả lời một câu hỏi khác và câu hỏi đó vẫn còn giá trị: "một
 * mình mốc này, với đúng phần ngân sách của nó, cần bước bao nhiêu để phủ khít
 * đoạn đã khoanh". Đó là cách rải mật độ RIÊNG từng mốc — mỗi cửa sổ phủ khít
 * bằng một nửa ngân sách, nhưng đoạn hẹp bị rải dày hơn đoạn rộng. Chủ repo
 * chọn mật độ đồng đều thay vào đó, và mật độ đồng đều cần backend biết mép để
 * tự dừng (`reaches`), chứ không giải được ở riêng phía giao diện.
 *
 * Bộ test của nó vẫn chạy: nếu quay lại cách cũ thì đây là chỗ để quay lại.
 *
 * The step that makes autofill's spread exactly blanket a marked interval.
 *
 * Autofill covers `anchor ± span` where `span = steps * step`. Solving that
 * for the step that makes `span` reach the interval's farther edge gives
 * `halfWidth / steps`, where `halfWidth` is the anchor's distance to whichever
 * edge is farther — not the interval's own half-width, so an off-centre anchor
 * still gets fully covered rather than covered on average.
 *
 * `anchorCount` là số mốc CÙNG được rải, và nó chia nhỏ ngân sách dòng.
 * `autofill.plan()` ở backend đi vòng tròn — mỗi bội số k, mỗi dấu, lần lượt
 * từng mốc — nên N mốc thì mỗi mốc chỉ nhận `needed / N` dòng, tức
 * `ceil(needed / (2N))` bậc về mỗi phía.
 *
 * Bỏ qua N là nguồn của một lỗi âm thầm: ghim đoạn rộng 300 lúc có một mốc ra
 * bước 3 (150/50), thêm mốc thứ hai thì ngân sách của mốc đầu tụt còn một nửa
 * mà bước vẫn 3, nên nó chỉ còn với tới ±72 thay vì ±150. Đoạn người dùng đã
 * khoanh không còn được phủ, mà trên màn hình không có gì nói ra điều đó.
 *
 * Returns null when there is nothing to suggest: no rows are needed, an
 * input is not finite, or the anchor sits exactly on a single-frame interval
 * (`halfWidth` 0 — any positive step already covers it).
 */
export function suggestStep(
  anchorFrame: number,
  range: MarkedRange,
  needed: number,
  anchorCount = 1
): number | null {
  if (
    !Number.isFinite(anchorFrame) ||
    !Number.isFinite(range.start) ||
    !Number.isFinite(range.end) ||
    !Number.isFinite(needed) ||
    !Number.isFinite(anchorCount) ||
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

  // `max(1, …)` vì gọi lúc chưa tick mốc nào thì anchorCount là 0, và chia cho
  // 0 ra Infinity — bước rơi về 1 và rải đặc kín một đoạn dài.
  const share = Math.max(1, Math.floor(anchorCount));
  const steps = Math.max(1, Math.ceil(needed / (2 * share)));
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

/** Số dòng `step` sinh ra khi mỗi mốc dừng ở mép cửa sổ của nó. */
function rowsAtStep(halfWidths: number[], step: number): number {
  return halfWidths.reduce(
    (total, halfWidth) => total + 2 * Math.floor(halfWidth / step),
    0
  );
}

/**
 * MỘT bước dùng chung cho mọi mốc, chọn sao cho tổng dòng vừa khít ngân sách.
 *
 * Mỗi mốc đi ra hai phía tới khi chạm mép cửa sổ của mình rồi nghỉ, nên với
 * cùng một bước thì cửa sổ rộng gấp đôi tự nhận gấp đôi số dòng. Không ai phải
 * tính tỉ lệ — nó rơi ra từ hình học. Đổi lại mọi frame sinh ra đều cách nhau
 * đúng bằng nhau, ở mọi mốc.
 *
 * Không phải một phép chia. `2 * Σ nửa-rộng / needed` là ước lượng tốt nhưng số
 * bậc phải làm tròn XUỐNG, nên phải dò một nhịp. Với hai đoạn 300 và 500 trong
 * giỏ 100 dòng (ước lượng 8.16):
 *
 *     bước 7 → 42 + 70 = 112 dòng
 *     bước 8 → 36 + 62 =  98 dòng ✓  vừa khít
 *     bước 9 → 32 + 54 =  86 dòng, bỏ phí 12 chỗ
 *
 * Lấy bước LỚN NHẤT mà tổng vẫn ĐỦ `needed` — tức bước cuối cùng còn dùng hết
 * ngân sách. Không phải "bước nhỏ nhất mà không vượt": luật đó nghe an toàn
 * hơn nhưng bỏ phí dòng. Một mốc, cửa sổ 300, còn thiếu 98 dòng:
 *
 *     bước 3 → 100 dòng, endpoint cắt còn 98, phủ ±147
 *     bước 4 →  74 dòng,                      phủ ±148
 *
 * Chọn 4 thì được thêm 1 frame tầm với mà mất 24 ứng viên. R@k đếm ứng viên,
 * nên 3 mới đúng.
 *
 * Vượt một chút thì không sao: endpoint đã chặn ở `needed` (`added >= needed`
 * thì dừng), nên giỏ không bao giờ lố. Phần bị cắt là các bậc XA tâm nhất, tức
 * mép cửa sổ hụt vài frame — rẻ hơn nhiều so với để trống hàng chục dòng. Và
 * vì lấy bước lớn nhất còn đủ, mức vượt luôn nhỏ: bước kế tiếp đã thiếu rồi.
 *
 * Trả null khi không có gì để tính: chưa cần dòng nào, hoặc chưa mốc nào được
 * khoanh đoạn.
 */
export function uniformStep(
  halfWidths: number[],
  needed: number
): number | null {
  const usable = halfWidths.filter(
    (halfWidth) => Number.isFinite(halfWidth) && halfWidth > 0
  );
  if (!Number.isFinite(needed) || needed <= 0 || usable.length === 0) {
    return null;
  }

  const total = usable.reduce((sum, halfWidth) => sum + halfWidth, 0);
  let step = Math.max(1, Math.min(2000, Math.floor((2 * total) / needed)));
  // Ước lượng lệch được cả hai phía, nên đi cả hai. Mỗi vòng đổi 1 và bước bị
  // chặn trong [1, 2000], nên không nhánh nào chạy mãi.
  while (step < 2000 && rowsAtStep(usable, step + 1) >= needed) {
    step += 1;
  }
  // Cửa sổ quá hẹp để lấp đầy giỏ thì không bước nào đủ — lúc đó lấy bước mịn
  // nhất, và giỏ đơn giản là không có đủ frame để điền. Bịa thêm bằng cách rải
  // ra ngoài cửa sổ là đi ngược điều người dùng vừa khoanh.
  while (step > 1 && rowsAtStep(usable, step) < needed) {
    step -= 1;
  }
  return step;
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
