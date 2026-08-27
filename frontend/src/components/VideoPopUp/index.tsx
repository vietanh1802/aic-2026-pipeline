import { useEffect, useMemo, useRef, useState } from "react";
import { SubmitForm } from "../SubmitForm";
import VideoDrive from "./VideoDisplay";
import { getFileIdByVideoId } from "../../helpers/getFileIdByVideoId.helper";
import { useSubmitStore, useSubmitTasks } from "../../store/submitStore";
import { neighbourKeyframesFor } from "../../helpers/keyframes";

import Button from "../Button";
import KeyframeFPS from "../../mapping/fps_map.json";
import { extractTimestamp } from "../FrameDisplay";
import type { BoardTask } from "../../api/board";
import TaskBrief from "../TaskBrief";
import AnswerPanel from "./AnswerPanel";
import FrameMarkStrip from "./FrameMarkStrip";

/**
 * Opened on one event of a TRAKE line rather than on a search result.
 *
 * The popup is otherwise identical — same player, same frame readout, same
 * stepping. Only the submit button changes: it pins this instant into one
 * event's cell instead of writing a whole answer, because a single frame is
 * not a TRAKE row.
 */
export interface TrakeSlot {
  /** 0-based event index. */
  index: number;
  label: string;
  total: number;
  onCommit: (frame: number) => void;
}

interface VideoPopupProps {
  videoId: string;
  frameId: string;
  startAt: number; // in milliseconds
  activeTask?: BoardTask | null;
  onBasketChanged?: () => void;
  onClose: () => void;
  setStartAt: (val: number) => void;
  trakeSlot?: TrakeSlot | null;
}
type VideoId = keyof typeof KeyframeFPS;
type MatchingKeyframe = {
  smaller: string;
  larger: string;
};

function getMatchingKeyframe(
  videoId: string,
  frameNum: number
): MatchingKeyframe {
  const match = neighbourKeyframesFor(videoId, frameNum);
  return {
    smaller: match.smaller?.name ?? "",
    larger: match.larger?.name ?? "",
  };
}

