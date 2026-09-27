import { useCallback, useEffect, useState } from "react";

import { getDresCurrentTask, type DresCurrentTask } from "../../api/dres";

// Câu chung kết chỉ 4–5 phút; 3 giây như hàng chờ duyệt ở tab DRES. Giữa hai
// lần hỏi, đồng hồ tự đếm ở trình duyệt (liveClock).
const POLL_MS = 3000;

/**
 * Câu DRES đang chạy, hỏi lại mỗi 3 giây khi `enabled`.
 *
 * `receivedAt` là lúc nhận được câu trả lời — đồng hồ đếm tiếp từ mốc đó, chứ
 * không từ lúc gửi, để độ trễ mạng không cộng dồn vào số giây còn lại.
 */
export function useDresCurrentTask(enabled: boolean) {
  const [current, setCurrent] = useState<DresCurrentTask | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await getDresCurrentTask();
      setCurrent(next);
      setReceivedAt(Date.now());
      setError(null);
    } catch (e) {
      setCurrent(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, refresh]);

  return { current, receivedAt, error, refresh };
}
