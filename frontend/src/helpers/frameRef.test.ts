import { describe, expect, it } from "vitest";

import { parseFrameRef } from "./frameRef";

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
    ["X01_V001-5", "wrong prefix letter"],
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
