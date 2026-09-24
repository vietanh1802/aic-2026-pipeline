// frontend/src/store/searchedSources.test.ts

/**
 * The searched-sources snapshot that lives next to the annotations in
 * useSearchStore. It exists because the live filter boxes cannot say which
 * sources ran: they can be edited while a search is in flight (last test).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { sourcesSearched } from "../helpers/textSignalView";
import type { VideoAnnotation } from "../types/api";
import { useQueryStore } from "./queryStore";
import { useSearchStore } from "./useSearchStore";

const NONE = { match_frame: null, match_type: null, location: "none" } as const;
const ANNOTATIONS: Record<string, VideoAnnotation> = {
  L21_V001: { matched: false, score: 0, mode: "substring", asr: NONE, ocr: NONE },
};

beforeEach(() => {
  useQueryStore.setState({
    asrFilter: "",
    asrFilterMode: "substring",
    ocrFilter: "",
    ocrFilterMode: "substring",
  });
  useSearchStore.setState({ videoAnnotations: null, searchedSources: null });
});

const state = () => useSearchStore.getState();

describe("searchedSources in useSearchStore", () => {
  it("starts as null", () => {
    expect(state().searchedSources).toBeNull();
  });

  it("is stored together with the annotations", () => {
    state().setVideoAnnotations(ANNOTATIONS, { asr: true, ocr: false });
    expect(state().videoAnnotations).toBe(ANNOTATIONS);
    expect(state().searchedSources).toEqual({ asr: true, ocr: false });
  });

  it("is null when the caller gives none: the old one-argument call still works", () => {
    state().setVideoAnnotations(ANNOTATIONS);
    expect(state().videoAnnotations).toBe(ANNOTATIONS);
    expect(state().searchedSources).toBeNull();
  });

  it("is cleared with the annotations", () => {
    state().setVideoAnnotations(ANNOTATIONS, { asr: true, ocr: true });
    state().setVideoAnnotations(null);
    expect(state().videoAnnotations).toBeNull();
    expect(state().searchedSources).toBeNull();
  });

  it("is never kept without annotations, even when a value is passed", () => {
    state().setVideoAnnotations(null, { asr: true, ocr: true });
    expect(state().searchedSources).toBeNull();
  });

  it("is replaced by the next search's own value", () => {
    state().setVideoAnnotations(ANNOTATIONS, { asr: true, ocr: false });
    state().setVideoAnnotations(ANNOTATIONS, { asr: false, ocr: true });
    expect(state().searchedSources).toEqual({ asr: false, ocr: true });
  });
});

describe("every filter setter clears it with the annotations", () => {
  const setters = [
    ["setAsrFilter", "lửa"],
    ["setAsrFilterMode", "bm25"],
    ["setOcrFilter", "2018"],
    ["setOcrFilterMode", "regex"],
  ] as const;

  it.each(setters)("%s", (name, value) => {
    state().setVideoAnnotations(ANNOTATIONS, { asr: true, ocr: true });
    (useQueryStore.getState()[name] as (value: string) => void)(value);
    expect(state().videoAnnotations).toBeNull();
    expect(state().searchedSources).toBeNull();
  });
});

describe("why the live filter fields are not used for it", () => {
  it("a box edited mid-search leaves the response's snapshot describing the search that ran", () => {
    // doSearch snapshots the fields, sends them, and waits...
    useQueryStore.setState({ asrFilter: "lửa", ocrFilter: "" });
    const snapshot = sourcesSearched(useQueryStore.getState());

    // ...the user fills the OCR box while it runs (the setter clears annotations)...
    useQueryStore.getState().setOcrFilter("2018");
    expect(state().videoAnnotations).toBeNull();

    // ...and the response, built from the ASR-only request, is stored afterwards.
    state().setVideoAnnotations(ANNOTATIONS, snapshot);

    // The live boxes now say both were filled; only the snapshot is right.
    expect(sourcesSearched(useQueryStore.getState())).toEqual({ asr: true, ocr: true });
    expect(state().searchedSources).toEqual({ asr: true, ocr: false });
  });
});
