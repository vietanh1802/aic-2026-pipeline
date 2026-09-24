// frontend/src/components/VideoPopUp/CandidateMarkers.tsx

import { memo, useEffect, useMemo, useState } from "react";

import {
  labelLeftPx,
  labelledMarkers,
  layoutMarkers,
  overlayVisible,
  secondsAtPointer,
  type BarScale,
  type MarkerBox,
} from "../../helpers/barMarkers";
import {
  candidateIntervals,
  mergeIntervals,
  opacityForScore,
  scoreRange,
} from "../../helpers/candidateStrip";
import { LABEL_PX, candidatesForVideo, formatScore } from "../../helpers/candidateStripView";
import { barPosition } from "../../helpers/frameRange";
import { formatSeconds } from "../../helpers/textSignalView";
import { useQueryStore } from "../../store/queryStore";
import { useSearchStore } from "../../store/useSearchStore";

/**
 * The candidate moments of this video, drawn ON the lower frame bar
 * (FrameMarkStrip) as amber markers with their score above them.
 *
 * READ-ONLY. The bar already seeks on any click (barSeconds over its own scale),
 * so every element here is pointer-transparent and nothing here can take focus:
 * a click on a marker is a click on the bar underneath and lands where it was
 * made, and the keyboard order of the popup is exactly what it was. The chips in
 * the upper strip (CandidateStrip) stay the way to jump to a block's best frame.
 *
 * It also shows, while the pointer is over the bar, a thin line and the time a
 * click there would seek to.
 *
 * Rendered by the popup through FrameMarkStrip's `barOverlay` slot, as the bar's
 * FIRST child so the pinned in/out block and the playhead paint on top of it.
 *
 * Draws nothing (returns null) unless ALL of these hold, the same conditions the
 * upper strip uses plus the one that is specific to the lower bar:
 *   - the bar's scale is the whole video and the duration is this video's own
 *     (overlayVisible: not zoomed, not unknown, not stale after a video switch);
 *   - the popup is not a TRAKE slot (`hidden`);
 *   - the search is a frame route, not temporal or TRAKE (whose results are not
 *     the store's list);
 *   - the results are not OCR (their distance is a word count, not a score);
 *   - this video is in the results.
 */

const RESIZE_DEBOUNCE_MS = 100;

/**
 * Width of an element in px, kept current with a ResizeObserver, debounced
 * because dragging the window edge fires it every frame. The same hook as in
 * CandidateStrip.tsx, repeated on purpose: exporting it from there would add a
 * non-component export to a component file, and moving it would touch the strip.
 */
function useElementWidth(element: HTMLElement | null): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!element) {
      return;
    }
    const measure = () => setWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    // No observer (very old browser): the first measurement stands.
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    let timer: number | undefined;
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(measure, RESIZE_DEBOUNCE_MS);
    });
    observer.observe(element);
    return () => {
      window.clearTimeout(timer);
      observer.disconnect();
    };
  }, [element]);
  return width;
}

interface MarkerLayerProps {
  markers: MarkerBox[];
  labelled: Set<MarkerBox>;
  scoreLow: number;
  scoreHigh: number;
  widthPx: number;
}

/**
 * The markers and their score labels. Memoised on its props, none of which
 * change on a playback tick or a pointer move, so neither repaints this layer.
 *
 * Exported only so CandidateMarkers.render.test.ts can render it at a chosen
 * width; the popup uses CandidateMarkers.
 */
export const MarkerLayer = memo(function MarkerLayer({
  markers,
  labelled,
  scoreLow,
  scoreHigh,
  widthPx,
}: MarkerLayerProps) {
  return (
    <>
      {/* `markers` is in render order (ascending score), so a later marker paints
          over an earlier one where they overlap; no z-index needed. */}
      {markers.map((marker) => (
        <span
          key={marker.block.bestFrame.name}
          data-marker=""
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 rounded-[3px] bg-proto-amber"
          style={{
            left: `${marker.leftPct}%`,
            width: `${marker.widthPct}%`,
            opacity: opacityForScore(marker.block.bestScore, scoreLow, scoreHigh),
          }}
        />
      ))}
      {/* Only the markers labelledMarkers() says have room; the rest are on the
          chips of the upper strip. */}
      {markers.map((marker) =>
        labelled.has(marker) ? (
          <span
            key={`label-${marker.block.bestFrame.name}`}
            data-marker-label=""
            aria-hidden="true"
            className="pointer-events-none absolute bottom-full text-center font-mono text-[10px] leading-3 text-proto-ink"
            style={{ left: `${labelLeftPx(marker, widthPx)}px`, width: `${LABEL_PX}px` }}
          >
            {formatScore(marker.block.bestScore)}
          </span>
        ) : null
      )}
    </>
  );
});

