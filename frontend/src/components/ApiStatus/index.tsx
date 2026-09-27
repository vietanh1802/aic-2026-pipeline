import { useEffect } from "react";

import { videoSearchApi } from "../../types/api";
import type { HealthResponse } from "../../types/api";
import {
  useHealthStore,
  type BackendHealth,
  type HealthStatus,
} from "../../store/healthStore";

const POLL_MS = 5000;

const CLASS_NAME: Record<HealthStatus, string> = {
  checking: "border-proto-line bg-white text-proto-muted",
  starting: "border-[#d4a017] bg-[#d4a017]/12 text-[#8a6a0f]",
  ready: "border-[#5db872] bg-[#5db872]/12 text-[#3d7a4d]",
  offline: "border-[#c64545] bg-[#c64545]/10 text-[#8f3030]",
  failed: "border-[#c64545] bg-[#c64545]/10 text-[#8f3030]",
};

function describe(health: HealthResponse): BackendHealth {
  if (!health.ok) {
    return { status: "offline", message: "API offline" };
  }
  if (health.warmup.state === "failed") {
    return {
      status: "failed",
      message: "API warm-up failed",
      detail: health.warmup.error ?? undefined,
    };
  }
  if (health.warmup.state !== "ready") {
    return {
      status: "starting",
      message: "API starting",
      detail: "Loading indexes and models",
    };
  }
  return { status: "ready", message: "API ready" };
}

/**
 * Backend còn sống không — một dấu chấm màu trên thanh điều hướng.
 *
 * Đây là chỗ DUY NHẤT gọi /health. Trước kia App.tsx vừa hỏi vừa vẽ badge
 * trong khối header riêng của màn Search; khối đó đã bỏ, nhưng App vẫn cần
 * biết trạng thái để khoá nút Search — nên nó đọc từ store, còn component này
 * ghi vào.
 *
 * Nằm trên thanh điều hướng nên nó có mặt ở MỌI màn, không riêng Search. Backend
 * chết trong lúc bạn đang ở Board hay Export cũng đáng biết ngay.
 */
export default function ApiStatus() {
  const health = useHealthStore((state) => state.health);
  const setHealth = useHealthStore((state) => state.setHealth);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const result = await videoSearchApi.getHealth();
        if (!cancelled) setHealth(describe(result));
      } catch (err) {
        if (!cancelled) {
          setHealth({
            status: "offline",
            message: "API offline",
            detail: err instanceof Error ? err.message : "Health check failed",
          });
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [setHealth]);

  return (
    <span
      className={`shrink-0 whitespace-nowrap rounded-[6px] border px-2 py-0.5 text-[11.5px] font-bold ${
        CLASS_NAME[health.status]
      }`}
      title={health.detail}
    >
      {health.message}
    </span>
  );
}
