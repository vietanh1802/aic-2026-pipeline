// frontend/src/components/VideoPopUp/VideoPopUp.seek.render.test.ts

/**
 * The seek callback the popup hands to FrameMarkStrip (a click on the lower bar
 * or on one of its three frame previews).
 *
 * The strip, the candidate strip and the player are replaced by stand-ins so the
 * popup's own callback can be reached and called. LIMIT: this runs on the server
 * renderer, where a state setter called after the render is a no-op, so it can
 * prove that the target VALUE still moves (setStartAt gets milliseconds) and that
 * the new request line does not throw - it cannot observe the seek request
 * itself, nor that a second click on the same spot moves the player. That is what
 * the manual checklist covers. The request object (nextSeekRequest) has its own
 * tests in seekRequest.test.ts.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => ({
  onSeek: null as null | ((seconds: number) => void),
}));
vi.mock("./FrameMarkStrip", () => ({
  default: (props: { onSeek: (seconds: number) => void }) => {
    captured.onSeek = props.onSeek;
    return null;
  },
}));
vi.mock("./CandidateStrip", () => ({ default: () => null }));
vi.mock("./VideoDisplay", () => ({ default: () => null }));

import VideoPopup from "./index";

const setStartAt = vi.fn();

function renderPopup() {
  renderToStaticMarkup(
    createElement(VideoPopup, {
      videoId: "L25_V014",
      frameId: "0046-2837",
      startAt: 94000,
      onClose: () => undefined,
      setStartAt,
    })
  );
}

beforeEach(() => {
  setStartAt.mockClear();
  captured.onSeek = null;
});

describe("the popup's seek callback for the lower bar", () => {
  it("is handed to FrameMarkStrip", () => {
    renderPopup();
    expect(typeof captured.onSeek).toBe("function");
  });

  it("still moves the target value, in milliseconds", () => {
    renderPopup();
    captured.onSeek?.(12.5);
    expect(setStartAt).toHaveBeenCalledTimes(1);
    expect(setStartAt).toHaveBeenCalledWith(12500);
  });

  it("does not throw on the edge values a click can produce", () => {
    renderPopup();
    for (const seconds of [0, 1591, 0.001, 794.7]) {
      expect(() => captured.onSeek?.(seconds)).not.toThrow();
    }
    expect(setStartAt).toHaveBeenCalledTimes(4);
    expect(setStartAt).toHaveBeenLastCalledWith(794700);
  });
});
