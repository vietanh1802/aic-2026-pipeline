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

  /**
   * Videos the grid is narrowed to. Deliberately not cleared by setResults:
   * the whole point is re-querying while watching the same few clips.
   */
  focusVideos: string[];
  toggleFocusVideo: (videoId: string) => void;
  clearFocus: () => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  results: [],
  setResults: (results) => set({ results }),
  maxDistance: 0,
  setMaxDistance: (distance) => set({ maxDistance: distance }),
  totalTime: 0,
  setTotalTime: (totalTime) => set({ totalTime: totalTime }),
  focusVideos: [],
  toggleFocusVideo: (videoId) =>
    set((state) => ({
      focusVideos: state.focusVideos.includes(videoId)
        ? state.focusVideos.filter((id) => id !== videoId)
        : [...state.focusVideos, videoId],
    })),
  clearFocus: () => set({ focusVideos: [] }),
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
