import { useCallback, useEffect, useState } from "react";

import {
  addAnswer,
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
import FramePreview from "../FramePreview";
import { autofillPlan, suggestStep, type MarkedRange } from "../../helpers/basketMath";
import { parseManualFrames } from "../../helpers/manualAnswer";
import KeyframeFPS from "../../mapping/fps_map.json";
import { useAuthStore } from "../../store/authStore";

// Final Score = (R@1 + R@5 + R@20 + R@50 + R@100) / 5, so there are exactly
// five rank boundaries that change anything. Moving a row from 7 to 6 buys
// nothing; from 6 to 5 buys a fifth of a point. Nobody does that arithmetic
// under time pressure, so the lines get drawn.
const CUTS = [1, 5, 20, 50, 100];

// The range AutofillRequest.step accepts on the server (ge=1, le=2000). The UI
// must not offer a value the API will reject.
const STEP_MIN = 1;
const STEP_MAX = 2000;
const inStepRange = (value: number) => value >= STEP_MIN && value <= STEP_MAX;

const ORIGIN_STRIPE: Record<string, string> = {
  mine: "border-l-proto-teal",
  mate: "border-l-[#9b6dd6]",
  auto: "border-l-transparent",
};

const VIDEO_IDS = Object.keys(KeyframeFPS as Record<string, number>);

/**
 * Everything below the dialog/panel chrome: fetching a task's answers,
 * autofill, the manual-entry escape hatch, and the row list with its R@k cut
 * lines.
 *
 * Shared between `AnswerBasket`'s dialog and `VideoPopUp`'s side panel so the
 * two stay one implementation. `variant` only ever changes sizing, whether
 * autofill starts open, and whether the hover preview renders — the panel
 * sits beside the video, so the video itself is the preview.
 */
export default function BasketBody({
  task,
  rowsPerQuery,
  variant,
  reloadKey,
  onRowClick,
  onChanged,
  activeRowId = null,
  markedRange = null,
}: {
  task: BoardTask;
  rowsPerQuery: number;
  variant: "dialog" | "panel";
  /** Bumped by the popup after every add so the panel re-reads. */
  reloadKey?: number;
  onRowClick: (row: AnswerRow) => void;
  /** Fired after any mutation, so the caller can refresh its own counters. */
  onChanged?: () => void;
  /** The row the user last clicked, highlighted so they know what they are checking. */
  activeRowId?: number | null;
  /** Mark-in/mark-out on the video, in frames. Only ever set by the popup panel. */
  markedRange?: MarkedRange | null;
}) {
  const isDialog = variant === "dialog";
  const me = useAuthStore((state) => state.user);
  const [rows, setRows] = useState<AnswerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(task.type === "trake" ? 2 : 25);
  // What is in the box, which may briefly be empty or half-typed. `step` only
  // ever holds a value the server would accept.
  const [stepText, setStepText] = useState(String(task.type === "trake" ? 2 : 25));
  // The dialog has the room to show autofill outright; the panel sits beside
  // the video where space is scarce, so it starts tucked behind a toggle.
  const [autofillOpen, setAutofillOpen] = useState(isDialog);
  // ── Nhập tay ─────────────────────────────────────────────────────────────
  const [manualOpen, setManualOpen] = useState(false);
  const [manualVideo, setManualVideo] = useState("");
  const [manualFrames, setManualFrames] = useState("");
  const [manualText, setManualText] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setRows((await getAnswers(task.id)).answers);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Không tải được giỏ");
    }
  }, [task.id]);

  useEffect(() => {
    // reloadKey has no meaning of its own — it is only ever bumped to say
    // "reload now", from the popup after it adds a row on the caller's behalf.
    void reload();
  }, [reload, reloadKey]);

  // TRAKE is graded inside a window the rules put at "usually under 10 frames",
  // so a one-second step would jump clean over it.
  useEffect(() => {
    const next = task.type === "trake" ? 2 : 25;
    setStep(next);
    setStepText(String(next));
  }, [task.type]);

  // Not `task.owner?.id !== me?.id`: an unclaimed task has no owner, and that
  // form would lock the holder out of a basket nobody owns.
  const readOnly = Boolean(task.owner) && task.owner?.id !== me?.id;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await reload();
      setError(null);
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Thao tác hỏng");
    } finally {
      setBusy(false);
    }
  };

  const submitManual = async () => {
    if (!VIDEO_IDS.includes(manualVideo.trim())) {
      setManualError(`Không có video ${manualVideo.trim() || "—"}`);
      return;
    }
    const parsed = parseManualFrames(
      manualFrames,
      task.type === "trake" ? task.n_events ?? 1 : 1
    );
    if ("error" in parsed) {
      setManualError(parsed.error);
      return;
    }
    setManualError(null);
    await act(() =>
      addAnswer(task.id, {
        video_id: manualVideo.trim(),
        frames: parsed.frames,
        answer_text: task.type === "qa" ? manualText || null : null,
      })
    );
    setManualFrames("");
    setManualText("");
  };

  const { anchor, autoCount, needed, from, to } = autofillPlan(rows, rowsPerQuery, step);

  // The step that would make the fill exactly blanket the marked interval.
  // Panel-only: the dialog basket (opened from the Board) has no marks.
  const suggestion =
    !isDialog && markedRange && anchor
      ? suggestStep(anchor.frames[0], markedRange, needed)
      : null;

  // Applied only when the marks themselves change, not on every render this
  // recomputes on — `needed` drops by one after every added row, so keying
  // this effect on it would overwrite the number the user just typed on
  // every single add.
  useEffect(() => {
    if (suggestion !== null) {
      setStep(suggestion);
      setStepText(String(suggestion));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markedRange?.start, markedRange?.end]);

  const stripe = (row: AnswerRow) => {
    if (row.origin === "auto") return ORIGIN_STRIPE.auto;
    return row.created_by?.id === me?.id ? ORIGIN_STRIPE.mine : ORIGIN_STRIPE.mate;
  };

  const padX = isDialog ? "px-5" : "px-3";
  const rowTextSize = isDialog ? "text-xs" : "text-[11px]";

  return (
    <div className="flex flex-col flex-1 min-h-0 font-baloo">
      <div className={`flex items-center gap-3 ${padX} py-3 border-b border-proto-line`}>
        <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
          Task {task.code} · {task.type === "qa" ? "Q&A" : task.type.toUpperCase()}
        </span>
        <b className={`font-mono text-proto-ink ml-auto ${isDialog ? "text-xl" : "text-sm"}`}>
          {rows.length}
          <span className="text-proto-muted text-sm">/{rowsPerQuery}</span>
        </b>
      </div>

      {/* Autofill — a panel rather than a bare button, because the step
          decides the coverage and nobody can pick it blind. */}
      {!readOnly && (
        <div className={`${padX} py-2 border-b border-proto-line bg-proto-soft`}>
          {!isDialog && (
            <button
              type="button"
              onClick={() => setAutofillOpen((open) => !open)}
              className="text-[12px] font-semibold text-proto-primary-active"
            >
              {autofillOpen ? "− Đóng điền tự động" : "+ Điền tự động"}
            </button>
          )}

          {autofillOpen && (
            <div className={isDialog ? "" : "mt-2"}>
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
                  Mốc neo
                </span>
                <span className="font-mono text-xs text-proto-ink">
                  {anchor ? `${anchor.video_id} · ${anchor.frames.join(", ")}` : "—"}
                </span>
                {/* Typed, not dragged. The step is a frame count someone has in
                    mind — 2 for a TRAKE window, 25 for a second at 25 fps — and a
                    track makes you hunt for a number you already knew. Typing also
                    reaches the whole range the API accepts (1-2000); the track
                    stopped at 120 because that was as far as dragging stayed
                    usable. */}
                <label className="flex items-center gap-2 ml-auto">
                  <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
                    Bước
                  </span>
                  <input
                    type="number"
                    min={STEP_MIN}
                    max={STEP_MAX}
                    value={stepText}
                    onChange={(event) => {
                      const raw = event.target.value;
                      setStepText(raw);
                      const parsed = Number(raw);
                      // Commit only a usable value, so clearing the field to
                      // retype does not snap it to 1 under the cursor.
                      if (raw !== "" && Number.isInteger(parsed) && inStepRange(parsed)) {
                        setStep(parsed);
                      }
                    }}
                    onBlur={() => setStepText(String(step))}
                    className="w-16 px-2 py-0.5 rounded-[6px] border border-proto-line bg-white font-mono font-bold text-sm text-right text-proto-ink"
                  />
                  <span className="text-[10px] text-proto-muted">frame</span>
                </label>
                {/* Only when the step differs from what the marked interval
                    calls for — hidden the moment they agree, so it never
                    fights the field the user is actively editing. */}
                {!isDialog && suggestion !== null && suggestion !== step && (
                  <button
                    type="button"
                    onClick={() => {
                      setStep(suggestion);
                      setStepText(String(suggestion));
                    }}
                    className="text-[10px] font-semibold text-proto-primary-active underline decoration-dotted"
                  >
                    gợi ý {suggestion}
                  </button>
                )}
              </div>
              {!isDialog && markedRange && (
                <p className="text-[11.5px] text-proto-muted mt-2">
                  Đoạn đã ghim {markedRange.start} → {markedRange.end}
                </p>
              )}
              <div className="flex items-center gap-3 mt-2 flex-wrap">
                <span className="text-[11.5px] text-proto-muted">
                  {!anchor
                    ? "Thêm ít nhất một đáp án để làm mốc neo."
                    : needed === 0
                    ? `Đã đủ ${rowsPerQuery} dòng. Xoá dòng auto rồi đổi bước nếu muốn trải lại.`
                    : `${needed} dòng auto → đủ ${rowsPerQuery} · phủ ${from} → ${to}`}
                </span>
                <span className="ml-auto flex gap-2">
                  {/* "Điền lại" used to send replace_auto, which deletes and
                      refills in one call - from the outside that is 100 rows
                      before and 100 rows after, indistinguishable from a dead
                      button. Clearing is its own action now. */}
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
          )}
        </div>
      )}

      {/* Item 7 — the way in when search found nothing at all. */}
      {!readOnly && (
        <div className={`${padX} py-2 border-b border-proto-line`}>
          <button
            type="button"
            onClick={() => setManualOpen((open) => !open)}
            className="text-[12px] font-semibold text-proto-primary-active"
          >
            {manualOpen ? "− Đóng nhập tay" : "+ Nhập tay"}
          </button>

          {manualOpen && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input
                list="basket-video-ids"
                value={manualVideo}
                onChange={(event) => {
                  setManualVideo(event.target.value);
                  setManualError(null);
                }}
                placeholder="L01_V001"
                className="w-[130px] px-2 py-1 rounded-[6px] border border-proto-line bg-white font-mono text-xs"
              />
              <datalist id="basket-video-ids">
                {VIDEO_IDS.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>

              <input
                value={manualFrames}
                onChange={(event) => {
                  setManualFrames(event.target.value);
                  setManualError(null);
                }}
                placeholder={
                  task.type === "trake"
                    ? `${task.n_events ?? 1} mốc, cách nhau dấu phẩy`
                    : "số frame"
                }
                className="w-[200px] px-2 py-1 rounded-[6px] border border-proto-line bg-white font-mono text-xs"
              />

              {task.type === "qa" && (
                <input
                  value={manualText}
                  onChange={(event) => setManualText(event.target.value)}
                  placeholder="đáp án"
                  className="flex-1 min-w-[120px] px-2 py-1 rounded-[6px] border border-proto-line bg-white text-xs"
                />
              )}

              <Button size="xs" disabled={busy} onClick={() => void submitManual()}>
                Thêm dòng
              </Button>

              {manualError && (
                <span className="w-full text-[11px] text-[#c64545]">{manualError}</span>
              )}
            </div>
          )}
        </div>
      )}

      {readOnly && (
        <p className={`${padX} py-2 border-b border-proto-line bg-proto-soft text-[12px] text-proto-muted`}>
          Đang xem giỏ của <b className="text-proto-ink">{task.owner?.display_name}</b> — chỉ đọc.
        </p>
      )}

      {error && <p className={`text-[#c64545] text-sm ${padX} pt-2`}>{error}</p>}

      <div className={`flex-1 overflow-y-auto ${padX} py-3`}>
        {rows.length === 0 && (
          <p className="text-sm text-proto-muted">
            Chưa có dòng nào. Bấm <b>+</b> trên một kết quả tìm kiếm để thêm.
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
              className={`${isDialog ? "group" : ""} relative flex items-center gap-2 px-2 py-0.5 rounded-[7px] bg-white border border-proto-line border-l-[3px] mb-1 ${rowTextSize} cursor-pointer ${stripe(
                row
              )} ${index === 0 ? "bg-proto-primary/10" : ""} ${
                row.id === activeRowId ? "ring-2 ring-proto-primary-active" : ""
              }`}
              onClick={() => onRowClick(row)}
              title={
                row.origin === "auto"
                  ? "Dòng tự sinh"
                  : `Thêm bởi ${row.created_by?.display_name ?? "—"}`
              }
            >
              <FramePreview videoId={row.video_id} frameIdx={row.frames[0]} />
              {/* Rendered always, revealed on hover: no fetch on hover, and the
                  browser has the file from the thumbnail already. Skipped in
                  the panel — it sits beside the video, so the video is the
                  preview. */}
              {isDialog && (
                <div className="pointer-events-none absolute left-14 top-0 z-[1000] hidden group-hover:block">
                  <FramePreview
                    videoId={row.video_id}
                    frameIdx={row.frames[0]}
                    size="large"
                    className="shadow-2xl border-2 border-white"
                  />
                </div>
              )}
              <i className="not-italic w-6 text-right font-mono font-extrabold text-proto-muted">
                {row.rank}
              </i>
              <span className="font-mono text-proto-muted">{row.video_id}</span>
              <span className="font-mono text-proto-ink font-semibold">
                {row.frames.join(" · ")}
              </span>
              {task.type === "qa" && (
                <input
                  className="flex-1 min-w-[80px] px-2 py-0.5 rounded-[6px] bg-proto-soft border border-proto-line disabled:opacity-60 disabled:cursor-not-allowed"
                  defaultValue={row.answer_text ?? ""}
                  placeholder="đáp án"
                  disabled={readOnly}
                  onClick={(event) => event.stopPropagation()}
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
              <span className="ml-auto flex gap-1" onClick={(event) => event.stopPropagation()}>
                {!readOnly && (
                  <>
                    {index > 0 && (
                      <button
                        type="button"
                        title="Đưa lên hạng 1"
                        className="flex h-10 w-10 items-center justify-center text-proto-muted hover:text-proto-primary-active"
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
                      className="flex h-10 w-10 items-center justify-center text-proto-muted hover:text-[#c64545]"
                      onClick={() => void act(() => deleteAnswer(row.id))}
                    >
                      ×
                    </button>
                  </>
                )}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
