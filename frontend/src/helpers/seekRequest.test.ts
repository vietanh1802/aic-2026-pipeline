// frontend/src/helpers/seekRequest.test.ts

import { describe, expect, it } from "vitest";

import { needsSeek, nextSeekRequest } from "./seekRequest";

describe("nextSeekRequest", () => {
  it("starts at id 1", () => {
    expect(nextSeekRequest(null, 100)).toEqual({ timeS: 100, id: 1 });
  });

  it("makes two requests of the same target: the second is a new object with a new id", () => {
    const first = nextSeekRequest(null, 98.365);
    const second = nextSeekRequest(first, 98.365);
    // The consuming effect runs on the object, so this is what makes a second
    // press on the same block do something.
    expect(second).not.toBe(first);
    expect(second.id).toBe(first.id + 1);
    expect(second.timeS).toBe(first.timeS);
  });

  it("keeps counting across different targets", () => {
    let request = nextSeekRequest(null, 10);
    for (const target of [20, 20, 30, 10]) {
      request = nextSeekRequest(request, target);
    }
    expect(request).toEqual({ timeS: 10, id: 5 });
  });

  it("does not change the request it was given", () => {
    const first = nextSeekRequest(null, 50);
    nextSeekRequest(first, 60);
    expect(first).toEqual({ timeS: 50, id: 1 });
  });
});

describe("needsSeek", () => {
  it("is false when the player is already on the target", () => {
    expect(needsSeek(98.365, 98.365, 29.97)).toBe(false);
  });

  it("is false within half a frame and true beyond it", () => {
    // 25 fps: a frame is 0.04 s, half of it 0.02 s.
    expect(needsSeek(100.019, 100, 25)).toBe(false);
    expect(needsSeek(100.021, 100, 25)).toBe(true);
    expect(needsSeek(99.981, 100, 25)).toBe(false);
    expect(needsSeek(99.97, 100, 25)).toBe(true);
  });

  it("is true again after the user scrubbed away, for the SAME target", () => {
    // Press a block (target 98.365, player was at 0), scrub to 300 s, press it again.
    expect(needsSeek(0, 98.365, 29.97)).toBe(true);
    expect(needsSeek(98.365, 98.365, 29.97)).toBe(false);
    expect(needsSeek(300, 98.365, 29.97)).toBe(true);
  });

  it("falls back to 25 fps when the fps is unknown", () => {
    expect(needsSeek(100.019, 100, 0)).toBe(false);
    expect(needsSeek(100.03, 100, 0)).toBe(true);
    expect(needsSeek(100.03, 100, Number.NaN)).toBe(true);
  });
});
