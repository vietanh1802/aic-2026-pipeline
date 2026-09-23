// frontend/src/components/TextSignalBadge/index.tsx

import { useRef, useState } from "react";
import ReactDOM from "react-dom";
import type { SourceMatch, VideoAnnotation } from "../../types/api";
import { parseFrameRef } from "../../helpers/frameRef";
import { fpsOf } from "../../helpers/frameIdentity";
import { usePopupStore } from "../../store/popupStore";

interface TextSignalBadgeProps {
  videoId: string;
  annotation: VideoAnnotation | undefined;
  filterQuery: string;
  mode: string;
}

export type Tone = "green" | "amber" | "gray";

// Same three-tone scale as FrameDisplay's own route-agreement dot
// (AGREEMENT_DOT: teal/amber/line) — reused here so the two dots on the same
// card read as one visual language rather than two different color systems.
const DOT_CLASS: Record<Tone, string> = {
  green: "bg-proto-teal",
  amber: "bg-proto-amber",
  gray: "bg-proto-line",
};

/**
 * Per-source badge color. Stage C's SourceMatch carries two independent
 * signals — match_type (exact vs. normalized/accent-stripped) and location
 * (here vs. elsewhere vs. none) — and they can disagree: a "here" match that
 * is only normalized, or an "elsewhere" match that is exact. Green is
 * reserved for the one combination with no caveat at all — an exact match on
 * a frame the user is already looking at. Any other real match (weaker
 * spelling, or sitting on a frame not currently shown) is amber, never
 * green, so the user never reads amber as "as good as green, just rarer."
 */
export function toneOfSource(source: SourceMatch): Tone {
  if (source.location === "none") return "gray";
  if (source.match_type === "exact" && source.location === "here") return "green";
  return "amber";
}

function statusText(source: SourceMatch): string {
  if (source.location === "none") return "no match";
  if (source.match_type === "exact" && source.location === "here") {
    return "exact match, visible here";
  }
  if (source.location === "elsewhere") return "matched on another frame of this video";
  return "matched after stripping diacritics";
}

const SOURCE_LABEL: Record<"asr" | "ocr", string> = { asr: "ASR", ocr: "OCR" };
const HIDE_DELAY_MS = 150;

/**
 * Jumps the video popup straight to the frame a SourceMatch named.
 *
 * Reuses the same pieces GotoFrame's own input box uses internally
 * (parseFrameRef + fpsOf + usePopupStore) rather than GotoFrame itself —
 * GotoFrame is a free-text paste box built for a teammate typing a frame
 * reference from memory, and this badge already has the exact frame name as
 * data, not text to parse from a user. Wrapping GotoFrame here would mean
 * pre-filling its input and synthesizing an Enter keypress just to reach the
 * same open() call this makes directly.
 */
function goToMatchFrame(matchFrame: string) {
  const ref = parseFrameRef(matchFrame);
  if (!ref || !fpsOf(ref.videoId)) return;
  usePopupStore.getState().open(ref.videoId, ref.frameIdx);
}

function SourceRow({
  source,
  match,
}: {
  source: "asr" | "ocr";
  match: SourceMatch;
}) {
  const tone = toneOfSource(match);
  return (
    <div className="mb-1.5 last:mb-0">
      <div className="flex items-center gap-1.5 text-[11.5px] font-bold text-proto-ink">
        <i className={`w-2 h-2 rounded-full shrink-0 ${DOT_CLASS[tone]}`} />
        <span>{SOURCE_LABEL[source]}</span>
        <span className="text-proto-muted font-normal">· {statusText(match)}</span>
      </div>
      {match.match_frame && (
        <div className="mt-0.5 flex items-center gap-1.5 text-[12px] text-proto-muted">
          <span className="truncate">{match.match_frame}</span>
          <button
            type="button"
            className="shrink-0 rounded-[4px] border border-proto-line bg-proto-soft px-1.5 py-0.5 text-[11px] font-bold text-proto-ink"
            onClick={(event) => {
              event.stopPropagation();
              goToMatchFrame(match.match_frame as string);
            }}
          >
            Go to frame
          </button>
        </div>
      )}
    </div>
  );
}

export default function TextSignalBadge({
  videoId,
  annotation,
  filterQuery,
  mode,
}: TextSignalBadgeProps) {
  const [open, setOpen] = useState(false);
  const [popoverAbove, setPopoverAbove] = useState(true);
  // Card's own rect at the moment the popover opens. Positioning the portal
  // with `position: fixed` off this (rather than the old absolute/top-full
  // placement) is what lets it escape the card's `overflow-hidden` ancestor.
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
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
      // the popover -> open upward instead.
      setPopoverAbove(rect.top > window.innerHeight / 2);
      setAnchorRect(rect);
    }
    setOpen(true);
  };

  const handleLeave = () => {
    hideTimer.current = window.setTimeout(() => setOpen(false), HIDE_DELAY_MS);
  };

  return (
    <span
      ref={containerRef}
      className="relative inline-block"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <span className="inline-flex items-center gap-1 rounded-full bg-white/90 px-1.5 py-0.5 shadow-sm border border-proto-line cursor-default">
        <i
          className={`w-2 h-2 rounded-full shrink-0 ${DOT_CLASS[toneOfSource(annotation.asr)]}`}
          title="ASR"
        />
        <i
          className={`w-2 h-2 rounded-full shrink-0 ${DOT_CLASS[toneOfSource(annotation.ocr)]}`}
          title="OCR"
        />
      </span>

      {open &&
        anchorRect &&
        ReactDOM.createPortal(
          <div
            // `fixed` + coordinates read off the card's own rect, rendered
            // straight into document.body — the card's `overflow-hidden`
            // ancestor (see FrameDisplay) only clips descendants of its own
            // DOM subtree, and a portal isn't one.
            style={{
              position: "fixed",
              right: window.innerWidth - anchorRect.right,
              ...(popoverAbove
                ? { bottom: window.innerHeight - anchorRect.top + 6 }
                : { top: anchorRect.bottom + 6 }),
            }}
            className="z-30 w-[260px] rounded-[8px] border border-proto-line bg-white p-2.5 shadow-lg font-baloo"
            onMouseEnter={handleEnter}
            onMouseLeave={handleLeave}
          >
            <div className="text-[13px] font-bold text-proto-muted truncate">
              Text signal · {videoId}
            </div>
            <div className="my-1.5 border-t border-proto-line" />

            <SourceRow source="asr" match={annotation.asr} />
            <SourceRow source="ocr" match={annotation.ocr} />

            <div className="my-1.5 border-t border-proto-line" />
            <div className="text-[11px] text-proto-muted truncate">
              Mode: {mode} · &quot;{filterQuery.slice(0, 30)}
              {filterQuery.length > 30 ? "…" : ""}&quot;
            </div>
          </div>,
          document.body
        )}
    </span>
  );
}
