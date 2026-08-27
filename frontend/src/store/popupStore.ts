import { create } from "zustand";

/**
 * "Open the video popup here", from anywhere.
 *
 * The popup lives in App.tsx and is driven by four pieces of its local state.
 * A basket row and the goto-frame box both sit outside App — one of them is
 * mounted by Root, beside App rather than within it — so lifting that state up
 * would mean threading four setters through Root into two subtrees. A request
 * object is smaller: the writer says where, App does the rest and clears it.
 */
export type PopupRequest = { videoId: string; frameIdx: number } | null;

interface PopupState {
  request: PopupRequest;
  open: (videoId: string, frameIdx: number) => void;
  clear: () => void;
}

export const usePopupStore = create<PopupState>((set) => ({
  request: null,
  open: (videoId, frameIdx) => set({ request: { videoId, frameIdx } }),
  clear: () => set({ request: null }),
}));
