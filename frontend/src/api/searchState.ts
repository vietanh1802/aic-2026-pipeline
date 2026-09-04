import { apiFetch } from "./base";
import type { Person } from "./board";

/**
 * Tham số search kèm theo truy vấn.
 *
 * Đủ để dựng lại y hệt màn hình của người kia. Thiếu một cái là "Coi X làm" ra
 * một danh sách khác với danh sách X đang nhìn — mà đúng cái đó mới là điểm
 * của tính năng này.
 */
export interface SearchStateParams {
  resultLimit?: string;
  topM?: number;
  useRerank?: boolean;
  singleModel?: string;
  ocrStripDiacritics?: boolean;
}

export interface SearchState {
  user: Pick<Person, "id" | "username" | "display_name">;
  query_text: string;
  search_type: string;
  params: SearchStateParams;
  /** Tên keyframe người này bấm vào, vd "L21_V001-0028-3175.jpg". */
  picked_frame: string | null;
  picked_video: string | null;
  picked_frame_idx: number | null;
  updated_at: string;
}

export interface SearchStateInput {
  query_text: string;
  search_type: string;
  params: SearchStateParams;
  picked_frame?: string | null;
  picked_video?: string | null;
  picked_frame_idx?: number | null;
}

/** Ghi đè trạng thái của chính mình trên câu này. */
export function saveSearchState(
  taskId: number,
  state: SearchStateInput
): Promise<{ ok: boolean }> {
  return apiFetch(`/api/tasks/${taskId}/search-state`, {
    method: "PUT",
    body: JSON.stringify(state),
  });
}

export function listSearchStates(
  taskId: number
): Promise<{ states: SearchState[] }> {
  return apiFetch(`/api/tasks/${taskId}/search-states`);
}

/** Một khung đã chốt trên một truy vấn. */
export interface HistoryPick {
  video: string;
  frame: number;
  /** Tên keyframe của thẻ đã bấm, null khi chốt trong popup sau khi tua. */
  name: string | null;
}

/** Một mục lịch sử: cùng hình dạng trạng thái, thêm id và lúc gõ lần đầu. */
export interface SearchHistoryEntry extends SearchState {
  id: number;
  created_at: string;
  /**
   * MỌI khung đã chốt trên truy vấn này, theo thứ tự bấm.
   *
   * `picked_*` kế thừa từ SearchState chỉ mang khung MỚI NHẤT — một lượt tìm
   * thường chốt nhiều khung, và trước đây mỗi lần chốt lại ghi đè lần trước
   * nên bảng này chỉ còn khung cuối.
   *
   * Dòng ghi trước khi có cột `picks` vẫn ra một phần tử: backend dựng nó lại
   * từ `picked_*`, nên chỗ hiển thị chỉ phải biết một hình dạng.
   */
  picks: HistoryPick[];
}

/**
 * MỌI truy vấn cả nhóm đã từng gõ cho câu này, mới nhất trước.
 *
 * Khác listSearchStates ở chỗ đó chỉ trả một dòng mỗi người — thứ họ đang gõ
 * ngay bây giờ. Hàm này giữ cả những câu đã bỏ, nên mở lại được truy vấn Bằng
 * thử hồi mười phút trước kể cả khi Bằng đã chuyển sang cách khác.
 */
export function listSearchHistory(
  taskId: number,
  limit = 200
): Promise<{ entries: SearchHistoryEntry[] }> {
  return apiFetch(`/api/tasks/${taskId}/search-history?limit=${limit}`);
}

/** "mine" = chỉ dòng của mình; "all" = cả nhóm, backend đòi quyền admin. */
export type ClearHistoryScope = "mine" | "all";

/**
 * Dọn lịch sử tìm của một câu. Trả về SỐ DÒNG đã xoá.
 *
 * Không đụng tới search-state: bảng "cả nhóm đang tìm câu này" là thứ khác, và
 * người vừa xoá vẫn còn nguyên truy vấn trên màn hình. Nghĩa là bấm tiếp một
 * khung trên chính truy vấn đó sẽ ghi lại một mục mới — đúng, vì họ vẫn đang
 * tìm nó.
 */
export function clearSearchHistory(
  taskId: number,
  scope: ClearHistoryScope
): Promise<{ removed: number }> {
  return apiFetch(`/api/tasks/${taskId}/search-history?scope=${scope}`, {
    method: "DELETE",
  });
}
