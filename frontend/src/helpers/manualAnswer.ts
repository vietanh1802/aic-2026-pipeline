/**
 * The frames of a hand-typed answer.
 *
 * The way out of "search found nothing": someone read the frame off the video
 * themselves, or off a teammate's message, and needs a row for it without a
 * search result to click. Everything is checked here so the form can refuse
 * before it calls the API.
 */
export type ManualFramesResult = { frames: number[] } | { error: string };

/** `expected` is n_events for TRAKE and 1 for KIS and Q&A. */
export function parseManualFrames(
  text: string,
  expected: number
): ManualFramesResult {
  const parts = text
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");

  if (parts.length === 0) {
    return { error: "Nhập ít nhất một số frame" };
  }

  const frames: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) {
      return { error: `"${part}" không phải số nguyên không âm` };
    }
    frames.push(Number(part));
  }

  // A short TRAKE row is a wrong row, not a partial one — the tuple is what is
  // scored — so the count is exact rather than a minimum.
  if (frames.length !== expected) {
    return { error: `Cần đúng ${expected} mốc, đang có ${frames.length}` };
  }

  return { frames };
}
