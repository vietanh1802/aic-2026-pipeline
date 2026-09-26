import { apiFetch } from "./base";

/**
 * Nộp bài vòng chung kết qua DRES — backend đứng giữa (app/routers/dres.py).
 *
 * Trình duyệt không bao giờ gọi thẳng DRES: mật khẩu đội nằm trên server, và
 * mọi lần nộp của cả đội đi qua một chỗ để chặn trùng. Thành viên chỉ ĐỀ XUẤT;
 * chỉ admin duyệt, và chỉ bước duyệt mới ra mạng.
 */

export type DresTaskType = "kis" | "qa" | "trake";

export type DresSubmissionStatus =
  | "proposed"
  | "sending"
  | "sent"
  | "failed"
  | "rejected";

export type DresVerdict = "CORRECT" | "WRONG" | "INDETERMINATE" | "UNDECIDABLE";

/**
 * Ai được bấm gửi lên DRES. 'admin_only' (mặc định): thành viên đề xuất, admin
 * duyệt. 'everyone': ai tìm ra thì người đó nộp luôn. Server kiểm lại lúc bấm.
 */
export type DresSubmitMode = "admin_only" | "everyone";

export interface DresStatus {
  configured: boolean;
  base_url: string;
  submit_mode: DresSubmitMode;
  username?: string;
  logged_in?: boolean;
  evaluation_id?: string | null;
  evaluation_name?: string | null;
  updated_at?: string;
}

export interface DresEvaluation {
  id: string;
  name: string;
  type: string;
  status: string;
}

export interface DresTask {
  templateId?: string | null;
  name: string;
  taskGroup: string;
  taskType: string;
  /** Giây. */
  duration: number | null;
}

/**
 * Đồng hồ câu đang chạy, giây, tại lúc server trả lời. 'estimate' = DRES không
 * cho xem (403), server tự đếm từ lúc nó thấy câu này — có thể trễ vài giây.
 */
export interface DresClock {
  time_left: number | null;
  time_elapsed: number;
  source: "dres" | "estimate";
}

/** Các lần ĐÃ GỬI cho câu đang chạy. `wrong` là k trong công thức điểm. */
export interface DresTally {
  wrong: number;
  indeterminate: number;
  correct: boolean;
}

export interface DresCurrentTask {
  evaluation_id: string;
  task: DresTask | null;
  clock: DresClock | null;
  tally: DresTally | null;
}

export interface DresSubmission {
  id: number;
  created_at: string;
  proposed_by_name: string;
  reviewed_by_name: string | null;
  task_type: DresTaskType;
  video_id: string;
  frames: number[];
  times_ms: number[];
  answer_text: string | null;
  evaluation_id: string;
  dres_task_name: string | null;
  /** JSON gửi đi NGUYÊN VĂN — thứ admin duyệt cũng là thứ ra mạng. */
  payload: { answerSets: { answers: Record<string, unknown>[] }[] };
  status: DresSubmissionStatus;
  reviewed_at: string | null;
  verdict: DresVerdict | null;
  dres_description: string | null;
  http_status: number | null;
  error: string | null;
  /** Những điểm BTC chưa nói rõ mà bài này dính vào. */
  warnings: string[];
}

export interface DresProposal {
  task_type: DresTaskType;
  video_id: string;
  /** Đúng MỘT trong hai: frames (từ keyframe) hoặc times_ms (từ trình phát). */
  frames?: number[];
  times_ms?: number[];
  answer?: string;
}

export function getDresStatus(): Promise<DresStatus> {
  return apiFetch<DresStatus>("/api/dres/status");
}

