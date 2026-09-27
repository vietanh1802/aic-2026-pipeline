// frontend/src/helpers/textSignalView.test.ts

import { describe, expect, it } from "vitest";

import type { MatchDetail, SourceMatch } from "../types/api";
import {
  SNIPPET_MAX_CHARS,
  TEXT,
  chips,
  fallbackStatus,
  formatSeconds,
  headline,
  matchedTermsLine,
  normalizeSnippet,
  popoverRight,
  rankLine,
  sourceState,
  sourcesSearched,
  timeLabel,
  timeTitle,
} from "./textSignalView";

function detail(overrides: Partial<MatchDetail> = {}): MatchDetail {
  return {
    snippet: [["nước ", false], ["lửa", true]],
    matched_terms: [],
    terms_total: 0,
    at_s: 833.4,
    start_s: null,
    end_s: null,
    time_approx: false,
    rank: null,
    total_matched: null,
    exact_phrase: null,
    ...overrides,
  };
}

function match(overrides: Partial<SourceMatch> = {}): SourceMatch {
  return {
    match_frame: "L21_V041-0012-1000.jpg",
    match_type: "exact",
    location: "elsewhere",
    detail: detail(),
    ...overrides,
  };
}

// A bm25 detail like the backend builds it: an estimate inside a 60 s window.
const BM25 = detail({
  matched_terms: ["thì", "hiện"],
  terms_total: 3,
  at_s: 833.4,
  start_s: 810,
  end_s: 870,
  time_approx: true,
  rank: 1,
  total_matched: 834,
});

describe("formatSeconds", () => {
  it.each([
    [0, "0:00"],
    [5, "0:05"],
    [59.9, "0:59"],
    [60, "1:00"],
    [833.4, "13:53"],
    [3599, "59:59"],
    [3599.9, "59:59"],
    [3600, "1:00:00"],
    [3723, "1:02:03"],
    [36000, "10:00:00"],
  ])("%s s reads %s", (seconds, expected) => {
    expect(formatSeconds(seconds)).toBe(expected);
  });

  it.each([[-5], [-0.4], [Number.NaN], [Number.POSITIVE_INFINITY], [Number.NEGATIVE_INFINITY]])(
    "reads %s as 0:00 instead of printing garbage",
    (seconds) => {
      expect(formatSeconds(seconds)).toBe("0:00");
    }
  );
});

describe("timeLabel and timeTitle", () => {
  it("marks the bm25 estimate as approximate and names its window", () => {
    expect(timeLabel("asr", BM25)).toBe("≈13:53");
    expect(timeTitle("asr", BM25)).toBe("window 13:30 to 14:30");
  });

  it("marks an ASR substring or regex hit as approximate too, without a window", () => {
    const frameHit = detail({ time_approx: false, at_s: 120 });
    expect(timeLabel("asr", frameHit)).toBe("≈2:00");
    expect(timeTitle("asr", frameHit)).toBe("transcript around this frame");
  });

  it("gives an OCR frame its exact time: no mark, no tooltip", () => {
    const frameHit = detail({ time_approx: false, at_s: 120 });
    expect(timeLabel("ocr", frameHit)).toBe("2:00");
    expect(timeTitle("ocr", frameHit)).toBeNull();
  });

  it("reads the hour boundary in the label and in the window", () => {
    const crossing = detail({ at_s: 3600, start_s: 3570, end_s: 3630, time_approx: true });
    expect(timeLabel("asr", crossing)).toBe("≈1:00:00");
    expect(timeTitle("asr", crossing)).toBe("window 59:30 to 1:00:30");
  });

  it("does not print a window when only one end is known", () => {
    expect(timeTitle("ocr", detail({ start_s: 10, end_s: null }))).toBeNull();
  });
});

describe("matchedTermsLine", () => {
  it("lists the found words and the count when some are missing", () => {
    expect(matchedTermsLine(BM25)).toBe("matched thì, hiện · 2 of 3");
  });

  it("says all words when nothing is missing", () => {
    const full = detail({ matched_terms: ["lửa", "nước"], terms_total: 2 });
    expect(matchedTermsLine(full)).toBe("all 2 words");
  });

  it("says nothing for a single word", () => {
    expect(matchedTermsLine(detail({ matched_terms: ["lửa"], terms_total: 1 }))).toBeNull();
  });

  it("says nothing outside bm25, where terms_total is 0", () => {
    expect(matchedTermsLine(detail())).toBeNull();
  });

  it("says nothing without a detail", () => {
    expect(matchedTermsLine(null)).toBeNull();
    expect(matchedTermsLine(undefined)).toBeNull();
  });

  it("does not print an empty list when no word was found", () => {
    expect(matchedTermsLine(detail({ matched_terms: [], terms_total: 3 }))).toBe("0 of 3 words");
  });
});

