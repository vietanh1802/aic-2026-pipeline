// frontend/src/helpers/frameIdentity.test.ts

import { describe, expect, it } from "vitest";

import {
  frameClock,
  frameIdFromName,
  frameIdxFromFrameId,
  frameIndexFromResult,
  fpsOf,
  frameMsOf,
  frameToMs,
  startMsAt,
  videoIdFromFrame,
} from "./frameIdentity";

describe("frameToMs", () => {
  it("rounds frame / fps * 1000 like the DRES router", () => {
    expect(frameToMs(2837, 25)).toBe(113480);
    // 1 / 29.97 * 1000 = 33.37 -> 33 (router: round(f / fps * 1000))
    expect(frameToMs(1, 29.97)).toBe(33);
    expect(frameToMs(0, 30)).toBe(0);
  });

  it("gives null instead of a fake 0 when it cannot convert", () => {
    expect(frameToMs(null, 25)).toBeNull();
    expect(frameToMs(100, 0)).toBeNull();
    expect(frameToMs(Number.NaN, 25)).toBeNull();
    expect(frameToMs(-1, 25)).toBeNull();
  });

  // Màn hình hiện ms, server quy ms về frame bằng round(t / 1000 * fps). Nếu
  // vòng đi-về lệch thì số frame người dùng thấy khác số frame bị nộp.
  it.each([25, 29.97, 30, 26.44, 59.94])("round-trips every frame at %s fps", (fps) => {
    for (let frame = 0; frame <= 200_000; frame += 1) {
      const ms = frameToMs(frame, fps) as number;
      if (Math.round((ms / 1000) * fps) !== frame) {
        throw new Error(`frame ${frame} -> ${ms} ms -> ${Math.round((ms / 1000) * fps)}`);
      }
    }
  });

  it("looks up the fps by video, batch 2 ids included", () => {
    expect(frameMsOf("L21_V001", 30)).toBe(Math.round((30 / fpsOf("L21_V001")) * 1000));
    expect(frameMsOf("N001-V001", 25)).toBe(Math.round((25 / fpsOf("N001-V001")) * 1000));
    expect(frameMsOf("NOPE_V999", 25)).toBeNull();
  });
});

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
    // Trước dùng K01_V001, nhưng fps_map.json đã bỏ K01–K20 (index không có
    // batch K). L21_V003 cũng 25 fps: 90000 frames is exactly one hour.
    expect(fpsOf("L21_V003")).toBe(25);
    expect(frameClock("L21_V003", 90000)).toBe("01:00:00.000");
    expect(frameClock("L21_V003", 89999)).toBe("00:59:59.960");
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

describe("video ids from new batches", () => {
  it.each([
    ["M01_V001-0049-5059.jpg", "M01_V001", "0049-5059", 5059],
    ["N001-V001-0012-345.jpg", "N001-V001", "0012-345", 345],
    ["S01-V001-0001-7.jpg", "S01-V001", "0001-7", 7],
  ])("reads %j", (name, video, frameId, frameIdx) => {
    expect(videoIdFromFrame(name)).toBe(video);
    expect(frameIdFromName(name)).toBe(frameId);
    expect(frameIndexFromResult({ frame: name })).toBe(frameIdx);
  });

  it("no longer cuts a hyphenated id at its first hyphen", () => {
    // The old frameIdFromName answered "V001-0012-345" here.
    expect(frameIdFromName("N001-V001-0012-345.jpg")).toBe("0012-345");
  });

  it("still gives the old answer for a name that is not a frame", () => {
    expect(videoIdFromFrame("not-a-keyframe.jpg")).toBe("");
    expect(frameIdFromName("not-a-keyframe.jpg")).toBe("a-keyframe");
  });
});

// The three parsers as they were before parseFrameName, verbatim.
const legacyVideoId = (frame: string) => frame.match(/^([LK]\d{2}_V\d{3})/)?.[1] ?? "";
const legacyFrameId = (name: string) =>
  name.replace(/\.[^/.]+$/, "").split("-").slice(1).join("-");
const legacyFrameIndex = (frame: string) => Number(frame.match(/-(\d+)\.jpg$/)?.[1] ?? 0);

describe("L and K ids give the same answers as the old parsers", () => {
  const videos = ["L21_V001", "L26_V194", "L30_V095", "K01_V003", "K19_V001"];
  const scenes = ["0000", "0012", "0224"];
  const frames = ["0", "3", "33", "004707", "36128"];
  const names: string[] = [];
  for (const video of videos) {
    for (const scene of scenes) {
      for (const frame of frames) {
        names.push(`${video}-${scene}-${frame}`);
      }
    }
  }

  it("covers a real spread of names", () => {
    expect(names).toHaveLength(75);
  });

  it.each(names)("%s.jpg", (base) => {
    const name = `${base}.jpg`;
    expect(videoIdFromFrame(name)).toBe(legacyVideoId(name));
    expect(frameIdFromName(name)).toBe(legacyFrameId(name));
    expect(frameIndexFromResult({ frame: name })).toBe(legacyFrameIndex(name));
    // Without an extension the id parsers agree too; the old frame index gave
    // 0 there, which is the one deliberate difference (it now reads the number).
    expect(videoIdFromFrame(base)).toBe(legacyVideoId(base));
    expect(frameIdFromName(base)).toBe(legacyFrameId(base));
  });

  it.each(["not-a-keyframe.jpg", "", "L26_V194", "L26_V194-4707.jpg", "foo-bar-baz.jpg"])(
    "odd input %j",
    (name) => {
      expect(videoIdFromFrame(name)).toBe(legacyVideoId(name));
      expect(frameIdFromName(name)).toBe(legacyFrameId(name));
      expect(frameIndexFromResult({ frame: name })).toBe(legacyFrameIndex(name));
    }
  );
});
