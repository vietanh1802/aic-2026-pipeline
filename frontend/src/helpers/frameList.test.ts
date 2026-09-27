import { describe, expect, it } from "vitest";

import { parseFrameList, parseManualPoint } from "./frameList";

describe("parseManualPoint", () => {
  // M05_V019 là 25 fps.
  it("converts a frame number to ms and clock position", () => {
    expect(parseManualPoint("15697", "frame", "M05_V019", 25)).toEqual({
      frame: 15697,
      ms: 627880,
      seconds: 627.88,
      error: null,
    });
    expect(parseManualPoint("M05_V019-0193-15697.jpg", "frame", "M05_V019", 25).ms).toBe(627880);
  });

  it("converts a time in the video to the frame shown there, then ms", () => {
    expect(parseManualPoint("10:27.88", "time", "M05_V019", 25)).toMatchObject({ frame: 15697, ms: 627880 });
    // 10:27.9 rơi giữa frame 15697 và 15698 → frame đang hiện (floor) là 15697.
    expect(parseManualPoint("10:27.9", "time", "M05_V019", 25)).toMatchObject({ frame: 15697, ms: 627880 });
    expect(parseManualPoint("10:27", "time", "M05_V019", 25)).toMatchObject({ frame: 15675, ms: 627000 });
    expect(parseManualPoint("1:02:03", "time", "M05_V019", 25)).toMatchObject({ frame: 93075, ms: 3723000 });
    // Số trần ở chế độ thời gian là giây.
    expect(parseManualPoint("627.88", "time", "M05_V019", 25).frame).toBe(15697);
  });

  it("matches the round trip the DRES server does (ms -> frame)", () => {
    for (const [text, fps] of [["10:27.88", 25], ["0:33.4", 29.97], ["1:40.5", 29.97]] as const) {
      const p = parseManualPoint(text, "time", "X", fps);
      expect(Math.round(((p.ms as number) / 1000) * fps)).toBe(p.frame);
    }
  });

  it("is empty for empty input and explains everything else", () => {
    expect(parseManualPoint("  ", "frame", "M05_V019", 25)).toEqual({
      frame: null, ms: null, seconds: null, error: null,
    });
    expect(parseManualPoint("1, 2", "frame", "M05_V019", 25).error).toContain("MỘT frame");
    expect(parseManualPoint("10:75", "time", "M05_V019", 25).error).not.toBeNull();
    expect(parseManualPoint("abc", "frame", "M05_V019", 25).error).not.toBeNull();
    expect(parseManualPoint("15697", "frame", "M05_V019", 0).error).toContain("fps");
    expect(parseManualPoint("M05_V020-0001-44", "frame", "M05_V019", 25).error).toContain("M05_V020");
  });
});

describe("parseFrameList", () => {
  it("reads numbers split by commas, spaces, semicolons and newlines, keeping order", () => {
    expect(parseFrameList("15697, 15820 16002;16100\n16250", "M05_V019")).toEqual({
      frames: [15697, 15820, 16002, 16100, 16250],
      error: null,
      warnings: [],
    });
  });

  it("takes the frame number out of pasted keyframe names of this video", () => {
    const got = parseFrameList("M05_V019-0193-15697.jpg, M05_V019-0194-15820", "M05_V019");
    expect(got.frames).toEqual([15697, 15820]);
    expect(got.error).toBeNull();
    // Mã video có gạch ngang (N, S) vẫn tách đúng.
    expect(parseFrameList("N001-V001-0000-11028", "N001-V001").frames).toEqual([11028]);
  });

  it("refuses a keyframe of another video", () => {
    expect(parseFrameList("15697, M05_V020-0001-44", "M05_V019").error).toContain("M05_V020");
  });

  it("refuses junk and repeated frames", () => {
    expect(parseFrameList("15697, abc", "M05_V019").error).toContain("abc");
    expect(parseFrameList("12.5", "M05_V019").error).not.toBeNull();
    expect(parseFrameList("-3", "M05_V019").error).not.toBeNull();
    expect(parseFrameList("100, 200, 100", "M05_V019").error).toBe("Frame 100 bị lặp");
  });

  it("warns, without blocking, when frames go backwards", () => {
    const got = parseFrameList("300, 200", "M05_V019");
    expect(got.error).toBeNull();
    expect(got.frames).toEqual([300, 200]);
    expect(got.warnings).toHaveLength(1);
  });

  it("gives an empty list for empty input", () => {
    expect(parseFrameList("  , ", "M05_V019")).toEqual({ frames: [], error: null, warnings: [] });
  });
});
