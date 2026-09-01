import { apiFetch } from "./base";

export interface Person {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "member";
}

export interface BoardTask {
  id: number;
  pack_id: number;
  code: string;
  type: "kis" | "qa" | "trake";
  query_text: string;
  question_text: string | null;
  n_events: number | null;
  event_labels: string[];
  /**
   * Ai TỪNG giành câu này thời còn Nhận/Nhả. Backend vẫn trả về vì cột trong
   * CSDL còn, nhưng không ai ghi vào nữa. Đừng dùng để quyết định quyền sửa —
   * giờ ai cũng sửa được, mỗi người một danh sách riêng.
   */
  owner: Person | null;
  /** Ai đã có đáp án cho câu này, kèm số dòng. Nhiều dòng nhất đứng trước. */
  contributors: Contributor[];
  /** Bài của ai được chọn để nộp. null = chưa chọn. */
  chosen_author_id: number | null;
  /** Tổng số dòng của MỌI người, không phải của riêng ai. */
  answer_count: number;
  verified_count: number;
  updated_at: string | null;
  claimed_at: string | null;
  version: number;
  viewers: { id: number; display_name: string; last_seen_at: string }[];
}

export interface BoardRound {
  id: number;
  label: string;
  source_filename: string;
  /** False when looking at a retired round rather than the live one. */
  active: boolean;
  deadline_at: string | null;
  server_time: string;
  rows_per_query: number;
}

export interface BoardResponse {
  round: BoardRound | null;
  tasks: BoardTask[];
  me: Person | null;
  /**
   * Số người đi thi, KHÔNG tính admin — mẫu số của cột "số người đã làm".
   *
   * Đếm ở backend chứ không viết cứng 5: thêm hay khoá một tài khoản là con số
   * phải đổi theo, mà mẫu số sai thì cả cột trở thành vô nghĩa.
   */
  team_size: number;
}

export function getBoard(packId?: number): Promise<BoardResponse> {
  const query = packId === undefined ? "" : `?pack_id=${packId}`;
  return apiFetch<BoardResponse>(`/api/board${query}`);
}

export interface Contributor {
  id: number;
  username: string;
  display_name: string;
  count: number;
}

/**
 * Chọn bài của ai làm bài nộp cho câu này. null = bỏ chọn.
 *
 * Ai cũng gọi được, không riêng admin: cả nhóm ngồi cùng lúc, bắt chờ một
 * người bấm là dựng lại đúng nút cổ chai mà việc bỏ Nhận/Nhả vừa gỡ.
 */
export function setChosenAuthor(
  taskId: number,
  authorId: number | null
): Promise<{ chosen_author_id: number | null }> {
  return apiFetch(`/api/tasks/${taskId}/chosen-author`, {
    method: "POST",
    body: JSON.stringify({ author_id: authorId }),
  });
}

/** Mọi danh sách của mọi người cho một câu — màn Export bày ra để chọn. */
export function answersByAuthor(taskId: number): Promise<{
  groups: { author: Person; count: number; answers: AnswerRowLite[] }[];
  chosen_author_id: number | null;
}> {
  return apiFetch(`/api/tasks/${taskId}/answers/by-author`);
}

export interface AnswerRowLite {
  id: number;
  rank: number;
  video_id: string;
  frames: number[];
  /** Đáp án chữ. Chỉ câu Q&A mới có, và đó chính là thứ được chấm. */
  answer_text: string | null;
  /** Cần cho patchAnswer: sửa mà gửi sai version thì backend trả 409. */
  version: number;
}

// claimTask/releaseTask đã bỏ cùng endpoint /claim và /release ở backend.
// Không để lại hàm bọc: giữ chúng chỉ khiến người sau gọi vào một URL đã 404.

export function heartbeat(taskId: number | null): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>("/api/presence", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId }),
  });
}

// ── Pack import ──────────────────────────────────────────────────────────────

export interface PreviewedFile {
  filename: string;
  matched: boolean;
  error: string | null;
  phase: string | null;
  code: string | null;
  type: "kis" | "qa" | "trake" | null;
  query_text: string;
  question_text: string | null;
  n_events: number | null;
  event_labels: string[];
  warnings: string[];
  lines: number;
}

export interface PreviewResponse {
  preview_token: string;
  source_filename: string;
  files: PreviewedFile[];
}

