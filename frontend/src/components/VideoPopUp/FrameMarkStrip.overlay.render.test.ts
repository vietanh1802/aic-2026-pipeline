// frontend/src/components/VideoPopUp/FrameMarkStrip.overlay.render.test.ts

/**
 * The `barOverlay` slot of FrameMarkStrip, with react-dom/server. Kept apart from
 * FrameMarkStrip.render.test.ts, whose snapshots are the golden markup of the
 * strip without an overlay and must never be edited together with a change to it.
 *
 * The point of these tests: an overlay adds its own elements and one class on the
 * bar, and NOTHING else in the strip moves.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import FrameMarkStrip from "./FrameMarkStrip";

type Props = Parameters<typeof FrameMarkStrip>[0];

const noop = () => undefined;
const HEADROOM = " has-[[data-candidate-markers]]:mt-4";
const PROBE = '<i data-probe=""></i>';

function render(overrides: Partial<Props> = {}): string {
  return renderToStaticMarkup(
    createElement(FrameMarkStrip, {
      videoId: "L25_V014",
      currentSeconds: 100.5,
      duration: 1591,
      fps: 29.97,
      markIn: null,
      markOut: null,
      onMarkIn: noop,
      onMarkOut: noop,
      onClear: noop,
      onSeek: noop,
      ...overrides,
    })
  );
}

const probe = () => createElement("i", { "data-probe": "" });

// Scenes the golden test also covers, so "nothing else moved" is checked on each.
const SCENES: [string, Partial<Props>][] = [
  ["no marks", {}],
  ["in only", { markIn: 60 }],
  ["both marks, midpoint", { markIn: 50, markOut: 200 }],
  ["TRAKE, both marks (zoomed)", { markIn: 50, markOut: 200, currentSeconds: 120, submits: "playhead" }],
  ["TRAKE, one mark", { markIn: 60, submits: "playhead" }],
  ["no fps", { fps: 0, markIn: 50, markOut: 200 }],
  ["unknown duration", { duration: 0 }],
];

describe("FrameMarkStrip without an overlay", () => {
  it.each(SCENES)("does not change: %s", (_name, overrides) => {
    const plain = render(overrides);
    expect(render({ ...overrides, barOverlay: undefined })).toBe(plain);
    expect(plain).not.toContain("has-[");
    expect(plain).not.toContain("data-probe");
  });
});

describe("FrameMarkStrip with an overlay", () => {
  it.each(SCENES)("changes only the overlay and one class on the bar: %s", (_name, overrides) => {
    const plain = render(overrides);
    const withOverlay = render({ ...overrides, barOverlay: () => probe() });
    expect(withOverlay.replace(PROBE, "").replace(HEADROOM, "")).toBe(plain);
    expect(withOverlay).toContain(PROBE);
    expect(withOverlay).toContain(HEADROOM.trim());
  });

  it("changes nothing at all when the overlay renders nothing, but for the class", () => {
    const plain = render({ markIn: 50, markOut: 200 });
    const empty = render({ markIn: 50, markOut: 200, barOverlay: () => null });
    expect(empty.replace(HEADROOM, "")).toBe(plain);
  });

  it("puts the overlay first inside the bar, before the pinned block and the playhead", () => {
    const markup = render({ markIn: 50, markOut: 200, barOverlay: () => probe() });
    const bar = markup.indexOf('title="Bấm để tua">');
    const overlay = markup.indexOf(PROBE);
    const pinned = markup.indexOf("bg-proto-primary/70");
    const playhead = markup.indexOf("bg-proto-dark rounded");
    expect(bar).toBeGreaterThan(-1);
    // Immediately after the bar's opening tag, i.e. the FIRST child.
    expect(markup.slice(bar + 'title="Bấm để tua">'.length)).toMatch(/^<i data-probe=""><\/i>/);
    expect(overlay).toBeLessThan(pinned);
    expect(pinned).toBeLessThan(playhead);
  });

  it("keeps the click handler on the bar and adds none: the overlay is not a click target", () => {
    // Static markup carries no handlers, so this checks the structure: the overlay
    // sits INSIDE the element with the seek title, and the strip's buttons are the
    // same ones as without it.
    const plain = render({ markIn: 50, markOut: 200 });
    const withOverlay = render({ markIn: 50, markOut: 200, barOverlay: () => probe() });
    expect(withOverlay.match(/<button/g)).toHaveLength(plain.match(/<button/g)?.length ?? -1);
    expect(withOverlay.match(/title="Bấm để tua"/g)).toHaveLength(1);
  });

  it("calls the overlay with the whole-video scale on the normal bar", () => {
    const seen: { low: number; high: number }[] = [];
    render({ barOverlay: (scale) => (seen.push(scale), null) });
    expect(seen).toEqual([{ low: 0, high: 1591 }]);
  });

  it("calls it with the zoomed scale when a TRAKE popup has both ends pinned", () => {
    const seen: { low: number; high: number }[] = [];
    render({
      markIn: 50,
      markOut: 200,
      submits: "playhead",
      barOverlay: (scale) => (seen.push(scale), null),
    });
    expect(seen).toEqual([{ low: 50, high: 200 }]);
  });

  it("calls it with the whole-video scale for two pinned ends of a KIS popup (not zoomed)", () => {
    const seen: { low: number; high: number }[] = [];
    render({ markIn: 50, markOut: 200, barOverlay: (scale) => (seen.push(scale), null) });
    expect(seen).toEqual([{ low: 0, high: 1591 }]);
  });

  it("calls it with the 1 second fallback scale while the duration is unknown", () => {
    const seen: { low: number; high: number }[] = [];
    render({ duration: 0, barOverlay: (scale) => (seen.push(scale), null) });
    expect(seen).toEqual([{ low: 0, high: 1 }]);
  });
});
