import { create } from "zustand";

export type SubmitType = "Task 1 - kis" | "Task 2 - qna" | "Task 3 - trake";
export type ViewType = "keyframe" | "video";
interface SubmitState {
  submitType: SubmitType;
  setSubmitType: (type: SubmitType) => void;

  viewType: ViewType;
  setViewType: (type: ViewType) => void;

  frameIdxSet: string;
  setFrameIdxSet: (limit: string) => void;

  submissonFileName: string;
  setSubmissionFileName: (filename: string) => void;
}

export const useSubmitStore = create<SubmitState>((set) => ({
  submitType: "Task 1 - kis", // default value
  setSubmitType: (type) => set({ submitType: type }),
  viewType: "keyframe",
  setViewType: (type) => set({ viewType: type }),
  frameIdxSet: "1",
  setFrameIdxSet: (limit) => set({ frameIdxSet: limit }),
  submissonFileName: "",
  setSubmissionFileName: (filename) => set({ submissonFileName: filename }),
}));

export interface Task1 {
  videoId: string;
  frameIdx: string;
}

export interface Task2 {
  videoId: string;
  frameIdx: string;
  answer: string;
}

export interface Task3 {
  videoId: string;
  frameIdx: string[];
}

interface SubmitTasks {
  task1: Task1[];
  addTask1: (videoId: string, frameIdx: string) => void;
  popTask1: () => void;

  task2: Task2[];
  addTask2: (videoId: string, frameIdx: string, answer: string) => void;
  popTask2: () => void;

  task3: Task3[];
  addTask3: (videoId: string, frameIdx: string, number_event: number) => void;
  popTask3: () => void;

  clearAll: () => void;
}

export const useSubmitTasks = create<SubmitTasks>((set) => ({
  task1: [],
  addTask1: (videoId, frameIdx) =>
    set((state) => {
      console.log("Doing Task1");
      const existing = state.task1.find((t) => t.videoId === videoId);
      if (existing) {
        console.log("exsiting", existing.frameIdx, frameIdx);
        if (existing.frameIdx === frameIdx) {
          console.log("Giữ nguyên");
          return state;
        } // giữ nguyên
      }
      return { task1: [...state.task1, { videoId, frameIdx }] };
    }),
  popTask1: () =>
    set((state) => {
      if (state.task1.length === 0) return state; // nothing to pop
      return { task1: state.task1.slice(0, -1) };
    }),

  task2: [],
  addTask2: (videoId, frameIdx, answer) =>
    set((state) => {
      return { task2: [...state.task2, { videoId, frameIdx, answer }] };
    }),
  popTask2: () =>
    set((state) => {
      if (state.task2.length === 0) return state; // nothing to pop
      return { task2: state.task2.slice(0, -1) };
    }),

  task3: [],
  addTask3: (videoId, frameIdx, number_event) =>
    set((state) => {
      // find all groups for this videoId
      const groups = state.task3.filter((t) => t.videoId === videoId);
      const lastGroup = groups[groups.length - 1]; // latest group for that video

      // case 1: if no group yet → create the first one
      if (!lastGroup) {
        return {
          task3: [...state.task3, { videoId, frameIdx: [frameIdx] }],
        };
      }

      // case 2: avoid duplicate frame
      if (lastGroup.frameIdx.includes(frameIdx)) return state;

      // case 3: if last group is not full → add into it
      if (lastGroup.frameIdx.length < number_event) {
        return {
          task3: state.task3.map((t, _) =>
            t === lastGroup ? { ...t, frameIdx: [...t.frameIdx, frameIdx] } : t
          ),
        };
      }

      // case 4: if last group is full → create a new one
      return {
        task3: [...state.task3, { videoId, frameIdx: [frameIdx] }],
      };
    }),
  popTask3: () =>
    set((state) => {
      if (state.task3.length === 0) return state; // nothing to pop

      const lastGroup = state.task3[state.task3.length - 1];
      const newFrameIdx = lastGroup.frameIdx.slice(0, -1);

      // case: no frame left → drop the whole group
      if (newFrameIdx.length === 0) {
        return {
          task3: state.task3.slice(0, -1),
        };
      }

      // case: still frames left → update the last group
      return {
        task3: state.task3.map((t, idx) =>
          idx === state.task3.length - 1 ? { ...t, frameIdx: newFrameIdx } : t
        ),
      };
    }),

  clearAll: () => set({ task1: [], task2: [], task3: [] }),
}));
