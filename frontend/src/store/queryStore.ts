// src/store/queryStore.ts
import { create } from "zustand";
import type { ModelName } from "../types/api";
import { useSearchStore } from "./useSearchStore";

export type QueryType = "text" | "image" | "audio";

// Mirrors the backend's real endpoints: /ensemble-search (full Alg.3),
// /single-search (one model, for Q4), /temporal-search-text (Alg.4, one input
// split on "."), /trake-search-text (N sequential events, split the same way),
// /ocr-search (text on screen).
//
// "ocr" is the PURE LEXICAL route: no model takes part and its scores are not
// blended with the visual route - see the app/ocr_search.py docstring. It
// therefore ignores topM/useRerank/model entirely and uses only resultLimit
// plus the "strip diacritics" checkbox below.
// (text-search/faiss-search/combined-search remain gone.)
export type SearchType = "ensemble" | "single" | "temporal" | "trake" | "ocr";

export type TranslateLanguage = "vi-en" | "en-vi";

// Matches backend's TextMatchMode (backend/app/text_signal.py). Only applies
// to /ensemble-search — see EnsembleSearchRequest.text_filter_mode.
export type TextFilterMode = "substring" | "regex" | "bm25";

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

  // ── Text-signal filter (ASR/OCR annotation, /ensemble-search only) ────────
  // Purely additive metadata on the results — never drops a frame. Empty
  // string disables it, matching the backend's own default.
  textFilter: string;
  setTextFilter: (value: string) => void;
  textFilterMode: TextFilterMode;
  setTextFilterMode: (mode: TextFilterMode) => void;
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
  singleModel: "beit3",
  setSingleModel: (model) => set({ singleModel: model }),

  topM: 50,
  setTopM: (topM) => set({ topM }),
  useRerank: true,
  setUseRerank: (value) => set({ useRerank: value }),

  ocrStripDiacritics: true,
  setOcrStripDiacritics: (value) => set({ ocrStripDiacritics: value }),

  // vi-en, không phải en-vi.
  //
  // Cả nhóm gõ tiếng Việt, còn BEiT3 và CLIP chỉ hiểu tiếng Anh — nên chiều
  // duy nhất giúp tìm được gì là Việt sang Anh. Chiều ngược lại chỉ để đọc
  // lại một câu vừa dịch, việc hiếm khi làm giữa lúc thi.
  //
  // Mặc định cũ là "en-vi", và store này không lưu xuống localStorage: đổi
  // sang vi-en xong tải lại trang là nó quay về, nên mỗi phiên lại phải đổi
  // tay một lần trước khi bấm Translate được.
  translateLang: "vi-en",
  setTranslateLang: (lang) => set({ translateLang: lang }),
  queryTranslated: "",
  setQueryTranslated: (text) => set({ queryTranslated: text }),

  textFilter: "",
  setTextFilter: (value) => {
    set({ textFilter: value });
    // Badges on screen describe the PREVIOUS filter query — clear them so
    // they never linger next to a field the user has since edited.
    useSearchStore.getState().setVideoAnnotations(null);
  },
  textFilterMode: "substring",
  setTextFilterMode: (mode) => {
    set({ textFilterMode: mode });
    useSearchStore.getState().setVideoAnnotations(null);
  },
}));

// NOTE: SearchResult/SearchState trùng lặp với store/useSearchStore.ts đã bị
// xóa khỏi file này — bản ở useSearchStore.ts mới là bản App.tsx thực sự dùng
// (App.tsx import useSearchStore từ "./store/useSearchStore", không phải từ
// đây). Giữ cả 2 định nghĩa trùng nhau trước đây là dead code gây nhầm lẫn.