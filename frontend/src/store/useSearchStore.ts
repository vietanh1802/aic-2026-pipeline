// useSearchStore.ts

import { create } from "zustand";

interface SearchResult {
  frame: string;
  distance: number;
  url: string;
  name: string;
}

interface SearchState {
  results: SearchResult[];
  setResults: (results: SearchResult[]) => void;
  maxDistance: number;
  setMaxDistance: (distance: number) => void;

  totalTime: number;
  setTotalTime: (totalTime: number) => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  results: [],
  setResults: (results) => set({ results }),
  maxDistance: 0,
  setMaxDistance: (distance) => set({ maxDistance: distance }),
  totalTime: 0,
  setTotalTime: (totalTime) => set({ totalTime: totalTime }),
}));

type isQueryStore = {
  hasQueried: boolean;
  setHasQueried: (value: boolean) => void;
  reset: () => void;
};

export const useIsQueryStore = create<isQueryStore>((set) => ({
  hasQueried: false,
  setHasQueried: (value) => set({ hasQueried: value }),
  reset: () => set({ hasQueried: false }),
}));
