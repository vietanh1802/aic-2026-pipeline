import { useEffect, useState } from "react";

import type { DresCurrentTask } from "../../api/dres";
import {
  clockTone,
  formatClock,
  isTrakeTask,
  liveClock,
  scoreIfCorrectNow,
  WRONG_PENALTY,
} from "../../helpers/dresScore";

const TONE_TEXT = {
  green: "text-[#2f8a4f]",
  yellow: "text-[#b8860b]",
  red: "text-[#c64545]",
};
const TONE_BAR = {
  green: "bg-[#2f8a4f]",
  yellow: "bg-[#d4a017]",
  red: "bg-[#c64545]",
};

function points(value: number): string {
  return value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

/**
 * Câu DRES đang chạy: đồng hồ đếm ngược, số lần đã sai, và điểm nếu nộp đúng
 * ngay giây này (HUONG-DAN-NOP-BAI.pdf, bước 2).
 *
 * Hiện ở cả tab DRES lẫn popup "Nộp DRES": người đang cầm khung hình mới là
 * người quyết định nộp hay chờ thêm gợi ý, nên họ phải thấy cái giá của cả hai
 * mà không phải chuyển tab.
 */
export default function DresTaskClock({
  current,
  receivedAt,
  error,
}: {
  current: DresCurrentTask | null;
  receivedAt: number;
  error: string | null;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);

  const task = current?.task ?? null;
  if (!task || !current?.clock) {
    return (
      <div className="text-sm text-proto-muted">
        Câu đang chạy: {error ?? "không có"}
      </div>
    );
  }

  const tally = current.tally ?? { wrong: 0, indeterminate: 0, correct: false };
  const { timeLeft, elapsed } = liveClock(current.clock, receivedAt, now);
  const tone = clockTone(timeLeft, task.duration);
  const score = scoreIfCorrectNow(task.duration, elapsed, tally.wrong);
  const trake = isTrakeTask(task.taskType, task.taskGroup);
  const ratio =
    timeLeft !== null && task.duration ? Math.min(1, timeLeft / task.duration) : null;
  const estimate = current.clock.source === "estimate";

  return (
    <div className="flex flex-col gap-1.5 min-w-[260px]">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <b className="text-proto-primary-active">{task.name}</b>
        <span className="px-2 py-0.5 rounded-full bg-white border border-proto-line text-[11px] font-bold">
          {task.taskType}
        </span>
        <span className="ml-auto text-[12px] text-proto-muted">
          {timeLeft === 0 ? "Hết giờ" : "Còn lại"}
        </span>
        <b
          className={`font-mono text-[20px] leading-none ${TONE_TEXT[tone]}`}
          title={
            estimate
              ? "DRES không cho thí sinh xem đồng hồ. Server tự đếm từ lúc nó thấy câu này, nên có thể chậm vài giây."
              : "Theo DRES"
          }
        >
          {timeLeft === null ? "--:--" : formatClock(timeLeft)}
          {estimate && <span className="text-[11px] align-top">≈</span>}
        </b>
      </div>

      {ratio !== null && (
        <div className="h-1.5 rounded-full bg-proto-line overflow-hidden">
          <div
            className={`h-full ${TONE_BAR[tone]} transition-[width] duration-500`}
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[12px]">
        {tally.correct ? (
          <b className="text-[#2f8a4f]">Đã ĐÚNG câu này — đừng nộp thêm</b>
        ) : (
          score !== null && (
            <span>
              Nộp đúng ngay bây giờ:{" "}
              <b className="text-[#2f8a4f]">{points(score)} điểm</b>
              {trake && (
                <span className="text-proto-muted"> · đúng một phần: {points(score / 2)}</span>
              )}
            </span>
          )
        )}
        {tally.wrong > 0 && (
          <span className="text-[#c64545]">
            Đã sai {tally.wrong} lần (−{tally.wrong * WRONG_PENALTY} điểm)
          </span>
        )}
        {tally.indeterminate > 0 && (
          <span className="text-[#8a6a0f]">
            {tally.indeterminate} bài BTC đang chấm tay
          </span>
        )}
        {estimate && <span className="text-proto-muted">đồng hồ ước lượng</span>}
      </div>
    </div>
  );
}