describe("rankLine", () => {
  it("prints the corpus-only rank", () => {
    expect(rankLine(BM25)).toBe("#1 of 834 videos");
  });

  it("uses the singular for a corpus of one video", () => {
    expect(rankLine(detail({ rank: 1, total_matched: 1 }))).toBe("#1 of 1 video");
  });

  it("prints nothing when the backend ranked nothing", () => {
    expect(rankLine(detail({ rank: null, total_matched: null }))).toBeNull();
    expect(rankLine(null)).toBeNull();
    expect(rankLine(undefined)).toBeNull();
  });

  it("prints just the rank when the total is missing", () => {
    expect(rankLine(detail({ rank: 3, total_matched: null }))).toBe("#3");
  });
});

describe("chips", () => {
  it("says accents were ignored for a normalized match", () => {
    expect(chips("ocr", match({ match_type: "normalized" }))).toEqual(["accents ignored"]);
    expect(chips("asr", match({ match_type: "normalized" }))).toEqual(["accents ignored"]);
  });

  it("says the words were scattered for an OCR frame without the whole phrase", () => {
    expect(chips("ocr", match({ detail: detail({ exact_phrase: false }) }))).toEqual([
      "words scattered",
    ]);
  });

  it("has no chip for a whole phrase or an unknown one", () => {
    expect(chips("ocr", match({ detail: detail({ exact_phrase: true }) }))).toEqual([]);
    expect(chips("ocr", match({ detail: detail({ exact_phrase: null }) }))).toEqual([]);
  });

  it("never says scattered for ASR", () => {
    expect(chips("asr", match({ detail: detail({ exact_phrase: false }) }))).toEqual([]);
  });

  it("has no chips without a detail, and both when both apply", () => {
    expect(chips("ocr", match({ detail: null }))).toEqual([]);
    expect(
      chips("ocr", match({ match_type: "normalized", detail: detail({ exact_phrase: false }) }))
    ).toEqual(["accents ignored", "words scattered"]);
  });
});

describe("sourceState", () => {
  it("is not-searched whenever the source did not run, whatever the annotation says", () => {
    expect(sourceState(match({ location: "none", detail: null }), false)).toBe("not-searched");
    expect(sourceState(match(), false)).toBe("not-searched");
  });

  it("is no-match for a searched source with nothing found", () => {
    expect(sourceState(match({ location: "none", match_frame: null, detail: null }), true)).toBe(
      "no-match"
    );
  });

  it("is match with a detail", () => {
    expect(sourceState(match(), true)).toBe("match");
  });

  it("is match-no-detail when an older backend sent none", () => {
    expect(sourceState(match({ detail: null }), true)).toBe("match-no-detail");
    // Property absent altogether, as an older backend sends it (not just null).
    const withoutDetail: SourceMatch = {
      match_frame: "L21_V041-0012-1000.jpg",
      match_type: "exact",
      location: "elsewhere",
    };
    expect(sourceState(withoutDetail, true)).toBe("match-no-detail");
  });
});

describe("headline", () => {
  it("says this frame, with no Go target, on the card's own frame", () => {
    expect(headline("asr", match(), "L21_V041-0012-1000.jpg")).toEqual({
      text: "this frame",
      title: null,
      jumpTo: null,
    });
  });

  it("gives the time and a Go target on another frame", () => {
    expect(headline("asr", match({ detail: BM25 }), "L21_V041-0099-9999.jpg")).toEqual({
      text: "≈13:53",
      title: "window 13:30 to 14:30",
      jumpTo: "L21_V041-0012-1000.jpg",
    });
  });

  it("never says this frame when the caller does not know its frame", () => {
    expect(headline("ocr", match(), undefined).jumpTo).toBe("L21_V041-0012-1000.jpg");
  });

  it("falls back to the frame name without a detail, and still knows this frame", () => {
    expect(headline("ocr", match({ detail: null }), "other.jpg")).toEqual({
      text: "L21_V041-0012-1000.jpg",
      title: null,
      jumpTo: "L21_V041-0012-1000.jpg",
    });
    expect(headline("ocr", match({ detail: null }), "L21_V041-0012-1000.jpg").text).toBe(
      "this frame"
    );
  });
});

