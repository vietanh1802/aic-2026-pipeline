// frontend/src/components/TextSignalBadge/TextSignalPopoverBody.render.test.ts

/**
 * Markup of the Text signal popover, rendered to a string with react-dom/server
 * (vitest runs in node, no DOM). Only the first render is visible: which lines
 * exist, in what order, with which text. Hover, the portal, positioning and the
 * Go click need a browser. The body takes everything as props, so no store is
 * mocked; the badge test at the end relies on the stores' initial state.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MatchDetail, SourceMatch, VideoAnnotation } from "../../types/api";
import TextSignalBadge from "./index";
import TextSignalPopoverBody, { type TextSignalPopoverBodyProps } from "./TextSignalPopoverBody";

const CARD = "L21_V041-0012-1000.jpg";
const OTHER = "L21_V041-0099-9999.jpg";

function detail(overrides: Partial<MatchDetail> = {}): MatchDetail {
  return {
    snippet: [["…nói về ", false], ["lửa", true], [" và nước…", false]],
    matched_terms: [],
    terms_total: 0,
    at_s: 120,
    start_s: null,
    end_s: null,
    time_approx: false,
    rank: null,
    total_matched: null,
    exact_phrase: null,
    ...overrides,
  };
}

function source(overrides: Partial<SourceMatch> = {}): SourceMatch {
  return { match_frame: OTHER, match_type: "exact", location: "elsewhere", detail: detail(), ...overrides };
}

const NONE: SourceMatch = { match_frame: null, match_type: null, location: "none", detail: null };

function annotation(asr: SourceMatch, ocr: SourceMatch): VideoAnnotation {
  return { matched: true, score: 1, mode: "substring", asr, ocr };
}

function render(overrides: Partial<TextSignalPopoverBodyProps> = {}): string {
  return renderToStaticMarkup(
    createElement(TextSignalPopoverBody, {
      videoId: "L21_V041",
      annotation: annotation(source(), NONE),
      cardFrame: CARD,
      searched: { asr: true, ocr: true },
      mode: "ASR substring",
      filterQuery: "lửa",
      dotClass: { asr: "bg-proto-amber", ocr: "bg-proto-line" },
      onGoToFrame: () => undefined,
      ...overrides,
    })
  );
}

// A tag becomes a space, not nothing: the gaps between a source's label, its time
// and its button are CSS (flex gap), so without one "ASR" and "this frame" would
// read as "ASRthis frame".
const text = (markup: string) => markup.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
const hits = (markup: string) => [...markup.matchAll(/<mark[^>]*>([^<]*)<\/mark>/g)].map((m) => m[1]);
const buttons = (markup: string) => (markup.match(/<button/g) ?? []).length;

// The bm25 estimate for "lửa, nước, gió": two of three words, 60 s window.
const BM25 = detail({
  snippet: [["…", false], ["lửa", true], [" và ", false], ["nước", true], [" trong…", false]],
  matched_terms: ["lửa", "nước"],
  terms_total: 3,
  at_s: 833.4,
  start_s: 810,
  end_s: 870,
  time_approx: true,
  rank: 1,
  total_matched: 834,
});

describe("header and footer", () => {
  it("keeps the header and the Mode line", () => {
    const markup = render({ mode: "ASR bm25", filterQuery: "lửa, nước" });
    expect(text(markup)).toContain("Text signal · L21_V041");
    expect(text(markup)).toContain("Mode: ASR bm25 · &quot;lửa, nước&quot;");
  });

  it("cuts a long query at 30 characters", () => {
    const markup = render({ filterQuery: "a".repeat(45) });
    expect(text(markup)).toContain(`&quot;${"a".repeat(30)}…&quot;`);
  });

  it("puts ASR before OCR and paints each dot with its own class", () => {
    const markup = render({ dotClass: { asr: "bg-proto-teal", ocr: "bg-proto-line" } });
    expect(markup.indexOf("ASR")).toBeLessThan(markup.indexOf("OCR"));
    expect(markup).toContain("bg-proto-teal");
    expect(markup).toContain("bg-proto-line");
  });
});

describe("a bm25 match", () => {
  const bm25Markup = () => render({ annotation: annotation(source({ detail: BM25 }), NONE) });

  it("shows the snippet with the found words marked", () => {
    const markup = bm25Markup();
    expect(hits(markup)).toEqual(["lửa", "nước"]);
    expect(text(markup)).toContain("… lửa và nước trong…");
    expect(markup).toContain("line-clamp-2");
  });

  it("shows an approximate time with the window as its tooltip", () => {
    const markup = bm25Markup();
    expect(text(markup)).toContain("≈13:53");
    expect(markup).toContain('title="window 13:30 to 14:30"');
  });

  it("names the matched words for a partial match, then the rank", () => {
    const markup = bm25Markup();
    expect(text(markup)).toContain("matched lửa, nước · 2 of 3");
    expect(text(markup)).toContain("#1 of 834 videos");
  });

  it("says all words when nothing is missing", () => {
    const full = detail({ ...BM25, matched_terms: ["lửa", "nước", "gió"] });
    const markup = render({ annotation: annotation(source({ detail: full }), NONE) });
    expect(text(markup)).toContain("all 3 words");
    expect(text(markup)).not.toContain("matched lửa");
  });

  it("says nothing about matched words for a single-word query", () => {
    const single = detail({ ...BM25, matched_terms: ["lửa"], terms_total: 1 });
    const markup = render({ annotation: annotation(source({ detail: single }), NONE) });
    expect(text(markup)).not.toContain(" of 1");
    expect(text(markup)).not.toContain("all 1");
    expect(text(markup)).not.toContain("matched lửa");
    // The rank line is still there.
    expect(text(markup)).toContain("#1 of 834 videos");
  });
});

describe("this frame versus a jump", () => {
  it("says this frame, without a Go button, when the match is on the card's own frame", () => {
    const markup = render({ annotation: annotation(source({ match_frame: CARD }), NONE) });
    expect(text(markup)).toContain("ASR · this frame");
    expect(buttons(markup)).toBe(0);
    // No time is printed for it.
    expect(text(markup)).not.toContain("2:00");
  });

  it("shows the time and a Go button for another frame", () => {
    const markup = render();
    expect(text(markup)).toContain("ASR · ≈2:00");
    expect(buttons(markup)).toBe(1);
    expect(markup).toContain(`aria-label="Go to ${OTHER}"`);
    expect(text(markup)).toContain("Go");
  });

  it("treats a card that does not know its frame as another frame", () => {
    const markup = render({ cardFrame: undefined, annotation: annotation(source({ match_frame: CARD }), NONE) });
    expect(text(markup)).not.toContain("this frame");
    expect(buttons(markup)).toBe(1);
  });

  it("decides per source: this frame for one, a jump for the other", () => {
    const markup = render({
      annotation: annotation(source({ match_frame: CARD }), source({ match_frame: OTHER })),
    });
    expect(text(markup)).toContain("ASR · this frame");
    expect(buttons(markup)).toBe(1);
    expect(markup).toContain(`aria-label="Go to ${OTHER}"`);
  });
});

describe("an ASR frame hit (substring or regex)", () => {
  it("marks the time approximate, though the backend gave a frame time", () => {
    const markup = render({ annotation: annotation(source({ detail: detail({ at_s: 125 }) }), NONE) });
    expect(text(markup)).toContain("≈2:05");
    expect(markup).toContain('title="transcript around this frame"');
  });

  it("has no rank line when the backend ranked nothing", () => {
    const markup = render();
    expect(text(markup)).not.toContain("#");
    expect(text(markup)).not.toContain(" of ");
  });
});

describe("an OCR match", () => {
  const ocr = (overrides: Partial<MatchDetail> = {}, extra: Partial<SourceMatch> = {}) =>
    source({
      detail: detail({ at_s: 3723, snippet: [["Đài ", false], ["Truyền hình", true]], ...overrides }),
      ...extra,
    });

  it("shows the exact frame time with no tilde and no scattered chip for a whole phrase", () => {
    const markup = render({
      annotation: annotation(NONE, ocr({ exact_phrase: true, rank: 4, total_matched: 12 })),
      searched: { asr: false, ocr: true },
    });
    expect(text(markup)).toContain("OCR · 1:02:03");
    expect(text(markup)).not.toContain("≈");
    expect(text(markup)).not.toContain("words scattered");
    expect(text(markup)).toContain("#4 of 12 videos");
    expect(hits(markup)).toEqual(["Truyền hình"]);
  });

  it("says the words were scattered when the frame lacks the whole phrase", () => {
    const markup = render({
      annotation: annotation(NONE, ocr({ exact_phrase: false })),
      searched: { asr: false, ocr: true },
    });
    expect(text(markup)).toContain("words scattered");
  });

  it("says nothing about the phrase when the backend does not know (regex)", () => {
    const markup = render({
      annotation: annotation(NONE, ocr({ exact_phrase: null })),
      searched: { asr: false, ocr: true },
    });
    expect(text(markup)).not.toContain("words scattered");
  });
});

describe("the accents chip", () => {
  it("shows for a normalized match", () => {
    const markup = render({ annotation: annotation(source({ match_type: "normalized" }), NONE) });
    expect(text(markup)).toContain("accents ignored");
  });

  it("does not show for an exact match", () => {
    expect(text(render())).not.toContain("accents ignored");
  });
});

describe("a source without a match", () => {
  it("is one grey line 'not searched' when its box was empty", () => {
    const markup = render({ searched: { asr: true, ocr: false } });
    expect(text(markup)).toContain("OCR · not searched");
    expect(text(markup)).not.toContain("OCR · no match");
  });

  it("is one grey line 'no match' when it was searched and found nothing", () => {
    const markup = render();
    expect(text(markup)).toContain("OCR · no match");
    expect(text(markup)).not.toContain("not searched");
  });

  it("is 'not searched' even when the annotation carries a match (the search decides)", () => {
    const markup = render({
      annotation: annotation(source(), source()),
      searched: { asr: true, ocr: false },
    });
    expect(text(markup)).toContain("OCR · not searched");
    expect(buttons(markup)).toBe(1);
  });

  it("has neither snippet, time nor button, so both grey lines stay compact", () => {
    const markup = render({
      annotation: annotation(NONE, NONE),
      searched: { asr: false, ocr: true },
    });
    expect(text(markup)).toContain("ASR · not searched");
    expect(text(markup)).toContain("OCR · no match");
    expect(buttons(markup)).toBe(0);
    expect(markup).not.toContain("line-clamp-2");
  });
});

describe("an older backend (no detail)", () => {
  const legacy = source({ detail: undefined, match_type: "exact", location: "here" });

  it("shows the frame, the Go button and a short status", () => {
    const markup = render({ annotation: annotation(legacy, NONE) });
    expect(text(markup)).toContain(`ASR · ${OTHER}`);
    expect(text(markup)).toContain("exact, visible here");
    expect(buttons(markup)).toBe(1);
    expect(markup).toContain(`aria-label="Go to ${OTHER}"`);
  });

  it("reads a normalized match as accents ignored", () => {
    const markup = render({
      annotation: annotation(source({ detail: null, match_type: "normalized", location: "elsewhere" }), NONE),
    });
    expect(text(markup)).toContain("accents ignored");
  });

  it("says this frame, without a button, when it is the card's own frame", () => {
    const markup = render({ annotation: annotation({ ...legacy, match_frame: CARD }, NONE) });
    expect(text(markup)).toContain("ASR · this frame");
    expect(buttons(markup)).toBe(0);
  });

  it("does not print the sentence that was removed, in any state", () => {
    const states = [
      annotation(legacy, NONE),
      annotation(source(), source({ match_type: "normalized" })),
      annotation(NONE, NONE),
    ];
    for (const one of states) {
      expect(render({ annotation: one })).not.toContain("another frame of this video");
    }
  });
});

describe("snippets are text, never HTML", () => {
  it("renders a segment containing <b> as characters", () => {
    const malicious = detail({
      snippet: [
        ["before <b>bold</b> ", false],
        ["<script>alert(1)</script>", true],
        [' <img src=x onerror="alert(2)">', false],
      ],
    });
    const markup = render({ annotation: annotation(source({ detail: malicious }), NONE) });
    expect(markup).toContain("&lt;b&gt;bold&lt;/b&gt;");
    expect(markup).not.toContain("<b>");
    expect(markup).not.toContain("<script");
    expect(markup).not.toContain("<img");
    // The hit is one <mark> whose content is the escaped script text.
    expect(hits(markup)).toEqual(["&lt;script&gt;alert(1)&lt;/script&gt;"]);
  });

  it("draws exactly as many highlights as there are hit segments", () => {
    const markup = render({ annotation: annotation(source({ detail: BM25 }), NONE) });
    expect(markup.match(/<mark/g)).toHaveLength(2);
  });

  it("leaves the snippet line out when there is nothing to show", () => {
    const empty = detail({ snippet: [] });
    const markup = render({ annotation: annotation(source({ detail: empty }), NONE) });
    expect(markup).not.toContain("line-clamp-2");
    // The time and the Go button are still there.
    expect(text(markup)).toContain("≈2:00");
    expect(buttons(markup)).toBe(1);
  });
});

describe("TextSignalBadge itself", () => {
  const badge = (props: Record<string, unknown>) =>
    renderToStaticMarkup(
      createElement(TextSignalBadge, {
        videoId: "L21_V041",
        filterQuery: "lửa",
        mode: "ASR substring",
        ...props,
      } as never)
    );

  it("renders nothing without an annotation", () => {
    expect(badge({ annotation: undefined })).toBe("");
  });

  it("renders its two dots and no popover before anyone hovers it", () => {
    const markup = badge({ annotation: annotation(source(), NONE), cardFrame: CARD });
    expect(markup.match(/<i /g)).toHaveLength(2);
    expect(markup).toContain('title="ASR"');
    expect(markup).toContain('title="OCR"');
    expect(text(markup)).not.toContain("Text signal");
  });
});