/**
 * The hover readout: a thin line at the pointer and the time a click there
 * would seek to. Presentational; HoverReadout below feeds it.
 * Exported for the render test.
 */
export function HoverView({ seconds, scale }: { seconds: number | null; scale: BarScale }) {
  if (seconds === null) {
    return null;
  }
  const left = `${barPosition(seconds, scale.low, scale.high) * 100}%`;
  return (
    <>
      <span
        data-hover-line=""
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-1 -top-1 z-10 w-px bg-proto-ink/60"
        style={{ left }}
      />
      <span
        data-hover-label=""
        aria-hidden="true"
        className="pointer-events-none absolute bottom-full z-10 mb-0.5 -translate-x-1/2 whitespace-nowrap rounded-[3px] bg-proto-ink px-1 font-mono text-[10px] leading-4 text-white"
        style={{ left }}
      >
        {formatSeconds(seconds)}
      </span>
    </>
  );
}

/**
 * Follows the pointer over the bar. The listeners go on the bar itself (the
 * overlay root's parent) with native events, in an effect, and the only state is
 * the hovered second, local to this component: FrameMarkStrip gets no handler,
 * and a pointer move re-renders this readout alone, never FrameMarkStrip or the
 * marker layer. The same second is not stored twice, so a still pointer costs
 * nothing.
 */
function HoverReadout({ root, scale }: { root: HTMLElement | null; scale: BarScale }) {
  const [seconds, setSeconds] = useState<number | null>(null);
  const { low, high } = scale;
  useEffect(() => {
    const bar = root?.parentElement;
    if (!bar) {
      return;
    }
    const onMove = (event: PointerEvent) => {
      const box = bar.getBoundingClientRect();
      setSeconds(secondsAtPointer(event.clientX, box.left, box.width, low, high));
    };
    const onLeave = () => setSeconds(null);
    bar.addEventListener("pointermove", onMove);
    bar.addEventListener("pointerleave", onLeave);
    return () => {
      bar.removeEventListener("pointermove", onMove);
      bar.removeEventListener("pointerleave", onLeave);
    };
  }, [root, low, high]);
  return <HoverView seconds={seconds} scale={scale} />;
}

export default function CandidateMarkers({
  videoId,
  stripDuration,
  hidden = false,
  scale,
}: {
  videoId: string;
  /**
   * The popup's duration for THIS video (durationForVideo): 0 when unknown, and 0
   * again after a switch until the new metadata arrives. Not the bar's own
   * `duration`, which can still hold the previous video's length.
   */
  stripDuration: number;
  /** True on a TRAKE popup. */
  hidden?: boolean;
  /** The bar's scale, from FrameMarkStrip's barLow and barHigh. */
  scale: BarScale;
}) {
  const results = useSearchStore((state) => state.results);
  const searchType = useQueryStore((state) => state.searchType);
  // After a temporal or TRAKE search `results` still holds the PREVIOUS frame
  // search, so the markers would describe a query that is not on screen. Same
  // test CandidateStrip and App use.
  const showsFrameResults = searchType !== "temporal" && searchType !== "trake";
  const visible = overlayVisible(scale, stripDuration);

  // Nothing below recomputes on a playback tick or a pointer move: every input is
  // the result list, the video, the duration or the width.
  const candidates = useMemo(
    () => (hidden || !showsFrameResults || !visible ? [] : candidatesForVideo(results, videoId)),
    [hidden, showsFrameResults, visible, results, videoId]
  );
  // Over the FULL list, like the strip: a marker must not change shade as more
  // pages load.
  const { low: scoreLow, high: scoreHigh } = useMemo(() => scoreRange(results), [results]);
  const blocks = useMemo(
    () => mergeIntervals(candidateIntervals(candidates, stripDuration)),
    [candidates, stripDuration]
  );

  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  const widthPx = useElementWidth(root);
  const markers = useMemo(
    () => layoutMarkers(blocks, stripDuration, widthPx),
    [blocks, stripDuration, widthPx]
  );
  const labelled = useMemo(() => labelledMarkers(markers, widthPx), [markers, widthPx]);

  if (candidates.length === 0) {
    return null;
  }

  return (
    // `isolate`: the hover readout's z-index must not leak above the bar's own
    // playhead and pinned block, which paint after this element.
    // `data-candidate-markers` is what FrameMarkStrip's headroom for the labels
    // keys on (a CSS :has), so the space above the bar exists only while markers do.
    <div
      ref={setRoot}
      data-candidate-markers=""
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 isolate"
    >
      <MarkerLayer
        markers={markers}
        labelled={labelled}
        scoreLow={scoreLow}
        scoreHigh={scoreHigh}
        widthPx={widthPx}
      />
      <HoverReadout root={root} scale={scale} />
    </div>
  );
}
