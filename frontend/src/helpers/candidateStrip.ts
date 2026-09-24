// frontend/src/helpers/candidateStrip.ts

/**
 * Pure helpers behind the candidate strip: the coloured blocks under the video
 * player that mark where in ONE video the search found candidate frames.
 *
 * The chain, each step a plain function so it can be tested without a browser:
 *
 *   groupByVideo      results  -> Map video -> candidates (frame, time, score)
 *   candidateIntervals candidates -> a 10 s interval around each frame
 *   mergeIntervals    intervals -> blocks (overlapping ones become one)
 *   layoutBlocks      blocks   -> boxes in percent of the bar, with a minimum
 *                                 visible width and a bigger hit area
 *   opacityForScore   score    -> how strongly a block is drawn
 *
 * Nothing here touches ranking or the DOM. The caller passes the FULL result
 * list to groupByVideo, not the visible page: the frame you want may rank 300th
 * and its block has to be on the strip even when its card is not on screen yet.
 */
import type { SearchResult } from "../types/api";
import { accuracyPercent } from "../components/FrameDisplay/accuracy";
import { videoOf } from "./focusFilter";
import { fpsOf } from "./frameIdentity";
import { parseFrameName } from "./frameRef";

/** A candidate frame at time t marks the interval [t - 5 s, t + 5 s]. */
export const CANDIDATE_HALF_WINDOW_S = 5;
/**
 * Intervals merge when they overlap or touch. 0 on purpose: a gap would claim
 * coverage the 10 s windows do not give. On L25_V014, scene 46 (40 frames 3.7 s
 * apart) every third frame is 11.2 s apart, so its windows stay 1.2 s short of
 * touching and the blocks stay separate.
 */
export const MERGE_GAP_S = 0;
/** A block is drawn at least this wide. 10 s of a 30 min video is ~5 px at 930 px. */
export const MIN_BLOCK_PX = 10;
/** The clickable box of a block or group is at least this wide (finger and mouse). */
export const HIT_PX = 24;

/** Weakest block opacity; the best one is 1. Below this a block reads as absent. */
const OPACITY_MIN = 0.35;
/**
 * Slack when deciding that two intervals touch. t - 5 and t + 5 are floats, so
 * two frames exactly 10 s apart can differ by 1e-13 and fail a plain <=.
 */
const EPSILON_S = 1e-6;

export interface Candidate {
  /** Keyframe name as the result carries it, e.g. "L25_V014-0046-3660.jpg". */
  name: string;
  frameIdx: number;
  /** frame_idx / fps, in seconds from the start of the video. */
  timeS: number;
  /** result.distance: already 0-100, the number the card prints with toFixed(1). */
  score: number;
}

export interface VideoCandidates {
  /** In the order the results came, i.e. best rank first. */
  candidates: Candidate[];
  /**
   * Frames that could not be placed on a timeline: the video is not in
   * fps_map.json (a new batch not synced yet) or the name carries no frame
   * number. Counted rather than dropped so the caller can say "3 not shown".
   */
  skipped: number;
}

/**
 * Video -> its candidates, videos in the order they first appear in `results`.
 *
 * `results` is ranked best first, so that order is also each video's best-score
 * order and matches the order of a one-card-per-video list. A video whose every
 * frame was skipped is still present (empty candidates) - it still deserves a
 * card. Results with no video id at all collect under "".
 */
export function groupByVideo(results: SearchResult[]): Map<string, VideoCandidates> {
  const groups = new Map<string, VideoCandidates>();
  for (const result of results) {
    const video = videoOf(result);
    let group = groups.get(video);
    if (!group) {
      group = { candidates: [], skipped: 0 };
      groups.set(video, group);
    }
    const fps = fpsOf(video);
    // Not frameIndexFromResult: that answers 0 for an unreadable name, which
    // would put a block at 00:00 for a frame whose time is simply unknown.
    const frameIdx =
      typeof result.frame_idx === "number"
        ? result.frame_idx
        : parseFrameName(result.frame)?.frameIdx;
    if (!fps || frameIdx === undefined || !Number.isFinite(frameIdx)) {
      group.skipped += 1;
      continue;
    }
    group.candidates.push({
      name: result.name,
      frameIdx,
      timeS: frameIdx / fps,
      score: result.distance,
    });
  }
  return groups;
}

export interface Interval {
  start: number;
  end: number;
  candidate: Candidate;
}

/** A duration counts as known only when it is a positive finite number. */
function isKnown(durationS: number | null | undefined): durationS is number {
  return typeof durationS === "number" && Number.isFinite(durationS) && durationS > 0;
}