export function putDresConfig(config: {
  base_url: string;
  username: string;
  password: string;
}): Promise<DresStatus & { evaluations: DresEvaluation[] }> {
  return apiFetch("/api/dres/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export function getDresEvaluations(): Promise<{ evaluations: DresEvaluation[] }> {
  return apiFetch("/api/dres/evaluations");
}

export function putDresEvaluation(evaluationId: string): Promise<DresStatus> {
  return apiFetch<DresStatus>("/api/dres/evaluation", {
    method: "PUT",
    body: JSON.stringify({ evaluation_id: evaluationId }),
  });
}

export function putDresSubmitMode(mode: DresSubmitMode): Promise<DresStatus> {
  return apiFetch<DresStatus>("/api/dres/submit-mode", {
    method: "PUT",
    body: JSON.stringify({ mode }),
  });
}

/**
 * Người này có được tự gửi bài không. Chỉ để quyết định bày nút nào ra — server
 * vẫn đọc lại chế độ lúc bấm, vì admin có thể vừa đổi mà tab này chưa cập nhật.
 */
export function canSubmitDres(
  role: string | undefined,
  status: DresStatus | null
): boolean {
  return role === "admin" || status?.submit_mode === "everyone";
}

export function getDresCurrentTask(): Promise<DresCurrentTask> {
  return apiFetch<DresCurrentTask>("/api/dres/current-task");
}

/** Một lần Search của ai đó trong đội, cho câu DRES đang chạy. */
export interface DresQuery {
  id: number;
  created_at: string;
  display_name: string;
  query_text: string;
  search_type: string;
}

export interface DresQueryList {
  /** null khi không có câu nào đang chạy — `reason` nói vì sao. */
  task_name: string | null;
  queries: DresQuery[];
  reason: string | null;
}

export function listDresQueries(): Promise<DresQueryList> {
  return apiFetch<DresQueryList>("/api/dres/queries");
}

/**
 * Ghi một lần Search vào câu DRES đang chạy. Server tự hỏi DRES câu nào đang
 * chạy; không có câu nào thì nó bỏ qua, không báo lỗi.
 */
export async function recordDresQuery(queryText: string, searchType: string): Promise<void> {
  await apiFetch("/api/dres/queries", {
    method: "POST",
    body: JSON.stringify({ query_text: queryText, search_type: searchType }),
  });
  // Danh sách bên dưới ô tìm kiếm tải lại ngay thay vì chờ nhịp poll 5 giây:
  // người vừa gõ phải thấy câu của mình nằm trong đó.
  window.dispatchEvent(new Event(DRES_QUERIES_CHANGED));
}

export const DRES_QUERIES_CHANGED = "dres-queries-changed";

export function listDresSubmissions(
  limit = 50
): Promise<{ submissions: DresSubmission[] }> {
  return apiFetch(`/api/dres/submissions?limit=${limit}`);
}

export function proposeDresSubmission(
  proposal: DresProposal
): Promise<DresSubmission> {
  return apiFetch<DresSubmission>("/api/dres/submissions", {
    method: "POST",
    body: JSON.stringify(proposal),
  });
}

export function approveDresSubmission(
  id: number,
  force = false
): Promise<DresSubmission> {
  return apiFetch<DresSubmission>(
    `/api/dres/submissions/${id}/approve${force ? "?force=true" : ""}`,
    { method: "POST" }
  );
}

export function rejectDresSubmission(id: number): Promise<DresSubmission> {
  return apiFetch<DresSubmission>(`/api/dres/submissions/${id}/reject`, {
    method: "POST",
  });
}

/** Chuỗi ngắn gọn của bài nộp để hiện trong hộp xác nhận và danh sách. */
export function describePayload(submission: DresSubmission): string {
  const answer = submission.payload.answerSets[0]?.answers[0] ?? {};
  if (typeof answer.text === "string") {
    return answer.text;
  }
  return `${String(answer.mediaItemName)} @ ${String(answer.start)} ms`;
}

/** mm:ss.mmm — đủ để đối chiếu với trình phát. */
export function formatMs(ms: number): string {
  const total = Math.max(0, Math.round(ms));
  const minutes = Math.floor(total / 60000);
  const seconds = Math.floor((total % 60000) / 1000);
  const millis = total % 1000;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}