export const DEFAULT_PATTERN =
  "query-(?P<phase>p\\d+)-(?P<code>\\d+)-(?P<type>kis|qa|trake)\\.txt";

export function previewPack(
  file: File,
  filenamePattern: string
): Promise<PreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("filename_pattern", filenamePattern);
  // No Content-Type here on purpose — apiFetch leaves it off for FormData so the
  // browser can supply the multipart boundary.
  return apiFetch<PreviewResponse>("/api/admin/packs/preview", {
    method: "POST",
    body: form,
  });
}

export function commitPack(payload: {
  preview_token: string;
  round_label: string;
  filename_pattern: string;
  source_filename: string;
  edits: { filename: string; question_text: string | null }[];
}): Promise<{
  pack_id: number;
  round_label: string;
  tasks_created: number;
  skipped: number;
  /** Always false — a new round goes live only from the rounds screen. */
  active: boolean;
}> {
  return apiFetch("/api/admin/packs/commit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Rounds (admin) ───────────────────────────────────────────────────────────
//
// Importing creates a round; it no longer decides which one the team works in.
// That is what these are for.

export interface RoundPack {
  id: number;
  label: string;
  source_filename: string;
  imported_at: string;
  imported_by: Person | null;
  deadline_at: string | null;
  active: boolean;
  /** Non-null means soft-deleted: hidden everywhere, restorable, nothing lost. */
  deleted_at: string | null;
  task_count: number;
  answer_count: number;
}

export function listPacks(): Promise<{ packs: RoundPack[] }> {
  return apiFetch<{ packs: RoundPack[] }>("/api/admin/packs");
}

export function activatePack(packId: number): Promise<{ pack: RoundPack }> {
  return apiFetch<{ pack: RoundPack }>(`/api/admin/packs/${packId}/activate`, {
    method: "POST",
  });
}

export function patchPack(
  packId: number,
  // An empty deadline_at clears the countdown; omitting it leaves it alone.
  payload: { round_label?: string; deadline_at?: string }
): Promise<{ pack: RoundPack }> {
  return apiFetch<{ pack: RoundPack }>(`/api/admin/packs/${packId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/**
 * Xoá một vòng và mọi thứ dưới nó. KHÔNG khôi phục được.
 *
 * Trả về số lượng đã xoá chứ không trả về pack: hàng đó không còn tồn tại.
 * Backend từ chối nếu đó là vòng đang thi.
 *
 * restorePack() đã bỏ cùng endpoint /restore — xoá mềm không còn nữa.
 */
export function deletePack(
  packId: number
): Promise<{ deleted: boolean; tasks: number; answers: number }> {
  return apiFetch(`/api/admin/packs/${packId}`, { method: "DELETE" });
}

// ── Audit ────────────────────────────────────────────────────────────────────

export interface AuditEntry {
  id: number;
  at: string;
  action: string;
  target: string;
  summary: string;
  by: { id: number; username: string; display_name: string };
  /** Rows this entry can put back. 0 means nothing to restore. */
  restorable: number;
  restored_at: string | null;
}

/**
 * KHÔNG màn nào gọi hai hàm dưới nữa.
 *
 * Bảng nhật ký từng nằm cuối màn Evaluation, đã bỏ: nó liệt kê thao tác quản
 * trị — nhập gói, kích hoạt, xoá — trong khi màn đó là chỗ đọ bài. Thứ người
 * ta thật sự cần lần lại ở đây là lịch sử TÌM KIẾM, và cái đó giờ nằm trong
 * bảng "Cả nhóm đang tìm câu này" ở màn Search.
 *
 * Hai endpoint /api/admin/audit vẫn còn ở backend và vẫn ghi đủ; giữ hai hàm
 * bọc này vì đó vẫn là cách đúng để gọi chúng nếu cần dựng lại màn nhật ký.
 */
export function getAudit(limit = 100): Promise<{ entries: AuditEntry[] }> {
  return apiFetch<{ entries: AuditEntry[] }>(`/api/admin/audit?limit=${limit}`);
}

export function restoreFromAudit(
  entryId: number
): Promise<{ restored: number; skipped: number }> {
  return apiFetch(`/api/admin/audit/${entryId}/restore`, { method: "POST" });
}
