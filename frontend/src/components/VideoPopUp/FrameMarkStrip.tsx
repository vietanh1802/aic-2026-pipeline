import { useEffect, useState } from "react";

import FramePreview from "../FramePreview";
import { frameAt, frameRange } from "../../helpers/frameRange";

/**
 * Marking the moment, directly under the player it refers to.
 *
 * This used to sit in the submit form at the bottom of the popup, which put the
 * two things that have to be read together — the frame on screen and the frame
 * being submitted — at opposite ends of a scrolling dialog. Everything here is
 * about the video above it, so it belongs against the video.
 *
 * The bar is the video's own duration. The block between the two marks is the
 * moment; the line is where playback is. Clicking anywhere on it seeks, which
 * makes it a coarse scrubber as well as a readout.
 */
function clock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const whole = Math.floor(seconds);
  const mm = String(Math.floor(whole / 60)).padStart(2, "0");
  const ss = String(whole % 60).padStart(2, "0");
  const ms = String(Math.round((seconds - whole) * 1000)).padStart(3, "0");
  return `${mm}:${ss}.${ms}`;
}

export default function FrameMarkStrip({
  videoId,
  currentSeconds,
  duration,
  fps,
  markIn,
  markOut,
  onMarkIn,
  onMarkOut,
  onClear,
  onSeek,
  submits = "midpoint",
}: {
  /** Để tra keyframe gần nhất cho ba ô xem trước. */
  videoId: string;
  currentSeconds: number;
  duration: number;
  fps: number;
  markIn: number | null;
  markOut: number | null;
  /** Reads the player's exact currentTime itself — no argument to go stale. */
  onMarkIn: () => void;
  onMarkOut: () => void;
  onClear: () => void;
  onSeek: (seconds: number) => void;
  /**
   * Khung nào sẽ được nộp — thứ duy nhất khác nhau giữa hai loại câu.
   *
   * "midpoint": KIS/Q&A, nộp khung GIỮA hai đầu đã ghim.
   * "playhead": TRAKE, nộp đúng khung đang dừng. TRAKE chấm từng mốc trong một
   * cửa sổ hẹp, nên lấy trung bình của một đoạn dài là tự đẩy mình ra khỏi cửa
   * sổ đó. Hai đầu vẫn ghim được — chúng đi vào ô "từ/đến" của Điền tự động
   * trong giỏ, để rải các dòng sau nằm trong đúng đoạn đã xem.
   */
  submits?: "midpoint" | "playhead";
}) {
  // Ba ô ảnh đầu/giữa/cuối, mở bằng nút. Mặc định đóng: phần lớn thời gian
  // người dùng đang nhìn chính cái video ngay trên, ba ô này chỉ có việc vào
  // đúng lúc chốt — khi cần biết khung giữa mà máy tính ra có rơi vào cảnh
  // mình muốn không, mà cái đó thì video không trả lời được nếu không tua về.
  const [showFrames, setShowFrames] = useState(false);
  // I and O are what every video editor binds these to. Guarded on the target
  // so typing an answer into a field does not drop marks behind the dialog.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable;
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;

      if (event.key === "i" || event.key === "I") onMarkIn();
      if (event.key === "o" || event.key === "O") onMarkOut();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onMarkIn, onMarkOut]);

  const range = frameRange(
    markIn ?? currentSeconds,
    markOut ?? currentSeconds,
    fps
  );
  const currentFrame = frameAt(currentSeconds, fps);

  const span = duration > 0 ? duration : 1;
  const pct = (seconds: number) =>
    `${Math.min(100, Math.max(0, (seconds / span) * 100))}%`;

  const low = Math.min(markIn ?? currentSeconds, markOut ?? currentSeconds);
  const high = Math.max(markIn ?? currentSeconds, markOut ?? currentSeconds);
  const marked = markIn !== null || markOut !== null;
  // Hai đầu trùng nhau thì khung giữa CHÍNH LÀ hai đầu — không có gì để đối
  // chiếu. `range` cũng null khi thiếu fps, và lúc đó không có số frame nào.
  const canCompare = range !== null && range.start !== range.end;

  // Khung sẽ được nộp, và cái nhãn nói nó là khung nào. Phải khớp đúng
  // SubmitForm.frameToSubmit() — dải này in ra con số, còn cái nút mới thật sự
  // gửi nó đi, và hai chỗ nói khác nhau là kiểu sai không ai phát hiện ra cho
  // tới lúc đọc bảng điểm.
  const onPlayhead = submits === "playhead";
  const submitFrame = onPlayhead ? currentFrame : range?.frame ?? null;
  const middleLabel = onPlayhead ? "đang đứng — sẽ nộp" : "giữa — sẽ nộp";

  // Nhánh `disabled` cho câu TRAKE đã bỏ. Nó thay cả dải điều khiển bằng một
  // dòng chữ "TRAKE nộp một frame cho mỗi mốc, không lấy trung bình" — đúng về
  // khung được nộp, nhưng vì thế mà câu TRAKE cũng mất luôn đường ghim hai
  // đầu, trong khi hai đầu đó còn một việc khác hẳn: chúng đi vào ô "từ/đến"
  // của Điền tự động trong giỏ. Giờ dải hiện đủ cho mọi loại câu, chỉ con số
  // "Nộp" là đổi theo `submits`.

  return (
    <div className="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div className="flex items-center gap-3 flex-wrap mb-2">
        <span className="text-[12px] text-proto-muted">
          Khung hiện tại{" "}
          <b className="font-mono text-proto-ink text-[15px]">
            {currentFrame ?? "—"}
          </b>{" "}
          <span className="font-mono">{clock(currentSeconds)}</span>
        </span>

        <span className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => onMarkIn()}
            className="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary"
          >
            ⇤ Đầu <span className="text-proto-muted font-normal">I</span>
          </button>
          <button
            type="button"
            onClick={() => onMarkOut()}
            className="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary"
          >
            Cuối ⇥ <span className="text-proto-muted font-normal">O</span>
          </button>
          {marked && (
            <button
              type="button"
              onClick={onClear}
              className="text-[11.5px] text-proto-muted underline"
            >
              bỏ ghim
            </button>
          )}
        </span>
      </div>

      {/* The video's duration, with the marked moment on it. */}
      <div
        className="relative h-2.5 rounded-full bg-proto-line cursor-pointer mb-2"
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const fraction = (event.clientX - box.left) / box.width;
          onSeek(Math.min(span, Math.max(0, fraction * span)));
        }}
        title="Bấm để tua"
      >
        {marked && (
          <div
            className="absolute inset-y-0 bg-proto-primary/70 rounded-full"
            style={{ left: pct(low), width: pct(high - low) }}
          />
        )}
        <div
          className="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded"
          style={{ left: pct(currentSeconds) }}
        />
      </div>

      <div className="flex items-center gap-3 flex-wrap text-[12px]">
        <span className="text-proto-muted">
          đầu{" "}
          <b
            className={`font-mono ${
              markIn === null ? "text-proto-muted" : "text-proto-ink"
            }`}
          >
            {range ? range.start : "—"}
          </b>
        </span>
        <span className="text-proto-muted">
          cuối{" "}
          <b
            className={`font-mono ${
              markOut === null ? "text-proto-muted" : "text-proto-ink"
            }`}
          >
            {range ? range.end : "—"}
          </b>
        </span>

        {/* Chỉ hiện khi hai đầu KHÁC nhau. Ghim trùng một chỗ thì ba ô ra ba
            ảnh giống hệt, và một cái nút mở ra ba bản sao thì tệ hơn là không
            có nút. */}
        {canCompare && (
          <button
            type="button"
            onClick={() => setShowFrames((open) => !open)}
            className="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted"
          >
            {showFrames ? "ẩn 3 khung" : "xem 3 khung"}
          </button>
        )}

        {submitFrame !== null ? (
          <span className="ml-auto flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Nộp
            </span>
            <b className="font-mono text-[18px] leading-none text-proto-primary-active">
              {submitFrame}
            </b>
            {/* Nói ra vì với TRAKE con số này KHÔNG đổi khi ghim hai đầu —
                không có dòng này thì trông như dải ghim bị hỏng. */}
            {onPlayhead && (
              <span
                className="text-[10.5px] text-proto-muted"
                title="TRAKE chấm từng mốc trong một cửa sổ hẹp. Hai đầu ghim ở đây đi vào ô từ/đến của Điền tự động trong giỏ."
              >
                khung đang đứng
              </span>
            )}
          </span>
        ) : (
          <span className="ml-auto text-[#c64545]">
            Thiếu fps cho video này — không tính được frame.
          </span>
        )}
      </div>

      {/* Ba khung: hai đầu người dùng ghim, và khung GIỮA do frameRange tính
          ra — chính là khung sẽ được nộp.

          Cái đáng xem là khung giữa: hai đầu thì vừa tua qua nên còn nhớ,
          còn `floor((start + end) / 2)` là một con số máy tính ra, và không
          có gì bảo đảm nó rơi vào đúng cảnh mình muốn. Trước đây muốn biết
          thì phải tua ngược video về đó rồi tua lại.

          Ảnh là keyframe GẦN NHẤT, không phải đúng khung đó — số frame dưới
          mỗi ô mới là số thật. Bấm vào ô nào thì tua video tới đó. */}
      {canCompare && showFrames && range && submitFrame !== null && (
        <div className="mt-2 pt-2 border-t border-dashed border-proto-line grid grid-cols-3 gap-2">
          {(
            [
              ["đầu", range.start],
              // Với TRAKE đây là khung đang dừng, không phải điểm giữa — ô này
              // phải bày đúng thứ sắp được nộp, nếu không nó khoe một khung
              // khác với khung thật.
              [middleLabel, submitFrame],
              ["cuối", range.end],
            ] as const
          ).map(([label, frame], index) => (
            <button
              key={label}
              type="button"
              onClick={() => onSeek(frame / fps)}
              title={`Tua video tới frame ${frame}`}
              className="text-left"
            >
              <span
                className={`block w-full aspect-video rounded-[6px] overflow-hidden border-2 ${
                  index === 1 ? "border-proto-primary" : "border-proto-line"
                }`}
              >
                <FramePreview
                  videoId={videoId}
                  frameIdx={frame}
                  size="fill"
                />
              </span>
              <span className="flex items-baseline justify-between gap-1 mt-0.5">
                <span
                  className={`text-[10px] truncate ${
                    index === 1
                      ? "font-bold text-proto-primary-active"
                      : "text-proto-muted"
                  }`}
                >
                  {label}
                </span>
                <b className="font-mono text-[11px] text-proto-ink">{frame}</b>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