/**
 * [t - 5, t + 5] around every candidate, clamped to [0, duration].
 *
 * Duration unknown (the player has not reported it yet): only the start is
 * clamped. A frame past the end of the real video (fps in the metadata not
 * matching the file) collapses to a zero-length interval at the end instead of
 * running off the bar; layoutBlocks widens it to a visible block.
 */
export function candidateIntervals(
  candidates: Candidate[],
  durationS?: number | null
): Interval[] {
  const ceiling = isKnown(durationS) ? durationS : Number.POSITIVE_INFINITY;
  return candidates.map((candidate) => ({
    start: Math.min(Math.max(0, candidate.timeS - CANDIDATE_HALF_WINDOW_S), ceiling),
    end: Math.min(Math.max(0, candidate.timeS + CANDIDATE_HALF_WINDOW_S), ceiling),
    candidate,
  }));
}

export interface Block {
  start: number;
  end: number;
  frameCount: number;
  bestScore: number;
  bestFrame: { name: string; frameIdx: number };
  /**
   * Where a click seeks: the time of the best-scoring frame, NOT the middle of
   * the block. Ties go to the earliest time.
   */
  bestTimeS: number;
}

/** Total order, so the result does not depend on the order the input came in. */
function byStart(a: Interval, b: Interval): number {
  if (a.start !== b.start) return a.start - b.start;
  if (a.end !== b.end) return a.end - b.end;
  if (a.candidate.timeS !== b.candidate.timeS) return a.candidate.timeS - b.candidate.timeS;
  return a.candidate.name < b.candidate.name ? -1 : a.candidate.name > b.candidate.name ? 1 : 0;
}

function beats(candidate: Candidate, best: Candidate): boolean {
  if (candidate.score !== best.score) return candidate.score > best.score;
  if (candidate.timeS !== best.timeS) return candidate.timeS < best.timeS;
  return candidate.name < best.name;
}

/** The block's best frame as a Candidate again, to compare a newcomer against it. */
function bestCandidateOf(block: Block): Candidate {
  return {
    name: block.bestFrame.name,
    frameIdx: block.bestFrame.frameIdx,
    timeS: block.bestTimeS,
    score: block.bestScore,
  };
}

function blockOf(interval: Interval): Block {
  const { candidate } = interval;
  return {
    start: interval.start,
    end: interval.end,
    frameCount: 1,
    bestScore: candidate.score,
    bestFrame: { name: candidate.name, frameIdx: candidate.frameIdx },
    bestTimeS: candidate.timeS,
  };
}

/**
 * Overlapping or touching intervals become one block (gap allowed: MERGE_GAP_S).
 * A chain merges through: A overlaps B and B overlaps C is one block even when
 * A and C do not touch. Sorted output, deterministic for any input order.
 */
export function mergeIntervals(intervals: Interval[]): Block[] {
  const blocks: Block[] = [];
  for (const interval of [...intervals].sort(byStart)) {
    const last = blocks[blocks.length - 1];
    if (!last || interval.start > last.end + MERGE_GAP_S + EPSILON_S) {
      blocks.push(blockOf(interval));
      continue;
    }
    last.end = Math.max(last.end, interval.end);
    last.frameCount += 1;
    const { candidate } = interval;
    if (beats(candidate, bestCandidateOf(last))) {
      last.bestScore = candidate.score;
      last.bestFrame = { name: candidate.name, frameIdx: candidate.frameIdx };
      last.bestTimeS = candidate.timeS;
    }
  }
  return blocks;
}

/**
 * What the strip draws: one block, or a cluster of blocks too close to click
 * apart. All positions are percent of the bar's width.
 */
export interface BlockGroup {
  /** In time order. One member is a plain block; more is a cluster. */
  members: Block[];
  /** The highest-scoring member: where a click on the group seeks. */
  best: Block;
  frameCount: number;
  /** The drawn box. At least MIN_BLOCK_PX wide. */
  leftPct: number;
  widthPct: number;
  /** The clickable box. At least HIT_PX wide, never overlapping a neighbour's. */
  hitLeftPct: number;
  hitWidthPct: number;
}