describe("fallbackStatus", () => {
  it.each([
    ["exact", "here", "exact, visible here"],
    ["exact", "elsewhere", "exact match"],
    ["normalized", "here", "accents ignored, visible here"],
    ["normalized", "elsewhere", "accents ignored"],
  ] as const)("%s and %s reads %s", (matchType, location, expected) => {
    const status = fallbackStatus(match({ match_type: matchType, location }));
    expect(status).toBe(expected);
    expect(status.split(/\s+/).length).toBeLessThanOrEqual(4);
  });
});

describe("normalizeSnippet", () => {
  const texts = (parts: { text: string }[]) => parts.map((part) => part.text);

  it("keeps a snippet with a hit at each edge as it is", () => {
    const parts = normalizeSnippet([["lửa", true], [" và nước ", false], ["gió", true]]);
    expect(parts).toEqual([
      { text: "lửa", hit: true },
      { text: " và nước ", hit: false },
      { text: "gió", hit: true },
    ]);
  });

  it("gives [] for an empty snippet and for anything that is not one", () => {
    expect(normalizeSnippet([])).toEqual([]);
    expect(normalizeSnippet(null)).toEqual([]);
    expect(normalizeSnippet(undefined)).toEqual([]);
    expect(normalizeSnippet("lửa" as never)).toEqual([]);
    expect(normalizeSnippet({ length: 1 } as never)).toEqual([]);
  });

  it("gives [] for a snippet of blanks only", () => {
    expect(normalizeSnippet([["  ", true], ["", false], [" ", false]])).toEqual([]);
  });

  it("drops empty segments and skips malformed ones instead of throwing", () => {
    const junk = [["a", false], ["", true], null, 5, [7, true], ["b", true], ["c"]] as never;
    expect(normalizeSnippet(junk)).toEqual([
      { text: "a", hit: false },
      { text: "b", hit: true },
      { text: "c", hit: false },
    ]);
  });

  it("merges neighbours with the same flag, also across a dropped empty one", () => {
    const parts = normalizeSnippet([["a", false], ["b", false], ["", true], ["c", false], ["d", true], ["e", true]]);
    expect(parts).toEqual([
      { text: "abc", hit: false },
      { text: "de", hit: true },
    ]);
  });

  it("does not modify its input", () => {
    const input: [string, boolean][] = [["a", false], ["b", false]];
    normalizeSnippet(input);
    expect(input).toEqual([["a", false], ["b", false]]);
  });

  describe("capping", () => {
    const filler = (n: number) => "x".repeat(n);

    it("leaves a snippet at exactly the cap alone", () => {
      const parts = normalizeSnippet([[filler(SNIPPET_MAX_CHARS - 3), false], ["lửa", true]]);
      expect(texts(parts).join("").length).toBe(SNIPPET_MAX_CHARS);
      expect(parts.some((part) => part.text.includes("…"))).toBe(false);
    });

    it("cuts around a hit in the middle and marks both edges", () => {
      const parts = normalizeSnippet([[filler(300), false], ["lửa", true], [filler(300), false]], 40);
      const joined = texts(parts).join("");
      expect(parts.some((part) => part.hit && part.text === "lửa")).toBe(true);
      expect(joined.startsWith("…")).toBe(true);
      expect(joined.endsWith("…")).toBe(true);
      expect(joined.length).toBeLessThanOrEqual(40 + 2);
    });

    it("keeps a hit at the start and marks only the end", () => {
      const parts = normalizeSnippet([["lửa", true], [filler(300), false]], 40);
      expect(parts[0]).toEqual({ text: "lửa", hit: true });
      const joined = texts(parts).join("");
      expect(joined.startsWith("…")).toBe(false);
      expect(joined.endsWith("…")).toBe(true);
    });

    it("keeps a hit at the end and marks only the start", () => {
      const parts = normalizeSnippet([[filler(300), false], ["lửa", true]], 40);
      expect(parts[parts.length - 1]).toEqual({ text: "lửa", hit: true });
      const joined = texts(parts).join("");
      expect(joined.startsWith("…")).toBe(true);
      expect(joined.endsWith("…")).toBe(false);
    });

    it("gives a hit its own ellipsis segments so the ellipsis is not bold", () => {
      // A hit longer than the cap is cut on both sides, and nothing else is left
      // to carry the ellipsis.
      const parts = normalizeSnippet([["a".repeat(5), false], [filler(200), true], ["b".repeat(5), false]], 40);
      expect(parts).toEqual([
        { text: "…", hit: false },
        { text: filler(40), hit: true },
        { text: "…", hit: false },
      ]);
    });

    it("keeps (part of) the first hit even when a second hit follows", () => {
      const parts = normalizeSnippet([["lửa", true], [filler(300), false], ["nước", true]], 40);
      expect(parts[0]).toEqual({ text: "lửa", hit: true });
      expect(texts(parts).join("").length).toBeLessThanOrEqual(40 + 2);
    });

    it("does not double an ellipsis the backend already put in the text", () => {
      // The cut lands right after the backend's own ellipsis.
      const parts = normalizeSnippet([[filler(39) + "…" + filler(300), false]], 40);
      expect(texts(parts).join("")).toBe(filler(39) + "…");
    });

    it("cuts a text without any hit from its start", () => {
      const parts = normalizeSnippet([[filler(300), false]], 40);
      expect(parts).toHaveLength(1);
      expect(parts[0].text).toBe(filler(40) + "…");
    });

    it("does not split a surrogate pair at either cut", () => {
      // An emoji is two UTF-16 units; the window edges around the hit land inside one.
      const emoji = "😀";
      const parts = normalizeSnippet(
        [[emoji.repeat(50), false], ["lửa", true], [emoji.repeat(50), false]],
        41
      );
      const joined = texts(parts).join("").replace(/…/g, "");
      expect(joined).toMatch(/^(?:😀)+lửa(?:😀)+$/u);
    });

    it("falls back to the default cap for a cap that cannot work", () => {
      const parts = normalizeSnippet([[filler(SNIPPET_MAX_CHARS + 50), false]], Number.NaN);
      expect(parts.length).toBeGreaterThan(0);
      expect(texts(parts).join("").length).toBeLessThanOrEqual(SNIPPET_MAX_CHARS + 1);
      expect(normalizeSnippet([["lửa", true], [filler(50), false]], 0)[0]).toEqual({
        text: "lửa",
        hit: true,
      });
    });
  });
});

