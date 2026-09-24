// frontend/src/helpers/groupResults.ts

/**
 * "One card per video" for the frame results grid.
 *
 * Keyframes are cut per scene, and a long static scene (a blackboard lecture) can
 * fill the top of the list with a dozen frames of one video a few seconds apart.
 * With the option on, the grid shows each video once, as its best-scoring frame;
 * the video's other candidates stay one click away, in the popup's candidate
 * strip (components/VideoPopUp/CandidateStrip.tsx), which reads the FULL result
 * list and so is not affected by any of this.
 *
 * Known trade-off: a distinct high-ranked moment of a video that is not its best
 * frame is no longer a thumbnail of its own. That is why the option is off by
 * default, and why it is a view preference and never reaches the search itself:
 * ranking, the request and the recorded search state are untouched, so R@k order
 * is exactly what the backend returned.
 *
 * Pure functions, no I/O. The caller passes the list it would have shown (after
 * the pin filter) and memoises the result - see the grid memo in App.tsx.
 */
import type { SearchResult } from "../types/api";
import { videoOf } from "./focusFilter";

export interface GroupInfo {
  /** Frames of this video in the list that was grouped. */
  count: number;
  /** Their names in list order, the card's own frame included. */
  memberNames: string[];
}

/** Keyed by the name of the frame the card shows. */
export type GroupInfoByFrame = Map<string, GroupInfo>;

export interface GridResults {
  /** What the grid renders, page by page. */
  cards: SearchResult[];
  /**
   * Present only when the list was grouped. Absent, not empty, when it was not,
   * so "the option is off" can be told from "grouped, nothing to say".
   */
  groupInfoByFrame?: GroupInfoByFrame;
}

/**
 * The score a frame competes with. NaN compares false against everything, so a
 * NaN first frame would stay "best" against every real score; it is treated as
 * the worst possible instead, and never wins.
 */
function scoreOf(result: SearchResult): number {
  return Number.isNaN(result.distance) ? Number.NEGATIVE_INFINITY : result.distance;
}

/**
 * One card per video: its highest-scoring frame (`distance`, higher is better on
 * the frame routes), a tie going to the frame that comes first in the list.
 *
 * Cards keep the order in which their video FIRST appears. The ensemble list is
 * sorted by descending fused score, so that is also the order of each video's
 * best score; for a list that is not sorted, the card still sits where its video
 * first showed up and merely shows a better frame than the one that got it there.
 *
 * A frame whose video id cannot be read (videoOf gives "") is never merged with
 * another: an unknown id is not evidence that two frames are the same video, and
 * hiding a frame on that guess would lose it. Each stays a card of its own.
 *
 * Every card has an entry in groupInfoByFrame, a one-frame video included
 * (count 1); the UI decides that only count > 1 earns a badge.
 */
export function groupResultsByVideo(
  results: SearchResult[]
): Required<GridResults> {
  const cards: SearchResult[] = [];
  // Parallel to `cards`: the names of every frame that landed in that card.
  const members: string[][] = [];
  const slotOfVideo = new Map<string, number>();

  for (const result of results) {
    const video = videoOf(result);
    const slot = video ? slotOfVideo.get(video) : undefined;
    if (slot === undefined) {
      if (video) {
        slotOfVideo.set(video, cards.length);
      }
      cards.push(result);
      members.push([result.name]);
      continue;
    }
    members[slot].push(result.name);
    if (scoreOf(result) > scoreOf(cards[slot])) {
      cards[slot] = result;
    }
  }

  const groupInfoByFrame: GroupInfoByFrame = new Map();
  cards.forEach((card, index) => {
    groupInfoByFrame.set(card.name, {
      count: members[index].length,
      memberNames: members[index],
    });
  });
  return { cards, groupInfoByFrame };
}

/**
 * The list the grid actually renders.
 *
 * With the option off, or on a route that must never be grouped (OCR results,
 * temporal, TRAKE), it returns `shownResults` ITSELF - the same array, no
 * `groupInfoByFrame` key - so the off path is provably the code that ran before
 * this option existed: same reference, same props for FrameDisplay.
 */
export function buildGridResults(
  shownResults: SearchResult[],
  onePerVideo: boolean,
  routeAllowsGrouping: boolean
): GridResults {
  if (!onePerVideo || !routeAllowsGrouping) {
    return { cards: shownResults };
  }
  return groupResultsByVideo(shownResults);
}

/**
 * Why a card is ringed as "the frame you picked", or null when it is not.
 *
 * "own": the card's frame is the picked one - the only case before grouping.
 * "hidden": the picked frame is another frame of this card's video, folded into
 * the card; without this the ring would vanish from the grid the moment the
 * option is switched on, or when the pick is made from the popup's strip.
 * Without groupInfoByFrame it is exactly the old rule.
 */
export type PickedKind = "own" | "hidden";

export function pickedKind(
  result: SearchResult,
  highlightFrame: string | undefined,
  groupInfoByFrame?: GroupInfoByFrame
): PickedKind | null {
  if (highlightFrame === undefined) {
    return null;
  }
  if (result.name === highlightFrame) {
    return "own";
  }
  const members = groupInfoByFrame?.get(result.name)?.memberNames;
  return members?.includes(highlightFrame) ? "hidden" : null;
}
