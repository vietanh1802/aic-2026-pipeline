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
import { frameAt, frameRange } from "../../helpers/frameRange";
import { addAnswer } from "../../api/answers";
import { recordSearchState } from "../../helpers/searchStateRecorder";
import type { BoardTask } from "../../api/board";
import type { TrakeSlot } from "../VideoPopUp";

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
}) => {
  const [answer, setAnswer] = useState<string>("");
  const [values, setValues] = useState(getValues(startAt, duration));

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
        // Ghi lại khung THẬT SỰ được lấy, không phải cái thẻ đã bấm để mở
        // popup. Bấm thẻ 3175 rồi tua tới 3180 và chốt 3180 thì thứ đáng mở
        // lại là 3180 — mà trước đây đường này không ghi gì, nên lịch sử vẫn
        // dừng ở 3175 và không ai biết người đó đã chỉnh đi đâu.
        //
        // Tên keyframe của thẻ cũ được giữ nguyên bên trong helper, vì vòng
        // khoanh đỏ so theo tên và 3180 thường không trùng keyframe nào.
        recordSearchState(activeTask.id, { video: videoId, frameIdx: frame });
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

        {/* ml-auto: với KIS/TRAKE thì thẻ nhập bên trái không hiện, nên cột
            này là thứ duy nhất trong hàng và nút Add Answer dạt hẳn về mép
            trái — xa chỗ mắt đang nhìn (dải ghim và số frame nằm bên phải). */}
        <div className="flex flex-col gap-3 h-full ml-auto">
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
              {trakeSlot
                ? trakeSlot.addsToBasket
                  ? `Chốt E${trakeSlot.index + 1} → vào giỏ`
                  : `Chốt cho E${trakeSlot.index + 1}`
                : "Add Answer"}
            </Button>
          </div>

          {/* Cụm "K dòng" + nút "Trải K dòng" đã bỏ.

              Nó trải K dòng chia đều trên đoạn vừa ghim, nhưng cùng việc đó
              nút "+ Điền tự động" trong giỏ đáp án làm tốt hơn: ở đó chọn được
              nhiều mốc, chọn bước nhảy, chọn chỉ rải lên hay xuống, và với
              TRAKE thì rải theo từng sự kiện. Hai đường làm một việc, đường ở
              đây lại chiếm hai dòng ngay dưới nút Add Answer. */}

        </div>
      </div>
    </>
  );
};
