/**
 * Shared shapes for the TRAKE line.
 *
 * Their own file because Fast Refresh only tracks a module that exports
 * components and nothing else — keeping these next to TrakeCard cost the whole
 * file its hot reload.
 */
import type { TemporalCandidate } from "../../types/api";

/**
 * A frame standing in one event's slot.
 *
 * `byHand` marks the ones scrubbed to in the video rather than picked from the
 * backend's candidate list. Those carry no keyframe image — there is no still
 * for an arbitrary frame — so the cell renders them differently instead of
 * showing a broken tile.
 */
export type EventPick = TemporalCandidate & { byHand?: boolean };

/** Overrides for one card, keyed by event index. Empty means "use the DP's". */
export type EventSwaps = Record<number, EventPick>;

/** One entry per TRAKE card on screen. */
export type TrakeSwapMap = Record<string, EventSwaps>;

/**
 * Identifies a card across renders.
 *
 * The video id alone is not enough: auto-discovery can return the same video
 * twice with different event tuples, and two cards sharing a key would share
 * each other's swaps.
 */
export function trakeCardKey(video: string | undefined, index: number): string {
  return `${video ?? "?"}#${index}`;
}
