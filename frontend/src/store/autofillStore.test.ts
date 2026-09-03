import { beforeEach, describe, expect, it } from "vitest";

import { defaultTuning, useAutofillStore } from "./autofillStore";

// Store là singleton, nên mỗi test phải bắt đầu từ bàn trống — nếu không thì
// thứ tự chạy quyết định kết quả.
beforeEach(() => {
  useAutofillStore.setState({ byTask: {} });
});

const read = (taskId: number) => useAutofillStore.getState().byTask[taskId];
const patch = useAutofillStore.getState().patch;

describe("defaultTuning", () => {
  it("gives TRAKE a 2-frame step and everything else 25", () => {
    // TRAKE được chấm trong cửa sổ "thường dưới 10 khung", nên bước một giây
    // (25 khung ở 25 fps) sẽ nhảy qua mất.
    expect(defaultTuning("trake").step).toBe(2);
    expect(defaultTuning("kis").step).toBe(25);
    expect(defaultTuning("qa").step).toBe(25);
  });

  it("keeps the text box in step with the number it starts on", () => {
    expect(defaultTuning("trake").stepText).toBe("2");
    expect(defaultTuning("kis").stepText).toBe("25");
  });

  it("starts with nothing pinned, nothing typed and nothing computed", () => {
    const tuning = defaultTuning("kis");
    expect(tuning.stepEdited).toBe(false);
    expect(tuning.markKey).toBeNull();
    expect(tuning.stepById).toEqual({});
    expect(tuning.autoStepById).toEqual({});
    expect(tuning.anchorOff).toEqual([]);
  });
});

describe("useAutofillStore", () => {
  it("survives the mount that wrote it — the bug this store exists for", () => {
    // Cột bên video tính ra 11 cho mốc 1 và 36 cho mốc 2...
    patch(3, "kis", { step: 36, stepText: "36", autoStepById: { 1: 11, 2: 36 } });
    // ...rồi hộp thoại "Giỏ" mở ra. Đó là một instance BasketBody KHÁC, dựng
    // lại từ đầu. Trước đây nó đọc `useState` của chính nó nên ra 25 mặc định.
    expect(read(3).autoStepById).toEqual({ 1: 11, 2: 36 });
    expect(read(3).step).toBe(36);
  });

  it("fills the rest from the task type's defaults on the first patch", () => {
    patch(7, "trake", { stepEdited: true });
    expect(read(7).stepEdited).toBe(true);
    // Không gửi thì phải là mặc định của TRAKE, không phải 25 của loại khác.
    expect(read(7).step).toBe(2);
    expect(read(7).stepText).toBe("2");
  });

  it("leaves untouched fields alone on a later patch", () => {
    patch(3, "kis", { autoStepById: { 1: 11 } });
    patch(3, "kis", { stepEdited: true });
    expect(read(3).autoStepById).toEqual({ 1: 11 });
    expect(read(3).stepEdited).toBe(true);
  });

  it("keeps one task's tuning out of another's", () => {
    // Bước của câu 3 không nói gì về câu 4: mỗi câu rải quanh khung của nó.
    patch(3, "kis", { step: 11 });
    patch(4, "kis", { step: 137 });
    expect(read(3).step).toBe(11);
    expect(read(4).step).toBe(137);
  });

  it("replaces a map wholesale rather than merging it key by key", () => {
    // Người dùng bỏ tick một mốc: danh sách mới phải THAY danh sách cũ. Trộn
    // sâu thì bỏ tick xong không bao giờ tick lại được.
    patch(3, "kis", { anchorOff: [1, 2] });
    patch(3, "kis", { anchorOff: [2] });
    expect(read(3).anchorOff).toEqual([2]);
  });

  it("records the marked interval so a remount does not look like a new one", () => {
    // `markKey` là thứ phân biệt "người dùng ghim lại hai đầu" với "vừa mở lại
    // giỏ" — mở lại giỏ mà bị coi là ghim mới thì cờ stepEdited bị xoá và số
    // người dùng vừa gõ bị tính đè.
    patch(3, "kis", { markKey: "1410:2469", stepEdited: false });
    expect(read(3).markKey).toBe("1410:2469");
  });
});
