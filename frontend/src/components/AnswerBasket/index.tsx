import { useCallback, useEffect, useState } from "react";

import {
  autofillAnswers,
  deleteAnswer,
  getAnswers,
  patchAnswer,
  reorderAnswer,
  type AnswerRow,
} from "../../api/answers";
import { ApiRequestError } from "../../api/base";
import type { BoardTask } from "../../api/board";
import Button from "../Button";
import { useAuthStore } from "../../store/authStore";

// Final Score = (R@1 + R@5 + R@20 + R@50 + R@100) / 5, so there are exactly
// five rank boundaries that change anything. Moving a row from 7 to 6 buys
// nothing; from 6 to 5 buys a fifth of a point. Nobody does that arithmetic
// under time pressure, so the lines get drawn.
const CUTS = [1, 5, 20, 50, 100];

const ORIGIN_STRIPE: Record<string, string> = {
  mine: "border-l-proto-teal",
  mate: "border-l-[#9b6dd6]",
  auto: "border-l-transparent",
};

export default function AnswerBasket({
  task,
  rowsPerQuery,
  open,
  onClose,
}: {
  task: BoardTask | null;
  rowsPerQuery: number;
  open: boolean;
  onClose: () => void;
}) {
  const me = useAuthStore((state) => state.user);
  const [rows, setRows] = useState<AnswerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(25);

  const reload = useCallback(async () => {
    if (!task) return;
    try {
      setRows((await getAnswers(task.id)).answers);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được giỏ");
    }
  }, [task]);

  useEffect(() => {
    if (open) void reload();
  }, [open, reload]);

  // TRAKE is graded inside a window the rules put at "usually under 10 frames",
  // so a one-second step would jump clean over it.
  useEffect(() => {
    setStep(task?.type === "trake" ? 2 : 25);
  }, [task?.type]);

  if (!open || !task) {
    return null;
  }

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await reload();
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Thao tác hỏng");
    } finally {
      setBusy(false);
    }
  };

  const anchor = rows[0];
  const autoCount = rows.filter((row) => row.origin === "auto").length;
  const needed = Math.max(0, rowsPerQuery - rows.length);
  const span = Math.ceil(needed / 2) * step;

  const stripe = (row: AnswerRow) => {
    if (row.origin === "auto") return ORIGIN_STRIPE.auto;
    return row.created_by?.id === me?.id ? ORIGIN_STRIPE.mine : ORIGIN_STRIPE.mate;
  };

  return (
    <div className="fixed inset-0 z-[999] bg-black/40 flex items-center justify-center p-4">
      <div className="bg-proto-canvas rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col font-baloo">
        <div className="flex items-center gap-3 px-5 py-3 border-b border-proto-line">
          <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
            Task {task.code} · {task.type === "qa" ? "Q&A" : task.type.toUpperCase()}
          </span>
          <b className="font-mono text-xl text-proto-ink ml-auto">
            {rows.length}
            <span className="text-proto-muted text-sm">/{rowsPerQuery}</span>
          </b>
          <button
            type="button"
            onClick={onClose}
            className="text-[#c64545] hover:bg-[#c64545]/15 rounded-full px-3 py-1 font-bold"
          >
            ×
          </button>
        </div>

        {/* Autofill — a panel rather than a bare button, because the step
            decides the coverage and nobody can pick it blind. */}
        <div className="px-5 py-3 border-b border-proto-line bg-proto-soft">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Mốc neo
            </span>
            <span className="font-mono text-xs text-proto-ink">
              {anchor ? `${anchor.video_id} · ${anchor.frames.join(", ")}` : "—"}
            </span>
            <label className="flex items-center gap-2 ml-auto">
              <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
                Bước
              </span>
              <input
                type="range"
                min={1}
                max={120}
                value={step}
                onChange={(e) => setStep(Number(e.target.value))}
                className="accent-proto-primary"
              />
              <span className="font-mono font-bold text-sm w-8 text-right">{step}</span>
            </label>
          </div>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="text-[11.5px] text-proto-muted">
              {!anchor
                ? "Thêm ít nhất một đáp án để làm mốc neo."
                : needed === 0
                ? `Đã đủ ${rowsPerQuery} dòng. Xoá dòng auto rồi đổi bước nếu muốn trải lại.`
                : `${needed} dòng auto → đủ ${rowsPerQuery} · phủ ${Math.max(
                    0,
                    anchor.frames[0] - span
                  )} → ${anchor.frames[0] + span}`}
            </span>
            <span className="ml-auto flex gap-2">
              {/* "Điền lại" used to send replace_auto, which deletes and
                  refills in one call - from the outside that is 100 rows before
                  and 100 rows after, indistinguishable from a dead button.
                  Clearing is its own action now. */}
              <Button
                size="xs"
                variant="outline"
                disabled={busy || autoCount === 0}
                onClick={() =>
                  void act(() => autofillAnswers(task.id, { step, mode: "clear" }))
                }
              >
                Xoá {autoCount} dòng auto
              </Button>
              <Button
                size="xs"
                disabled={busy || !anchor || needed === 0}
                onClick={() => void act(() => autofillAnswers(task.id, { step }))}
              >
                Điền {needed} dòng
              </Button>
            </span>
          </div>
        </div>

        {error && <p className="text-[#c64545] text-sm px-5 pt-2">{error}</p>}

        <div className="flex-1 overflow-y-auto px-5 py-3">
          {rows.length === 0 && (
            <p className="text-sm text-proto-muted">
              Chưa có dòng nào. Bấm <b>A</b> trên một kết quả tìm kiếm để thêm.
            </p>
          )}
          {rows.map((row, index) => (
            <div key={row.id}>
              {CUTS.includes(index + 1) && (
                <div className="flex items-center gap-2 my-1.5">
                  <b className="text-[9px] font-extrabold tracking-wide text-proto-primary-active">
                    R@{index + 1}
                  </b>
                  <span className="flex-1 h-px bg-proto-primary/40" />
                </div>
              )}
              <div
                className={`flex items-center gap-2 px-2 py-1 rounded-[7px] bg-white border border-proto-line border-l-[3px] mb-1 text-xs ${stripe(
                  row
                )} ${index === 0 ? "bg-proto-primary/10" : ""}`}
              >
                <i className="not-italic w-6 text-right font-mono font-extrabold text-proto-muted">
                  {row.rank}
                </i>
                <span className="font-mono text-proto-muted">{row.video_id}</span>
                <span className="font-mono text-proto-ink font-semibold">
                  {row.frames.join(" · ")}
                </span>
                {task.type === "qa" && (
                  <input
                    className="flex-1 min-w-[80px] px-2 py-0.5 rounded-[6px] bg-proto-soft border border-proto-line"
                    defaultValue={row.answer_text ?? ""}
                    placeholder="đáp án"
                    onBlur={(e) => {
                      if (e.target.value !== (row.answer_text ?? "")) {
                        void act(() =>
                          patchAnswer(row.id, {
                            version: row.version,
                            answer_text: e.target.value,
                          })
                        );
                      }
                    }}
                  />
                )}
                <span className="ml-auto flex gap-1">
                  {index > 0 && (
                    <button
                      type="button"
                      title="Đưa lên hạng 1"
                      className="px-1.5 text-proto-muted hover:text-proto-primary-active"
                      onClick={() =>
                        void act(() => reorderAnswer(task.id, { answer_id: row.id }))
                      }
                    >
                      ↑1
                    </button>
                  )}
                  <button
                    type="button"
                    title="Xoá dòng"
                    className="px-1.5 text-proto-muted hover:text-[#c64545]"
                    onClick={() => void act(() => deleteAnswer(row.id))}
                  >
                    ×
                  </button>
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
