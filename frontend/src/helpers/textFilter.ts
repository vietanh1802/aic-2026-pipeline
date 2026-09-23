// frontend/src/helpers/textFilter.ts
//
// Pure helpers for the two independent text filters (ASR and OCR). The search
// request and the popover badge both need the same reading of the store's four
// filter fields, so it lives here instead of being repeated in App.tsx and
// FrameDisplay, and it can be tested without a browser.

import type {
  AsrFilterMode,
  OcrFilterMode,
  TextFilterRequestFields,
} from "../types/api";

/** The four store fields that describe the text filters. */
export interface TextFilterFields {
  asrFilter: string;
  asrFilterMode: AsrFilterMode;
  ocrFilter: string;
  ocrFilterMode: OcrFilterMode;
}

/**
 * True when at least one filter has text. A blank filter counts as empty,
 * like on the backend (it strips before deciding a filter is active).
 */
export function hasTextFilter(fields: TextFilterFields): boolean {
  return fields.asrFilter.trim() !== "" || fields.ocrFilter.trim() !== "";
}

/**
 * The four request fields for /ensemble-search, with trimmed strings. An empty
 * source is sent as "" (plus its mode), which the backend reads as inactive.
 * Callers send these only when hasTextFilter() is true.
 */
export function buildTextFilterParams(
  fields: TextFilterFields
): Required<TextFilterRequestFields> {
  return {
    asr_filter: fields.asrFilter.trim(),
    asr_filter_mode: fields.asrFilterMode,
    ocr_filter: fields.ocrFilter.trim(),
    ocr_filter_mode: fields.ocrFilterMode,
  };
}

/**
 * The mode and term strings the badge popover already knows how to show
 * ("Mode: {mode} · "{term}""). Same idea as the backend's mode label:
 *   one source active  -> that source and its mode, and its term
 *   both active        -> both modes ("ASR bm25 · OCR substring") and both
 *                         terms ("ASR: x | OCR: y")
 *   none               -> empty strings
 */
export function describeTextFilter(fields: TextFilterFields): {
  mode: string;
  term: string;
} {
  const asr = fields.asrFilter.trim();
  const ocr = fields.ocrFilter.trim();
  if (asr && ocr) {
    return {
      mode: `ASR ${fields.asrFilterMode} · OCR ${fields.ocrFilterMode}`,
      term: `ASR: ${asr} | OCR: ${ocr}`,
    };
  }
  if (asr) return { mode: `ASR ${fields.asrFilterMode}`, term: asr };
  if (ocr) return { mode: `OCR ${fields.ocrFilterMode}`, term: ocr };
  return { mode: "", term: "" };
}
