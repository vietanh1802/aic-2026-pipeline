// frontend/src/helpers/textSignalView.ts

/**
 * The decisions behind the Text signal popover (components/TextSignalBadge),
 * kept out of the component so each rule can be tested without rendering it:
 * which state a source is in, how its time, matched words and rank read, and how
 * the snippet is cleaned up before it is drawn.
 *
 * The backend sends a MatchDetail on every matched source (types/api.ts), but an
 * older backend sends none, so every function here also has a defined answer for
 * a missing detail. Nothing in this file throws on odd input: the popover is a
 * side feature and must never take a result card down with it.
 */
import type { MatchDetail, SourceMatch } from "../types/api";

export type SourceKey = "asr" | "ocr";

/** Which sources actually ran in the search that produced the annotations on screen. */
export interface SearchedSources {
  asr: boolean;
  ocr: boolean;
}

/** What a popover assumes when it was never told: both ran, the pre-split behaviour. */
export const ALL_SEARCHED: SearchedSources = { asr: true, ocr: true };

/**
 * Every user-facing string of the popover, in one place so it can be translated
 * later. Entries that need a number or a word are small template functions.
 */
export const TEXT = {
  title: "Text signal",
  modeLabel: "Mode",
  asrLabel: "ASR",
  ocrLabel: "OCR",
  thisFrame: "this frame",
  go: "Go",
  goTitle: (frame: string) => `Go to ${frame}`,
  approxMark: "≈",
  notSearched: "not searched",
  noMatch: "no match",
  accentsIgnored: "accents ignored",
  wordsScattered: "words scattered",
  transcriptAroundFrame: "transcript around this frame",
  windowRange: (from: string, to: string) => `window ${from} to ${to}`,
  matchedAll: (total: number) => `all ${total} words`,
  matchedSome: (words: string[], total: number) =>
    words.length > 0
      ? `matched ${words.join(", ")} · ${words.length} of ${total}`
      : `0 of ${total} words`,
  rank: (rank: number, total: number) => `#${rank} of ${total} video${total === 1 ? "" : "s"}`,
  rankOnly: (rank: number) => `#${rank}`,
  // Status of a match that came without detail (an older backend): at most four words.
  statusExact: "exact match",
  statusExactHere: "exact, visible here",
  statusAccents: "accents ignored",
  statusAccentsHere: "accents ignored, visible here",
} as const;

/** Snippet cap in characters; the backend already sends about 90, this is a safety net. */
export const SNIPPET_MAX_CHARS = 120;

/** Popover width in px. Keep in sync with the w-[340px] class in TextSignalBadge/index.tsx. */
export const POPOVER_WIDTH_PX = 340;
/** Smallest gap kept between the popover and the viewport edge. */
export const POPOVER_MARGIN_PX = 8;

/**
 * Which sources a search actually ran, from the filter boxes it was sent with.
 * A blank box is inactive, like on the backend (it strips before deciding).
 * Read from the snapshot doSearch takes, never from the live store fields: those
 * can be edited while the search is still running.
 */
export function sourcesSearched(fields: { asrFilter: string; ocrFilter: string }): SearchedSources {
  return { asr: fields.asrFilter.trim() !== "", ocr: fields.ocrFilter.trim() !== "" };
}

/**
 * M:SS, or H:MM:SS from one hour on ("13:55", "1:02:03"). Whole seconds, rounded
 * down like a player clock. A negative or non-finite value reads as 0:00 rather
 * than printing "NaN:NaN".
 */
