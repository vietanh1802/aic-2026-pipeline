import { useMemo, useState } from "react";
import { SubmitForm } from "../SubmitForm";
import VideoDrive from "./VideoDisplay";
import { getFileIdByVideoId } from "../../helpers/getFileIdByVideoId.helper";
import { useSubmitStore, useSubmitTasks } from "../../store/submitStore";
import { findMatchingKeyframes } from "../../helpers/findMatchingKeyframe";
import KeyframeDB from "../../mapping/keyframes.json";

import Button from "../Button";
import KeyframeFPS from "../../mapping/fps_map.json";
import { extractTimestamp } from "../FrameDisplay";

interface VideoPopupProps {
  videoId: string;
  frameId: string;
  startAt: number; // in milliseconds
  onClose: () => void;
  setStartAt: (val: number) => void;
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
  const match = findMatchingKeyframes(videoId, frameNum, KeyframeDB);
  return {
    smaller: match.smaller ?? "",
    larger: match.larger ?? "",
  };
}

export default function VideoPopup({
  videoId,
  frameId,
  startAt,
  onClose,
  setStartAt,
}: VideoPopupProps) {
  const submissionFileName = useSubmitStore((state) => state.submissonFileName);
  const setSubmissionFileName = useSubmitStore(
    (state) => state.setSubmissionFileName
  );
  const submitType = useSubmitStore((state) => state.submitType);

  const [frameIdx, setFrameIdx] = useState<string>("");

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
      <div className="relative bg-white rounded-xl p-6 shadow-lg max-w-[800px] w-4/5">
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
            fileId={fileId}
            onDuration={(s) => setDuration(s)}
            onFrameIdx={(frameIdx) => setFrameIdx(frameIdx)}
            jumpTo={startAt / 1000}
            setStartAt={setStartAt}
            mapping_frame={matching_keyframe}
            frame_detect={frame_detect}
          />
        </div>

        {duration > 0 && (
          <div className="mt-[10px]">
            <SubmitForm
              videoId={videoId}
              duration={duration}
              startAt={startAt / 1000}
              setStartAt={setStartAt}
              frame_detect={frame_detect}
            />
          </div>
        )}
      </div>
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
    </div>
  );
}
