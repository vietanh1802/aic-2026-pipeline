// frontend/src/components/TextSignalBadge/TextSignalPopoverBody.tsx

/**
 * The content of the Text signal popover: header, one block per source (ASR,
 * OCR) and the mode footer. TextSignalBadge owns the portal, the positioning and
 * the hover logic and renders this inside it.
 *
 * Deliberately free of stores, hooks and browser globals: everything it shows
 * comes in as props, so the whole popover can be rendered to markup in a test.
 * The decisions (which state a source is in, the time label, the snippet
 * cleanup) live in helpers/textSignalView.ts; this file only draws them.
 *
 * Snippet segments are drawn as React text nodes, never as HTML: a segment that
 * contains "<b>" shows the characters "<b>", it does not create an element.
 */
import type { SourceMatch, VideoAnnotation } from "../../types/api";
import {
  TEXT,
  chips,
  fallbackStatus,
  headline,
  matchedTermsLine,
  normalizeSnippet,
  rankLine,
  sourceState,
  type Headline,
  type SearchedSources,
  type SnippetPart,
  type SourceKey,
} from "../../helpers/textSignalView";

export interface TextSignalPopoverBodyProps {
  videoId: string;
  annotation: VideoAnnotation;
  /** Name of the frame the card shows; a match on it reads "this frame". */
  cardFrame?: string;
  /** Which sources ran in the search on screen (an empty box means "not searched"). */
  searched: SearchedSources;
  mode: string;
  filterQuery: string;
  /** Tailwind class of each source's colour dot, the same one the badge itself shows. */
  dotClass: Record<SourceKey, string>;
  /** Opens the video popup at a frame; the badge passes its existing goToMatchFrame. */
  onGoToFrame: (frame: string) => void;
}

const SOURCE_LABEL: Record<SourceKey, string> = { asr: TEXT.asrLabel, ocr: TEXT.ocrLabel };

function GoButton({ frame, onGoToFrame }: { frame: string; onGoToFrame: (frame: string) => void }) {
  return (
    <button
      type="button"
      title={TEXT.goTitle(frame)}
      aria-label={TEXT.goTitle(frame)}
      className="ml-auto shrink-0 rounded-[4px] border border-proto-line bg-proto-soft px-1.5 py-0.5 text-[11px] font-bold text-proto-ink"
      onClick={(event) => {
        // The badge sits on a card that opens its own popup on click.
        event.stopPropagation();
        onGoToFrame(frame);
      }}
    >
      {TEXT.go}
    </button>
  );
}

/** The matched text, hits in bold with a soft highlight, at most two lines. */
function Snippet({ parts }: { parts: SnippetPart[] }) {
  return (
    <div className="mt-0.5 line-clamp-2 break-words text-[12px] leading-snug text-proto-body">
      {parts.map((part, index) =>
        part.hit ? (
          <mark key={index} className="rounded-[2px] bg-proto-amber/25 px-px font-bold text-proto-ink">
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        )
      )}
    </div>
  );
}

function SourceBlock({
  source,
  match,
  searched,
  cardFrame,
  dotClass,
  onGoToFrame,
}: {
  source: SourceKey;
  match: SourceMatch;
  searched: boolean;
  cardFrame: string | undefined;
  dotClass: string;
  onGoToFrame: (frame: string) => void;
}) {
  const state = sourceState(match, searched);
  const dot = <i className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`} />;

  // Two compact grey lines: nothing to read, so nothing more than a label.
  if (state === "not-searched" || state === "no-match") {
    return (
      <div className="mb-1.5 flex items-center gap-1.5 text-[11.5px] text-proto-muted last:mb-0">
        {dot}
        <span className="font-bold">{SOURCE_LABEL[source]}</span>
        <span>· {state === "not-searched" ? TEXT.notSearched : TEXT.noMatch}</span>
      </div>
    );
  }

  const head: Headline = headline(source, match, cardFrame);
  const goButton = head.jumpTo ? <GoButton frame={head.jumpTo} onGoToFrame={onGoToFrame} /> : null;

  // A match from a backend that sent no detail: the frame, Go, and a short status.
  if (state === "match-no-detail") {
    return (
      <div className="mb-1.5 last:mb-0">
        <div className="flex items-center gap-1.5 text-[11.5px]">
          {dot}
          <span className="font-bold text-proto-ink">{SOURCE_LABEL[source]}</span>
          <span className="truncate text-proto-muted" title={head.jumpTo ?? undefined}>
            · {head.text}
          </span>
          {goButton}
        </div>
        <div className="mt-0.5 text-[11px] text-proto-muted">{fallbackStatus(match)}</div>
      </div>
    );
  }

  // state === "match": the detail exists (sourceState checked it).
  const detail = match.detail;
  const snippet = normalizeSnippet(detail?.snippet);
  const meta = [matchedTermsLine(detail), rankLine(detail)].filter(
    (line): line is string => line !== null
  );
  const pills = chips(source, match);

  return (
    <div className="mb-1.5 last:mb-0">
      <div className="flex items-center gap-1.5 text-[11.5px] text-proto-ink">
        {dot}
        <span className="font-bold">{SOURCE_LABEL[source]}</span>
        <span className="text-proto-muted">·</span>
        <span
          className={`font-bold tabular-nums ${head.title ? "cursor-help" : ""}`}
          title={head.title ?? undefined}
        >
          {head.text}
        </span>
        {goButton}
      </div>
      {snippet.length > 0 && <Snippet parts={snippet} />}
      {(meta.length > 0 || pills.length > 0) && (
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-proto-muted">
          {meta.map((line) => (
            <span key={line}>{line}</span>
          ))}
          {pills.map((pill) => (
            <span
              key={pill}
              className="rounded-[4px] border border-proto-line bg-proto-soft px-1 text-[10.5px]"
            >
              {pill}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TextSignalPopoverBody({
  videoId,
  annotation,
  cardFrame,
  searched,
  mode,
  filterQuery,
  dotClass,
  onGoToFrame,
}: TextSignalPopoverBodyProps) {
  return (
    <>
      <div className="truncate text-[13px] font-bold text-proto-muted">
        {TEXT.title} · {videoId}
      </div>
      <div className="my-1.5 border-t border-proto-line" />

      <SourceBlock
        source="asr"
        match={annotation.asr}
        searched={searched.asr}
        cardFrame={cardFrame}
        dotClass={dotClass.asr}
        onGoToFrame={onGoToFrame}
      />
      <SourceBlock
        source="ocr"
        match={annotation.ocr}
        searched={searched.ocr}
        cardFrame={cardFrame}
        dotClass={dotClass.ocr}
        onGoToFrame={onGoToFrame}
      />

      <div className="my-1.5 border-t border-proto-line" />
      <div className="truncate text-[11px] text-proto-muted">
        {TEXT.modeLabel}: {mode} · &quot;{filterQuery.slice(0, 30)}
        {filterQuery.length > 30 ? "…" : ""}&quot;
      </div>
    </>
  );
}
