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
