import React, { useState } from "react";
import Button from "../Button";
import { SuperSimple } from "./RangeForm";
import {
  useSubmitStore,
  useSubmitTasks,
  type SubmitType,
} from "../../store/submitStore";
import type { DropdownOption } from "../DropDown";
import Dropdown from "../DropDown";
import { getValues } from "../../helpers/getValues.helper";
import { frameAt, frameRange, spreadFrames } from "../../helpers/frameRange";
import { addAnswer } from "../../api/answers";
import type { BoardTask } from "../../api/board";
import type { TrakeSlot } from "../VideoPopUp";
import { useAuthStore } from "../../store/authStore";

interface SubmitFormData {
  videoId: string;
  duration: number;
  startAt: number;
  setStartAt: (val: number) => void;
  frame_detect: number;
  /** Task đang mở từ Board. Có nó thì Add Answer ghi thẳng vào cơ sở dữ liệu. */
  activeTask?: BoardTask | null;
  onBasketChanged?: () => void;
  /** Mép của khoảnh khắc, ghim từ dải điều khiển ngay dưới video. Null = chưa
   *  ghim, và chưa ghim cả hai thì nộp đúng frame như trước. */
  markIn?: number | null;
  markOut?: number | null;
  /** The player's exact position, read at the moment of submitting. */
  getPlayhead?: () => number;
  /** Set when the popup was opened on one event of a TRAKE line. */
  trakeSlot?: TrakeSlot | null;
  /** The Q&A answer already on the task's first row. A Q&A task has exactly
   *  one answer — only the frame varies per row — so "Trải K dòng" falls back
   *  to this when the popup's answer box is left empty, instead of writing
   *  `null` into every new row. */
  fallbackAnswer?: string | null;
}

