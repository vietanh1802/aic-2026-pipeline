import { describe, expect, it } from "vitest";

import { frameGap, splitQueryParts } from "./candidates";

describe("splitQueryParts", () => {
  it("splits on a dot followed by whitespace", () => {
    expect(splitQueryParts("người bước lên sân khấu. khán giả vỗ tay")).toEqual([
      "người bước lên sân khấu",
      "khán giả vỗ tay",
    ]);
  });

  it("does not split a dot with no whitespace after it", () => {
    // Matches preprocess.py's \.\s+ — "cắt nấm.cắt đậu hũ" must stay one part.
    expect(splitQueryParts("cắt nấm.cắt đậu hũ")).toEqual(["cắt nấm.cắt đậu hũ"]);
  });

  it("drops a trailing dot and empty parts", () => {
    expect(splitQueryParts("cắt nấm.  cắt đậu hũ.  bật bếp.")).toEqual([
      "cắt nấm",
      "cắt đậu hũ",
      "bật bếp",
    ]);
  });

  it("returns an empty list for blank input", () => {
    expect(splitQueryParts("   ")).toEqual([]);
  });
});

describe("frameGap", () => {
  it("reports the frame distance and its duration", () => {
    expect(frameGap(1804, 2386, 30)).toEqual({ frames: 582, seconds: 19.4 });
  });

  it("is unsigned", () => {
    expect(frameGap(2386, 1804, 30).frames).toBe(582);
  });

  it("reports 0 seconds when fps is unusable", () => {
    expect(frameGap(1804, 2386, 0)).toEqual({ frames: 582, seconds: 0 });
  });
});
