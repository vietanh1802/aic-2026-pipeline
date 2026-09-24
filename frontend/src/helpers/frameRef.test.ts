// frontend/src/helpers/frameRef.test.ts

import { describe, expect, it } from "vitest";

import { VIDEO_ID_PATTERN, parseFrameName, parseFrameRef } from "./frameRef";

describe("parseFrameRef", () => {
  it("reads video and frame separated by a space", () => {
    expect(parseFrameRef("L01_V001 1234")).toEqual({
      videoId: "L01_V001",
      frameIdx: 1234,
    });
  });

  it("reads video and frame separated by a dash", () => {
    expect(parseFrameRef("L01_V001-1234")).toEqual({
      videoId: "L01_V001",
      frameIdx: 1234,
    });
  });

  // A teammate pasting what they see under a result tile.
  it("reads a full keyframe filename, taking the frame not the scene", () => {
    expect(parseFrameRef("L25_V085-0086-30870.jpg")).toEqual({
      videoId: "L25_V085",
      frameIdx: 30870,
    });
  });

  it("reads the same filename without its extension", () => {
    expect(parseFrameRef("L25_V085-0086-30870")).toEqual({
      videoId: "L25_V085",
      frameIdx: 30870,
    });
  });

  it("accepts the K prefix as well as L", () => {
    expect(parseFrameRef("K19_V001-0000-29")?.videoId).toBe("K19_V001");
  });

  it("ignores surrounding whitespace", () => {
    expect(parseFrameRef("  L01_V001 1234  ")?.frameIdx).toBe(1234);
  });

  it("accepts frame zero", () => {
    expect(parseFrameRef("L01_V001-0")).toEqual({
      videoId: "L01_V001",
      frameIdx: 0,
    });
  });

  it.each([
    ["", "empty"],
    ["   ", "whitespace"],
    ["L01_V001", "no frame"],
    ["1234", "no video"],
    // Was ["X01_V001-5", "wrong prefix letter"]: X is an accepted batch letter
    // now (VIDEO_ID_PATTERN takes any A-Z), so the row uses a lowercase one,
    // which is still rejected.
    ["l01_V001-5", "lowercase prefix letter"],
    ["L1_V001-5", "short lab number"],
    ["L01_V1-5", "short video number"],
    ["L01_V001-abc", "frame is not a number"],
    ["L01_V001--", "separators only"],
    ["L01_V001-1-2-3", "too many parts"],
    ["L01_V001-1.5", "fractional frame"],
  ])("rejects %j (%s)", (input) => {
    expect(parseFrameRef(input)).toBeNull();
  });
});

describe("parseFrameRef with the new batch ids", () => {
  it("reads a new batch id with an underscore", () => {
    expect(parseFrameRef("M01_V001 1234")).toEqual({ videoId: "M01_V001", frameIdx: 1234 });
    expect(parseFrameRef("X01_V001-5")).toEqual({ videoId: "X01_V001", frameIdx: 5 });
  });

  it("reads a hyphenated id and keeps the hyphen in the video id", () => {
    expect(parseFrameRef("N001-V001 345")).toEqual({ videoId: "N001-V001", frameIdx: 345 });
    expect(parseFrameRef("S01-V001-7")).toEqual({ videoId: "S01-V001", frameIdx: 7 });
  });

  it("takes the frame, not the scene, from a hyphenated filename", () => {
    expect(parseFrameRef("N001-V001-0012-345.jpg")).toEqual({
      videoId: "N001-V001",
      frameIdx: 345,
    });
  });
});

// The parser as it was before the shared video id pattern, verbatim, to prove
// the change did not move anything for L and K ids.
function legacyParseFrameRef(input: string) {
  const VIDEO = /^[LK]\d{2}_V\d{3}/;
  const text = input.trim().replace(/\.[a-z]+$/i, "");
  const match = VIDEO.exec(text);
  if (!match) return null;
  const videoId = match[0];
  const rest = text.slice(videoId.length).replace(/^[\s\-_]+/, "");
  const parts = rest.split(/[\s\-_]+/).filter((part) => part !== "");
  if (parts.length === 0 || parts.length > 2) return null;
  if (!parts.every((part) => /^\d+$/.test(part))) return null;
  return { videoId, frameIdx: Number(parts[parts.length - 1]) };
}

