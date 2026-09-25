// src/store/queryStore.ts
import { create } from "zustand";
import type { AsrFilterMode, ModelName, OcrFilterMode } from "../types/api";
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

// The two text filters are independent, each with its own mode: ASR takes
// substring | regex | bm25 (backend TextMatchMode), OCR takes substring | regex
// only (backend OcrFilterMode: OCR has no BM25 index). Defined in types/api.ts
// with the request contract and re-exported here. Only applies to
// /ensemble-search — see EnsembleSearchRequest.asr_filter / ocr_filter.
export type { AsrFilterMode, OcrFilterMode };

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

  // [siglip2] Tổ hợp model tham gia /ensemble-search (Alg.3) — checkbox bất kỳ
  // trong beit3/clip/siglip2, tick 1-3 cái tuỳ ý. Mặc định cả 3 (bằng đúng
  // hành vi backend khi models rỗng), nhưng hiện rõ trên UI ngay từ đầu là
  // đang chạy tổ hợp nào thay vì im lặng.
  ensembleModels: ModelName[];
  setEnsembleModels: (models: ModelName[]) => void;
  toggleEnsembleModel: (model: ModelName) => void;

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

  // ── Text-signal filters (ASR and OCR annotation, /ensemble-search only) ───
  // Purely additive metadata on the results — never drops a frame. An empty
  // string disables that source, matching the backend's own default. Every
  // setter clears videoAnnotations at once: the badges on screen describe the
  // PREVIOUS filter and must not linger next to a field the user has edited.
  asrFilter: string;
  setAsrFilter: (value: string) => void;
  asrFilterMode: AsrFilterMode;
  setAsrFilterMode: (mode: AsrFilterMode) => void;
  ocrFilter: string;
  setOcrFilter: (value: string) => void;
  ocrFilterMode: OcrFilterMode;
  setOcrFilterMode: (mode: OcrFilterMode) => void;
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

  // [siglip2] Mặc định tick cả 3 — khớp hành vi cũ trước khi có field này
  // (backend chạy ACTIVE_MODELS = mọi model có index khi không nhận `models`).
  ensembleModels: ["beit3", "clip", "siglip2"],
  setEnsembleModels: (models) => set({ ensembleModels: models }),
  toggleEnsembleModel: (model) =>
    set((state) => {
      const has = state.ensembleModels.includes(model);
      // Không cho bỏ tick xuống 0 model: ensemble rỗng vô nghĩa, và backend
      // coi models=[] như "không truyền" rồi chạy lại TẤT CẢ — khác hẳn cái
      // UI đang hiển thị (0 checkbox tick). Im lặng sai lệch.
      if (has && state.ensembleModels.length === 1) return state;
      return {
        ensembleModels: has
          ? state.ensembleModels.filter((m) => m !== model)
          : [...state.ensembleModels, model],
      };
    }),

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

  asrFilter: "",
  setAsrFilter: (value) => {
    set({ asrFilter: value });
    // Badges on screen describe the PREVIOUS filter query — clear them so
    // they never linger next to a field the user has since edited.
    useSearchStore.getState().setVideoAnnotations(null);
  },
  asrFilterMode: "substring",
  setAsrFilterMode: (mode) => {
    set({ asrFilterMode: mode });
    useSearchStore.getState().setVideoAnnotations(null);
  },
  ocrFilter: "",
  setOcrFilter: (value) => {
    set({ ocrFilter: value });
    useSearchStore.getState().setVideoAnnotations(null);
  },
  ocrFilterMode: "substring",
  setOcrFilterMode: (mode) => {
    set({ ocrFilterMode: mode });
    useSearchStore.getState().setVideoAnnotations(null);
  },
}));

// NOTE: SearchResult/SearchState trùng lặp với store/useSearchStore.ts đã bị
// xóa khỏi file này — bản ở useSearchStore.ts mới là bản App.tsx thực sự dùng
// (App.tsx import useSearchStore từ "./store/useSearchStore", không phải từ
// đây). Giữ cả 2 định nghĩa trùng nhau trước đây là dead code gây nhầm lẫn.