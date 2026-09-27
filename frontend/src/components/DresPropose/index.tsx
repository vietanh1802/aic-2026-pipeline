import { useEffect, useState } from "react";

import {
  canSubmitDres,
  describePayload,
  formatMs,
  getDresStatus,
  proposeDresSubmission,
  rejectDresSubmission,
  type DresStatus,
  type DresSubmission,
  type DresTaskType,
} from "../../api/dres";
import { approveWithConfirm } from "../../helpers/dresApprove";
import { fpsOf, frameToMs } from "../../helpers/frameIdentity";
import { frameAt } from "../../helpers/frameRange";
import { parseFrameList, parseManualPoint, type PointUnit } from "../../helpers/frameList";
import { formatClock } from "../../helpers/youtube";
import { useAuthStore } from "../../store/authStore";
import Button from "../Button";
import DresTaskClock from "../DresTaskClock";
import { useDresCurrentTask } from "../DresTaskClock/useDresCurrentTask";

const TYPES: { id: DresTaskType; label: string }[] = [
  { id: "kis", label: "KIS" },
  { id: "qa", label: "Q&A" },
  { id: "trake", label: "TRAKE" },
];

/**
 * "Nộp DRES" trong popup video — đề xuất, hoặc nộp luôn, một bài chung kết.
 *
 * Lấy THỜI ĐIỂM ĐANG PHÁT của trình phát chứ không phải keyframe gần nhất: ở
 * chung kết đáp án là một đoạn trong video gốc, và người dùng đã tua tới đúng
 * khoảnh khắc đó. Mili-giây gửi lên server; server quy ra frame bằng fps BTC.
 *
 * Tách hẳn khỏi SubmitForm/giỏ đáp án: giỏ là danh sách xếp hạng R@k của vòng
 * sơ tuyển, còn đây là MỘT đáp án được chấm ngay — trộn hai luồng thì một cú
 * "Add Answer" quen tay có thể thành một lần nộp −10 điểm.
 *
 * Người được tự gửi (admin, hoặc mọi người khi admin bật chế độ đó) có nút
 * "Nộp ngay": đề xuất rồi duyệt liền, qua cùng hộp xác nhận. Người còn lại chỉ
 * đề xuất và chờ duyệt ở tab DRES.
 */
