// frontend/src/store/useSearchStore.ts

import { create } from "zustand";
import type { VideoAnnotation } from "../types/api";

interface SearchResult {
  frame: string;
  distance: number;
  url: string;
  name: string;
}

/**
 * Dòng "50 khung · 1.8s" hiện trên thanh điều hướng.
 *
 * Nằm trong store chứ không tính lúc render, vì thanh nav do Root dựng còn số
 * ứng viên temporal/TRAKE lại là state cục bộ của App — hai cây component khác
 * nhau. Mỗi nhánh tìm kiếm tự ghi vào đây con số của chính nó, nên không cần
 * nhánh nào biết nhánh nào.
 */
export interface SearchSummary {
  count: number;
  /** Tuyến ảnh đếm KHUNG; temporal/TRAKE đếm VIDEO. */
  unit: "frames" | "videos";
  seconds: number;
}

interface SearchState {
  results: SearchResult[];
  setResults: (results: SearchResult[]) => void;
  maxDistance: number;
  setMaxDistance: (distance: number) => void;

  totalTime: number;
  setTotalTime: (totalTime: number) => void;

  summary: SearchSummary | null;
  setSummary: (summary: SearchSummary | null) => void;

  /**
   * Videos the grid is narrowed to. Deliberately not cleared by setResults:
   * the whole point is re-querying while watching the same few clips.
   */
  focusVideos: string[];
  toggleFocusVideo: (videoId: string) => void;
  clearFocus: () => void;

  /**
   * Whether the grid is actually narrowed to focusVideos, or just highlights
   * them. Pinning used to do both at once, which meant the second video's
   * card (and its own pin button) vanished from the DOM the instant the
   * first pin filtered it away, so a user could never pin more than one.
   * Kept separate from focusVideos so pinning stays a pure "mark these"
   * action, and narrowing is an explicit opt-in on top of it.
   */
  showOnlyPinned: boolean;
  toggleShowOnlyPinned: () => void;

  /**
   * View option: one card per video in the frame results grid, showing the
   * video's best frame (helpers/groupResults.ts). Default off.
   *
   * A VIEW preference, so it lives here beside showOnlyPinned and not in
   * queryStore: it is not a search parameter. Consequently it is not cleared
   * by a new search (setResults leaves it alone, like focusVideos), not reset
   * by clearFocus, and not recorded by searchStateRecorder - "Coi X làm" replays
   * someone else's query and parameters and must not override how the viewer
   * chose to look at the results.
   */
  onePerVideo: boolean;
  toggleOnePerVideo: () => void;

  /**
   * Per-video text-signal annotations from the last /ensemble-search response
   * (video_id -> VideoAnnotation). null when text_filter was empty or the
   * last search wasn't ensemble — TextSignalBadge treats null the same as a
   * missing entry and renders nothing.
   */
  videoAnnotations: Record<string, VideoAnnotation> | null;
  setVideoAnnotations: (annotations: Record<string, VideoAnnotation> | null) => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  results: [],
  setResults: (results) => set({ results }),
  maxDistance: 0,
  setMaxDistance: (distance) => set({ maxDistance: distance }),
  totalTime: 0,
  setTotalTime: (totalTime) => set({ totalTime: totalTime }),
  summary: null,
  setSummary: (summary) => set({ summary }),
  focusVideos: [],
  toggleFocusVideo: (videoId) =>
    set((state) => ({
      focusVideos: state.focusVideos.includes(videoId)
        ? state.focusVideos.filter((id) => id !== videoId)
        : [...state.focusVideos, videoId],
    })),
  clearFocus: () => set({ focusVideos: [], showOnlyPinned: false }),

  showOnlyPinned: false,
  toggleShowOnlyPinned: () =>
    set((state) => ({ showOnlyPinned: !state.showOnlyPinned })),

  onePerVideo: false,
  toggleOnePerVideo: () => set((state) => ({ onePerVideo: !state.onePerVideo })),

  videoAnnotations: null,
  setVideoAnnotations: (annotations) => set({ videoAnnotations: annotations }),
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
