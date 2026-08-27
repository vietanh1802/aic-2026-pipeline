import { describe, expect, it } from "vitest";

import { splitQueryParts } from "./candidates";
import { taskBriefText, taskQueryForSearch } from "./taskBrief";

describe("taskBriefText", () => {
  it("returns the prose for a KIS task", () => {
    expect(
      taskBriefText({
        type: "kis",
        query_text: "Tìm cảnh người đàn ông mặc áo đỏ",
        event_labels: [],
      })
    ).toBe("Tìm cảnh người đàn ông mặc áo đỏ");
  });

  it("joins the event labels for a TRAKE task with empty query_text", () => {
    expect(
      taskBriefText({
        type: "trake",
        query_text: "",
        event_labels: ["Người mở cửa", "Người bước vào", "Người ngồi xuống"],
      })
    ).toBe(
      "E1 · Người mở cửa → E2 · Người bước vào → E3 · Người ngồi xuống"
    );
  });

  it("prefers prose over labels when a TRAKE task unusually has both", () => {
    expect(
      taskBriefText({
        type: "trake",
        query_text: "Đề bài có sẵn văn bản",
        event_labels: ["Người mở cửa", "Người bước vào"],
      })
    ).toBe("Đề bài có sẵn văn bản");
  });

  it("returns an empty string when there is neither prose nor labels", () => {
    expect(
      taskBriefText({
        type: "trake",
        query_text: "",
        event_labels: [],
      })
    ).toBe("");
  });

  it("returns an empty string for a non-TRAKE task with empty query_text", () => {
    expect(
      taskBriefText({
        type: "qa",
        query_text: "",
        event_labels: [],
      })
    ).toBe("");
  });

  it("handles a TRAKE task with exactly one label", () => {
    expect(
      taskBriefText({
        type: "trake",
        query_text: "",
        event_labels: ["Người mở cửa"],
      })
    ).toBe("E1 · Người mở cửa");
  });
});

describe("taskQueryForSearch", () => {
  it("collapses whitespace in a prose brief", () => {
    expect(
      taskQueryForSearch({
        type: "kis",
        query_text: "  Hai người   phụ nữ\n cho dê ăn  ",
        event_labels: [],
      })
    ).toBe("Hai người phụ nữ cho dê ăn");
  });

  // The property that matters: what this produces must split back into exactly
  // n_events parts, because that is how E1..EN line up with the backend's
  // event list. The display form's " → " separator would give one part.
  it("round-trips through splitQueryParts to one part per event", () => {
    const labels = ["Người mở cửa", "Xe dừng lại", "Hai người bắt tay"];
    const query = taskQueryForSearch({
      type: "trake",
      query_text: "",
      event_labels: labels,
    });
    expect(splitQueryParts(query)).toEqual(labels);
  });

  it("does not produce an empty part when a label already ends in a period", () => {
    const labels = ["Người mở cửa.", "Xe dừng lại."];
    const query = taskQueryForSearch({
      type: "trake",
      query_text: "",
      event_labels: labels,
    });
    expect(splitQueryParts(query)).toEqual(["Người mở cửa", "Xe dừng lại"]);
  });

  it("keeps the display form and the search form distinct", () => {
    const task = {
      type: "trake" as const,
      query_text: "",
      event_labels: ["Một", "Hai"],
    };
    expect(taskBriefText(task)).toBe("E1 · Một → E2 · Hai");
    expect(taskQueryForSearch(task)).toBe("Một. Hai");
  });

  it("returns an empty string when there is nothing to search for", () => {
    expect(
      taskQueryForSearch({ type: "trake", query_text: "", event_labels: [] })
    ).toBe("");
  });
});