export function formatSeconds(seconds: number): string {
  const whole = Number.isFinite(seconds) ? Math.floor(Math.max(seconds, 0)) : 0;
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = String(whole % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

/**
 * Whether a time should be read as approximate: the bm25 estimate says so itself
 * (time_approx), and every ASR match does too. A frame's ASR text can cover about
 * 60 s of transcript, so a substring or regex hit may be spoken at another time
 * than the frame's own. bm25 is the only ASR mode that sets time_approx, so
 * "source is asr" is exactly "ASR in substring or regex mode" on top of it.
 */
export function isApproxTime(source: SourceKey, detail: MatchDetail): boolean {
  return detail.time_approx || source === "asr";
}

/** The moment of a match, "≈13:55" when approximate, "13:55" when exact. */
export function timeLabel(source: SourceKey, detail: MatchDetail): string {
  const clock = formatSeconds(detail.at_s);
  return isApproxTime(source, detail) ? `${TEXT.approxMark}${clock}` : clock;
}

/**
 * Tooltip of the time: the transcript window for bm25, a plain reminder for an
 * ASR frame hit, nothing for an exact OCR frame time.
 */
export function timeTitle(source: SourceKey, detail: MatchDetail): string | null {
  if (typeof detail.start_s === "number" && typeof detail.end_s === "number") {
    return TEXT.windowRange(formatSeconds(detail.start_s), formatSeconds(detail.end_s));
  }
  return source === "asr" ? TEXT.transcriptAroundFrame : null;
}

/**
 * The matched-words line, only for a bm25 query of more than one word:
 * "matched thì, hiện · 2 of 3", or "all 3 words" when nothing is missing.
 * A single word (or any other mode: terms_total is 0) has nothing to add.
 */
export function matchedTermsLine(detail: MatchDetail | null | undefined): string | null {
  if (!detail || !(detail.terms_total > 1)) return null;
  const found = Array.isArray(detail.matched_terms) ? detail.matched_terms : [];
  return found.length >= detail.terms_total
    ? TEXT.matchedAll(detail.terms_total)
    : TEXT.matchedSome(found, detail.terms_total);
}

/** "#1 of 834 videos"; null when the backend ranked nothing (ASR substring and regex). */
export function rankLine(detail: MatchDetail | null | undefined): string | null {
  if (!detail || typeof detail.rank !== "number") return null;
  return typeof detail.total_matched === "number"
    ? TEXT.rank(detail.rank, detail.total_matched)
    : TEXT.rankOnly(detail.rank);
}

/** The small pills under a match: how the spelling matched and how the words sat. */
export function chips(source: SourceKey, match: SourceMatch): string[] {
  const out: string[] = [];
  if (match.match_type === "normalized") out.push(TEXT.accentsIgnored);
  // exact_phrase is null outside OCR, so only an explicit false means scattered.
  if (source === "ocr" && match.detail?.exact_phrase === false) out.push(TEXT.wordsScattered);
  return out;
}

export type SourceState = "not-searched" | "no-match" | "match" | "match-no-detail";

/**
 * Which of the four layouts a source gets. "Not searched" wins over "no match":
 * a source whose box was empty comes back from the backend looking exactly like
 * one that found nothing, and only `searched` tells them apart.
 */
export function sourceState(match: SourceMatch, searched: boolean): SourceState {
  if (!searched) return "not-searched";
  if (match.location === "none") return "no-match";
  return match.detail ? "match" : "match-no-detail";
}

/** The first line of a matched source, and where its Go button leads. */
export interface Headline {
  text: string;
  title: string | null;
  /** Frame name the Go button opens; null hides the button. */
  jumpTo: string | null;
}

/**
 * "this frame" (and no Go button) when the match is on the card's own frame;
 * otherwise the time and a Go button. Without a detail there is no time to show,
 * so the frame name stands in for it. `cardFrame` is undefined for a caller that
 * does not know its frame, which never counts as "this frame".
 */
export function headline(
  source: SourceKey,
  match: SourceMatch,
  cardFrame: string | undefined
): Headline {
  const frame = match.match_frame;
  if (frame && cardFrame && frame === cardFrame) {
    return { text: TEXT.thisFrame, title: null, jumpTo: null };
  }
  if (match.detail) {
    return {
      text: timeLabel(source, match.detail),
      title: timeTitle(source, match.detail),
      jumpTo: frame,
    };
  }
  return { text: frame ?? "", title: null, jumpTo: frame };
}

/** Status of a match that came without detail; at most four words. */
export function fallbackStatus(match: SourceMatch): string {
  const here = match.location === "here";
  if (match.match_type === "normalized") {
    return here ? TEXT.statusAccentsHere : TEXT.statusAccents;
  }
  return here ? TEXT.statusExactHere : TEXT.statusExact;
}

/** One run of snippet text: a hit is drawn bold with a soft highlight. */
export interface SnippetPart {
  text: string;
  hit: boolean;
}

const isLowSurrogate = (code: number) => code >= 0xdc00 && code <= 0xdfff;

/**
 * Cleans the backend's [text, is_hit] segments for drawing: drops empty ones,
 * merges neighbours with the same flag, and caps the total length while keeping
 * (part of) the first hit. Returns [] for anything unusable, never throws.
 *
 * The cap is a safety net, not the normal path: the backend already slices about
 * 90 characters around the hits. When it does cut, the window is centred on the
 * first hit and an ellipsis marks each cut edge (a hit is never given the
 * ellipsis, so it does not turn bold). Cuts do not split a surrogate pair, so an
 * emoji in OCR text is not left as a broken half.
 */
export function normalizeSnippet(
  raw: MatchDetail["snippet"] | null | undefined,
  cap: number = SNIPPET_MAX_CHARS
): SnippetPart[] {
  if (!Array.isArray(raw)) return [];
  // A cap below one character (or NaN) would cut everything, including the hit.
  const maxChars = Number.isFinite(cap) && cap >= 1 ? Math.floor(cap) : SNIPPET_MAX_CHARS;

  const merged: SnippetPart[] = [];
  for (const item of raw) {
    if (!Array.isArray(item) || typeof item[0] !== "string" || item[0] === "") continue;
    const hit = item[1] === true;
    const last = merged[merged.length - 1];
    if (last && last.hit === hit) last.text += item[0];
    else merged.push({ text: item[0], hit });
  }
  // Nothing but whitespace is not worth a line.
  if (merged.every((part) => part.text.trim() === "")) return [];

  const total = merged.reduce((sum, part) => sum + part.text.length, 0);
  if (total <= maxChars) return merged;

  const flat = merged.map((part) => part.text).join("");
  const firstHit = merged.findIndex((part) => part.hit);
  let hitStart = 0;
  let hitLength = 0;
  if (firstHit >= 0) {
    hitStart = merged.slice(0, firstHit).reduce((sum, part) => sum + part.text.length, 0);
    hitLength = Math.min(merged[firstHit].text.length, maxChars);
  }
  // Centre the window on the first hit, then keep it inside the text.
  let lo = Math.min(Math.max(hitStart - Math.floor((maxChars - hitLength) / 2), 0), total - maxChars);
  let hi = lo + maxChars;
  if (lo > 0 && isLowSurrogate(flat.charCodeAt(lo))) lo -= 1;
  if (hi < total && isLowSurrogate(flat.charCodeAt(hi))) hi += 1;

  const cut: SnippetPart[] = [];
  let offset = 0;
  for (const part of merged) {
    const start = Math.max(lo - offset, 0);
    const end = Math.min(hi - offset, part.text.length);
    if (start < end) cut.push({ text: part.text.slice(start, end), hit: part.hit });
    offset += part.text.length;
  }

  // The backend puts its own ellipses inside the text, so do not double one up.
  if (lo > 0) {
    if (cut[0].hit) cut.unshift({ text: "…", hit: false });
    else if (!cut[0].text.startsWith("…")) cut[0].text = "…" + cut[0].text;
  }
  if (hi < total) {
    const last = cut[cut.length - 1];
    if (last.hit) cut.push({ text: "…", hit: false });
    else if (!last.text.endsWith("…")) last.text += "…";
  }
  return cut;
}

/**
 * The `right` offset (px from the viewport's right edge) for the fixed popover.
 *
 * The badge sits at the top right of a card and the popover is anchored so the
 * two right edges line up. At 340 px wide that pushes the popover off the LEFT
 * of the screen for a card in the first column or in a narrow window, so the
 * offset is clamped: never closer than the margin to the right edge, never so far
 * that the left edge crosses the margin. The width mirrors the CSS
 * (min(340 px, viewport - 2 margins)).
 */
export function popoverRight(viewportWidth: number, anchorRight: number): number {
  const width = Math.min(POPOVER_WIDTH_PX, viewportWidth - 2 * POPOVER_MARGIN_PX);
  const flush = viewportWidth - anchorRight;
  const farthest = viewportWidth - width - POPOVER_MARGIN_PX;
  return Math.max(POPOVER_MARGIN_PX, Math.min(flush, farthest));
}
