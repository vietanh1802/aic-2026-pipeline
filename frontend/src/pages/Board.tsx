import { useEffect, useState } from "react";

import {
  claimTask,
  getBoard,
  releaseTask,
  type BoardResponse,
  type BoardTask,
} from "../api/board";
import { ApiRequestError } from "../api/base";
import Button from "../components/Button";
import { useAuthStore } from "../store/authStore";

const POLL_MS = 3000;

const TYPE_LABEL: Record<BoardTask["type"], string> = {
  kis: "KIS",
  qa: "Q&A",
  trake: "TRAKE",
};

/**
 * Answers three questions and nothing else: which task is free, what does it
 * ask, who is holding it.
 *
 * Polls rather than opening a socket. Five people at three seconds is under two
 * requests a second, and a socket that dies quietly leaves the screen showing
 * stale data as if it were live — during a round, silent staleness is worse
 * than a three-second lag.
 */
export default function Board({
  onOpenTask,
}: {
  onOpenTask: (task: BoardTask) => void;
}) {
  const me = useAuthStore((state) => state.user);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "open" | "mine">("all");

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await getBoard();
        if (!cancelled) {
          setBoard(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiRequestError ? err.message : "Mất kết nối"
          );
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setBoard(await getBoard());
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Thao tác hỏng");
    }
  };

  const rowsPerQuery = board?.round?.rows_per_query ?? 100;
  const tasks = (board?.tasks ?? []).filter((task) => {
    if (filter === "open") return !task.owner;
    if (filter === "mine") return task.owner?.id === me?.id;
    return true;
  });
  const done = (board?.tasks ?? []).filter(
    (task) => task.answer_count >= rowsPerQuery
  ).length;

  if (board && !board.round) {
    return (
      <div className="max-w-[1200px] mx-auto p-8 font-baloo">
        <h2 className="text-2xl text-proto-ink mb-2">Chưa có gói truy vấn</h2>
        <p className="text-sm text-proto-muted">
          {me?.role === "admin"
            ? "Vào tab Import để thả file zip của ban tổ chức."
            : "Chờ quản trị nhập gói truy vấn của vòng thi."}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[1200px] mx-auto p-6 font-baloo">
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <h2 className="text-2xl text-proto-ink">{board?.round?.label ?? "…"}</h2>
        <span className="text-xs text-proto-muted font-mono">
          {board?.round?.source_filename}
        </span>
        <span className="text-sm text-proto-muted ml-auto">
          <b className="text-proto-ink">{done}</b>/{board?.tasks.length ?? 0} đủ{" "}
          {rowsPerQuery} dòng
        </span>
      </div>

      <div className="flex gap-1 mb-3">
        {(
          [
            ["all", "Tất cả"],
            ["open", "Chưa ai nhận"],
            ["mine", "Của tôi"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            className={`text-[12.5px] px-3 py-1 rounded-[7px] border ${
              filter === id
                ? "bg-proto-cream-strong border-proto-cream-strong text-proto-ink font-semibold"
                : "border-proto-line text-proto-muted"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="text-[#c64545] text-sm mb-2">{error}</p>}

      <div className="border border-proto-line rounded-[10px] overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-proto-soft text-[10px] uppercase tracking-wide text-proto-muted">
              <th className="text-left px-3 py-2 w-16">Mã</th>
              <th className="text-left px-3 py-2 w-20">Loại</th>
              <th className="text-left px-3 py-2">Đề bài</th>
              <th className="text-left px-3 py-2 w-36">Người giữ</th>
              <th className="text-left px-3 py-2 w-24">Đáp án</th>
              <th className="px-3 py-2 w-32"></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const mine = task.owner?.id === me?.id;
              const full = task.answer_count >= rowsPerQuery;
              return (
                <tr
                  key={task.id}
                  className="border-t border-proto-line align-top"
                >
                  <td className="px-3 py-2 font-mono font-bold text-proto-ink">
                    {task.code}
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-proto-dark text-proto-canvas">
                      {TYPE_LABEL[task.type]}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-proto-body">
                    <span className="line-clamp-2">{task.query_text}</span>
                    {task.viewers.length > 0 && (
                      <span className="text-[10.5px] text-[#9b6dd6] block mt-0.5">
                        đang xem: {task.viewers.map((v) => v.display_name).join(", ")}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-proto-muted">
                    {task.owner ? (
                      <span className={mine ? "text-proto-ink font-semibold" : ""}>
                        {task.owner.display_name}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    <span className={full ? "text-[#3d7a4d] font-bold" : ""}>
                      {task.answer_count}
                    </span>
                    <span className="text-proto-muted">/{rowsPerQuery}</span>
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {!task.owner && (
                      <Button
                        size="xs"
                        onClick={() => void act(() => claimTask(task.id))}
                      >
                        Nhận
                      </Button>
                    )}
                    {mine && (
                      <span className="inline-flex gap-1.5">
                        <Button size="xs" onClick={() => onOpenTask(task)}>
                          Mở
                        </Button>
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => void act(() => releaseTask(task.id))}
                        >
                          Nhả
                        </Button>
                      </span>
                    )}
                    {task.owner && !mine && (
                      <Button size="xs" variant="ghost" onClick={() => onOpenTask(task)}>
                        Xem
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
