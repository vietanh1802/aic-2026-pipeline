import { describe, expect, it } from "vitest";

import { thumbUrl } from "./thumb";

describe("thumbUrl", () => {
  it("points a keyframe at its thumbnail", () => {
    expect(thumbUrl("https://aic-frames.umaga.fun/images/M05_V019-0193-15697.jpg")).toBe(
      "https://aic-frames.umaga.fun/images/t/M05_V019-0193-15697.jpg"
    );
    expect(thumbUrl("https://aic-frames.umaga.fun/images/N001-V001-0000-24.jpg")).toBe(
      "https://aic-frames.umaga.fun/images/t/N001-V001-0000-24.jpg"
    );
  });

  it("leaves anything else alone", () => {
    expect(thumbUrl(undefined)).toBeUndefined();
    expect(thumbUrl("")).toBe("");
    expect(thumbUrl("https://x/images/t/A.jpg")).toBe("https://x/images/t/A.jpg");
    expect(thumbUrl("https://x/static/images/sub/A.jpg")).toBe("https://x/static/images/sub/A.jpg");
    expect(thumbUrl("https://x/other/A.jpg")).toBe("https://x/other/A.jpg");
  });
});
