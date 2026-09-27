import { describe, expect, it } from "vitest";

import { formatClock, parseClock, youtubeOf, youtubeUrlAt } from "./youtube";

describe("youtubeOf", () => {
  it("knows L, M and S videos by their local ids", () => {
    expect(youtubeOf("L21_V001")).toEqual({ id: "Rzpw5WR7nAY", length: 1262 });
    expect(youtubeOf("M05_V019")?.id).toBe("kZ59hou1X3Y");
    // media-info đặt S01_V001; video của mình là S01-V001.
    expect(youtubeOf("S01-V001")?.id).toBe("kfE6yVr6dnA");
  });

  it("has nothing for N, for S01-V005 (wrong link in media-info), or unknown ids", () => {
    expect(youtubeOf("N001-V001")).toBeNull();
    expect(youtubeOf("S01-V005")).toBeNull();
    expect(youtubeOf("S01_V001")).toBeNull();
    expect(youtubeOf("")).toBeNull();
  });
});

describe("youtubeUrlAt", () => {
  it("floors to whole seconds", () => {
    expect(youtubeUrlAt("kZ59hou1X3Y", 627.88)).toBe("https://www.youtube.com/watch?v=kZ59hou1X3Y&t=627s");
    expect(youtubeUrlAt("kZ59hou1X3Y", -3)).toBe("https://www.youtube.com/watch?v=kZ59hou1X3Y&t=0s");
  });
});

describe("parseClock", () => {
  it.each([
    ["10:27", 627],
    ["10:27.88", 627.88],
    ["10:27,88", 627.88],
    ["1:02:03", 3723],
    ["0:05", 5],
    ["627.88", 627.88],
    ["  9:05 ", 545],
  ])("reads %s", (text, seconds) => {
    expect(parseClock(text)).toBeCloseTo(seconds, 6);
  });

  it.each(["", "abc", "10:75", "1:75:00", "10::27", "-5", "1:2:3:4"])("rejects %j", (text) => {
    expect(parseClock(text)).toBeNull();
  });
});

describe("formatClock", () => {
  it("prints like YouTube plus milliseconds", () => {
    expect(formatClock(627.88)).toBe("10:27.880");
    expect(formatClock(3723.5)).toBe("1:02:03.500");
    expect(formatClock(0)).toBe("0:00.000");
  });

  it("round-trips through parseClock", () => {
    for (const s of [0, 1.25, 59.999, 627.88, 3723.5, 17795]) {
      expect(parseClock(formatClock(s))).toBeCloseTo(s, 3);
    }
  });
});
