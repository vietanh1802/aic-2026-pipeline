import { describe, expect, it } from "vitest";

import { parseManualFrames } from "./manualAnswer";

describe("parseManualFrames", () => {
  it("reads a single frame for KIS and Q&A", () => {
    expect(parseManualFrames("1234", 1)).toEqual({ frames: [1234] });
  });

  it("reads a comma list for TRAKE", () => {
    expect(parseManualFrames("10,20,30", 3)).toEqual({ frames: [10, 20, 30] });
  });

  it("ignores spacing around the commas", () => {
    expect(parseManualFrames(" 10 , 20 ,30 ", 3)).toEqual({
      frames: [10, 20, 30],
    });
  });

  it("accepts frame zero", () => {
    expect(parseManualFrames("0", 1)).toEqual({ frames: [0] });
  });

  it("keeps the order typed, because that is the event order", () => {
    expect(parseManualFrames("300,100,200", 3)).toEqual({
      frames: [300, 100, 200],
    });
  });

  it("rejects too few frames for the event count", () => {
    expect(parseManualFrames("10,20", 3)).toEqual({
      error: "Cần đúng 3 mốc, đang có 2",
    });
  });

  it("rejects too many frames for the event count", () => {
    expect(parseManualFrames("10,20,30,40", 3)).toEqual({
      error: "Cần đúng 3 mốc, đang có 4",
    });
  });

  it("rejects an empty input", () => {
    expect(parseManualFrames("   ", 1)).toEqual({
      error: "Nhập ít nhất một số frame",
    });
  });

  it("rejects a negative frame", () => {
    expect(parseManualFrames("-5", 1)).toEqual({
      error: '"-5" không phải số nguyên không âm',
    });
  });

  it("rejects a fractional frame", () => {
    expect(parseManualFrames("12.5", 1)).toEqual({
      error: '"12.5" không phải số nguyên không âm',
    });
  });

  it("rejects anything that is not a number", () => {
    expect(parseManualFrames("abc", 1)).toEqual({
      error: '"abc" không phải số nguyên không âm',
    });
  });
});
