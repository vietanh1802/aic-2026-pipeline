// frontend/src/components/VideoPopUp/CandidateStrip.tsx

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  candidateIntervals,
  layoutBlocks,
  mergeIntervals,
  opacityForScore,
  scoreRange,
  type Block,
  type BlockGroup,
} from "../../helpers/candidateStrip";
import {
  LABEL_PX,
  activeBlockIndex,
  activeGroupIndex,
  candidatesForVideo,
  describeBlock,
  formatScore,
  jumpOfBlock,
  labelledGroups,
  shortClock,
} from "../../helpers/candidateStripView";
import { frameClock } from "../../helpers/frameIdentity";
import { barPosition } from "../../helpers/frameRange";
import { useQueryStore } from "../../store/queryStore";
import { useSearchStore } from "../../store/useSearchStore";

/**
 * The OTHER candidate moments of this video, from the current search results,
 * under the player: amber blocks on a track that stands for the video's whole
 * duration, opacity by score, the score printed above, click to jump to the
 * block's best frame.
 *
 * Its own strip and not part of the player's bar or of FrameMarkStrip. The
 * player uses the browser's native controls, whose bar sits in a shadow tree
 * and cannot be marked; FrameMarkStrip already scrubs and marks in/out (and
 * rescales itself for TRAKE), and mixing a second job into it would make both
 * harder to read. This one only shows where the search found things.
 *
 * Renders nothing when there is nothing to show: no results for this video
 * (Go to frame, the basket and the text-signal badge open the popup with no
 * result context), the OCR route, a TRAKE popup, or temporal/TRAKE search. Gone
 * in the browser's native fullscreen too, which only shows the <video>.
 */

const RESIZE_DEBOUNCE_MS = 100;

/**
 * Width of an element in px, kept current with a ResizeObserver.
 *
 * Debounced: dragging the window edge fires it every frame, and each new width
 * re-lays out every block. Takes the element as state (a callback ref) because
 * the track only exists once there are candidates.
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

interface BlockLayerProps {
  groups: BlockGroup[];
  activeGroup: BlockGroup | undefined;
  labelled: Set<BlockGroup>;
  scoreLow: number;
  scoreHigh: number;
  widthPx: number;
  videoId: string;
  onJumpBlock: (block: Block) => void;
}

/**
 * The blocks and their labels. Memoised on its props, none of which change on
 * a playback tick, so the four-a-second timeupdate re-renders only the
 * playhead line and never repaints this layer.
 *
 * Exported only so CandidateStrip.render.test.ts can render it to markup; the
 * popup uses CandidateStrip.
 */
export const BlockLayer = memo(function BlockLayer({
  groups,
  activeGroup,
  labelled,
  scoreLow,
  scoreHigh,
  widthPx,
  videoId,
  onJumpBlock,
}: BlockLayerProps) {
  // layoutBlocks returns render order (ascending score, best drawn last). The
  // DOM has to be in TIME order instead, so Tab walks the video left to right;
  // stacking is then z-index, the same order as before.
  const inTimeOrder = useMemo(
    () =>
      groups
        .map((group, stack) => ({ group, stack }))
        .sort((a, b) => a.group.leftPct - b.group.leftPct),
    [groups]
  );

  return (
    <>
      {inTimeOrder.map(({ group, stack }) => {
        const selected = group === activeGroup;
        const label = describeBlock({
          clock: shortClock(frameClock(videoId, group.best.bestFrame.frameIdx)),
          frames: group.frameCount,
          score: group.best.bestScore,
          blocks: group.members.length,
        });
        return (
          <button
            key={group.best.bestFrame.name}
            type="button"
            aria-label={label}
            aria-current={selected ? "true" : undefined}
            title={label}
            onClick={() => onJumpBlock(group.best)}
            className="absolute inset-y-0 rounded-[4px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-proto-primary"
            // The button is the HIT box (at least 24 px wide, the full height of
            // the strip); the block is drawn inside it at its own position.
            style={{
              left: `${group.hitLeftPct}%`,
              width: `${group.hitWidthPct}%`,
              zIndex: stack + 1,
            }}
          >
            <span
              aria-hidden="true"
              className={`absolute bottom-1.5 h-2.5 rounded-[3px] ${
                selected ? "ring-2 ring-proto-primary" : ""
              }`}
              style={{
                left: `${((group.leftPct - group.hitLeftPct) / group.hitWidthPct) * 100}%`,
                width: `${(group.widthPct / group.hitWidthPct) * 100}%`,
              }}
            >
              {/* Opacity on its own layer: on the outer one it would fade the
                  selection ring together with the block. */}
              <span
                className="absolute inset-0 rounded-[3px] bg-proto-amber"
                style={{
                  opacity: opacityForScore(group.best.bestScore, scoreLow, scoreHigh),
                }}
              />
            </span>
          </button>
        );
      })}

      {/* Score labels, in their own pointer-transparent layer above the blocks
          so a click on a label still reaches the block under it. Only the
          groups labelledGroups() says have room; the rest are in the chips. */}
      {inTimeOrder.map(({ group }) => {
        if (!labelled.has(group)) {
          return null;
        }
        const centrePx = ((group.leftPct + group.widthPct / 2) / 100) * widthPx;
        const leftPx = Math.min(Math.max(centrePx - LABEL_PX / 2, 0), widthPx - LABEL_PX);
        return (
          <span
            key={`label-${group.best.bestFrame.name}`}
            aria-hidden="true"
            className="pointer-events-none absolute top-0 text-center font-mono text-[10px] leading-3 text-proto-ink"
            style={{ left: `${leftPx}px`, width: `${LABEL_PX}px`, zIndex: groups.length + 1 }}
          >
            {formatScore(group.best.bestScore)}
          </span>
        );
      })}
    </>
  );
});