describe("sourcesSearched", () => {
  it("is true for each box that has text", () => {
    expect(sourcesSearched({ asrFilter: "lửa", ocrFilter: "" })).toEqual({ asr: true, ocr: false });
    expect(sourcesSearched({ asrFilter: "", ocrFilter: "2018" })).toEqual({ asr: false, ocr: true });
    expect(sourcesSearched({ asrFilter: "a", ocrFilter: "b" })).toEqual({ asr: true, ocr: true });
  });

  it("treats a blank box as empty, like the backend", () => {
    expect(sourcesSearched({ asrFilter: "   ", ocrFilter: "\t" })).toEqual({
      asr: false,
      ocr: false,
    });
  });
});

describe("popoverRight", () => {
  it("lines the right edges up when there is room", () => {
    expect(popoverRight(1400, 1000)).toBe(400);
  });

  it("moves the popover right when a first-column card would push it off the left edge", () => {
    // Flush would be 1400 - 250 = 1150, leaving a left edge at 1400 - 1150 - 340 = -90.
    expect(popoverRight(1400, 250)).toBe(1400 - 340 - 8);
  });

  it("keeps the margin when the badge is at or beyond the right edge", () => {
    expect(popoverRight(1400, 1400)).toBe(8);
    expect(popoverRight(1400, 1500)).toBe(8);
  });

  it("shrinks with the viewport, like the CSS max width", () => {
    // 320 px wide: the popover is 304 px, so it fills the space between the margins.
    expect(popoverRight(320, 300)).toBe(8);
  });

  it("keeps the popover inside the viewport for any anchor", () => {
    for (const viewport of [320, 640, 1400]) {
      for (const anchor of [0, 100, 300, viewport / 2, viewport, viewport + 50]) {
        const right = popoverRight(viewport, anchor);
        const width = Math.min(340, viewport - 16);
        expect(right).toBeGreaterThanOrEqual(8);
        expect(viewport - right - width).toBeGreaterThanOrEqual(8);
      }
    }
  });
});

describe("TEXT", () => {
  it("keeps the removed sentence out of every string", () => {
    const everything = Object.values(TEXT).map((value) =>
      typeof value === "function" ? "" : String(value)
    );
    expect(everything.join(" ")).not.toContain("another frame of this video");
  });
});
