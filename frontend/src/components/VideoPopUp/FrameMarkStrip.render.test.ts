// frontend/src/components/VideoPopUp/FrameMarkStrip.render.test.ts

/**
 * Golden markup of FrameMarkStrip, rendered to a string with react-dom/server
 * (vitest runs in node, no DOM), taken BEFORE the candidate markers were added.
 *
 * The strip is where a team member reads and sets the frame that gets submitted:
 * the marks (Dau, Cuoi, clear), the readouts, the submit number, the bar's
 * geometry. Every later change to it has to leave this markup byte-identical
 * when nothing new is passed in, so these snapshots are the safety net and must
 * not be edited together with a change to the component. A tag boundary is
 * written as a line break only to make a diff readable; nothing else is
 * normalised.
 *
 * Only the first render is visible: effects (the I and O keys), clicks and the
 * "xem 3 khung" toggle do not run, so the three-frame panel (closed by default)
 * is not covered here.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import FrameMarkStrip from "./FrameMarkStrip";

type Props = Parameters<typeof FrameMarkStrip>[0];

const noop = () => undefined;

// L25_V014 is 29.97 fps and 1591 s long.
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

const pretty = (markup: string) => markup.replace(/></g, ">\n<");

describe("FrameMarkStrip markup, no overlay", () => {
  it("has no marks: playhead only, no clear button", () => {
    expect(pretty(render())).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-muted">3011</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-muted">3011</b>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">3011</b>
      </span>
      </div>
      </div>"
    `);
  });

  it("has only the in mark set", () => {
    expect(pretty(render({ markIn: 60 }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute inset-y-0 bg-proto-primary/70 rounded-full" style="left:3.7712130735386546%;width:2.5455688246385924%">
      </div>
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-ink">1798</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-muted">3011</b>
      </span>
      <button type="button" class="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted">xem 3 khung</button>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">2404</b>
      </span>
      </div>
      </div>"
    `);
  });

  it("has only the out mark set", () => {
    expect(pretty(render({ markOut: 150 }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute inset-y-0 bg-proto-primary/70 rounded-full" style="left:6.316781898177247%;width:3.111250785669391%">
      </div>
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-muted">3011</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-ink">4495</b>
      </span>
      <button type="button" class="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted">xem 3 khung</button>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">3753</b>
      </span>
      </div>
      </div>"
    `);
  });

  it("has both marks (KIS / Q&A): the in/out block and the midpoint as the submit number", () => {
    expect(pretty(render({ markIn: 50, markOut: 200 }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute inset-y-0 bg-proto-primary/70 rounded-full" style="left:3.142677561282212%;width:9.428032683846638%">
      </div>
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-ink">1498</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-ink">5994</b>
      </span>
      <button type="button" class="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted">xem 3 khung</button>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">3746</b>
      </span>
      </div>
      </div>"
    `);
  });

  it("has both marks on the same instant: nothing to compare", () => {
    expect(pretty(render({ markIn: 100, markOut: 100 }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute inset-y-0 bg-proto-primary/70 rounded-full" style="left:6.285355122564424%;width:0%">
      </div>
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-ink">2997</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-ink">2997</b>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">2997</b>
      </span>
      </div>
      </div>"
    `);
  });

  it("is a TRAKE popup with both marks: the bar is zoomed to the range", () => {
    expect(
      pretty(render({ markIn: 50, markOut: 200, currentSeconds: 120, submits: "playhead" }))
    ).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3596</b> <span class="font-mono">02:00.000</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <p class="text-[11px] text-proto-primary-active mb-1.5">Đã ghim xong hai đầu — thanh dưới giờ chỉ còn đoạn này. Bấm để chọn đúng khung sẽ nộp, hoặc <b>bỏ ghim</b> để xem lại cả video.</p>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-primary/25" title="Bấm để chọn khung trong đoạn">
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:46.666666666666664%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-ink">1498</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-ink">5994</b>
      </span>
      <button type="button" class="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted">xem 3 khung</button>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">3596</b>
      <span class="text-[10.5px] text-proto-muted" title="TRAKE chấm từng mốc trong một cửa sổ hẹp. Hai đầu ghim ở đây đi vào ô từ/đến của Điền tự động trong giỏ.">khung đang đứng</span>
      </span>
      </div>
      </div>"
    `);
  });

  it("is a TRAKE popup with one mark: not zoomed, the submit number is the playhead", () => {
    expect(pretty(render({ markIn: 60, submits: "playhead" }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute inset-y-0 bg-proto-primary/70 rounded-full" style="left:3.7712130735386546%;width:2.5455688246385924%">
      </div>
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-ink">1798</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-muted">3011</b>
      </span>
      <button type="button" class="text-[11.5px] font-semibold text-proto-primary-active underline decoration-dotted">xem 3 khung</button>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">3011</b>
      <span class="text-[10.5px] text-proto-muted" title="TRAKE chấm từng mốc trong một cửa sổ hẹp. Hai đầu ghim ở đây đi vào ô từ/đến của Điền tự động trong giỏ.">khung đang đứng</span>
      </span>
      </div>
      </div>"
    `);
  });

  it("has no fps for the video: a warning instead of frame numbers", () => {
    expect(pretty(render({ fps: 0, markIn: 50, markOut: 200 }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">—</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      <button type="button" class="text-[11.5px] text-proto-muted underline">bỏ ghim</button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute inset-y-0 bg-proto-primary/70 rounded-full" style="left:3.142677561282212%;width:9.428032683846638%">
      </div>
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:6.316781898177247%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-ink">—</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-ink">—</b>
      </span>
      <span class="ml-auto text-[#c64545]">Thiếu fps cho video này — không tính được frame.</span>
      </div>
      </div>"
    `);
  });

  it("does not know the duration yet: the bar scale falls back to 1 second", () => {
    expect(pretty(render({ duration: 0 }))).toMatchInlineSnapshot(`
      "<div class="mt-2 px-3 py-2.5 rounded-[10px] bg-proto-soft border border-proto-line font-baloo">
      <div class="flex items-center gap-3 flex-wrap mb-2">
      <span class="text-[12px] text-proto-muted">Khung hiện tại <b class="font-mono text-proto-ink text-[15px]">3011</b> <span class="font-mono">01:40.500</span>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">⇤ Đầu <span class="text-proto-muted font-normal">I</span>
      </button>
      <button type="button" class="px-2.5 py-1 rounded-[7px] border border-proto-line bg-white text-[12px] font-bold text-proto-ink hover:border-proto-primary">Cuối ⇥ <span class="text-proto-muted font-normal">O</span>
      </button>
      </span>
      </div>
      <div class="relative h-2.5 rounded-full cursor-pointer mb-2 bg-proto-line" title="Bấm để tua">
      <div class="absolute -top-1 -bottom-1 w-[2px] bg-proto-dark rounded" style="left:100%">
      </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap text-[12px]">
      <span class="text-proto-muted">đầu <b class="font-mono text-proto-muted">3011</b>
      </span>
      <span class="text-proto-muted">cuối <b class="font-mono text-proto-muted">3011</b>
      </span>
      <span class="ml-auto flex items-center gap-2">
      <span class="text-[10px] font-bold uppercase tracking-wide text-proto-muted">Nộp</span>
      <b class="font-mono text-[18px] leading-none text-proto-primary-active">3011</b>
      </span>
      </div>
      </div>"
    `);
  });
});
