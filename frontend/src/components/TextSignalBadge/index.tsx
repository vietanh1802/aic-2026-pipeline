import { useRef, useState } from "react";
import type { VideoAnnotation } from "../../types/api";

interface TextSignalBadgeProps {
  videoId: string;
  annotation: VideoAnnotation | undefined;
  filterQuery: string;
  mode: string;
}

type Tone = "green" | "amber" | "gray";

// Same three-tone scale as FrameDisplay's own route-agreement dot
// (AGREEMENT_DOT: teal/amber/line) — reused here so the two dots on the same
// card read as one visual language rather than two different color systems.
const DOT_CLASS: Record<Tone, string> = {
  green: "bg-proto-teal",
  amber: "bg-proto-amber",
  gray: "bg-proto-line",
};

function toneOf(annotation: Pick<VideoAnnotation, "matched" | "score">): Tone {
  if (!annotation.matched) return "gray";
  if (annotation.score >= 0.7) return "green";
  if (annotation.score >= 0.3) return "amber";
  return "gray"; // low-relevance BM25 match
}

function badgeLabel(annotation: VideoAnnotation): string {
  if (!annotation.matched) return "—";
  return annotation.mode === "bm25" ? `✓ ${annotation.score.toFixed(2)}` : "✓";
}

/** "matched" for substring/regex (binary), the normalized float for bm25. */
function sourceScoreLabel(mode: string, score: number): string {
  return mode === "bm25" ? score.toFixed(2) : "matched";
}

/** Splits on "**...**" markers and renders the wrapped span as <strong>. */
function renderSnippet(text: string) {
  return text.split("**").map((part, i) =>
    i % 2 === 1 ? <strong key={i}>{part}</strong> : <span key={i}>{part}</span>
  );
}

const SOURCE_LABEL: Record<string, string> = { asr: "ASR", ocr: "OCR" };
const HIDE_DELAY_MS = 150;

export default function TextSignalBadge({
  videoId,
  annotation,
  filterQuery,
  mode,
}: TextSignalBadgeProps) {
  const [open, setOpen] = useState(false);
  const [popoverAbove, setPopoverAbove] = useState(true);
  const hideTimer = useRef<number | null>(null);
  const containerRef = useRef<HTMLSpanElement | null>(null);

  if (!annotation) return null;

  const handleEnter = () => {
    if (hideTimer.current !== null) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) {
      // Card in the lower half of the viewport -> not enough room below for
      // a 260px popover -> open upward instead.
      setPopoverAbove(rect.top > window.innerHeight / 2);
    }
    setOpen(true);
  };

  const handleLeave = () => {
    hideTimer.current = window.setTimeout(() => setOpen(false), HIDE_DELAY_MS);
  };

  const tone = toneOf(annotation);
  // sources/snippets are parallel arrays in the SAME order the backend
  // appended them (asr before ocr when both matched) — see text_signal.py.
  const snippetFor = (source: string): string | null => {
    const index = annotation.sources.indexOf(source);
    return index === -1 ? null : annotation.snippets[index] ?? null;
  };

  return (
    <span
      ref={containerRef}
      className="relative inline-block"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <span className="inline-flex items-center gap-1 rounded-full bg-white/90 px-1.5 py-0.5 text-[11px] font-mono font-bold text-proto-ink shadow-sm border border-proto-line cursor-default">
        <i className={`w-2 h-2 rounded-full shrink-0 ${DOT_CLASS[tone]}`} />
        {badgeLabel(annotation)}
      </span>

      {open && (
        <div
          className={`absolute right-0 z-30 w-[260px] rounded-[8px] border border-proto-line bg-white p-2.5 shadow-lg font-baloo ${
            popoverAbove ? "bottom-full mb-1.5" : "top-full mt-1.5"
          }`}
        >
          <div className="text-[13px] font-bold text-proto-muted truncate">
            Text signal · {videoId}
          </div>
          <div className="my-1.5 border-t border-proto-line" />

          {["asr", "ocr"].map((source) => {
            const snippet = snippetFor(source);
            const matched = snippet !== null;
            const sourceTone: Tone = matched ? tone : "gray";
            return (
              <div key={source} className="mb-1.5 last:mb-0">
                <div className="flex items-center gap-1.5 text-[11.5px] font-bold text-proto-ink">
                  <i className={`w-2 h-2 rounded-full shrink-0 ${DOT_CLASS[sourceTone]}`} />
                  <span>{SOURCE_LABEL[source]}</span>
                  <span className="text-proto-muted font-normal">
                    · {matched ? sourceScoreLabel(mode, annotation.score) : "no match"}
                  </span>
                </div>
                {matched && (
                  <div className="mt-0.5 text-[12px] leading-snug text-proto-muted">
                    {renderSnippet(snippet)}
                  </div>
                )}
              </div>
            );
          })}

          <div className="my-1.5 border-t border-proto-line" />
          <div className="text-[11px] text-proto-muted truncate">
            Mode: {mode} · &quot;{filterQuery.slice(0, 30)}
            {filterQuery.length > 30 ? "…" : ""}&quot;
          </div>
        </div>
      )}
    </span>
  );
}