describe("parseFrameRef on L and K ids", () => {
  it.each([
    "L01_V001 1234", "L01_V001-1234", "L01_V001_1234", "L25_V085-0086-30870.jpg",
    "L25_V085-0086-30870", "K19_V001-0000-29", "  L01_V001 1234  ", "L01_V001-0",
    "L01_V001 0012 004707", "K01_V003-0001-000025.jpg", "L26_V194.jpg", "L01_V001-1-2-3",
    "L01_V001-1.5", "L01_V001-abc", "L01_V001--", "L01_V1-5", "L1_V001-5", "1234", "",
    "L01_V001", "not a frame", "L01_V0011 5",
  ])("gives the same answer as before for %j", (input) => {
    expect(parseFrameRef(input)).toEqual(legacyParseFrameRef(input));
  });
});

describe("VIDEO_ID_PATTERN", () => {
  it.each(["L26_V194", "K01_V003", "M01_V001", "N001-V001", "S01-V001", "L260_V194"])(
    "accepts %j",
    (id) => expect(VIDEO_ID_PATTERN.test(id)).toBe(true)
  );

  it.each(["", "L1_V001", "L26_V19", "l26_v194", "L26_V1940", "L26V194", "L26_V194 ", "26_V194"])(
    "rejects %j",
    (id) => expect(VIDEO_ID_PATTERN.test(id)).toBe(false)
  );
});

describe("parseFrameName", () => {
  it.each([
    ["L25_V008-0116-36128.jpg", "L25_V008", "0116-36128", 116, 36128],
    ["K01_V001-0003-45.jpg", "K01_V001", "0003-45", 3, 45],
    ["M01_V001-0049-5059.jpg", "M01_V001", "0049-5059", 49, 5059],
    ["N001-V001-0012-345.jpg", "N001-V001", "0012-345", 12, 345],
    ["S01-V001-0001-7.jpg", "S01-V001", "0001-7", 1, 7],
  ])("takes %j apart", (name, videoId, frameId, sceneId, frameIdx) => {
    expect(parseFrameName(name)).toEqual({ videoId, frameId, sceneId, frameIdx });
  });

  it("keeps the zero padding of the frame in frameId", () => {
    expect(parseFrameName("L26_V194-0012-004707.jpg")).toEqual({
      videoId: "L26_V194",
      frameId: "0012-004707",
      sceneId: 12,
      frameIdx: 4707,
    });
  });

  it("reads a name without its extension", () => {
    expect(parseFrameName("M01_V001-0049-5059")?.frameIdx).toBe(5059);
    expect(parseFrameName("N001-V001-0012-345")?.videoId).toBe("N001-V001");
  });

  it("drops a directory part or a URL in front of the name", () => {
    expect(parseFrameName("/static/images/L25_V008-0116-36128.jpg")?.videoId).toBe("L25_V008");
    expect(
      parseFrameName("http://localhost:8000/static/images/N001-V001-0012-345.jpg")?.videoId
    ).toBe("N001-V001");
    expect(parseFrameName("C:\\imgs\\M01_V001-0049-5059.jpg")?.frameIdx).toBe(5059);
  });

  it("does not take a trailing number for an extension", () => {
    expect(parseFrameName("L25_V008-0116-36128")?.frameIdx).toBe(36128);
  });

  it.each([
    ["", "empty"],
    ["not-a-keyframe.jpg", "not a frame"],
    ["L25_V008", "a video id alone"],
    ["L25_V008-0116.jpg", "one number only"],
    ["L25_V008-abc-12.jpg", "scene is not a number"],
    ["L25_V008-0116-1.5.jpg", "fractional frame"],
    ["l25_v008-0116-36128.jpg", "lowercase video id"],
    ["X-1-2.jpg", "video id outside the pattern"],
    ["L25_V008-0116-36128-1.jpg", "one part too many, id would be L25_V008-0116"],
  ])("returns null for %j (%s)", (name) => {
    expect(parseFrameName(name)).toBeNull();
  });
});
