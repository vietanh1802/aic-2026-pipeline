// frontend/src/helpers/frameIdentity.test.ts

import { describe, expect, it } from "vitest";

import {
  frameClock,
  frameIdFromName,
  frameIdxFromFrameId,
  frameIndexFromResult,
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

// "HH:MM:SS.mmm" back to milliseconds, so the tests can compare against
// frame / fps without repeating the formatting under test.
function clockToMs(clock: string): number {
  const [hours, minutes, rest] = clock.split(":");
  const [seconds, millis] = rest.split(".");
  return ((Number(hours) * 60 + Number(minutes)) * 60 + Number(seconds)) * 1000 + Number(millis);
}

describe("frameClock", () => {
  it("shows L25_V008 frame 36128 at 20:05, not 00:36 as the old parser did", () => {
    const fps = fpsOf("L25_V008");
    expect(fps).toBeGreaterThan(0);
    const clock = frameClock("L25_V008", 36128);
    // 36128 / 29.97 = 1205.472 s. Equal to the backend's timestamp_str for
    // this keyframe in keyframe_metadata.json.
    expect(clock).toBe("00:20:05.472");
    expect(Math.abs(clockToMs(clock) - (36128 / fps) * 1000)).toBeLessThan(1);
  });

  it("matches the backend's timestamp_str for L25_V001 keyframes (25 fps)", () => {
    // Real rows of keyframe_metadata.json: floor(frame / fps * 1000), not round.
    expect(fpsOf("L25_V001")).toBe(25);
    expect(frameClock("L25_V001", 3)).toBe("00:00:00.120");
    expect(frameClock("L25_V001", 33)).toBe("00:00:01.320");
    expect(frameClock("L25_V001", 64)).toBe("00:00:02.560");
    expect(frameClock("L25_V001", 118)).toBe("00:00:04.720");
  });

  it("starts at 00:00:00.000 for frame 0", () => {
    expect(frameClock("L25_V008", 0)).toBe("00:00:00.000");
  });

  it("rolls over at the hour boundary", () => {
    // K01_V001 runs at 25 fps: 90000 frames is exactly one hour.
    expect(fpsOf("K01_V001")).toBe(25);
    expect(frameClock("K01_V001", 90000)).toBe("01:00:00.000");
    expect(frameClock("K01_V001", 89999)).toBe("00:59:59.960");
  });

  it("returns an empty string for an unknown video, not a made-up clock", () => {
    expect(frameClock("ZZ99_V999", 36128)).toBe("");
  });

  it("returns an empty string for a frame that is not a usable number", () => {
    expect(frameClock("L25_V008", Number.NaN)).toBe("");
    expect(frameClock("L25_V008", -1)).toBe("");
  });
});

describe("frameIdxFromFrameId", () => {
  it("takes the frame from a scene-frame id", () => {
    expect(frameIdxFromFrameId("0116-36128")).toBe(36128);
  });

  it("takes a bare frame number as is", () => {
    expect(frameIdxFromFrameId("36128")).toBe(36128);
  });

  it("is NaN when there is no number, rather than frame 0", () => {
    expect(frameIdxFromFrameId("")).toBeNaN();
    expect(frameIdxFromFrameId("abc")).toBeNaN();
  });
});

describe("frameIndexFromResult", () => {
  it("prefers the field the backend sends", () => {
    expect(
      frameIndexFromResult({ frame: "L25_V008-0116-36128.jpg", frame_idx: 7 })
    ).toBe(7);
  });

  it("falls back to the trailing number of the filename", () => {
    expect(frameIndexFromResult({ frame: "L25_V008-0116-36128.jpg" })).toBe(36128);
  });

  it("is 0 when neither is usable, as it was inside App.tsx", () => {
    expect(frameIndexFromResult({ frame: "not-a-keyframe" })).toBe(0);
  });
});
