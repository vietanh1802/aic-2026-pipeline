import { create } from "zustand";

import type { SpreadDirection } from "../api/answers";

/**
 * Phần chỉnh của bảng "Điền tự động", giữ theo TỪNG CÂU.
 *
 * Trước đây tất cả những thứ này là `useState` trong `BasketBody`. Mà giỏ được
 * dựng ở HAI chỗ — hộp thoại của nút "Giỏ" (`AnswerBasket`) và cột bên video
 * (`AnswerPanel`) — nên đó là hai instance khác nhau, mỗi cái một bộ state.
 * `AnswerBasket` lại `return null` khi đóng, tức mỗi lần mở là một instance
 * mới toanh. Kết quả: bước tự tính 11 và 137 vừa tính xong bên cột video, bấm
 * "Giỏ" ra là cả hai mốc về 25 mặc định.
 *
 * Để trong store thì hai chỗ dựng cùng đọc một bản ghi, và bản ghi sống lâu
 * hơn cái hộp thoại. Khoá theo `task.id` vì mỗi câu tự rải theo cách của nó —
 * bước của câu 3 không nói gì về câu 4.
 *
 * KHÔNG `persist` xuống localStorage: đây là con số tính từ đoạn vừa ghim
 * trong phiên này. Tải lại trang thì các mốc được ghim lại và nó tự tính lại,
 * còn giữ một con số cũ qua nhiều ngày thì chỉ tạo cảm giác nó đúng.
 */
export interface AutofillTuning {
  /** Ô "Bước" chung — mặc định cho mốc chưa có số riêng. */
  step: number;
  /** Chữ đang nằm trong ô đó, có thể rỗng hoặc đang gõ dở. */
  stepText: string;
  /** Người dùng đã tự gõ chưa. Rồi thì giao diện thôi tính giùm. */
  stepEdited: boolean;
  /**
   * Đoạn ghim gần nhất đã xử lý, dạng "đầu:cuối".
   *
   * Có mặt vì việc "ghim lại hai đầu thì trả quyền tự tính về cho giao diện"
   * trước đây làm bằng một `useEffect` phụ thuộc vào hai đầu — mà effect thì
   * chạy cả lúc MỚI GẮN. Khi state còn nằm trong component thì mới gắn cũng là
   * mới tinh nên không ai để ý; giờ state sống lâu hơn component, mỗi lần mở
   * hộp thoại sẽ xoá mất cờ `stepEdited` mà người dùng vừa giành lấy. So với
   * khoá này thì phân biệt được "đoạn đổi thật" với "vừa mở lại giỏ".
   */
  markKey: string | null;
  /** Bước người dùng GÕ cho riêng một mốc, khoá theo id dòng. */
  stepById: Record<number, string>;
  /** Bước giao diện TỰ TÍNH cho riêng một mốc, khoá theo id dòng. */
  autoStepById: Record<number, number>;
  /** Chiều rải của riêng một mốc. */
  dirById: Record<number, SpreadDirection>;
  /**
   * Các dòng bị BỎ tick, không phải các dòng được tick.
   *
   * Giữ mặt trái để một dòng vừa thêm vào giỏ tự động được tính là mốc. Mảng
   * chứ không phải Set: store là dữ liệu thuần, và `Set` làm mọi chỗ cập nhật
   * phải nhớ sao chép trước khi sửa.
   */
  anchorOff: number[];
  /** TRAKE: hai đầu và chiều của từng hành động, khoá theo vị trí sự kiện. */
  eventLo: Record<number, string>;
  eventHi: Record<number, string>;
  eventDir: Record<number, SpreadDirection>;
}

/**
 * TRAKE được chấm trong một cửa sổ mà luật ghi là "thường dưới 10 khung", nên
 * bước một giây sẽ nhảy qua mất. Các loại còn lại lấy 25 = một giây ở 25 fps.
 *
 * Trước đây con số này do một `useEffect([task.type])` đặt vào sau khi gắn:
 *
 *     useEffect(() => { setStep(task.type === "trake" ? 2 : 25); ... }, [task.type])
 *
 * Bỏ effect đó đi vì `task.type` không bao giờ đổi trong một bản ghi — cùng một
 * `task.id` thì luôn cùng loại — nên nó chỉ còn tác dụng duy nhất là dội lại
 * mặc định mỗi lần component gắn, tức xoá đúng thứ store này sinh ra để giữ.
 */
export function defaultTuning(taskType: string): AutofillTuning {
  const step = taskType === "trake" ? 2 : 25;
  return {
    step,
    stepText: String(step),
    stepEdited: false,
    markKey: null,
    stepById: {},
    autoStepById: {},
    dirById: {},
    anchorOff: [],
    eventLo: {},
    eventHi: {},
    eventDir: {},
  };
}

interface AutofillState {
  byTask: Record<number, AutofillTuning>;
  /** Sửa vài trường của một câu, giữ nguyên phần còn lại. */
  patch: (
    taskId: number,
    taskType: string,
    change: Partial<AutofillTuning>
  ) => void;
}

export const useAutofillStore = create<AutofillState>((set) => ({
  byTask: {},
  patch: (taskId, taskType, change) =>
    set((state) => ({
      byTask: {
        ...state.byTask,
        [taskId]: {
          ...(state.byTask[taskId] ?? defaultTuning(taskType)),
          ...change,
        },
      },
    })),
}));
