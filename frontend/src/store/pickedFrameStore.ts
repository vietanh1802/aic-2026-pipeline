import { create } from "zustand";

/**
 * Khung hình đang được khoanh đỏ trong lưới kết quả — khung BẠN đang chọn.
 *
 * Thay cho peerViewStore cũ, vốn giữ "tôi đang xem bài của ai" kèm một dải báo
 * và nút thoát. Cách đó sai mô hình: bấm "Coi An làm" không phải là mượn tạm
 * màn hình của An rồi trả lại, mà là LẤY LUÔN trạng thái của An làm của mình —
 * cùng truy vấn, cùng tham số, cùng khung đã chọn. Đã là của mình thì không có
 * gì để "thoát" cả.
 *
 * `from` chỉ để ghi công: chép từ ai. Null khi tự bấm chọn.
 */
interface PickedFrameState {
  /** Tên keyframe, vd "L21_V009-0224-20822.jpg". Null = chưa chọn khung nào. */
  frame: string | null;
  /** Tên người mình chép trạng thái từ đó, null nếu tự chọn. */
  from: string | null;
  set: (frame: string | null, from?: string | null) => void;
}

export const usePickedFrameStore = create<PickedFrameState>((set) => ({
  frame: null,
  from: null,
  set: (frame, from = null) => set({ frame, from }),
}));
