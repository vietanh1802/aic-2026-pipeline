import { create } from "zustand";

export type HealthStatus =
  | "checking"
  | "starting"
  | "ready"
  | "offline"
  | "failed";

export interface BackendHealth {
  status: HealthStatus;
  message: string;
  detail?: string;
}

/**
 * Backend còn sống không, và đã nạp xong index chưa.
 *
 * Nằm trong store vì hai chỗ cách xa nhau cùng cần nó: badge trên thanh điều
 * hướng (do AppNav vẽ, Root dựng) và ô Search (App.tsx khoá nút khi backend
 * chưa sẵn sàng). Để mỗi bên tự hỏi thì thành hai vòng lặp gọi /health mỗi 5
 * giây, và hai bên có thể hiện hai trạng thái khác nhau trong cùng một khoảnh
 * khắc — đúng lúc người dùng đang cố hiểu vì sao nút Search không bấm được.
 *
 * Chỉ ApiStatus ghi vào đây. Mọi chỗ khác chỉ đọc.
 */
interface HealthState {
  health: BackendHealth;
  setHealth: (health: BackendHealth) => void;
}

export const useHealthStore = create<HealthState>((set) => ({
  health: { status: "checking", message: "Checking API" },
  setHealth: (health) => set({ health }),
}));
