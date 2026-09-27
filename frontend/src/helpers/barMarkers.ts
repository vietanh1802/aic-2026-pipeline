// frontend/src/helpers/barMarkers.ts

/**
 * Pure rules for the candidate markers drawn on the LOWER frame bar
 * (components/VideoPopUp/FrameMarkStrip): when they may be drawn at all, where
 * each block's marker goes, which markers get a score label, and which time a
 * click at a given pointer position would seek to.
 *
 * The lower bar already seeks on any click (barSeconds over its own low..high),
 * so the markers are a read-only overlay on it and never take a click. That makes
 * one rule matter more than any other: a marker may only be drawn where the bar's
 * scale is exactly the whole video, because that is the only scale on which a
 * block's seconds and a pixel on the bar mean the same thing.
 *
 * helpers/candidateStrip.ts is the block geometry of the UPPER strip (clusters,
 * hit boxes); this is deliberately simpler: one marker per block, no union, no
 * hit box. The few lines of box arithmetic are repeated here rather than shared,
 * so the strip's memoised layer stays untouched.
 */
import { MIN_BLOCK_PX, type Block } from "./candidateStrip";
import { LABEL_PX } from "./candidateStripView";
import { barSeconds } from "./frameRange";

/** The lower bar's scale: the seconds its left and right edges stand for. */
export interface BarScale {
  low: number;
  high: number;
}

/**
 * How far the bar's right edge may differ from the tagged duration and still
 * count as the same number. Both are floats that travelled through props.
 */
const SCALE_TOLERANCE_S = 1e-6;

/**
 * Whether the markers may be drawn on a bar with this scale.
 *
 * `taggedDuration` is the popup's duration for THIS video (durationForVideo): 0
 * when unknown, and 0 again right after a switch to another video, while the
 * bar's own `duration` still holds the previous video's length. Comparing the
 * bar's scale against the tagged value therefore rejects, in one test:
 *   - a zoomed bar (TRAKE with both ends pinned): low is not 0, or high is short;
 *   - an unknown duration: the bar falls back to a 1-second scale (high = 1);
 *   - a stale duration after a video switch: the tag no longer matches.
 * A zoom that happens to span the whole video (0 to the duration) passes, and
 * rightly so: that scale is the full one.
 */
export function overlayVisible(scale: BarScale, taggedDuration: number): boolean {
  return (
    Number.isFinite(taggedDuration) &&
    taggedDuration > 0 &&
    scale.low === 0 &&
    Number.isFinite(scale.high) &&
    Math.abs(scale.high - taggedDuration) <= SCALE_TOLERANCE_S
  );
}

/** One block's marker on the bar, in percent of the bar's width. */
export interface MarkerBox {
  block: Block;
  leftPct: number;
  widthPct: number;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

/**
 * One marker per block, at least MIN_BLOCK_PX wide and centred on the block
 * (10 s of a 26 minute video is about 6 px on a 930 px bar, too thin to see).
 * Never merged with a neighbour: two blocks close together give two overlapping
 * markers, not one wide one that would claim time between them.
 *
 * Positions are percent, so the markers scale with the bar between two width
 * measurements; the minimum is applied in px, so it needs `widthPx`.
 *
 * Returned in RENDER order, ascending by best score (ties left to right), so the
 * better block is painted later and ends up on top where markers overlap.
 * [] when the duration or the width is unknown.
 */
export function layoutMarkers(
  blocks: Block[],
  durationS: number | null | undefined,
  widthPx: number
): MarkerBox[] {
  if (
    typeof durationS !== "number" ||
    !Number.isFinite(durationS) ||
    durationS <= 0 ||
    !(widthPx > 0)
  ) {
    return [];
  }
  const toPx = (seconds: number) => clamp((seconds / durationS) * widthPx, 0, widthPx);
  return blocks
    .filter((block) => Number.isFinite(block.start) && Number.isFinite(block.end))
    .map((block) => {
      const startPx = toPx(block.start);
      const endPx = toPx(block.end);
      const width = Math.min(widthPx, Math.max(endPx - startPx, MIN_BLOCK_PX));
      const left = clamp((startPx + endPx) / 2 - width / 2, 0, widthPx - width);
      return { block, leftPct: (left / widthPx) * 100, widthPct: (width / widthPx) * 100 };
    })
    .sort((a, b) => a.block.bestScore - b.block.bestScore || a.leftPct - b.leftPct);
}

/** Centre of a marker in px. */
function centrePx(marker: MarkerBox, widthPx: number): number {
  return ((marker.leftPct + marker.widthPct / 2) / 100) * widthPx;
}

/**
 * Which markers get their score printed above them. Best score first, and a
 * marker is skipped when an already labelled one is closer than LABEL_PX, so two
 * labels never print on top of each other. The skipped score is still on its
 * chip in the upper strip. Same rule as labelledGroups() for the strip's blocks.
 */
export function labelledMarkers(markers: MarkerBox[], widthPx: number): Set<MarkerBox> {
  const shown = new Set<MarkerBox>();
  if (!(widthPx > 0)) {
    return shown;
  }
  const ranked = [...markers].sort(
    (a, b) => b.block.bestScore - a.block.bestScore || a.leftPct - b.leftPct
  );
  for (const marker of ranked) {
    const x = centrePx(marker, widthPx);
    if ([...shown].every((other) => Math.abs(centrePx(other, widthPx) - x) >= LABEL_PX)) {
      shown.add(marker);
    }
  }
  return shown;
}

/**
 * Left edge of a marker's score label in px: centred over the marker and kept
 * inside the bar, so a label at either end is not cut off by the popup.
 */
export function labelLeftPx(marker: MarkerBox, widthPx: number): number {
  return clamp(centrePx(marker, widthPx) - LABEL_PX / 2, 0, Math.max(0, widthPx - LABEL_PX));
}

/**
 * The second a click at this pointer position would seek to.
 *
 * Exactly the expression FrameMarkStrip's onClick evaluates, on the same scale,
 * so the hover time and the landing spot cannot disagree. A zero or unknown
 * width, or a non-finite pointer, answers the bar's low edge (what barSeconds
 * does with a fraction it cannot use), never NaN.
 */
export function secondsAtPointer(
  clientX: number,
  rectLeft: number,
  rectWidth: number,
  low: number,
  high: number
): number {
  return barSeconds((clientX - rectLeft) / rectWidth, low, high);
}
