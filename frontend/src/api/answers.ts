import { apiFetch } from "./base";
import type { Person } from "./board";

export interface AnswerRow {
  id: number;
  task_id: number;
  rank: number;
  video_id: string;
  frames: number[];
  answer_text: string | null;
  origin: "auto" | "manual";
  created_by: Person | null;
  updated_by: Person | null;
  updated_at: string;
  version: number;
}

export function getAnswers(taskId: number): Promise<{ answers: AnswerRow[] }> {
  return apiFetch(`/api/tasks/${taskId}/answers`);
}

export function addAnswer(
  taskId: number,
  payload: {
    video_id: string;
    frames: number[];
    answer_text?: string | null;
    position?: "top" | { after_id: number };
  }
): Promise<{ answer: AnswerRow }> {
  return apiFetch(`/api/tasks/${taskId}/answers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function patchAnswer(
  answerId: number,
  payload: Partial<Pick<AnswerRow, "video_id" | "frames" | "answer_text">> & {
    version: number;
  }
): Promise<{ answer: AnswerRow }> {
  return apiFetch(`/api/answers/${answerId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAnswer(answerId: number): Promise<{ ok: boolean }> {
  return apiFetch(`/api/answers/${answerId}`, { method: "DELETE" });
}

/**
 * Empties one task's basket, manual pins included.
 *
 * Not the same as autofill's `clear`, which spares the manual rows so the
 * spread can be redone with a different step.
 *
 * KHÔNG màn nào gọi hàm này nữa. Nút "Xoá sạch" trên Export đã bỏ: từ khi mỗi
 * người một danh sách, nó xoá trắng công của một người trong một cú bấm. Giữ
 * hàm lại vì endpoint vẫn còn và đây vẫn là cách đúng để gọi nó — nhưng nếu
 * bạn định nối lại vào một nút nào đó, hãy đọc lại lý do nó bị gỡ trước.
 */
export function clearAnswers(
  taskId: number
): Promise<{ removed: number; total: number }> {
  return apiFetch(`/api/tasks/${taskId}/answers`, { method: "DELETE" });
}

export function reorderAnswer(
  taskId: number,
  payload: { answer_id: number; before_id?: number; after_id?: number }
): Promise<{ answers: AnswerRow[] }> {
  return apiFetch(`/api/tasks/${taskId}/answers/reorder`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Chiều rải quanh mốc. */
export type SpreadDirection = "both" | "up" | "down";

/**
 * Khoảng người dùng khoanh cho MỘT hành động của câu TRAKE.
 *
 * Xem video thấy hành động 1 nằm đâu đó giữa frame 90 và 120 thì gõ đúng hai
 * số đó. Chính xác hơn hẳn một "bước" chung: mỗi hành động dài ngắn khác nhau,
 * và cái người ta THẤY là hai đầu, không phải khoảng cách giữa các mẫu.
 */
export interface EventRange {
  lo: number;
  hi: number;
  mode: SpreadDirection;
}

export function autofillAnswers(
  taskId: number,
  payload: {
    limit?: number;
    step?: number;
    // clear drops the generated rows and stops; replace_auto drops and refills
    // in one call, which reads as a no-op from the UI.
    mode?: "append" | "replace_auto" | "clear";
    /**
     * Những dòng dùng làm mốc. Bỏ trống = mọi dòng ghim tay trong giỏ.
     *
     * Trước đây backend chỉ lấy dòng hạng 1, nên thấy bốn khung cùng đúng thì
     * ba khung kia phải tự ngồi tính số frame bằng tay.
     */
    anchor_ids?: number[];
    /** Bước riêng cho từng mốc, cùng thứ tự với anchor_ids. Bỏ trống = dùng `step`. */
    steps?: number[];
    direction?: SpreadDirection;
    directions?: SpreadDirection[];
    /**
     * Độ dời LỚN NHẤT của từng mốc — nửa rộng đoạn người dùng đã khoanh quanh
     * nó. 0 = mốc đó không có mép, đi tới khi hết ngân sách.
     *
     * Đây là thứ cho phép mọi mốc dùng chung một bước mà đoạn dài hơn vẫn nhận
     * nhiều dòng hơn: cùng bước, cửa sổ hẹp chạm mép sớm rồi nghỉ, cửa sổ rộng
     * đi tiếp. Không ai phải tính tỉ lệ — nó rơi ra từ hình học.
     *
     * Danh sách NGẮN hơn số mốc thì phần còn lại coi như không có mép; backend
     * cố ý không rơi về phần tử cuối như `steps`, vì làm vậy là gán cửa sổ của
     * mốc này cho mốc khác.
     */
    reaches?: number[];
    /**
     * TRAKE: khoảng của từng hành động.
     *
     * Có mặt thì backend đổi hẳn cách rải — giữ nguyên N−1 mốc của dòng neo và
     * chỉ đổi MỘT mốc mỗi dòng. TRAKE chấm theo từng mốc nên sai một mốc chỉ
     * mất 1/N; giữ phần đúng của dòng hạng 1 đáng giá hơn đoán lại cả bộ.
     */
    event_ranges?: EventRange[];
  }
): Promise<{ added: number; removed?: number; total: number }> {
  return apiFetch(`/api/tasks/${taskId}/answers/autofill`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Export ───────────────────────────────────────────────────────────────────

/**
 * KHÔNG màn nào gọi hàm này nữa.
 *
 * Nút "Kiểm tra" trên màn Export đã bỏ: với một gói vừa nhập nó đổ ra đúng 30
 * dòng "chưa ai làm — sẽ nộp file rỗng", nhiều tới mức che mất cảnh báo thật.
 * Endpoint /api/export/validate vẫn còn và vẫn báo được những thứ đáng giá —
 * thiếu dòng, đáp án bỏ trống, dấu phẩy trong đáp án, dòng trùng, TRAKE thiếu
 * mốc. Nếu nối lại, hãy lọc bớt mức "info" trước.
 */
export interface ExportIssue {
  task_code: string;
  severity: "warning" | "info";
  message: string;
}

export function validateExport(
  packId: number
): Promise<{ ready: boolean; issues: ExportIssue[] }> {
  return apiFetch(`/api/export/validate?pack_id=${packId}`);
}

export function previewExport(taskId: number): Promise<{
  filename: string;
  rows: number;
  bytes: number;
  content: string;
}> {
  return apiFetch(`/api/export/preview?task_id=${taskId}`);
}

export function exportZipUrl(packId: number): string {
  return `/api/export/zip?pack_id=${packId}`;
}

/**
 * Số vòng trong TÊN FILE của ban tổ chức — "p1", "p2", "p3".
 *
 * Không phải nhãn hiển thị: nó đi thẳng vào tên mọi file trong gói nộp
 * (`query-p2-15-qa.csv`). Đặt sai thì bài bị chấm hỏng mà giao diện không có
 * dấu hiệu gì, nên `sample_filename` luôn đi kèm để nhìn thấy hậu quả.
 */
export interface ExportPhase {
  phase: string;
  /** True khi phải đoán vì gói nhập trước đây không lưu số vòng. */
  guessed: boolean;
  sample_filename: string | null;
}

export function getExportPhase(packId: number): Promise<ExportPhase> {
  return apiFetch(`/api/export/phase?pack_id=${packId}`);
}

export function setExportPhase(
  packId: number,
  phase: string
): Promise<ExportPhase> {
  return apiFetch(`/api/export/phase?pack_id=${packId}`, {
    method: "POST",
    body: JSON.stringify({ phase }),
  });
}
