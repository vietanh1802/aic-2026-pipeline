import { describe, expect, it } from "vitest";

import {
  frameIdFromName,
  fpsOf,
  startMsAt,
  videoIdFromFrame,
} from "./frameIdentity";

describe("videoIdFromFrame", () => {
  it("reads the video out of a keyframe filename", () => {
    expect(videoIdFromFrame("L26_V194-0012-004707.jpg")).toBe("L26_V194");
  });

  it("accepts the K prefix as well as L", () => {
    expect(videoIdFromFrame("K01_V003-0001-000025.jpg")).toBe("K01_V003");
  });

  it("returns an empty string rather than guessing", () => {
    expect(videoIdFromFrame("not-a-keyframe.jpg")).toBe("");
  });
});

describe("frameIdFromName", () => {
  it("drops the video and the extension, keeps the rest", () => {
    expect(frameIdFromName("L26_V194-0012-004707.jpg")).toBe("0012-004707");
  });
});

describe("startMsAt", () => {
  it("converts a frame index to milliseconds at the video's fps", () => {
    const video = "L26_V194";
    const fps = fpsOf(video);
    // Guard rather than skip: a missing entry would make the assertion below
    // pass vacuously, which is the failure mode this whole helper exists for.
    expect(fps).toBeGreaterThan(0);
    expect(startMsAt(video, 4707)).toBeCloseTo((4707 / fps) * 1000, 6);
  });

  it("opens at zero for a video with no fps instead of seeking to NaN", () => {
    expect(startMsAt("ZZ99_V999", 4707)).toBe(0);
  });

  it("opens at zero for a non-finite frame index", () => {
    expect(startMsAt("L26_V194", Number.NaN)).toBe(0);
  });
});