export default function VideoPopup({
  videoId,
  frameId,
  startAt,
  activeTask = null,
  onBasketChanged,
  onClose,
  setStartAt,
  trakeSlot = null,
}: VideoPopupProps) {
  const submissionFileName = useSubmitStore((state) => state.submissonFileName);
  const setSubmissionFileName = useSubmitStore(
    (state) => state.setSubmissionFileName
  );
  const submitType = useSubmitStore((state) => state.submitType);

  const [frameIdx, setFrameIdx] = useState<string>("");

  // Bumped after every add so the panel beside the video re-reads the task's
  // answers. Without it the list only refreshed when the popup was reopened.
  const [answerTick, setAnswerTick] = useState<number>(0);

  // Marked edges of the moment, in seconds. They live here rather than in the
  // submit form because the strip that sets them sits against the video, and
  // the form only needs the result.
  const [markIn, setMarkIn] = useState<number | null>(null);
  const [markOut, setMarkOut] = useState<number | null>(null);

  // The element itself, so a mark reads the exact currentTime at the instant it
  // is pressed. `playhead` below is the same value throttled to timeupdate's
  // four-a-second, which is fine for a readout and far too coarse for a frame.
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playhead, setPlayhead] = useState<number>(startAt / 1000);
  const livePosition = () => videoRef.current?.currentTime ?? playhead;

  // A different video is a different moment; carrying marks across would submit
  // a frame number the user pinned somewhere else entirely.
  useEffect(() => {
    setMarkIn(null);
    setMarkOut(null);
  }, [videoId]);

  // 0 = metadata not loaded yet. Previously this was 1 and the form below was
  // gated on `duration !== 1`, which silently tied the submission form to the
  // Drive metadata request being the only caller of onDuration.
  const [duration, setDuration] = useState<number>(0);
  const frame_detect = KeyframeFPS[videoId as VideoId] as number;

  const computed = Number(parseInt(frameIdx) * frame_detect);

  const matching_keyframe = useMemo(
    () => getMatchingKeyframe(videoId, Number.isFinite(computed) ? computed : 0),
    [computed, videoId]
  );
  const fileId = getFileIdByVideoId(videoId);

  const driveWatchUrl = `https://drive.google.com/file/d/${fileId}/view?t=${Math.floor(
    startAt / 1000
  )}`;
  const { task1, task2, task3, popTask1, popTask2, popTask3 } =
    useSubmitTasks();
  return (
    <div className="fixed inset-0 bg-black/60 bg-opacity-60 flex items-center justify-center z-999 gap-x-5">
      <div className="relative bg-white rounded-xl p-6 shadow-lg max-w-[800px] w-4/5 max-h-[95vh] overflow-y-auto">
        {/* Đề bài đi theo popup. Banner pin trên trang không cứu được ở đây:
            popup là overlay phủ kín khung nhìn nên mọi thứ phía sau đều khuất. */}
        {activeTask && <TaskBrief task={activeTask} variant="popup" />}
        {/* Which moment this popup is pinning. Without it the player looks the
            same for E1 and E3 and the frame lands in whichever cell was last
            clicked, with nothing on screen saying which. */}
        {trakeSlot && (
          <div className="flex items-center gap-2 mb-2 px-3 py-1.5 rounded-full w-fit border border-proto-primary bg-proto-primary/10 font-baloo">
            <b className="font-mono text-[12.5px] text-proto-primary-active">
              E{trakeSlot.index + 1}/{trakeSlot.total}
            </b>
            <span className="text-[12.5px] text-proto-body">
              {trakeSlot.label}
            </span>
          </div>
        )}
        <div className="flex justify-between items-center mb-[15px]">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-[8px]">
              <span className="font-bold">Video ID :</span>
              <span>{videoId + "-" + frameId}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold">Timestamp :</span>
              <span>{extractTimestamp(videoId + "-" + frameId)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold">Video FPS:</span>
              <span>{frame_detect}</span>
            </div>
          </div>

          <div className="flex items-center gap-4 h-full">
            <Button
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300 h-full"
              onClick={() => window.open(driveWatchUrl, "_blank")}
              // size="xs"
            >
              Link
            </Button>
            <input
              type="text"
              value={submissionFileName}
              onChange={(e) => setSubmissionFileName(e.target.value)}
              placeholder="Submission File Name"
              className="block h-full w-full rounded-md border border-gray-300 p-3"
            />
          </div>
        </div>
        <button
          onClick={onClose}
          className="absolute top-2 right-2 text-gray-500 hover:text-red-500 text-xl font-bold"
        >
          ×
        </button>
        <div className="flex justify-center items-center">
          <VideoDrive
            videoId={videoId}
            onDuration={(s) => setDuration(s)}
            videoRef={videoRef}
            onPosition={(seconds) => {
              setPlayhead(seconds);
              setFrameIdx(String(seconds));
            }}
            jumpTo={startAt / 1000}
            setStartAt={setStartAt}
            mapping_frame={matching_keyframe}
            frame_detect={frame_detect}
          />
        </div>

        <FrameMarkStrip
          currentSeconds={playhead}
          duration={duration}
          fps={frame_detect}
          markIn={markIn}
          markOut={markOut}
          onMarkIn={() => setMarkIn(livePosition())}
          onMarkOut={() => setMarkOut(livePosition())}
          onClear={() => {
            setMarkIn(null);
            setMarkOut(null);
          }}
          onSeek={(seconds) => setStartAt(seconds * 1000)}
          disabled={activeTask?.type === "trake"}
        />

        {duration > 0 && (
          <div className="mt-[10px]">
            <SubmitForm
              activeTask={activeTask}
              onBasketChanged={() => {
                setAnswerTick((tick) => tick + 1);
                onBasketChanged?.();
              }}
              videoId={videoId}
              duration={duration}
              startAt={startAt / 1000}
              setStartAt={setStartAt}
              frame_detect={frame_detect}
              markIn={markIn}
              markOut={markOut}
              getPlayhead={livePosition}
              trakeSlot={trakeSlot}
            />
          </div>
        )}
      </div>

      {/* Có task đang mở thì Add Answer ghi thẳng lên server, nên panel phải
          đọc từ đó. Giỏ Zustand bên dưới chỉ còn dùng khi chưa nhận task nào. */}
      {activeTask ? (
        <AnswerPanel
          task={activeTask}
          reloadKey={answerTick}
          onChanged={() => onBasketChanged?.()}
        />
      ) : (
      <div className="w-1/5 h-[70%] bg-white rounded-sm p-6 shadow-lg flex flex-col">
        <h1>
          <b>Filename:</b> {submissionFileName}.csv
        </h1>
        <div className="flex-1 overflow-y-auto">
          {submitType == "Task 1 - kis" && (
            <div>
              <div className="flex flex-row justify-between">
                <h2 className="text-red-500">Task 1 - KIS</h2>
                <h2>Length: {task1.length}</h2>
              </div>
              <pre>{JSON.stringify(task1, null, 2)}</pre>
            </div>
          )}

          {submitType == "Task 2 - qna" && (
            <div>
              <div className="flex flex-row justify-between">
                <h2 className="text-blue-500">Task 2 - Q&A</h2>
                <h2>Length: {task2.length}</h2>
              </div>
              <pre>{JSON.stringify(task2, null, 2)}</pre>
            </div>
          )}

          {submitType == "Task 3 - trake" && (
            <div>
              <div className="flex flex-row justify-between">
                <h2 className="text-green-500">Task 3 - TRAKE</h2>
                <h2>Length: {task3.length}</h2>
              </div>
              <pre>{JSON.stringify(task3, null, 2)}</pre>
            </div>
          )}
        </div>

        {/* Sticks bottom-right */}
        <div className="flex justify-end mt-4">
          <Button
            onClick={() => {
              if (submitType === "Task 3 - trake") {
                popTask3();
              } else if (submitType === "Task 2 - qna") {
                popTask2();
              } else if (submitType === "Task 1 - kis") {
                popTask1();
              }
            }}
          >
            Delete the last one
          </Button>
        </div>
      </div>
      )}
    </div>
  );
}