interface Box {
  left: number;
  right: number;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

/** The drawn box in px: the block's own span, widened to MIN_BLOCK_PX around its centre. */
function drawnBox(startPx: number, endPx: number, widthPx: number): Box {
  const width = Math.min(widthPx, Math.max(endPx - startPx, MIN_BLOCK_PX));
  const left = clamp((startPx + endPx) / 2 - width / 2, 0, widthPx - width);
  return { left, right: left + width };
}

/** The clickable box in px: the drawn box widened to HIT_PX around its centre. */
function hitBox(drawn: Box, widthPx: number): Box {
  const width = Math.min(widthPx, Math.max(drawn.right - drawn.left, HIT_PX));
  const left = clamp((drawn.left + drawn.right) / 2 - width / 2, 0, widthPx - width);
  return { left, right: left + width };
}

/**
 * Blocks -> boxes on a bar `widthPx` wide that stands for `durationS`.
 *
 * A 10 s block on a 30 min video is ~5 px at 930 px, so two things widen it: a
 * drawn box of at least MIN_BLOCK_PX, and a hit box of at least HIT_PX around it.
 * Widening makes neighbours collide, so blocks whose HIT boxes would overlap
 * become ONE group (a cluster): it is drawn as their union, a click seeks to its
 * best member, and `members` still lists every block for a chip row. That is
 * stricter than "closer than MIN_BLOCK_PX": two 10 px blocks 12 px apart would
 * pass that test and still steal each other's clicks.
 *
 * Returned in RENDER order - ascending by best score, so the best group is
 * drawn last and ends up on top when boxes still overlap.
 *
 * [] when the duration or the width is unknown, in which case the caller shows
 * the chips alone.
 */
export function layoutBlocks(
  blocks: Block[],
  durationS: number | null | undefined,
  widthPx: number
): BlockGroup[] {
  if (!isKnown(durationS) || !(widthPx > 0) || blocks.length === 0) {
    return [];
  }
  const toPx = (seconds: number) => clamp((seconds / durationS) * widthPx, 0, widthPx);

  let groups = [...blocks]
    .sort((a, b) => a.start + a.end - (b.start + b.end))
    .map((block) => ({
      members: [block],
      box: drawnBox(toPx(block.start), toPx(block.end), widthPx),
    }));

  // A merged group is drawn wider and so has a wider hit box, which can now
  // reach the PREVIOUS group. Repeat until nothing overlaps; every pass that
  // changes anything removes a group, so this ends.
  let changed = true;
  while (changed) {
    changed = false;
    const next = [groups[0]];
    for (const group of groups.slice(1)) {
      const previous = next[next.length - 1];
      if (hitBox(group.box, widthPx).left < hitBox(previous.box, widthPx).right) {
        next[next.length - 1] = {
          members: [...previous.members, ...group.members],
          box: {
            left: Math.min(previous.box.left, group.box.left),
            right: Math.max(previous.box.right, group.box.right),
          },
        };
        changed = true;
      } else {
        next.push(group);
      }
    }
    groups = next;
  }

  const pct = (px: number) => (px / widthPx) * 100;
  return groups
    .map(({ members, box }) => {
      const hit = hitBox(box, widthPx);
      const best = members.reduce((top, block) =>
        block.bestScore > top.bestScore ||
        (block.bestScore === top.bestScore && block.bestTimeS < top.bestTimeS)
          ? block
          : top
      );
      return {
        members,
        best,
        frameCount: members.reduce((sum, block) => sum + block.frameCount, 0),
        leftPct: pct(box.left),
        widthPct: pct(box.right - box.left),
        hitLeftPct: pct(hit.left),
        hitWidthPct: pct(hit.right - hit.left),
      };
    })
    .sort((a, b) => a.best.bestScore - b.best.bestScore || a.leftPct - b.leftPct);
}

/**
 * The lowest and highest score of a result list, for opacityForScore.
 *
 * Pass the FULL list. FrameDisplay colours its percentage over the results it
 * was handed, which is only the visible page (100 at a time), so a card's colour
 * can shift as more pages load; the strip is drawn once per video and must not.
 */
export function scoreRange(results: { distance: number }[]): { low: number; high: number } {
  if (results.length === 0) {
    return { low: 0, high: 0 };
  }
  let low = results[0].distance;
  let high = results[0].distance;
  for (const { distance } of results) {
    if (distance < low) low = distance;
    if (distance > high) high = distance;
  }
  return { low, high };
}

/**
 * Block opacity from 0.35 (the lowest score in the range) to 1 (the highest).
 *
 * The same min-max idea as the card colour: accuracyPercent, reused as is, so
 * "how good is this one within this result set" reads the same in both places.
 * One score across the whole range (or none) gives 1. Opacity alone is not
 * accessible - the score number (Block.bestScore, printed with toFixed(1) like
 * the cards) always goes next to the block.
 */
export function opacityForScore(score: number, lowScore: number, highScore: number): number {
  return OPACITY_MIN + (1 - OPACITY_MIN) * (accuracyPercent(score, lowScore, highScore) / 100);
}
