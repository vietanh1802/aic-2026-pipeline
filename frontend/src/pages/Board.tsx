import { useEffect, useState } from "react";

import {

  getBoard,

  type BoardResponse,
  type BoardTask,
} from "../api/board";
import { ApiRequestError } from "../api/base";
import Button from "../components/Button";
import { taskBriefText } from "../helpers/taskBrief";
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
  onOpenTask: (task: BoardTask, options?: { openBasket?: boolean }) => void;
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

  // `act` từng bọc claimTask/releaseTask — hai thứ duy nhất trang này gọi mà
  // có thể đổi dữ liệu. Bỏ Nhận/Nhả rồi thì Board chỉ còn đọc: nó tải bảng và
  // mở task, không ghi gì. Xoá luôn cho khỏi ai tưởng còn đường ghi ở đây.

  const rowsPerQuery = board?.round?.rows_per_query ?? 100;
  const tasks = (board?.tasks ?? []).filter((task) => {
    // Không còn quyền sở hữu, nên lọc theo VIỆC ĐÃ LÀM: câu nào chưa ai đụng
    // tới, và câu nào chính tôi đã có đáp án.
    if (filter === "open") return task.contributors.length === 0;
    if (filter === "mine")
      return task.contributors.some((c) => c.id === me?.id);
    return true;
  });
  // "Đủ 100 dòng" nghĩa là CÓ MỘT NGƯỜI làm xong, không phải tổng của cả nhóm
  // đạt 100.
  //
  // Trước đây đếm bằng task.answer_count, mà con số đó cộng dồn cả 5 người: ba
  // người mỗi người 40 dòng thành 120, vượt 100, và câu đó bị tính là xong
  // trong khi không ai có nổi một danh sách hoàn chỉnh để nộp. Bài nộp lấy của
  // MỘT người, nên phép đếm cũng phải theo từng người.
  const done = (board?.tasks ?? []).filter((task) =>
    task.contributors.some((c) => c.count >= rowsPerQuery)
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
        {/* Only reachable by asking for a pack_id explicitly, but if a screen
            ever does, saying so beats letting someone work a dead round. */}
        {board?.round && !board.round.active && (
          <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-[#d4a017]/20 text-[#8a6a0f]">
            Vòng đã nghỉ
          </span>
        )}
        <span className="text-sm text-proto-muted ml-auto">
          <b className="text-proto-ink">{done}</b>/{board?.tasks.length ?? 0} đủ{" "}
          {rowsPerQuery} dòng
        </span>
      </div>

      <div className="flex gap-1 mb-3">
        {(
          [
            ["all", "Tất cả"],
            // "Chưa ai nhận" là chữ còn sót từ thời Nhận/Nhả. Bộ lọc này vốn
            // đã đọc contributors, tức là "chưa ai LÀM" — nhãn cũ mô tả một cơ
            // chế không còn tồn tại.
            ["open", "Chưa ai làm"],
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
              <th className="text-left px-3 py-2 w-44">Ai đã làm</th>
              <th className="text-left px-3 py-2 w-24">Số người</th>
              <th className="px-3 py-2 w-32"></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const mine = task.contributors.some((c) => c.id === me?.id);
              // Cùng phép đếm với `done` ở trên: đã có ít nhất một người làm
              // xong một danh sách đầy đủ.
              const full = task.contributors.some(
                (c) => c.count >= rowsPerQuery
              );
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
                    <span className="line-clamp-2">{taskBriefText(task)}</span>
                    {task.viewers.length > 0 && (
                      <span className="text-[10.5px] text-[#9b6dd6] block mt-0.5">
                        đang xem: {task.viewers.map((v) => v.display_name).join(", ")}
                      </span>
                    )}
                  </td>
                  {/* Thay cho cột "Người giữ". Ai cũng làm được mọi câu, nên
                      thứ đáng biết không phải ai đang giữ mà là câu nào đã có
                      người ngó tới, và mỗi người được bao nhiêu dòng. Tên tôi
                      in đậm để tự nhận ra giữa 5 người. */}
                  <td className="px-3 py-2 text-proto-muted">
                    {task.contributors.length === 0 ? (
                      <span className="text-proto-line">chưa ai làm</span>
                    ) : (
                      <span className="flex flex-wrap gap-x-2 gap-y-0.5">
                        {task.contributors.map((c) => (
                          <span
                            key={c.id}
                            className={
                              c.id === task.chosen_author_id
                                ? "text-[#3d7a4d] font-bold"
                                : c.id === me?.id
                                ? "text-proto-ink font-semibold"
                                : ""
                            }
                            title={
                              c.id === task.chosen_author_id
                                ? `${c.display_name} — bài đang được chọn để nộp`
                                : `${c.display_name} · ${c.count} dòng`
                            }
                          >
                            {c.display_name}
                            <span className="text-proto-line">({c.count})</span>
                          </span>
                        ))}
                      </span>
                    )}
                  </td>
                  {/* Số NGƯỜI đã làm câu này, không phải tổng số dòng.
                      "300/100" là con số vô nghĩa: nó cộng dồn ba danh sách
                      của ba người rồi đem so với hạn mức của MỘT danh sách,
                      nên vừa vượt trần vừa không nói lên điều gì. Bài nộp lấy
                      của một người, còn thứ đáng biết khi lướt bảng là câu nào
                      đã có người ngó tới. Chi tiết từng người vẫn nằm nguyên ở
                      cột bên trái. */}
                  <td className="px-3 py-2">
                    {task.contributors.length === 0 ? (
                      <span className="text-proto-line">—</span>
                    ) : (
                      <button
                        type="button"
                        title={
                          full
                            ? `Đã có người làm đủ ${rowsPerQuery} dòng`
                            : `Chưa ai đủ ${rowsPerQuery} dòng`
                        }
                        onClick={() => onOpenTask(task, { openBasket: true })}
                        className="underline decoration-dotted underline-offset-2"
                      >
                        <b
                          className={`font-mono ${
                            full ? "text-[#3d7a4d]" : "text-proto-ink"
                          }`}
                        >
                          {task.contributors.length}
                        </b>
                        <span className="text-proto-muted"> người</span>
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {/* Chỉ còn một nút. "Nhận"/"Nhả" đã bỏ — không còn gì để
                        giành — và "Xem" cũng vậy: xem hay sửa giờ là một, ai
                        mở cũng làm được. */}
                    <Button
                      size="xs"
                      variant={mine ? "primary" : "outline"}
                      onClick={() => onOpenTask(task)}
                    >
                      Mở
                    </Button>
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
