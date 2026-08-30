// src/store/queryStore.ts
import { create } from "zustand";
import type { ModelName } from "../types/api";

export type QueryType = "text" | "image" | "audio";

// Mirrors the visual, multimodal, temporal, TRAKE, and OCR search routes.
// OCR is a pure lexical route; its diacritic option is independent of the
// multimodal Visual/Balanced/Speech emphasis.
export type SearchType =
  | "ensemble"
  | "single"
  | "multimodal"
  | "temporal"
  | "trake"
  | "ocr";

export type SearchEmphasis = "visual" | "balanced" | "speech";

export const SEARCH_EMPHASIS_WEIGHTS = {
  visual:   { visualWeight: 0.8, asrWeight: 0.2 },
  balanced: { visualWeight: 0.5, asrWeight: 0.5 },
  speech:   { visualWeight: 0.2, asrWeight: 0.8 },
} as const;

export type TranslateLanguage = "vi-en" | "en-vi";

export interface QueryStore {
  queryType: QueryType;
  setQueryType: (type: QueryType) => void;
  resultLimit: string;
  setResultLimit: (limit: string) => void;
  queryText: string;
  setQueryText: (text: string) => void;

  // ── Loại search: ensemble (BEiT3+CLIP) hoặc single (1 model) ──────────────
  searchType: SearchType;
  setSearchType: (type: SearchType) => void;
  searchEmphasis: SearchEmphasis;
  setSearchEmphasis: (emphasis: SearchEmphasis) => void;

  // Model dùng khi searchType === "single"
  singleModel: ModelName;
  setSingleModel: (model: ModelName) => void;

  // ── Tham số Alg.3 / Alg.2, khớp EnsembleSearchRequest/SingleSearchRequest ──
  topM: number; // top-M mỗi model trước khi gộp (paper dùng 50)
  setTopM: (topM: number) => void;
  useRerank: boolean; // bật Alg.2 rerank lân cận từng model trước ensemble
  setUseRerank: (value: boolean) => void;

  // ── OCR route ────────────────────────────────────────────────────────────
  // Strip diacritics from both the query and the corpus before comparing. ON
  // by default: Vintern most often misreads the diacritics themselves
  // (HỂ THAO ~ THỂ THAO, MỘT LÀNH ĐẠO ~ LÃNH ĐẠO), so stripping catches more.
  // Turn it off when an exact match is what you want.
  ocrStripDiacritics: boolean;
  setOcrStripDiacritics: (value: boolean) => void;

  // Translate — độc lập với backend, gọi thẳng Google Translate ở client
  translateLang: TranslateLanguage;
  setTranslateLang: (lang: TranslateLanguage) => void;
  queryTranslated: string;
  setQueryTranslated: (text: string) => void;
}

export const useQueryStore = create<QueryStore>((set) => ({
  queryType: "text",
  setQueryType: (type) => set({ queryType: type }),
  resultLimit: "100",
  setResultLimit: (limit) => set({ resultLimit: limit }),
  queryText: "",
  setQueryText: (text) => set({ queryText: text }),

  searchType: "ensemble",
  setSearchType: (type) => set({ searchType: type }),
  searchEmphasis: "balanced",
  setSearchEmphasis: (emphasis) => set({ searchEmphasis: emphasis }),
  singleModel: "beit3",
  setSingleModel: (model) => set({ singleModel: model }),

  topM: 50,
  setTopM: (topM) => set({ topM }),
  useRerank: true,
  setUseRerank: (value) => set({ useRerank: value }),

  ocrStripDiacritics: true,
  setOcrStripDiacritics: (value) => set({ ocrStripDiacritics: value }),

  translateLang: "en-vi",
  setTranslateLang: (lang) => set({ translateLang: lang }),
  queryTranslated: "",
  setQueryTranslated: (text) => set({ queryTranslated: text }),
}));

// NOTE: SearchResult/SearchState trùng lặp với store/useSearchStore.ts đã bị
// xóa khỏi file này — bản ở useSearchStore.ts mới là bản App.tsx thực sự dùng
// (App.tsx import useSearchStore từ "./store/useSearchStore", không phải từ
// đây). Giữ cả 2 định nghĩa trùng nhau trước đây là dead code gây nhầm lẫn.