export default function CandidateStrip({
  videoId,
  durationS,
  currentTimeS,
  hidden = false,
  onJump,
}: {
  videoId: string;
  /** 0 until the player reports it; the chips work without it, the track waits. */
  durationS: number;
  /** The playhead, in seconds. */
  currentTimeS: number;
  /** True on a TRAKE popup. */
  hidden?: boolean;
  /**
   * The block's best frame: name, time and frame number. The popup turns it
   * into a seek exactly as if it had been opened on that keyframe.
   */
  onJump: (frameName: string, timeS: number, frameIdx: number) => void;
}) {
  const results = useSearchStore((state) => state.results);
  const searchType = useQueryStore((state) => state.searchType);
  // `results` is the frame search's list. After a temporal or TRAKE search it
  // still holds the PREVIOUS frame search (App only shows it for the frame
  // routes: isFrameRoute), so the strip would describe a query that is not the
  // one on screen. Same test App uses.
  const showsFrameResults = searchType !== "temporal" && searchType !== "trake";

  // Nothing below recomputes on a playback tick: every input is the result
  // list, the video, the duration or the width.
  const candidates = useMemo(
    () => (hidden || !showsFrameResults ? [] : candidatesForVideo(results, videoId)),
    [hidden, showsFrameResults, results, videoId]
  );
  // Over the FULL list, unlike the card colour (visible page only): a block
  // must not change shade as more pages load.
  const { low: scoreLow, high: scoreHigh } = useMemo(() => scoreRange(results), [results]);
  const blocks = useMemo(
    () => mergeIntervals(candidateIntervals(candidates, durationS)),
    [candidates, durationS]
  );

  const [trackElement, setTrackElement] = useState<HTMLDivElement | null>(null);
  const widthPx = useElementWidth(trackElement);
  const groups = useMemo(
    () => layoutBlocks(blocks, durationS, widthPx),
    [blocks, durationS, widthPx]
  );
  const labelled = useMemo(() => labelledGroups(groups, widthPx), [groups, widthPx]);

  // The parent passes a fresh onJump every render, which would defeat the memo
  // on BlockLayer. Keep the latest in a ref and hand down one stable callback.
  const onJumpRef = useRef(onJump);
  useEffect(() => {
    onJumpRef.current = onJump;
  });
  const jumpToBlock = useCallback((block: Block) => {
    const { frameName, timeS, frameIdx } = jumpOfBlock(block);
    onJumpRef.current(frameName, timeS, frameIdx);
  }, []);

  if (candidates.length === 0) {
    return null;
  }

  const hasDuration = Number.isFinite(durationS) && durationS > 0;
  const activeGroup = groups[activeGroupIndex(groups, currentTimeS)];
  const activeBlock = activeBlockIndex(blocks, currentTimeS);
  const anyCluster = groups.some((group) => group.members.length > 1);

  return (
    <div className="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div className="flex items-baseline gap-2 flex-wrap mb-1 text-[12px] text-proto-muted">
        <span>
          Candidates in this video{" "}
          <b className="font-mono text-proto-ink">{candidates.length}</b> frame
          {candidates.length === 1 ? "" : "s"} in{" "}
          <b className="font-mono text-proto-ink">{blocks.length}</b> block
          {blocks.length === 1 ? "" : "s"}
        </span>
        {anyCluster && (
          <span className="text-[11px]">
            Blocks too close to tell apart share one button on the bar - the list below has each one.
          </span>
        )}
      </div>

      {hasDuration && (
        // `isolate`: the z-indexes below stack the blocks against each other
        // and must not leak above the popup's own controls.
        <div ref={setTrackElement} className="relative isolate h-9">
          <div className="absolute inset-x-0 bottom-1.5 h-2.5 rounded-full bg-proto-line" />
          <BlockLayer
            groups={groups}
            activeGroup={activeGroup}
            labelled={labelled}
            scoreLow={scoreLow}
            scoreHigh={scoreHigh}
            widthPx={widthPx}
            videoId={videoId}
            onJumpBlock={jumpToBlock}
          />
          <div
            className="pointer-events-none absolute inset-y-0 w-[2px] rounded bg-proto-dark"
            style={{
              left: `${barPosition(currentTimeS, 0, durationS) * 100}%`,
              zIndex: groups.length + 2,
            }}
          />
        </div>
      )}

      {/* The same blocks as a list. It is what works before the duration is
          known, when two blocks are too close to click apart, and by keyboard
          in reading order. Time, best score, frames in the block. */}
      <div className="mt-1.5 flex flex-wrap gap-1.5 max-h-[72px] overflow-y-auto">
        {blocks.map((block, index) => {
          const clock = shortClock(frameClock(videoId, block.bestFrame.frameIdx));
          const label = describeBlock({
            clock,
            frames: block.frameCount,
            score: block.bestScore,
          });
          return (
            <button
              key={block.bestFrame.name}
              type="button"
              aria-label={label}
              aria-current={index === activeBlock ? "true" : undefined}
              title={label}
              onClick={() => jumpToBlock(block)}
              className={`inline-flex min-h-6 items-center gap-1.5 rounded-[6px] border px-2 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-proto-primary ${
                index === activeBlock
                  ? "border-proto-primary bg-proto-primary/10"
                  : "border-proto-line bg-white hover:border-proto-primary"
              }`}
            >
              <span className="font-mono text-proto-ink">{clock}</span>
              <span className="font-mono font-bold text-proto-primary-active">
                {formatScore(block.bestScore)}
              </span>
              <span className="text-proto-muted">
                {block.frameCount} frame{block.frameCount === 1 ? "" : "s"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
