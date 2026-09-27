// frontend/src/components/TextSignalBadge/toneOfSource.test.ts

import { describe, expect, it } from "vitest";

import { toneOfSource } from "./index";
import type { SourceMatch } from "../../types/api";

function match(overrides: Partial<SourceMatch>): SourceMatch {
  return { match_frame: null, match_type: null, location: "none", ...overrides };
}

describe("toneOfSource", () => {
  it("is gray when location is none", () => {
    expect(toneOfSource(match({ location: "none" }))).toBe("gray");
  });

  it("is green for an exact match on a frame already visible", () => {
    expect(
      toneOfSource(
        match({ location: "here", match_type: "exact", match_frame: "L21_V041-0012-1000.jpg" })
      )
    ).toBe("green");
  });

  it("is amber for a real match on a frame not currently shown, even if exact", () => {
    expect(
      toneOfSource(
        match({ location: "elsewhere", match_type: "exact", match_frame: "L21_V041-0013-2000.jpg" })
      )
    ).toBe("amber");
  });

  it("is amber for a normalized (accent-stripped) match even when it's here", () => {
    // match_type and location disagree: normalized would suggest "weaker",
    // here would suggest "visible" — the combination must still read as
    // amber, not green, since the spelling itself wasn't a real match.
    expect(
      toneOfSource(
        match({ location: "here", match_type: "normalized", match_frame: "L21_V041-0012-1000.jpg" })
      )
    ).toBe("amber");
  });

  it("is amber for a normalized match that is also elsewhere", () => {
    expect(
      toneOfSource(
        match({ location: "elsewhere", match_type: "normalized", match_frame: "L21_V041-0014-3000.jpg" })
      )
    ).toBe("amber");
  });
});
