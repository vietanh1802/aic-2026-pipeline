// frontend/src/store/queryStore.test.ts

import { beforeEach, describe, expect, it } from "vitest";

import type { VideoAnnotation } from "../types/api";
import { useQueryStore } from "./queryStore";
import { useSearchStore } from "./useSearchStore";

const ANNOTATION: VideoAnnotation = {
  matched: true,
  score: 1,
  mode: "substring",
  asr: { match_frame: "L21_V001-0000-3.jpg", match_type: "exact", location: "here" },
  ocr: { match_frame: null, match_type: null, location: "none" },
};

// Both stores are singletons, so every test starts from the same clean state.
beforeEach(() => {
  useQueryStore.setState({
    asrFilter: "",
    asrFilterMode: "substring",
    ocrFilter: "",
    ocrFilterMode: "substring",
  });
  useSearchStore.setState({ videoAnnotations: { L21_V001: ANNOTATION } });
});

function filterState() {
  const { asrFilter, asrFilterMode, ocrFilter, ocrFilterMode } = useQueryStore.getState();
  return { asrFilter, asrFilterMode, ocrFilter, ocrFilterMode };
}

describe("text filter defaults", () => {
  it("has two empty filters, both in substring mode", () => {
    expect(filterState()).toEqual({
      asrFilter: "",
      asrFilterMode: "substring",
      ocrFilter: "",
      ocrFilterMode: "substring",
    });
  });
});

describe("text filter setters clear the annotations at once and touch only their own field", () => {
  it("setAsrFilter", () => {
    useQueryStore.getState().setAsrFilter("ngò");
    expect(useSearchStore.getState().videoAnnotations).toBeNull();
    expect(filterState()).toEqual({
      asrFilter: "ngò",
      asrFilterMode: "substring",
      ocrFilter: "",
      ocrFilterMode: "substring",
    });
  });

  it("setAsrFilterMode", () => {
    useQueryStore.getState().setAsrFilterMode("bm25");
    expect(useSearchStore.getState().videoAnnotations).toBeNull();
    expect(filterState()).toEqual({
      asrFilter: "",
      asrFilterMode: "bm25",
      ocrFilter: "",
      ocrFilterMode: "substring",
    });
  });

  it("setOcrFilter", () => {
    useQueryStore.getState().setOcrFilter("2018");
    expect(useSearchStore.getState().videoAnnotations).toBeNull();
    expect(filterState()).toEqual({
      asrFilter: "",
      asrFilterMode: "substring",
      ocrFilter: "2018",
      ocrFilterMode: "substring",
    });
  });

  it("setOcrFilterMode", () => {
    useQueryStore.getState().setOcrFilterMode("regex");
    expect(useSearchStore.getState().videoAnnotations).toBeNull();
    expect(filterState()).toEqual({
      asrFilter: "",
      asrFilterMode: "substring",
      ocrFilter: "",
      ocrFilterMode: "regex",
    });
  });

  it("editing one filter leaves the other filter and its mode alone", () => {
    const { setAsrFilter, setAsrFilterMode, setOcrFilter, setOcrFilterMode } =
      useQueryStore.getState();
    setAsrFilterMode("bm25");
    setAsrFilter("thì hiện tại");
    setOcrFilterMode("regex");
    setOcrFilter("ngh[eê]u");
    setAsrFilter("");
    expect(filterState()).toEqual({
      asrFilter: "",
      asrFilterMode: "bm25",
      ocrFilter: "ngh[eê]u",
      ocrFilterMode: "regex",
    });
  });
});
