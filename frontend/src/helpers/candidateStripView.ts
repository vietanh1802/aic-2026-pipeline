// frontend/src/helpers/candidateStripView.ts

/**
 * The decisions the candidate strip in the video popup makes, kept out of the
 * component so they can be tested without rendering it: which candidates a
 * popup gets, which block the playhead is in, which score labels fit, and the
 * wording of a jump. helpers/candidateStrip.ts is the geometry (group, merge,
 * layout); this is the glue between it and the popup.
 */
import type { OcrSearchResult, SearchResult } from "../types/api";
import { videoOf } from "./focusFilter";
import {
  groupByVideo,
  type Block,
  type BlockGroup,
  type Candidate,
} from "./candidateStrip";

/** Slack for "the playhead is at a block's edge": float seconds from the player. */
const EDGE_EPSILON_S = 1e-6;

/** Width reserved for one score label, "94.2%" at 10 px mono plus a margin. */
export const LABEL_PX = 34;

/**
 * True for the OCR route's results.
 *
 * Their `distance` is a matched-word count plus 1000 for a whole phrase, not a
 * similarity, so a block "opacity by score" would be meaningless. Read from the
 * data (`total_words`, the same test FrameDisplay's MatchLabel uses) and not
 * from the search-type dropdown, which can be changed after the search ran.
 */
export function isOcrResults(results: SearchResult[]): boolean {
  return results.some(
    (result) => typeof (result as OcrSearchResult).total_words === "number"
  );
}

/**
 * The candidates of ONE video out of a result list, best rank first.
 *
 * Takes the FULL list, not the visible page: the frame you want may rank 300th
 * and its block belongs on the strip even when its card has not loaded yet.
 * Empty for an OCR list, an empty video id, or a video that is not in the
 * results (a popup opened with Go to frame, from the basket, or from a badge).
 */
export function candidatesForVideo(
  results: SearchResult[],
  videoId: string
): Candidate[] {
  if (!videoId || isOcrResults(results)) {
    return [];
  }
  const ofVideo = results.filter((result) => videoOf(result) === videoId);
  return groupByVideo(ofVideo).get(videoId)?.candidates ?? [];
}

function contains(block: Block, timeS: number): boolean {
  return timeS >= block.start - EDGE_EPSILON_S && timeS <= block.end + EDGE_EPSILON_S;
}

/**
 * Which drawn group the playhead is inside: index into `groups`, or -1.
 * A cluster counts as inside when the playhead is in ANY of its blocks; the
 * gaps between its blocks are not. Both edges of a block are inside.
 */
export function activeGroupIndex(groups: BlockGroup[], timeS: number): number {
  return groups.findIndex((group) => group.members.some((block) => contains(block, timeS)));
}

/** The same for the plain block list the chips are built from: index or -1. */
export function activeBlockIndex(blocks: Block[], timeS: number): number {
  return blocks.findIndex((block) => contains(block, timeS));
}

/**
 * Which groups get their score printed above them.
 *
 * At 5 to 10 px per block the labels (LABEL_PX wide) would print on top of each
 * other, so labels are given out best score first and a group is skipped when
 * an already-labelled one is closer than LABEL_PX. The skipped score is still
 * on the block's aria-label and in the chip list, just not on the bar.
 */
export function labelledGroups(groups: BlockGroup[], widthPx: number): Set<BlockGroup> {
  const centre = (group: BlockGroup) => ((group.leftPct + group.widthPct / 2) / 100) * widthPx;
  const shown = new Set<BlockGroup>();
  const ranked = [...groups].sort(
    (a, b) => b.best.bestScore - a.best.bestScore || a.leftPct - b.leftPct
  );
  for (const group of ranked) {
    const x = centre(group);
    if ([...shown].every((other) => Math.abs(centre(other) - x) >= LABEL_PX)) {
      shown.add(group);
    }
  }
  return shown;
}

/**
 * "00:20:05.472" -> "20:05"; "01:02:03.000" -> "1:02:03". The chips and the
 * spoken label have no use for milliseconds or a leading "00:" hour.
 * Anything that is not a clock (an empty string) comes back as it was.
 */
export function shortClock(clock: string): string {
  const match = /^(\d+):(\d{2}):(\d{2})(?:\.\d+)?$/.exec(clock);
  if (!match) {
    return clock;
  }
  const hours = Number(match[1]);
  return hours > 0 ? `${hours}:${match[2]}:${match[3]}` : `${match[2]}:${match[3]}`;
}

/** Same number and format as the cards: distance already 0-100, one decimal. */
export function formatScore(score: number): string {
  return `${score.toFixed(1)}%`;
}

/** The text of a block's aria-label and tooltip: "Jump to 20:05, 3 frames, best 94.2%". */
export function describeBlock(parts: {
  clock: string;
  frames: number;
  score: number;
  /** More than one when the button stands for a cluster of blocks. */
  blocks?: number;
}): string {
  const frames = `${parts.frames} frame${parts.frames === 1 ? "" : "s"}`;
  const blocks = parts.blocks && parts.blocks > 1 ? `, ${parts.blocks} blocks` : "";
  return `Jump to ${parts.clock}, ${frames}${blocks}, best ${formatScore(parts.score)}`;
}

/** Where a click on a block seeks. */
export interface Jump {
  frameName: string;
  frameIdx: number;
  timeS: number;
}

/**
 * The jump target of a block: its best-scoring frame, NOT the middle of the
 * block. The popup then continues from that exact keyframe, so the answer can
 * still end on an exact frame with the usual +/- steps.
 */
export function jumpOfBlock(block: Block): Jump {
  return {
    frameName: block.bestFrame.name,
    frameIdx: block.bestFrame.frameIdx,
    timeS: block.bestTimeS,
  };
}
