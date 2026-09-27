// frontend/src/helpers/textFilter.test.ts

import { describe, expect, it } from "vitest";

import {
  buildTextFilterParams,
  describeTextFilter,
  hasTextFilter,
  type TextFilterFields,
} from "./textFilter";

function fields(overrides: Partial<TextFilterFields> = {}): TextFilterFields {
  return {
    asrFilter: "",
    asrFilterMode: "substring",
    ocrFilter: "",
    ocrFilterMode: "substring",
    ...overrides,
  };
}

describe("hasTextFilter", () => {
  it("is false for empty and whitespace-only filters", () => {
    expect(hasTextFilter(fields())).toBe(false);
    expect(hasTextFilter(fields({ asrFilter: "   ", ocrFilter: "\t \n" }))).toBe(false);
  });

  it("is true when either source has text", () => {
    expect(hasTextFilter(fields({ asrFilter: "ngò" }))).toBe(true);
    expect(hasTextFilter(fields({ ocrFilter: "QUÁN TRỌ" }))).toBe(true);
  });
});

describe("buildTextFilterParams", () => {
  it("sends empty strings and both modes when nothing is set", () => {
    expect(buildTextFilterParams(fields())).toEqual({
      asr_filter: "",
      asr_filter_mode: "substring",
      ocr_filter: "",
      ocr_filter_mode: "substring",
    });
  });

  it("trims each string and keeps the mode of each source", () => {
    expect(
      buildTextFilterParams(
        fields({
          asrFilter: "  thì hiện tại  ",
          asrFilterMode: "bm25",
          ocrFilter: "\tngh[eê]u ",
          ocrFilterMode: "regex",
        })
      )
    ).toEqual({
      asr_filter: "thì hiện tại",
      asr_filter_mode: "bm25",
      ocr_filter: "ngh[eê]u",
      ocr_filter_mode: "regex",
    });
  });

  it("with one source only, the other stays empty for the backend to ignore", () => {
    const params = buildTextFilterParams(fields({ ocrFilter: "2018" }));
    expect(params.asr_filter).toBe("");
    expect(params.ocr_filter).toBe("2018");
  });

  it("never sends the legacy single-filter fields", () => {
    expect(Object.keys(buildTextFilterParams(fields({ asrFilter: "x" }))).sort()).toEqual([
      "asr_filter",
      "asr_filter_mode",
      "ocr_filter",
      "ocr_filter_mode",
    ]);
  });
});

describe("describeTextFilter", () => {
  it("is empty when no filter is set", () => {
    expect(describeTextFilter(fields())).toEqual({ mode: "", term: "" });
    expect(describeTextFilter(fields({ asrFilter: "  ", ocrFilter: " " }))).toEqual({
      mode: "",
      term: "",
    });
  });

  it("names the ASR source, its mode and its term when only ASR is active", () => {
    expect(describeTextFilter(fields({ asrFilter: " ngò ", asrFilterMode: "bm25" }))).toEqual({
      mode: "ASR bm25",
      term: "ngò",
    });
  });

  it("names the OCR source, its mode and its term when only OCR is active", () => {
    expect(describeTextFilter(fields({ ocrFilter: "ngh[eê]u", ocrFilterMode: "regex" }))).toEqual({
      mode: "OCR regex",
      term: "ngh[eê]u",
    });
  });

  it("joins both sources when both are active", () => {
    expect(
      describeTextFilter(
        fields({
          asrFilter: "thịt bò",
          asrFilterMode: "bm25",
          ocrFilter: "nghêu",
          ocrFilterMode: "substring",
        })
      )
    ).toEqual({
      mode: "ASR bm25 · OCR substring",
      term: "ASR: thịt bò | OCR: nghêu",
    });
  });
});
