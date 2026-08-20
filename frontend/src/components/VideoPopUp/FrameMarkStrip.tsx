import { useEffect } from "react";

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
  currentSeconds,
  duration,
  fps,
  markIn,
  markOut,
  onMarkIn,
  onMarkOut,
  onClear,
  onSeek,
  disabled = false,
}: {
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
  /** TRAKE submits one frame per event, so a midpoint has nowhere to go. */
  disabled?: boolean;
}) {
  // I and O are what every video editor binds these to. Guarded on the target
  // so typing an answer into a field does not drop marks behind the dialog.
  useEffect(() => {
    if (disabled) return;
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
  }, [disabled, onMarkIn, onMarkOut]);

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

  if (disabled) {
    return (
      <div className="mt-2 px-3 py-2 rounded-[8px] bg-proto-soft border border-proto-line font-baloo text-[12px] text-proto-muted">
        Khung hiện tại{" "}
        <b className="font-mono text-proto-ink text-[14px]">
          {currentFrame ?? "—"}
        </b>{" "}
        · {clock(currentSeconds)} — TRAKE nộp một frame cho mỗi mốc, không lấy
        trung bình.
      </div>
    );
  }

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

        {range ? (
          <span className="ml-auto flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wide text-proto-muted">
              Nộp
            </span>
            <b className="font-mono text-[18px] leading-none text-proto-primary-active">
              {range.frame}
            </b>
          </span>
        ) : (
          <span className="ml-auto text-[#c64545]">
            Thiếu fps cho video này — không tính được frame.
          </span>
        )}
      </div>
    </div>
  );
}
