// src/store/queryStore.ts
import { create } from "zustand";

export type QueryType = "text" | "image" | "audio";
export type SearchType =
  | "text-search"
  | "faiss-search"
  | "combined-search"
  | "ocr-search";
export type TranslateLanguage = "vi-en" | "en-vi";
interface FilterFields {
  object: string;
  color: string;
  action: string;
  ocr: string;
}
export interface QueryStore {
  queryType: QueryType;
  setQueryType: (type: QueryType) => void;
  resultLimit: string;
  setResultLimit: (limit: string) => void;
  queryText: string;
  setQueryText: (text: string) => void;
  searchType: SearchType;
  setSearchType: (type: SearchType) => void;

  // Filter
  filter: FilterFields;
  setFilter: (filter: Partial<FilterFields>) => void;

  // Translate
  translateLang: TranslateLanguage;
  setTranslateLang: (lang: TranslateLanguage) => void;
  queryTranslated: string;
  setQueryTranslated: (text: string) => void;

  // New
  rank: number;
  setRank: (rank: number) => void;
  uniqueKeyword: string;
  setUniqueKeyword: (keyword: string) => void;
}

export const useQueryStore = create<QueryStore>((set) => ({
  queryType: "text",
  setQueryType: (type) => set({ queryType: type }),
  resultLimit: "100",
  setResultLimit: (limit) => set({ resultLimit: limit }),
  queryText: "",
  setQueryText: (text) => set({ queryText: text }),
  searchType: "text-search",
  setSearchType: (type) => set({ searchType: type }),

  // Filter defaults
  filter: {
    object: "",
    color: "",
    action: "",
    ocr: "",
  },
  setFilter: (newFilter) =>
    set((state) => ({
      filter: { ...state.filter, ...newFilter },
    })),

  // Translated
  translateLang: "en-vi",
  setTranslateLang: (lang) => set({ translateLang: lang }),
  queryTranslated: "",
  setQueryTranslated: (text) => set({ queryTranslated: text }),

  rank: 3,
  setRank: (rank) => set({ rank: rank }),
  uniqueKeyword: "",
  setUniqueKeyword: (keyword) => set({ uniqueKeyword: keyword }),
}));

interface SearchResult {
  frame: string;
  distance: number;
  url: string;
}

interface SearchState {
  results: SearchResult[];
  setResults: (results: SearchResult[]) => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  results: [],
  setResults: (results) => set({ results }),
}));