export default function DresPropose({
  videoId,
  getPlayhead,
  defaultType,
  defaultOpen = false,
  currentSeconds,
  pickedSeconds = null,
  onClearPicked,
}: {
  videoId: string;
  /** Giây, đọc thẳng currentTime của <video> tại lúc bấm. */
  getPlayhead: () => number;
  defaultType?: DresTaskType;
  /** Chung kết: khối này là thứ duy nhất để nộp, nên mở sẵn. */
  defaultOpen?: boolean;
  /**
   * Vị trí đang phát (giây, cập nhật ~4 lần/giây) — chỉ để HIỆN frame/ms sẽ
   * nộp. Lúc bấm nút vẫn đọc `getPlayhead()` cho đúng khung.
   */
  currentSeconds?: number;
  /**
   * Thời điểm chọn trên "Khung thời gian YouTube" (giây). Khác null thì bài
   * nộp dùng thời điểm này thay cho vị trí trình phát — video trong popup có
   * thể chưa tải xong trên mạng chậm.
   */
  pickedSeconds?: number | null;
  onClearPicked?: () => void;
}) {
  const role = useAuthStore((state) => state.user?.role);
  const [open, setOpen] = useState(defaultOpen);
  const [status, setStatus] = useState<DresStatus | null>(null);
  const [type, setType] = useState<DresTaskType>(defaultType ?? "kis");
  const [answer, setAnswer] = useState("");
  // Was: const [marks, setMarks] = useState<number[]>([]);
  // Mốc nối đuôi theo thứ tự bấm, nên buộc phải tìm E1 trước rồi mới tới E2 —
  // trong khi thường cảnh E2 lại là cảnh dễ tìm nhất. Giờ là N ô cố định (ms,
  // null = chưa điền), điền ô nào trước cũng được; nộp theo thứ tự E1..EN.
  const [eventCount, setEventCount] = useState(3);
  const [slots, setSlots] = useState<(number | null)[]>([null, null, null]);
  // TRAKE điền tay: gõ/dán thẳng số frame. Gửi `frames` thay cho `times_ms`,
  // nên số trong ô chính là số nằm trong chuỗi TR- — không qua quy đổi ms.
  const [trakeManual, setTrakeManual] = useState(false);
  const [manualText, setManualText] = useState("");
  // KIS / Q&A điền tay một thời điểm: số frame hoặc thời gian trong video, có
  // bộ chuyển đổi ra ms ngay dưới ô. Điền tay thì thắng cả trình phát lẫn khung
  // YouTube — người ta gõ vì đã biết chính xác mình muốn nộp gì.
  const [pointManual, setPointManual] = useState(false);
  const [pointUnit, setPointUnit] = useState<PointUnit>("frame");
  const [pointText, setPointText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DresSubmission | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Mốc TRAKE thuộc về một video; trỏ popup sang video khác thì bỏ.
  useEffect(() => {
    setSlots((s) => s.map(() => null));
    setManualText("");
    setPointText("");
    setResult(null);
    setError(null);
  }, [videoId]);

  // Đọc chế độ mỗi lần mở khung: admin có thể vừa đổi giữa buổi.
  useEffect(() => {
    if (open) {
      void getDresStatus().then(setStatus).catch(() => undefined);
    }
  }, [open]);

  // Chỉ hỏi khi khung đang mở: popup video mở suốt buổi sơ tuyển cũng không
  // được bắn request DRES mỗi 3 giây.
  const currentTask = useDresCurrentTask(open);

  const canSubmit = canSubmitDres(role, status);
  const fps = fpsOf(videoId);
  // Gửi ms của đúng KHUNG đang hiện (frameAt, cùng phép với dải khung dưới
  // video), không phải ms thô của playhead.
  //
  // Old: const nowMs = () => Math.round(getPlayhead() * 1000);
  // Lệch một khung: ở 100,5 s / 29,97 fps dải khung ghi frame 3011 (floor),
  // còn server quy 100500 ms về round(3011,985) = 3012. Màn hình nói một khung,
  // bài nộp mang khung khác. Giờ gửi frameToMs(3011) = 100467 ms, server quy
  // lại đúng 3011 (vòng đi-về đã kiểm trong frameIdentity.test.ts). Lệch so
  // với playhead thô luôn dưới một khung.
  const msAt = (seconds: number): number =>
    frameToMs(frameAt(seconds, fps), fps) ?? Math.round(seconds * 1000);
  // Old: const nowMs = () => msAt(getPlayhead());
  // Khung YouTube đã chọn thì thắng trình phát: người ta chọn ở đó chính vì
  // trình phát chưa tải được tới cảnh cần nộp.
  const fromPicked = pickedSeconds !== null;
  const nowMs = () => msAt(fromPicked ? pickedSeconds : getPlayhead());
  // Frame mà server sẽ quy ra từ ms: cùng `round(t / 1000 * fps)` như
  // routers/dres.py, để số hiện ở đây trùng số nằm trong bài nộp.
  const frameOfMs = (ms: number): number | null => (fps ? Math.round((ms / 1000) * fps) : null);
  const withFrame = (ms: number) => {
    const frame = frameOfMs(ms);
    return frame === null ? `${ms} ms` : `frame ${frame} · ${ms} ms`;
  };

  const manual = parseFrameList(manualText, videoId);
  const useManual = type === "trake" && trakeManual;
  const point = parseManualPoint(pointText, pointUnit, videoId, fps);
  const useManualPoint = type !== "trake" && pointManual;

  const propose = async (): Promise<DresSubmission | null> => {
    // TRAKE điền tay: gửi frames nguyên văn. KIS/Q&A điền tay: gửi đúng số ms
    // bộ chuyển đổi đang hiện — KIS/Q&A chấm theo ms nên số nhìn thấy phải là
    // số được gửi. Còn lại: ms như trước.
    const points = useManual
      ? { frames: manual.frames }
      : {
          times_ms:
            type === "trake" ? (slots as number[]) : [useManualPoint ? (point.ms as number) : nowMs()],
        };
    const created = await proposeDresSubmission({
      task_type: type,
      video_id: videoId,
      ...points,
      answer: type === "qa" ? answer : undefined,
    });
    setResult(created);
    // Cả ô điền tay lẫn các ô E1..EN đều GIỮ nguyên sau khi nộp: TRAKE được
    // điểm một phần, nên nộp sai một mốc thì sửa đúng ô đó rồi nộp lại, khỏi
    // tìm lại cả dãy. (Trước đây danh sách mốc bị xoá sau mỗi lần nộp.)
    return created;
  };

  const run = async (sendNow: boolean) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const created = await propose();
      if (!sendNow || !created) {
        return;
      }
      const sent = await approveWithConfirm(created);
      if (sent) {
        setResult(sent);
      } else {
        // Huỷ ở hộp xác nhận thì rút luôn đề xuất vừa tạo, để nó không nằm
        // trong hàng chờ như thể còn ai đó phải duyệt.
        setResult(await rejectDresSubmission(created.id));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      void currentTask.refresh();
    }
  };

  // Bài đã đề xuất mà chưa gửi (ví dụ gửi lỗi mạng) thì gửi lại từ đây.
  const approveNow = async () => {
    if (!result) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const sent = await approveWithConfirm(result);
      if (sent) {
        setResult(sent);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      void currentTask.refresh();
    }
  };

  const pointReady = !useManualPoint || (point.error === null && point.ms !== null);
  // Các ô E1..EN: đủ hết mới nộp được, và hai ô không được trùng frame (server
  // cũng từ chối). Frame tính như server: round(ms / 1000 * fps).
  const filledCount = slots.filter((v) => v !== null).length;
  const slotFrames = slots.map((ms) => (ms === null ? null : frameOfMs(ms)));
  const dupSlot = slotFrames.findIndex(
    (f, i) => f !== null && slotFrames.indexOf(f) !== i
  );
  const slotsReady = filledCount === eventCount && dupSlot < 0;
  const setSlot = (index: number, value: number | null) =>
    setSlots((s) => s.map((v, i) => (i === index ? value : v)));
  const changeCount = (n: number) => {
    setEventCount(n);
    // Giữ các ô đã điền khi đổi số hành động; ô thừa thì bỏ.
    setSlots((s) => Array.from({ length: n }, (_, i) => s[i] ?? null));
  };
  const ready =
    !busy &&
    ((type === "kis" && pointReady) ||
      (type === "qa" && answer.trim().length > 0 && pointReady) ||
      (type === "trake" &&
        (useManual ? manual.error === null && manual.frames.length > 0 : slotsReady)));
  // Nhãn nút nói rõ nộp theo nguồn nào — hai nguồn cho hai con số khác nhau.
  const what =
    type === "trake"
      ? useManual
        ? `TRAKE (${manual.frames.length} frame điền tay)`
        : `TRAKE (${filledCount}/${eventCount} mốc)`
      : `${type === "qa" ? "Q&A" : "KIS"} ${
          useManualPoint
            ? `tại frame ${point.frame ?? "?"} (điền tay)`
            : fromPicked
              ? "tại thời điểm đã chọn (YouTube)"
              : "tại thời điểm đang phát"
        }`;

  return (
    <div className="mt-3 rounded-[10px] border-2 border-[#7b1fa2]/40 bg-[#7b1fa2]/5 p-3 font-baloo">
      <button
        type="button"
        className="text-[13px] font-bold text-[#7b1fa2]"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "▾" : "▸"} Nộp DRES (chung kết)
      </button>

      {open && (
        <div className="flex flex-col gap-2 mt-2">
          <div className="p-2 rounded-[8px] bg-white border border-proto-line">
            <DresTaskClock {...currentTask} />
          </div>
          {/* Điền tay thì hai dòng này không còn là thứ được nộp — ẩn đi cho
              khỏi đọc nhầm con số. */}
          {useManualPoint ? null : fromPicked ? (
            <div className="text-[12px] text-[#c4302b]">
              Nộp theo khung YouTube:{" "}
              <b className="font-mono">{withFrame(msAt(pickedSeconds))}</b>
              {onClearPicked && (
                <button
                  type="button"
                  className="ml-2 text-[11px] text-proto-muted underline"
                  onClick={onClearPicked}
                >
                  dùng trình phát
                </button>
              )}
            </div>
          ) : (
            currentSeconds !== undefined && (
              <div className="text-[12px] text-proto-muted">
                Đang đứng:{" "}
                <b className="font-mono text-proto-ink">
                  {withFrame(msAt(currentSeconds))}
                </b>
              </div>
            )
          )}
          <div className="flex flex-wrap items-center gap-1">
            {TYPES.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setType(t.id)}
                className={`text-[12px] px-3 py-1 rounded-[7px] border ${
                  type === t.id
                    ? "bg-white border-[#7b1fa2] font-bold text-[#7b1fa2]"
                    : "border-transparent text-proto-muted"
                }`}
              >
                {t.label}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-proto-muted">
              {status?.submit_mode === "everyone"
                ? "Chế độ: mọi người nộp được"
                : "Chế độ: chỉ admin nộp"}
            </span>
          </div>

          {type !== "trake" && (
            <div className="flex items-center gap-1">
              {(
                [
                  [false, fromPicked ? "Theo khung YouTube" : "Theo trình phát"],
                  [true, "Điền tay frame / thời gian"],
                ] as const
              ).map(([manualMode, label]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setPointManual(manualMode)}
                  className={`text-[11.5px] px-2.5 py-0.5 rounded-[6px] border ${
                    pointManual === manualMode
                      ? "bg-white border-[#7b1fa2] font-bold text-[#7b1fa2]"
                      : "border-transparent text-proto-muted"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {useManualPoint && (
            <div className="flex flex-col gap-1.5 p-2 rounded-[8px] bg-white border border-proto-line">
              <div className="flex items-center gap-1.5 flex-wrap">
                {(
                  [
                    ["frame", "Số frame"],
                    ["time", "Thời gian"],
                  ] as const
                ).map(([unit, label]) => (
                  <button
                    key={unit}
                    type="button"
                    onClick={() => setPointUnit(unit)}
                    className={`text-[11.5px] px-2 py-0.5 rounded-[6px] border ${
                      pointUnit === unit
                        ? "border-[#7b1fa2] font-bold text-[#7b1fa2]"
                        : "border-proto-line text-proto-muted"
                    }`}
                  >
                    {label}
                  </button>
                ))}
                <input
                  className="flex-1 min-w-[140px] px-2 py-1 rounded-[6px] border border-proto-line text-[13px] font-mono"
                  value={pointText}
                  onChange={(e) => setPointText(e.target.value)}
                  placeholder={
                    pointUnit === "frame" ? "15697 hoặc tên keyframe" : "10:27 · 1:02:03.5 · số giây"
                  }
                />
              </div>
              {/* Bộ chuyển đổi: cùng một khoảnh khắc ở cả ba đơn vị. ms là số
                  được gửi lên DRES cho KIS / Q&A. */}
              {point.error ? (
                <span className="text-[12px] text-[#c64545]">{point.error}</span>
              ) : point.frame !== null ? (
                <span className="text-[12.5px] font-mono text-proto-ink">
                  = frame <b>{point.frame}</b> · <b>{point.ms}</b> ms ·{" "}
                  {formatClock(point.seconds as number)}
                  <span className="text-proto-muted"> ({fps} fps)</span>
                </span>
              ) : (
                <span className="text-[11.5px] text-proto-muted">
                  Gõ một số frame hoặc thời gian để xem quy đổi ra ms.
                </span>
              )}
            </div>
          )}

          {type === "qa" && (
            <input
              className="p-2 rounded-[8px] bg-white border border-proto-line text-sm"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Đáp án Q&A"
            />
          )}

          {type === "trake" && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[12px] text-proto-muted">Số hành động:</span>
              {[2, 3, 4, 5, 6, 7, 8].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => changeCount(n)}
                  className={`w-7 text-[12px] py-0.5 rounded-[6px] border font-mono ${
                    eventCount === n
                      ? "bg-[#7b1fa2] border-[#7b1fa2] text-white font-bold"
                      : "bg-white border-proto-line text-proto-ink"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          )}

          {type === "trake" && (
            <div className="flex items-center gap-1">
              {(
                [
                  [false, "Mốc tại đây"],
                  [true, "Điền tay số frame"],
                ] as const
              ).map(([manual, label]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setTrakeManual(manual)}
                  className={`text-[11.5px] px-2.5 py-0.5 rounded-[6px] border ${
                    trakeManual === manual
                      ? "bg-white border-[#7b1fa2] font-bold text-[#7b1fa2]"
                      : "border-transparent text-proto-muted"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {type === "trake" && trakeManual && (
            <div className="flex flex-col gap-1.5">
              <textarea
                className="p-2 rounded-[8px] bg-white border border-proto-line text-[12.5px] font-mono min-h-[56px]"
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder={"15697, 15820, 16002\nhoặc dán tên keyframe: M05_V019-0193-15697.jpg"}
              />
              {manual.error ? (
                <span className="text-[12px] text-[#c64545]">{manual.error}</span>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {manual.frames.map((frame, i) => (
                    <span
                      key={`${i}-${frame}`}
                      className="text-[12px] px-2 py-0.5 rounded-full bg-white border border-proto-line font-mono"
                    >
                      E{i + 1} frame {frame}
                      {frameToMs(frame, fps) !== null && (
                        <span className="text-proto-muted"> · {frameToMs(frame, fps)} ms</span>
                      )}
                    </span>
                  ))}
                </div>
              )}
              {manual.warnings.map((w) => (
                <span key={w} className="text-[11.5px] text-[#8a6a0f]">⚠ {w}</span>
              ))}
              {!manual.error && manual.frames.length > 0 && manual.frames.length !== eventCount && (
                <span className="text-[11.5px] text-[#8a6a0f]">
                  ⚠ Đã điền {manual.frames.length} frame nhưng chọn {eventCount} hành động.
                </span>
              )}
            </div>
          )}

          {type === "trake" && !trakeManual && (
            <div className="flex flex-col gap-1.5">
              {/* Was: một nút "+ Mốc E{n} tại đây" nối đuôi danh sách mốc, nên
                  bắt buộc đi E1 → E2 → E3. Giờ mỗi ô có nút riêng. */}
              {slots.map((ms, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-2 px-2 py-1 rounded-[8px] border text-[12px] ${
                    ms === null
                      ? "bg-white/60 border-dashed border-proto-line"
                      : dupSlot >= 0 && slotFrames[i] === slotFrames[dupSlot]
                        ? "bg-white border-[#c64545]"
                        : "bg-white border-[#7b1fa2]/50"
                  }`}
                >
                  <b className="font-mono text-[#7b1fa2] w-7">E{i + 1}</b>
                  {ms === null ? (
                    <span className="text-proto-muted">chưa chọn</span>
                  ) : (
                    <span className="font-mono">
                      {formatMs(ms)} <span className="text-proto-muted">({withFrame(ms)})</span>
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-1.5">
                    <Button size="xs" variant="outline" onClick={() => setSlot(i, nowMs())}>
                      {ms === null ? "Đặt tại đây" : "Đặt lại"}
                    </Button>
                    {ms !== null && (
                      <button
                        type="button"
                        className="text-proto-muted hover:text-[#c64545] px-1"
                        onClick={() => setSlot(i, null)}
                        title={`Xoá E${i + 1}`}
                      >
                        ×
                      </button>
                    )}
                  </span>
                </div>
              ))}
              {dupSlot >= 0 && (
                <span className="text-[12px] text-[#c64545]">
                  Hai mốc trùng frame {slotFrames[dupSlot]} — đặt lại một trong hai.
                </span>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {canSubmit ? (
              <>
                <Button size="sm" variant="danger" disabled={!ready} onClick={() => void run(true)}>
                  Nộp ngay {what}
                </Button>
                <Button size="sm" variant="outline" disabled={!ready} onClick={() => void run(false)}>
                  Chỉ đề xuất
                </Button>
              </>
            ) : (
              <Button size="sm" disabled={!ready} onClick={() => void run(false)}>
                Đề xuất {what}
              </Button>
            )}
            {canSubmit && result && (result.status === "proposed" || result.status === "failed") && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => void approveNow()}>
                {result.status === "failed" ? "Gửi lại" : "Duyệt & nộp"} #{result.id}
              </Button>
            )}
          </div>

          {result && (
            <div className="text-[12px] flex flex-col gap-0.5">
              <span>
                <b>#{result.id}</b>{" "}
                {result.verdict
                  ? `→ ${result.verdict}`
                  : result.status === "proposed"
                    ? "đã đề xuất — chờ duyệt ở tab DRES"
                    : result.status === "failed"
                      ? `lỗi: ${result.error ?? ""}`
                      : result.status === "rejected"
                        ? "đã huỷ, không gửi"
                        : result.status}
              </span>
              <code className="break-all">{describePayload(result)}</code>
              {result.warnings.map((w) => (
                <span key={w} className="text-[#8a6a0f]">⚠ {w}</span>
              ))}
            </div>
          )}
          {error && <span className="text-[12px] text-[#c64545]">{error}</span>}
        </div>
      )}
    </div>
  );
}