export const SubmitForm: React.FC<SubmitFormData> = ({
  videoId,
  duration,
  startAt,
  setStartAt,
  frame_detect,
  activeTask = null,
  onBasketChanged,
  markIn = null,
  markOut = null,
  getPlayhead,
  trakeSlot = null,
  fallbackAnswer = null,
}) => {
  const [answer, setAnswer] = useState<string>("");
  const [values, setValues] = useState(getValues(startAt, duration));
  const me = useAuthStore((state) => state.user);

  const submitType = useSubmitStore((state) => state.submitType);
  const setSubmitType = useSubmitStore((state) => state.setSubmitType);

  // TRAKE keeps the old single-instant path: one row carries one frame per
  // event, so a midpoint between two edges has no slot to go in yet.
  const isTrakeAnswer =
    activeTask !== null
      ? activeTask.type === "trake"
      : submitType === "Task 3 - trake";

  // Once a Board task is open there is exactly one task type and it is fixed
  // by the task itself, not by a dropdown — a KIS task pins a single frame and
  // a TRAKE row is assembled on the search line, so only Q&A still needs
  // typed text here.
  const isQaAnswer =
    activeTask !== null ? activeTask.type === "qa" : submitType === "Task 2 - qna";

  // Read at submit time, not at render time: the player moves without React
  // hearing about it between renders.
  const frameToSubmit = (): number => {
    const now = getPlayhead ? getPlayhead() : startAt;
    const here = frameAt(now, frame_detect);
    if (isTrakeAnswer) {
      return here ?? Number.NaN;
    }
    return frameRange(markIn ?? now, markOut ?? now, frame_detect)?.frame
      ?? here ?? Number.NaN;
  };

  // ── Trải K dòng ──────────────────────────────────────────────────────────
  const [spreadK, setSpreadK] = useState<number>(5);
  const [spreadNote, setSpreadNote] = useState<string | null>(null);
  const [spreading, setSpreading] = useState<boolean>(false);

  // Both edges marked, a real task open, and not TRAKE — a TRAKE row is N
  // moments in one row, so K rows over an interval means nothing there. The
  // mark strip is already disabled for TRAKE, so this can never light up.
  const canSpread =
    activeTask !== null &&
    activeTask.type !== "trake" &&
    // Same rule as the answer basket: a task with an owner who is not you is
    // read-only at the UI layer. Boolean() first, because an unclaimed task has
    // no owner and must not lock out the person holding it.
    !(Boolean(activeTask.owner) && activeTask.owner?.id !== me?.id) &&
    markIn !== null &&
    markOut !== null &&
    Number.isFinite(frame_detect) &&
    frame_detect > 0;

  const spreadOptions: DropdownOption[] = [
    { id: 0, label: "3 dòng", value: "3" },
    { id: 1, label: "5 dòng", value: "5" },
    { id: 2, label: "7 dòng", value: "7" },
    { id: 3, label: "9 dòng", value: "9" },
  ];

  /**
   * Sequential on purpose, and not atomic.
   *
   * The rows are ranked in the order they arrive, and that order is the whole
   * point — it is the bisection priority. Firing them together would rank them
   * by whichever response came back first. A failure part-way leaves the rows
   * that landed in place: they are correct rows, individually deletable, and
   * silently rolling them back would be worse than saying how far it got.
   */
  const handleSpread = async () => {
    if (!activeTask || markIn === null || markOut === null) {
      return;
    }
    const range = frameRange(markIn, markOut, frame_detect);
    if (!range) {
      setSpreadNote(`Không tính được frame: thiếu fps cho ${videoId}`);
      return;
    }
    const frames = spreadFrames(range.start, range.end, spreadK);
    if (frames.length === 0) {
      setSpreadNote("Khoảng đã ghim không có frame nào");
      return;
    }

    setSpreading(true);
    let added = 0;
    try {
      // An empty box must not blank out the K new rows: a Q&A task has one
      // answer for the whole task, so the first row's answer (passed in as
      // fallbackAnswer) is what an empty box really means here.
      const qaAnswerText =
        activeTask.type === "qa" ? answer || fallbackAnswer || null : null;
      for (const frame of frames) {
        await addAnswer(activeTask.id, {
          video_id: videoId,
          frames: [frame],
          answer_text: qaAnswerText,
        });
        added += 1;
        setSpreadNote(`${added}/${frames.length}…`);
        onBasketChanged?.();
      }
      setSpreadNote(`Đã thêm ${added}/${frames.length} dòng`);
    } catch (err) {
      console.error("Trải K dòng dừng giữa chừng:", err);
      setSpreadNote(`Đã thêm ${added}/${frames.length} dòng rồi dừng vì lỗi`);
    } finally {
      setSpreading(false);
    }
  };

  const { addTask1, addTask2, addTask3 } = useSubmitTasks();

  const submitTypeOptions: DropdownOption[] = [
    { id: 0, label: "Task 1 - KIS", value: "Task 1 - kis" as SubmitType },
    { id: 1, label: "Task 2 - Q&A", value: "Task 2 - qna" as SubmitType },
    { id: 2, label: "Task 3 - TRAKE", value: "Task 3 - trake" as SubmitType },
  ];

  const handleSubmit = async () => {
    // Midpoint of the marked edges for KIS and Q&A; the raw playhead for TRAKE
    // and for a video whose fps is unknown. frameRange() returns null in that
    // second case, which is also why the button is disabled there.
    const frame = frameToSubmit();
    if (!Number.isFinite(frame)) {
      console.error("Không tính được frame: thiếu fps cho", videoId);
      return;
    }

    // Có task đang mở thì đây là đường ghi thật: một hàng trong bảng answers,
    // sống qua F5 và đồng đội thấy được. Giỏ Zustand bên dưới chỉ còn là đường
    // lùi cho lúc chưa nhận task nào — trước đây nó là đường duy nhất, và đó là
    // lý do bấm Add Answer xong số trên thanh nav vẫn đứng yên.
    // Pinning one moment of a TRAKE line. Nothing is written to the basket
    // here — the line becomes an answer only once all N cells are filled and
    // the row's own button is pressed.
    if (trakeSlot) {
      trakeSlot.onCommit(frame);
      return;
    }

    if (activeTask) {
      try {
        await addAnswer(activeTask.id, {
          video_id: videoId,
          frames: [frame],
          answer_text: activeTask.type === "qa" ? answer || null : null,
        });
        onBasketChanged?.();
        if (activeTask.type !== "trake") {
          setAnswer("");
        }
        return;
      } catch (err) {
        console.error("Không thêm được vào giỏ:", err);
        return;
      }
    }

    switch (submitType) {
      case "Task 1 - kis":
        addTask1(videoId, String(frame));
        console.log("Task 1 Done");
        break;
      case "Task 2 - qna":
        addTask2(videoId, String(frame), answer);
        break;
      case "Task 3 - trake":
        addTask3(
          videoId,
          String(frame),
          Number(answer)
        );
        break;
    }
    if (submitType != "Task 3 - trake") {
      setAnswer("");
    }
  };

  return (
    <>
      <div className="flex items-start gap-4 w-full">
        {/* Once a Board task is open, KIS pins a single frame and TRAKE is
            assembled on the search line — this card has nothing left to show
            unless the task is Q&A. */}
        {(!activeTask || activeTask.type === "qa") && (
          <div className="flex flex-col gap-4 flex-1 rounded-md border border-gray-300 bg-white p-4 shadow-sm">
            {/* The range slider drives the old scratchpad's own notion of
                "current position"; a Board task already has the mark-in/out
                strip against the video for that. */}
            {!activeTask && (
              <div className="flex items-center gap-4">
                <label className="text-sm font-medium text-gray-700">Range</label>
                <SuperSimple
                  min={0}
                  max={duration}
                  values={values}
                  setValues={setValues}
                  setStartAt={setStartAt}
                />
              </div>
            )}

            {/* Input — nothing to type when pinning a TRAKE moment, and once a
                Board task is open, only Q&A still needs typed text here. */}
            {!trakeSlot && (!activeTask || isQaAnswer) && (
              <input
                type={isQaAnswer ? "text" : "number"}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder={
                  isQaAnswer ? "Type in your answer" : "Type in the number of activities"
                }
                className="w-full rounded-md border border-gray-300 p-2 text-sm focus:border-blue-400 focus:ring focus:ring-blue-100 outline-none"
                disabled={!activeTask && submitType === "Task 1 - kis"}
              />
            )}
          </div>
        )}

        <div className="flex flex-col gap-3 h-full">
          {/* The task-type picker is about a whole scratchpad session; a
              Board task already fixes its own type. */}
          {!activeTask && (
            <Dropdown
              options={submitTypeOptions}
              value={submitType}
              onChange={(opt) => setSubmitType(opt.value as SubmitType)}
              dropDownWidth={194}
              dropDirection="up"
            />
          )}
          <div className="flex gap-3 items-stretch">
            <Button
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10 "
              onClick={handleSubmit}
              size="xs"
              // No fps for this video means every frame number downstream is
              // NaN. It used to submit that; now it says so and stops.
              disabled={!Number.isFinite(frame_detect) || frame_detect <= 0}
            >
              {trakeSlot ? `Chốt cho E${trakeSlot.index + 1}` : "Add Answer"}
            </Button>
          </div>

          {/* Item 5 — one press instead of "add the edges, add the middle,
              then subdivide", which is minutes of clicking per query. */}
          {!trakeSlot && (
            <div className="flex flex-col gap-1">
              <div className="flex gap-2 items-stretch">
                <Dropdown
                  options={spreadOptions}
                  value={String(spreadK)}
                  onChange={(opt) => setSpreadK(Number(opt.value))}
                  dropDownWidth={96}
                  dropDirection="up"
                  size="sm"
                />
                <Button
                  className="bg-proto-primary hover:opacity-90 text-white px-4 rounded-md shadow-sm transition-all duration-300 flex-1 h-10"
                  size="xs"
                  onClick={() => void handleSpread()}
                  disabled={!canSpread || spreading}
                  title={
                    canSpread
                      ? "Trải đều K dòng trên đoạn đã ghim"
                      : activeTask &&
                        Boolean(activeTask.owner) &&
                        activeTask.owner?.id !== me?.id
                      ? "Giỏ của người khác — chỉ đọc"
                      : "Ghim cả điểm đầu và điểm cuối trước"
                  }
                >
                  {spreading ? spreadNote ?? "Đang thêm…" : `Trải ${spreadK} dòng`}
                </Button>
              </div>
              {!spreading && spreadNote && (
                <span className="text-[11px] text-proto-muted">{spreadNote}</span>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};
