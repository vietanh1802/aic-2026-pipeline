// frontend/src/components/VideoPopUp/YoutubeTimeline.render.test.ts

/**
 * First render of the YouTube timeline (react-dom/server, no DOM). What matters
 * here is that the numbers on screen are the numbers DRES gets: the readout is
 * frameAt -> frameToMs, the same path DresPropose submits through.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import YoutubeTimeline from "./YoutubeTimeline";

type Props = Parameters<typeof YoutubeTimeline>[0];
const noop = () => undefined;

// M05_V019: 25 fps, YouTube kZ59hou1X3Y, 1123 s.
function render(overrides: Partial<Props> = {}): string {
  return renderToStaticMarkup(
    createElement(YoutubeTimeline, {
      info: { id: "kZ59hou1X3Y", length: 1123 },
      fps: 25,
      picked: null,
      onPick: noop,
      playerSeconds: 627.88,
      onSeekPlayer: noop,
      ...overrides,
    })
  );
}

describe("YoutubeTimeline", () => {
  it("follows the player until something is picked", () => {
    const html = render();
    expect(html).toContain("Chưa chọn — đang theo trình phát:");
    expect(html).toContain("10:27.880 · frame 15697 · 627880 ms");
    expect(html).toContain('href="https://www.youtube.com/watch?v=kZ59hou1X3Y&amp;t=627s"');
    expect(html).toContain("dài 18:43");
    expect(html).not.toContain("bỏ chọn");
  });

  it("shows the picked moment, snapped to a frame, and says DRES uses it", () => {
    // 600.01 s at 25 fps is frame 15000 -> 600000 ms: the ms is the frame's, not the raw pick.
    const html = render({ picked: 600.01 });
    expect(html).toContain("Đã chọn:");
    expect(html).toContain("frame 15000 · 600000 ms");
    expect(html).toContain("t=600s");
    expect(html).toContain("bỏ chọn");
    expect(html).toContain("Nộp DRES");
  });

  it("clamps to the YouTube length", () => {
    const html = render({ picked: 5000 });
    expect(html).toContain("18:43.000 · frame 28075 · 1123000 ms");
  });
});
