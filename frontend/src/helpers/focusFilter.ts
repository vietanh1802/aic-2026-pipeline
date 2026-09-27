/**
 * Narrowing the result grid to a handful of clips.
 *
 * The move it exists for: two or three videos look plausible, so you re-word
 * the query five times and watch only those. That is why the list survives a
 * search — clearing it on every query would mean re-picking them every time.
 */
import type { SearchResult } from "../types/api";
import { videoIdFromFrame } from "./frameIdentity";

/** The backend sends `video`; older responses only have the filename. */
export function videoOf(result: SearchResult): string {
  return result.video ?? videoIdFromFrame(result.frame);
}

/** An empty focus list means no filtering, not "hide everything". */
export function filterByFocus(
  results: SearchResult[],
  focus: string[]
): SearchResult[] {
  if (focus.length === 0) {
    return results;
  }
  const wanted = new Set(focus);
  return results.filter((result) => wanted.has(videoOf(result)));
}
