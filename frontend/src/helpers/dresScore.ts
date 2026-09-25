import type { DresClock } from "../api/dres";

/**
 * Công thức điểm vòng chung kết (HD-ChungKet-2026.pdf, HUONG-DAN-NOP-BAI.pdf):
 *   f(t) = 1 − t/T,  điểm = max(0, 50 + 50·f(t) − 10·k)
 * với k = số lần sai TRƯỚC lần đúng đầu tiên. TRAKE đúng một phần (≥ 50% mốc)
 * được nửa số đó.
 *
 * Chỉ để người bấm nộp thấy cái giá của việc chờ (câu 5 phút: 6 giây = 1 điểm)
 * so với cái giá của một lần sai (10 điểm). Điểm thật do DRES tính.
 */
export const BASE_POINTS = 50;
export const MAX_POINTS = 100;
export const WRONG_PENALTY = 10;

export function scoreIfCorrectNow(
  durationS: number | null | undefined,
  elapsedS: number,
  wrong: number
): number | null {
  if (!durationS || durationS <= 0) {
    return null;
  }
  const t = Math.min(Math.max(elapsedS, 0), durationS);
  const timeFactor = 1 - t / durationS;
  return Math.max(
    0,
    BASE_POINTS + (MAX_POINTS - BASE_POINTS) * timeFactor - WRONG_PENALTY * wrong
  );
}

/**
 * Đồng hồ tại thời điểm `nowMs`, từ ảnh chụp server trả về lúc `receivedAtMs`.
 * Server chỉ hỏi 3 giây một lần; đếm tiếp ở trình duyệt để số giây không nhảy
 * cóc. Không bao giờ âm.
 */
export function liveClock(
  clock: DresClock,
  receivedAtMs: number,
  nowMs: number
): { timeLeft: number | null; elapsed: number } {
  const drift = Math.max(0, (nowMs - receivedAtMs) / 1000);
  return {
    timeLeft:
      clock.time_left === null ? null : Math.max(0, clock.time_left - drift),
    elapsed: clock.time_elapsed + drift,
  };
}

/** Còn dưới bao nhiêu giây thì coi là "sắp hết giờ" (đỏ). */
export const RED_SECONDS = 30;

/**
 * Xanh → vàng khi còn dưới một nửa thời gian → đỏ khi sắp hết giờ, như portal
 * của BTC. Không biết tổng thời gian thì chỉ dựa vào mốc đỏ.
 */
export function clockTone(
  timeLeft: number | null,
  durationS: number | null | undefined
): "green" | "yellow" | "red" {
  if (timeLeft === null) {
    return "green";
  }
  if (timeLeft <= RED_SECONDS) {
    return "red";
  }
  if (durationS && timeLeft <= durationS / 2) {
    return "yellow";
  }
  return "green";
}

/** mm:ss, làm tròn LÊN: còn 0,4 giây vẫn hiện 00:01 chứ không phải 00:00. */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** DRES đặt tên loại câu tự do; TRAKE là loại duy nhất có điểm một phần. */
export function isTrakeTask(taskType: string, taskGroup: string): boolean {
  return /trake/i.test(`${taskType} ${taskGroup}`);
}
