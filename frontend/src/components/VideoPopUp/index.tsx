import { useEffect, useMemo, useRef, useState } from "react";
import { SubmitForm } from "../SubmitForm";
import VideoDrive from "./VideoDisplay";
import { getFileIdByVideoId } from "../../helpers/getFileIdByVideoId.helper";
import { useSubmitStore, useSubmitTasks } from "../../store/submitStore";
import { neighbourKeyframesFor } from "../../helpers/keyframes";

import Button from "../Button";
import KeyframeFPS from "../../mapping/fps_map.json";
import { extractTimestamp } from "../FrameDisplay";
import type { AnswerRow } from "../../api/answers";
import type { BoardTask } from "../../api/board";
import TaskBrief from "../TaskBrief";
import AnswerPanel from "./AnswerPanel";
import FrameMarkStrip from "./FrameMarkStrip";
import { usePopupStore } from "../../store/popupStore";
import { startMsAt } from "../../helpers/frameIdentity";
import { frameRange } from "../../helpers/frameRange";
import type { MarkedRange } from "../../helpers/basketMath";

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
  /** From the round the task belongs to; the panel's autofill target. */
  rowsPerQuery?: number;
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
  rowsPerQuery = 100,
  onBasketChanged,
  onClose,
  setStartAt,
  trakeSlot = null,
}: VideoPopupProps) {
  const submissionFileName = useSubmitStore((state) => state.submissonFileName);
  const submitType = useSubmitStore((state) => state.submitType);

  const [frameIdx, setFrameIdx] = useState<string>("");

  // Bumped after every add so the panel beside the video re-reads the task's
  // answers. Without it the list only refreshed when the popup was reopened.
  const [answerTick, setAnswerTick] = useState<number>(0);

  // The basket row the user last clicked, so the panel can highlight which one
  // they are currently checking against the video.
  const [activeRowId, setActiveRowId] = useState<number | null>(null);

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

  // The marked interval, in frames, for the autofill step suggestion. Null
  // whenever either edge is unset or the video's fps is unknown — the same
  // condition SubmitForm uses to disable submission on the marked interval.
  const markedRange: MarkedRange | null = useMemo(() => {
    if (markIn === null || markOut === null) {
      return null;
    }
    const range = frameRange(markIn, markOut, frame_detect);
    return range ? { start: range.start, end: range.end } : null;
  }, [markIn, markOut, frame_detect]);
  const fileId = getFileIdByVideoId(videoId);

  const driveWatchUrl = `https://drive.google.com/file/d/${fileId}/view?t=${Math.floor(
    startAt / 1000
  )}`;
  const { task1, task2, task3, popTask1, popTask2, popTask3 } =
    useSubmitTasks();

  // A basket row on the same video seeks in place — no remount, the player
  // just jumps. A different video re-targets the whole popup through the
  // store, the same path a search result or the goto-frame box uses.
  const handleAnswerRowClick = (row: AnswerRow) => {
    setActiveRowId(row.id);
    if (row.video_id === videoId) {
      setStartAt(startMsAt(videoId, row.frames[0]));
    } else {
      usePopupStore.getState().open(row.video_id, row.frames[0]);
    }
  };

  return (
    <div className="fixed inset-0 z-[1000] bg-black/60 flex items-center justify-center p-4">
      <div className="relative bg-white rounded-xl shadow-lg w-full max-w-[1320px] max-h-[94vh] flex overflow-hidden font-baloo">
        <button
          onClick={onClose}
          className="absolute top-2 right-2 z-30 flex h-10 w-10 items-center justify-center text-gray-500 hover:text-red-500 text-xl font-bold"
        >
          ×
        </button>

        <div className="flex-1 min-w-0 overflow-y-auto p-6">
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

            <div className="flex items-center gap-4">
              <Button
                className="bg-blue-500 hover:bg-blue-600 text-white px-4 rounded-md shadow-sm transition-all duration-300"
                onClick={() => window.open(driveWatchUrl, "_blank")}
              >
                Link
              </Button>
            </div>
          </div>
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

        <div className="w-[340px] shrink-0 border-l border-proto-line flex flex-col overflow-hidden">
          {/* Có task đang mở thì Add Answer ghi thẳng lên server, nên panel
              phải đọc từ đó. Giỏ Zustand bên dưới chỉ còn dùng khi chưa nhận
              task nào. */}
          {activeTask ? (
            <AnswerPanel
              task={activeTask}
              rowsPerQuery={rowsPerQuery}
              reloadKey={answerTick}
              onRowClick={handleAnswerRowClick}
              onChanged={() => onBasketChanged?.()}
              activeRowId={activeRowId}
              markedRange={markedRange}
            />
          ) : (
            <div className="flex flex-col h-full p-4 overflow-hidden">
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
      </div>
    </div>
  );
}
