import type { BoardTask } from "../api/board";

/**
 * The text that describes a task.
 *
 * TRAKE briefs have no prose: the query file is a list of E1..EN event lines
 * and the parser keeps only what precedes them, which is nothing. The events
 * ARE the brief, so they are what gets shown.
 */
export function taskBriefText(
  task: Pick<BoardTask, "type" | "query_text" | "event_labels">
): string {
  if (task.query_text) {
    return task.query_text;
  }
  if (task.type === "trake" && task.event_labels.length > 0) {
    return task.event_labels
      .map((label, index) => `E${index + 1} · ${label}`)
      .join(" → ");
  }
  return "";
}

/**
 * The same brief, shaped for the search box rather than for reading.
 *
 * These cannot be the same string. TRAKE search splits the query on `.\s+` —
 * `splitQueryParts`, which matches preprocess.py:_split_query_text character
 * for character — and the number of parts it yields has to equal `n_events`,
 * or the E1..EN labels line up against the wrong events. The display form's
 * " → " separator contains no period, so pasting it into the box would give
 * one part instead of N and search a single merged event.
 *
 * Joining with ". " is what the splitter expects. Trailing periods are dropped
 * first so a label already ending in one does not produce an empty part.
 */
export function taskQueryForSearch(
  task: Pick<BoardTask, "type" | "query_text" | "event_labels">
): string {
  if (task.query_text) {
    return task.query_text.replace(/\s+/g, " ").trim();
  }
  if (task.type === "trake" && task.event_labels.length > 0) {
    return task.event_labels
      .map((label) => label.replace(/\s+/g, " ").trim().replace(/\.+$/, ""))
      .filter((label) => label.length > 0)
      .join(". ");
  }
  return "";
}
