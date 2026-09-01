import { useCallback, useEffect, useState } from "react";

import {
  addAnswer,
  autofillAnswers,
  deleteAnswer,
  getAnswers,
  patchAnswer,
  reorderAnswer,
  type AnswerRow,
  type SpreadDirection,
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

// Ba chiều rải, dùng chung cho hàng "đặt cho tất cả" và cho từng hàng mốc.
// Ký hiệu: ↕ hai phía, ↑ chỉ cộng lên, ↓ chỉ trừ xuống.
const DIRECTIONS: readonly (readonly [SpreadDirection, string, string])[] = [
  ["both", "Hai phía", "↕"],
  ["up", "Chỉ cộng lên", "↑"],
  ["down", "Chỉ trừ xuống", "↓"],
] as const;

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
  // ── Kéo thả để sắp lại thứ tự ──────────────────────────────────────────
  // Dùng drag-and-drop gốc của HTML5, không thêm thư viện: danh sách này là
  // một cột dọc đơn giản, và mỗi phụ thuộc mới lại là một thứ phải cài trên
  // máy mọi người rồi qua CI.
  //
  // `dragIndex` là dòng đang cầm, `overIndex` là chỗ sắp thả — cái sau chỉ để
  // vẽ vạch chỉ chỗ, không đụng gì tới dữ liệu.
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  // Dòng đang được rê chuột vào ẢNH NHỎ — quyết định ảnh xem trước nào bung.
  // Giữ id chứ không giữ chỉ số: id không đổi khi danh sách được sắp lại, còn
  // chỉ số thì đổi, và ảnh sẽ nhảy sang dòng khác ngay giữa lúc kéo thả.
  const [hoverRowId, setHoverRowId] = useState<number | null>(null);
  // ── Rải quanh nhiều mốc ─────────────────────────────────────────────────
  //
  // Mốc = các dòng người dùng tự ghim (origin "manual"). Mặc định dùng HẾT.
  // `anchorOff` giữ những dòng bị bỏ tick — giữ mặt trái thay vì giữ mặt phải
  // để một dòng vừa thêm vào giỏ tự động được tính là mốc, không phải tick lại.
  const [anchorOff, setAnchorOff] = useState<Set<number>>(new Set());
  // Chiều và bước RIÊNG theo id dòng. Mốc nào chưa đặt thì rơi về mặc định
  // ("hai phía", và ô "Bước" chung bên trên) — nên mở bảng ra là dùng được
  // ngay, chỉ ai cần mới phải chỉnh.
  const [dirById, setDirById] = useState<Record<number, SpreadDirection>>({});
  const [stepById, setStepById] = useState<Record<number, string>>({});

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

  // Giỏ này LUÔN sửa được. Trước đây readOnly bật khi câu đã bị người khác
  // "Nhận", nhưng giờ mỗi người có danh sách riêng cho mỗi câu, và backend chỉ
  // cho ghi vào danh sách của chính người đang đăng nhập — không còn gì để
  // khoá ở tầng giao diện.
  //
  // Giữ lại biến thay vì xoá và gỡ 6 chỗ dùng nó: màn Export sắp tới cần bày
  // bài của người khác ở chế độ chỉ đọc, và lúc đó nó lại có việc.
  const readOnly = false;

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

  /**
   * Thả dòng `from` vào chỗ của dòng `to`.
   *
   * Backend chỉ nhận "đặt ngay TRƯỚC dòng X" hoặc "ngay SAU dòng X", nên phải
   * chọn vế nào tuỳ hướng kéo:
   *
   *   kéo XUỐNG (from < to)  →  đặt SAU  rows[to]
   *   kéo LÊN   (from > to)  →  đặt TRƯỚC rows[to]
   *
   * Chọn nhầm vế thì dòng lệch đúng một bậc so với chỗ người dùng thả — sai
   * kiểu rất khó thấy, vì nó vẫn di chuyển, chỉ là không tới đúng chỗ.
   */
  const dropRow = async (from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || to >= rows.length) {
      return;
    }
    const moved = rows[from];
    const anchor = rows[to];
    await act(() =>
      reorderAnswer(
        task.id,
        from < to
          ? { answer_id: moved.id, after_id: anchor.id }
          : { answer_id: moved.id, before_id: anchor.id }
      )
    );
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

  // Dòng auto không bao giờ làm mốc: bấm điền lần hai mà rải quanh thứ mình
  // vừa sinh ra thì tâm rải trôi xa dần khỏi khung thật.
  const pinned = rows.filter((row) => row.origin !== "auto");
  const anchors = pinned.filter((row) => !anchorOff.has(row.id));
  const stepOf = (id: number) => {
    const parsed = Number(stepById[id]);
    return Number.isInteger(parsed) && inStepRange(parsed) ? parsed : step;
  };
  const dirOf = (id: number): SpreadDirection => dirById[id] ?? "both";
  // Gửi luôn cả hai danh sách, không cần cờ bật/tắt: mốc chưa chỉnh gì thì
  // stepOf trả về `step` chung và dirOf trả "both", tức đúng hành vi mặc định.
  // Một cờ "bật riêng" chỉ thêm một trạng thái để quên bật.
  const autofillArgs = () => ({
    step,
    // Chỉ gửi anchor_ids khi đã bỏ bớt: gửi cả danh sách đầy đủ cũng ra kết
    // quả y hệt, nhưng để trống thì backend tự lấy mọi dòng ghim tay và tính
    // năng vẫn đúng kể cả khi giao diện lệch pha với giỏ.
    ...(anchors.length === pinned.length
      ? {}
      : { anchor_ids: anchors.map((row) => row.id) }),
    steps: anchors.map((row) => stepOf(row.id)),
    directions: anchors.map((row) => dirOf(row.id)),
  });

  /** Đặt cùng một chiều cho mọi mốc đang tick — lối tắt cho trường hợp thường. */
  const setAllDirections = (value: SpreadDirection) =>
    setDirById((current) => {
      const next = { ...current };
      anchors.forEach((row) => {
        next[row.id] = value;
      });
      return next;
    });

  // ── Áp đáp án cho tất cả dòng ────────────────────────────────────────────
  // A Q&A task has one answer; only the frame varies per row. The anchor
  // (rank 1) usually gets typed first, so this copies it onto every other
  // row instead of leaving them to autofill with whatever `addAnswer` sent —
  // often nothing, which is exactly the gap this closes.
  const [applyAllNote, setApplyAllNote] = useState<string | null>(null);
  const applyAllTargets = anchor ? rows.filter((row) => row.id !== anchor.id) : [];
  const canApplyAll =
    task.type === "qa" && !readOnly && Boolean(anchor?.answer_text);

  const applyAnswerToAll = () => {
    if (!anchor?.answer_text || applyAllTargets.length === 0) {
      return;
    }
    const text = anchor.answer_text;
    const targets = applyAllTargets;
    setApplyAllNote(null);
    return act(async () => {
      let applied = 0;
      try {
        for (const row of targets) {
          await patchAnswer(row.id, { version: row.version, answer_text: text });
          applied += 1;
        }
      } catch (err) {
        setApplyAllNote(
          `Đã áp cho ${applied}/${targets.length} dòng rồi dừng vì lỗi`
        );
        throw err;
      }
      setApplyAllNote(`Đã áp cho ${applied}/${targets.length} dòng`);
    });
  };

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
                <span className="text-[11.5px] text-proto-ink">
                  {anchors.length === 0
                    ? "—"
                    : `${anchors.length}/${pinned.length} dòng ghim tay`}
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
              {/* Lối tắt, KHÔNG phải trạng thái. Chiều thật nằm trên từng
                  hàng mốc bên dưới; ba nút này chỉ ghi cùng một giá trị vào
                  mọi hàng đang tick. Có mặt vì phần lớn lúc cả ba mốc cùng
                  một chiều, bấm ba lần trên ba hàng là thừa. */}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
                  Đặt cho tất cả
                </span>
                {DIRECTIONS.map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    disabled={anchors.length === 0}
                    onClick={() => setAllDirections(id)}
                    className="text-[11.5px] px-2 py-0.5 rounded-[6px] border border-proto-line bg-white text-proto-muted disabled:opacity-40"
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Mỗi mốc một hàng, mỗi hàng tự quyết bước VÀ chiều của nó.
                  Trước đây chiều là một lựa chọn dùng chung cho cả ba mốc, mà
                  ba mốc nằm ở ba chỗ khác nhau trong ba video khác nhau: cái
                  giữa cảnh cần hai phía, cái ngay đầu cảnh mà rải xuống là ném
                  đi nửa số dòng. Hiện cả khi chỉ có một mốc — đó vẫn là chỗ
                  duy nhất đặt được chiều. */}
              {pinned.length > 0 && (
                <div className="mt-2 border border-proto-line rounded-[8px] bg-white divide-y divide-proto-line max-h-48 overflow-y-auto">
                  {pinned.map((row, index) => {
                    const on = !anchorOff.has(row.id);
                    return (
                      <div
                        key={row.id}
                        className={`flex items-center gap-2 px-2 py-1 text-[11.5px] ${
                          on ? "" : "opacity-45"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          title="Dùng dòng này làm mốc"
                          onChange={() =>
                            setAnchorOff((current) => {
                              const next = new Set(current);
                              if (next.has(row.id)) next.delete(row.id);
                              else next.add(row.id);
                              return next;
                            })
                          }
                        />
                        <b className="font-mono text-proto-ink w-5 shrink-0">
                          {index + 1}
                        </b>
                        <span className="font-mono text-proto-ink truncate min-w-0">
                          {row.video_id}
                        </span>
                        <span className="font-mono text-proto-muted ml-auto shrink-0">
                          {row.frames.join(", ")}
                        </span>

                        {/* Ba nút chiều, ký hiệu thay cho chữ: ba hàng × ba
                            nhãn dài là một bức tường chữ, mà mũi tên thì đọc
                            được ngay. Chữ đầy đủ nằm ở tooltip. */}
                        <span className="flex shrink-0 rounded-[5px] overflow-hidden border border-proto-line">
                          {DIRECTIONS.map(([id, label, glyph]) => (
                            <button
                              key={id}
                              type="button"
                              disabled={!on}
                              title={label}
                              onClick={() =>
                                setDirById((current) => ({
                                  ...current,
                                  [row.id]: id,
                                }))
                              }
                              className={`w-6 py-0.5 text-[12px] leading-none ${
                                dirOf(row.id) === id
                                  ? "bg-proto-primary text-white font-bold"
                                  : "bg-white text-proto-muted"
                              }`}
                            >
                              {glyph}
                            </button>
                          ))}
                        </span>

                        <input
                          type="number"
                          min={STEP_MIN}
                          max={STEP_MAX}
                          disabled={!on}
                          value={stepById[row.id] ?? String(step)}
                          onChange={(event) =>
                            setStepById((current) => ({
                              ...current,
                              [row.id]: event.target.value,
                            }))
                          }
                          title="Bước riêng cho mốc này"
                          className="w-14 px-1 py-0.5 rounded-[5px] border border-proto-line bg-white font-mono text-[11px] text-right text-proto-ink shrink-0"
                        />
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex items-center gap-3 mt-2 flex-wrap">
                <span className="text-[11.5px] text-proto-muted">
                  {anchors.length === 0
                    ? "Thêm ít nhất một đáp án, hoặc tick lại một mốc."
                    : needed === 0
                    ? `Đã đủ ${rowsPerQuery} dòng. Xoá dòng auto rồi đổi bước nếu muốn trải lại.`
                    : anchors.length > 1
                    ? `${needed} dòng auto → đủ ${rowsPerQuery} · vòng tròn qua ${anchors.length} mốc`
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
                    disabled={busy || anchors.length === 0 || needed === 0}
                    onClick={() =>
                      void act(() => autofillAnswers(task.id, autofillArgs()))
                    }
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
      {applyAllNote && (
        <p className={`text-[11px] text-proto-muted ${padX} pt-2`}>{applyAllNote}</p>
      )}

      <div className={`flex-1 overflow-y-auto ${padX} py-3`}>
        {rows.length === 0 && (
          <p className="text-sm text-proto-muted">
            Chưa có dòng nào. Bấm <b>+</b> trên một kết quả tìm kiếm để thêm.
          </p>
        )}
        {rows.map((row, index) => (
          <div key={row.id}>
            <div
              draggable={!readOnly}
              // Cả DÒNG kéo được, không phải chỉ một tay cầm nhỏ. Nhưng dòng
              // có chứa ô nhập số frame với mấy cái nút — bắt đầu kéo từ trong
              // đó thì người dùng mất luôn khả năng bôi đen sửa số. Nên chặn
              // drag khi điểm bắt đầu nằm trong một phần tử tương tác.
              onDragStart={(e) => {
                const el = e.target as HTMLElement;
                if (el.closest("input,textarea,button,select,a")) {
                  e.preventDefault();
                  return;
                }
                setDragIndex(index);
                e.dataTransfer.effectAllowed = "move";
                // Firefox không khởi động drag nếu dataTransfer rỗng.
                e.dataTransfer.setData("text/plain", String(row.id));
              }}
              onDragOver={(e) => {
                if (dragIndex === null) return;
                e.preventDefault();          // không gọi thì onDrop không chạy
                e.dataTransfer.dropEffect = "move";
                if (overIndex !== index) setOverIndex(index);
              }}
              onDrop={(e) => {
                e.preventDefault();
                const from = dragIndex;
                setDragIndex(null);
                setOverIndex(null);
                if (from !== null) void dropRow(from, index);
              }}
              onDragEnd={() => {
                setDragIndex(null);
                setOverIndex(null);
              }}
              // `group` đã bỏ khỏi đây: chỗ duy nhất dùng group-hover là ảnh
              // xem trước, và nó đã chuyển sang group/thumb gắn vào riêng cái
              // ảnh nhỏ. Để lại một class không ai dùng chỉ khiến người sau
              // tưởng có thứ gì đó phụ thuộc vào nó.
              className={`relative flex items-center gap-2 px-2 py-0.5 rounded-[7px] bg-white border border-proto-line border-l-[3px] mb-1 ${rowTextSize} ${
                readOnly ? "cursor-pointer" : "cursor-grab active:cursor-grabbing"
              } ${stripe(row)} ${index === 0 ? "bg-proto-primary/10" : ""} ${
                row.id === activeRowId ? "ring-2 ring-proto-primary-active" : ""
              } ${dragIndex === index ? "opacity-40" : ""} ${
                overIndex === index && dragIndex !== null && dragIndex !== index
                  ? dragIndex < index
                    ? "border-b-2 border-b-proto-primary-active"
                    : "border-t-2 border-t-proto-primary-active"
                  : ""
              }`}
              onClick={() => onRowClick(row)}
              title={
                row.origin === "auto"
                  ? "Dòng tự sinh"
                  : `Thêm bởi ${row.created_by?.display_name ?? "—"}`
              }
            >
              {/* Chấm nắm: chỉ để người dùng biết dòng này kéo được. Bản thân
                  nó không xử lý gì — cả dòng mới là vùng kéo. */}
              {!readOnly && (
                <span
                  className="shrink-0 select-none text-proto-line leading-none"
                  title="Kéo để đổi thứ tự"
                >
                  ⠿
                </span>
              )}
              {/* Ảnh xem trước chỉ bung khi rê vào ĐÚNG cái ảnh nhỏ này.
                  Trước đây `group` đặt trên cả dòng, nên rê vào bất kỳ đâu —
                  kể cả số frame hay khoảng trống — là ảnh lớn 360×240 bung ra
                  che mất mấy dòng trên dưới.

                  Điều khiển bằng state của React chứ KHÔNG dùng group-hover
                  của Tailwind. Lý do đo được: bản dev bọc luật hover trong
                  `@media (hover: hover)` còn bản build production thì không,
                  nên cùng một dòng mã cho ra hai hành vi khác nhau ở hai chỗ —
                  kiểu sai chỉ lộ ra sau khi deploy. `onMouseEnter` chạy y hệt
                  nhau ở cả hai. */}
              <span
                className="relative shrink-0 leading-none"
                onMouseEnter={() => setHoverRowId(row.id)}
                onMouseLeave={() =>
                  setHoverRowId((cur) => (cur === row.id ? null : cur))
                }
              >
                <FramePreview videoId={row.video_id} frameIdx={row.frames[0]} />
                {/* Chỉ dựng khi đang rê tới. Ảnh lớn dùng CÙNG file với ảnh
                    nhỏ nên trình duyệt đã có sẵn, không phải tải gì thêm. Bỏ
                    qua ở panel — nó nằm cạnh video, nên video chính là ảnh xem
                    trước. */}
                {isDialog && hoverRowId === row.id && (
                  <div className="pointer-events-none absolute left-14 top-0 z-[1000]">
                    <FramePreview
                      videoId={row.video_id}
                      frameIdx={row.frames[0]}
                      size="large"
                      className="shadow-2xl border-2 border-white"
                    />
                  </div>
                )}
              </span>
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
              {index === 0 && canApplyAll && (
                <button
                  type="button"
                  disabled={busy || applyAllTargets.length === 0}
                  title="Chép đáp án này sang mọi dòng còn lại của task"
                  className="shrink-0 text-[10.5px] font-semibold text-proto-primary-active underline decoration-dotted disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={(event) => {
                    event.stopPropagation();
                    void applyAnswerToAll();
                  }}
                >
                  Áp đáp án cho tất cả dòng
                </button>
              )}
              <span className="ml-auto flex gap-1" onClick={(event) => event.stopPropagation()}>
                {!readOnly && (
                  <>
                    {/* Chỉ còn "↑1" và "×". Việc sắp lại thứ tự đã chuyển
                        sang KÉO THẢ cả dòng (xem onDragStart phía trên).

                        Giữ "↑1" vì kéo một dòng từ hạng 60 lên hạng 1 là cuộn
                        rất lâu, còn nút thì một cú bấm. Hai thứ bù nhau chứ
                        không thay nhau. */}
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
            {/* Vạch R@k nằm SAU dòng thứ k, không phải trước.
                R@k nghĩa là "điểm tính trên k dòng đầu", nên mọi thứ PHÍA TRÊN
                vạch mới là phần được tính. Vẽ trước dòng thì R@1 hiện lên trên
                dòng 1 — trông như dòng 1 nằm ngoài top-1, ngược hẳn ý nghĩa. */}
            {CUTS.includes(index + 1) && (
              <div className="flex items-center gap-2 my-1.5">
                <b className="text-[9px] font-extrabold tracking-wide text-proto-primary-active">
                  R@{index + 1}
                </b>
                <span className="flex-1 h-px bg-proto-primary/40" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
