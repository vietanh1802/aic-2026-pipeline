import { create } from "zustand";

/**
 * "Tôi đang xem lại đường tìm của ai."
 *
 * Tách khỏi queryStore vì hai thứ khác hẳn nhau: queryStore là Ô NHẬP — nó
 * chứa cái đang gõ dở, thay đổi theo từng phím. Cái này là một NHÃN dán lên
 * lần search vừa rồi, nói rằng lưới kết quả đang hiện là của người khác chứ
 * không phải của tôi.
 *
 * Nó cũng phải sống lâu hơn một lần render của App: vòng khoanh đỏ nằm trong
 * FrameDisplay, ở tận đáy cây component, còn nút "Coi X làm" nằm trong panel
 * bên trên — luồn state qua bốn tầng props chỉ để nối hai chỗ đó là không đáng.
 */
export interface PeerView {
  userId: number;
  displayName: string;
  /** Tên keyframe người đó đã bấm. null = họ tìm nhưng chưa chọn khung nào. */
  pickedFrame: string | null;
  pickedVideo: string | null;
  pickedFrameIdx: number | null;
}

interface PeerViewState {
  viewing: PeerView | null;
  view: (peer: PeerView) => void;
  /** Quay lại việc của mình. Gọi khi tự bấm Search hoặc bấm "Thoát". */
  clear: () => void;
}

export const usePeerViewStore = create<PeerViewState>((set) => ({
  viewing: null,
  view: (peer) => set({ viewing: peer }),
  clear: () => set({ viewing: null }),
}));
