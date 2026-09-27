// frontend/src/components/TextSignalBadge/index.tsx

import { useRef, useState } from "react";
import ReactDOM from "react-dom";
import type { SourceMatch, VideoAnnotation } from "../../types/api";
import { parseFrameRef } from "../../helpers/frameRef";
import { fpsOf } from "../../helpers/frameIdentity";
import { ALL_SEARCHED, popoverRight } from "../../helpers/textSignalView";
import { usePopupStore } from "../../store/popupStore";
import { useSearchStore } from "../../store/useSearchStore";
import TextSignalPopoverBody from "./TextSignalPopoverBody";

interface TextSignalBadgeProps {
  videoId: string;
  annotation: VideoAnnotation | undefined;
  filterQuery: string;
  mode: string;
  /**
   * Name of the frame the card shows. A source whose match is on that very frame
   * reads "this frame" in the popover, with no Go button. Optional: a caller that
   * does not pass it just never gets that wording.
   */
  cardFrame?: string;
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

// Old status wording, kept for the record. It named the state but never showed
// the match itself, and the sentence "matched on another frame of this video"
// told the reader nothing they could act on. Replaced by TextSignalPopoverBody
// (snippet, time, rank) and the short fallback in helpers/textSignalView.ts.
//
// function statusText(source: SourceMatch): string {
//   if (source.location === "none") return "no match";
//   if (source.match_type === "exact" && source.location === "here") {
//     return "exact match, visible here";
//   }
//   if (source.location === "elsewhere") return "matched on another frame of this video";
//   return "matched after stripping diacritics";
// }
//
// const SOURCE_LABEL: Record<"asr" | "ocr", string> = { asr: "ASR", ocr: "OCR" };
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

// Old per-source row, kept for the record; moved into TextSignalPopoverBody so
// the popover content can be rendered to markup without the portal or the stores.
//
// function SourceRow({
//   source,
//   match,
// }: {
//   source: "asr" | "ocr";
//   match: SourceMatch;
// }) {
//   const tone = toneOfSource(match);
//   return (
//     <div className="mb-1.5 last:mb-0">
//       <div className="flex items-center gap-1.5 text-[11.5px] font-bold text-proto-ink">
//         <i className={`w-2 h-2 rounded-full shrink-0 ${DOT_CLASS[tone]}`} />
//         <span>{SOURCE_LABEL[source]}</span>
//         <span className="text-proto-muted font-normal">· {statusText(match)}</span>
//       </div>
//       {match.match_frame && (
//         <div className="mt-0.5 flex items-center gap-1.5 text-[12px] text-proto-muted">
//           <span className="truncate">{match.match_frame}</span>
//           <button
//             type="button"
//             className="shrink-0 rounded-[4px] border border-proto-line bg-proto-soft px-1.5 py-0.5 text-[11px] font-bold text-proto-ink"
//             onClick={(event) => {
//               event.stopPropagation();
//               goToMatchFrame(match.match_frame as string);
//             }}
//           >
//             Go to frame
//           </button>
//         </div>
//       )}
//     </div>
//   );
// }

export default function TextSignalBadge({
  videoId,
  annotation,
  filterQuery,
  mode,
  cardFrame,
}: TextSignalBadgeProps) {
  // Which sources ran in the search on screen, stored with the annotations (see
  // useSearchStore.searchedSources). ALL_SEARCHED when absent, which keeps the old
  // "no match" wording instead of guessing "not searched". Read above the early
  // return below so the hook order never depends on the annotation.
  const searched = useSearchStore((state) => state.searchedSources) ?? ALL_SEARCHED;
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
              // Old offset, kept for the record: lined the popover's right edge up
              // with the badge's. At 340 px wide that pushes a first-column card's
              // popover off the left of the screen, so popoverRight clamps it.
              //   right: window.innerWidth - anchorRect.right,
              right: popoverRight(window.innerWidth, anchorRect.right),
              ...(popoverAbove
                ? { bottom: window.innerHeight - anchorRect.top + 6 }
                : { top: anchorRect.bottom + 6 }),
            }}
            // Width was w-[260px]. 340 px fits a two-line snippet; the max width
            // keeps it inside a narrow window (popoverRight assumes the same
            // numbers: helpers/textSignalView POPOVER_WIDTH_PX / POPOVER_MARGIN_PX).
            className="z-30 w-[340px] max-w-[calc(100vw-16px)] rounded-[8px] border border-proto-line bg-white p-2.5 shadow-lg font-baloo"
            onMouseEnter={handleEnter}
            onMouseLeave={handleLeave}
          >
            <TextSignalPopoverBody
              videoId={videoId}
              annotation={annotation}
              cardFrame={cardFrame}
              searched={searched}
              mode={mode}
              filterQuery={filterQuery}
              dotClass={{
                asr: DOT_CLASS[toneOfSource(annotation.asr)],
                ocr: DOT_CLASS[toneOfSource(annotation.ocr)],
              }}
              onGoToFrame={goToMatchFrame}
            />
          </div>,
          document.body
        )}
    </span>
  );
}
