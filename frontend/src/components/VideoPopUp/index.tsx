// frontend/src/components/VideoPopUp/index.tsx

import { useEffect, useMemo, useRef, useState } from "react";
import { SubmitForm } from "../SubmitForm";
import DresPropose from "../DresPropose";
import VideoDrive from "./VideoDisplay";
import { getFileIdByVideoId } from "../../helpers/getFileIdByVideoId.helper";
import { useSubmitStore, useSubmitTasks } from "../../store/submitStore";
import { neighbourKeyframesFor } from "../../helpers/keyframes";

import Button from "../Button";
import KeyframeFPS from "../../mapping/fps_map.json";
// import { extractTimestamp } from "../FrameDisplay"; // read the frame number as ms, see below
import { type AnswerRow } from "../../api/answers";
import type { BoardTask } from "../../api/board";
import TaskBrief from "../TaskBrief";
import AnswerPanel from "./AnswerPanel";
import CandidateMarkers from "./CandidateMarkers";
import CandidateStrip from "./CandidateStrip";
import FrameMarkStrip from "./FrameMarkStrip";
import { usePopupStore } from "../../store/popupStore";
import {
  frameClock,
  frameIdxFromFrameId,
  frameMsOf,
  startMsAt,
} from "../../helpers/frameIdentity";
import { DRES_ONLY } from "../../helpers/finalRound";
import { frameRange } from "../../helpers/frameRange";
import { durationForVideo, type DurationTag } from "../../helpers/candidateStripView";
import { nextSeekRequest, type SeekRequest } from "../../helpers/seekRequest";
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
  /**
   * Thẻ ứng viên mà mốc này thuộc về. Chỉ dùng để nhận ra "đã chuyển sang mốc
   * khác" — cả N mốc của một thẻ nằm trên CÙNG một video, nên `videoId` không
   * phân biệt được E1 với E2.
   */
  cardKey: string;
  /** 0-based event index. */
  index: number;
  label: string;
  total: number;
  /**
   * `addsToBasket` đã bỏ. Nó phân biệt "chốt xong là có ngay một dòng trong
   * giỏ" (KIS/Q&A) với "mới chỉ điền vào ô" (TRAKE), chỉ để nhãn nút nói đúng
   * việc nó làm. Giờ ô mốc chỉ tồn tại cho câu TRAKE — câu KIS/Q&A dùng popup
   * thường với nút Add Answer, y như ensemble — nên vế thứ nhất không còn xảy
   * ra và nhãn luôn là "Chốt cho E…".
   */
  /**
   * @param range Hai đầu đã ghim cho riêng mốc này, null khi chưa ghim đủ cả
   *   hai. Câu TRAKE dùng nó để điền ô "từ/đến" của Điền tự động trong giỏ;
   *   nó KHÔNG quyết định `frame` — xem `submits` của FrameMarkStrip.
   */
  onCommit: (frame: number, range?: MarkedRange | null) => void;
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

  // Vòng nạp "câu trả lời Q&A của dòng đầu" đã bỏ cùng với nút "Trải K dòng" —
  // nó chỉ tồn tại để làm giá trị dự phòng cho nút đó.

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

  // Popup được trỏ sang một khoảnh khắc khác thì bỏ ghim cũ.
  //
  // Trước đây chỉ nghe `[videoId]`. Không đủ, và với TRAKE search thì hụt ngay
  // ở lần dùng đầu: cả N mốc của một thẻ nằm trên CÙNG một video, nên bấm kính
  // lúp ở E1 rồi E3 không đổi `videoId` và popup cũng không gắn lại — E3 thừa
  // hưởng nguyên đoạn vừa ghim cho E1, rồi "Add Answer" nộp điểm giữa của một
  // cảnh khác hẳn cảnh đang xem.
  //
  // `frameId` là khung mà popup được trỏ tới, chỉ đổi khi có người trỏ nó đi
  // chỗ khác — hai nút −/+ dưới video sửa `frameIdx` cục bộ, không đụng vào
  // đây, nên bước từng khung KHÔNG làm mất ghim.
  useEffect(() => {
    setMarkIn(null);
    setMarkOut(null);
  }, [videoId, frameId]);

  // Và đổi mốc cũng là đổi khoảnh khắc — kể cả khi hai mốc tình cờ trỏ vào
  // cùng một khung, lúc đó `frameId` ở trên không đổi.
  //
  // Bỏ qua khi `slotKey` null: câu KIS/Q&A không có ô mốc nào, và hiệu ứng này
  // không có việc gì ở đó.
  const slotKey = trakeSlot ? `${trakeSlot.cardKey}:${trakeSlot.index}` : null;
  useEffect(() => {
    if (slotKey === null) {
      return;
    }
    setMarkIn(null);
    setMarkOut(null);
  }, [slotKey]);

  // 0 = metadata not loaded yet. Previously this was 1 and the form below was
  // gated on `duration !== 1`, which silently tied the submission form to the
  // Drive metadata request being the only caller of onDuration.
  const [duration, setDuration] = useState<number>(0);
  // The same duration, tagged with the video it was read from, for the candidate
  // strip only. `duration` above is left as it was for FrameMarkStrip and the
  // submit form. It is written only by the player's loadedmetadata and this
  // popup is not remounted when pointed at another video, so after a switch it
  // holds the previous video's length until the new metadata arrives; the strip
  // must never be laid out with that (see durationForVideo).
  const [durationTag, setDurationTag] = useState<DurationTag | null>(null);
  const stripDuration = durationForVideo(durationTag, videoId);
  // Set by a press on a candidate block; VideoDrive seeks on each new request,
  // including a second press on the same block (see helpers/seekRequest.ts).
  const [seekRequest, setSeekRequest] = useState<SeekRequest | null>(null);
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

  // Which moment this popup is pinning. Without it the player looks the same
  // for E1 and E3 and the frame lands in whichever cell was last clicked, with
  // nothing on screen saying which.
  //
  // Tách ra thành một biến vì nó được đặt vào hai chỗ khác nhau tuỳ có task
  // đang mở hay không — xem chỗ dùng bên dưới.
  const slotChip = trakeSlot ? (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full w-fit border border-proto-primary bg-proto-primary/10 font-baloo">
      <b className="font-mono text-[12.5px] text-proto-primary-active">
        E{trakeSlot.index + 1}/{trakeSlot.total}
      </b>
      <span className="text-[12.5px] text-proto-body">{trakeSlot.label}</span>
    </div>
  ) : null;

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
              popup là overlay phủ kín khung nhìn nên mọi thứ phía sau đều khuất.

              Thẻ "đang chốt mốc nào" đi CHUNG vào khối đề bài thay vì nằm rời
              bên dưới. Nằm rời thì nó cuộn mất ngay khi kéo xuống dải điều
              khiển dưới video — đúng lúc cần nó nhất, vì tới đó màn hình không
              còn gì nói frame sắp chốt sẽ rơi vào ô nào. Khối đề bài vốn đã
              dính ở `top-0`, nên đi nhờ vào đó là hết chuyện, không phải đo
              chiều cao của nó (mà chiều cao ấy còn đổi khi bấm "Mở rộng"). */}
          {activeTask ? (
            <TaskBrief task={activeTask} variant="popup" trailing={slotChip} />
          ) : (
            // Không có task đang mở thì không có khối đề bài để đi nhờ — tự
            // dựng phần dính cho riêng nó, cùng kiểu để nhìn không lệch.
            slotChip && (
              <div className="sticky top-0 z-20 -mx-6 -mt-6 mb-3 px-6 py-3 bg-white border-b-2 border-proto-primary/40">
                {slotChip}
              </div>
            )
          )}
          <div className="flex justify-between items-center mb-[15px]">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-[8px]">
                <span className="font-bold">Video ID :</span>
                <span>{videoId + "-" + frameId}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-bold">Timestamp :</span>
                {/* Computed from frame / fps: it equals the backend's
                    timestamp_str (00:20:05.472) and needs nothing threaded in
                    from the caller, since every way of opening the popup
                    already gives a frame id. The old
                    extractTimestamp(videoId + "-" + frameId) read the frame
                    number as milliseconds and showed 00:36.128 for frame 36128. */}
                <span>
                  {frameClock(videoId, frameIdxFromFrameId(frameId)) || "Unknown"}
                </span>
                {/* Frame và ms đứng cạnh nhau: DRES chung kết nhận ms, còn
                    mọi chỗ khác trên màn hình nói bằng số frame. */}
                {Number.isFinite(frameIdxFromFrameId(frameId)) && (
                  <span className="font-mono text-[12px] text-proto-muted">
                    frame {frameIdxFromFrameId(frameId)}
                    {frameMsOf(videoId, frameIdxFromFrameId(frameId)) !== null &&
                      ` · ${frameMsOf(videoId, frameIdxFromFrameId(frameId))} ms`}
                  </span>
                )}
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
              onDuration={(s) => {
                setDuration(s);
                setDurationTag({ videoId, seconds: s });
              }}
              videoRef={videoRef}
              onPosition={(seconds) => {
                setPlayhead(seconds);
                setFrameIdx(String(seconds));
              }}
              jumpTo={startAt / 1000}
              seekRequest={seekRequest}
              setStartAt={setStartAt}
              mapping_frame={matching_keyframe}
              frame_detect={frame_detect}
            />
          </div>

          {/* Other candidate moments of this video from the current results.
              Mounted here rather than inside VideoDrive: that component owns
              the <video> and the seek effect, and a slot in it would mean
              reshaping a file every seek path goes through. Here it needs no
              change to the player at all, and it sits next to the other
              timeline strip. Renders nothing when there is nothing to show. */}
          <CandidateStrip
            videoId={videoId}
            durationS={stripDuration}
            currentTimeS={playhead}
            hidden={trakeSlot !== null}
            // Header and chips only: the blocks themselves are drawn on the
            // lower frame bar below (barOverlay), so one bar shows them together
            // with the playhead and the marks. Was: the strip drew its own track
            // (showTrack defaulted to true).
            showTrack={false}
            // Same route as opening on that keyframe: the popup's target time
            // moves to startMsAt(video, frame), and frameId, the marks, +/-,
            // Frame_idx and Đầu/Cuối carry on from there untouched. The request
            // on top is what makes a SECOND press on the same block seek again:
            // setStartAt with the value it already holds does nothing.
            onJump={(_frameName, _timeS, frameIdx) => {
              const targetMs = startMsAt(videoId, frameIdx);
              setStartAt(targetMs);
              setSeekRequest((previous) => nextSeekRequest(previous, targetMs / 1000));
            }}
          />

          <FrameMarkStrip
            videoId={videoId}
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
            // Old handler, kept for the record: only moved the target VALUE, so a
            // second click on the same spot after scrubbing away with the native
            // bar changed nothing (setStartAt got the value it already held and
            // React bailed out). The request on top is the same event the
            // candidate chips send (helpers/seekRequest.ts), so it seeks again.
            //   onSeek={(seconds) => setStartAt(seconds * 1000)}
            onSeek={(seconds) => {
              setStartAt(seconds * 1000);
              setSeekRequest((previous) => nextSeekRequest(previous, seconds));
            }}
            // Read-only candidate markers ON the bar. A click on one is a click on
            // the bar, so it seeks to where it was made, exactly as before. The
            // overlay draws nothing when the bar is zoomed, when the duration is
            // not this video's (stripDuration, tagged), or wherever the strip
            // above is hidden; it gets the same `hidden` and duration as the strip.
            barOverlay={(scale) => (
              <CandidateMarkers
                videoId={videoId}
                stripDuration={stripDuration}
                hidden={trakeSlot !== null}
                scale={scale}
              />
            )}
            // TRAKE nộp đúng khung đang dừng; KIS/Q&A nộp khung giữa hai đầu.
            // Hai đầu vẫn ghim được ở cả hai — với TRAKE chúng chảy vào ô
            // "từ/đến" của Điền tự động thay vì quyết định khung nộp.
            //
            // Chung kết: "Nộp DRES" luôn lấy THỜI ĐIỂM ĐANG PHÁT, nên con số
            // "Nộp" ở đây cũng phải là khung đang đứng — để midpoint thì màn
            // hình nói một frame còn bài nộp đi mang frame khác.
            submits={
              DRES_ONLY || activeTask?.type === "trake" ? "playhead" : "midpoint"
            }
          />

          {/* Chung kết (DRES_ONLY): Add Answer ghi vào giỏ xếp hạng của sơ
              tuyển nên ẩn đi. Riêng popup mở từ một mốc TRAKE vẫn giữ — nút
              "Chốt cho E…" ở đó chỉ ghim khung vào ô của thẻ, không ghi giỏ. */}
          {duration > 0 && (!DRES_ONLY || trakeSlot !== null) && (
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
                // Cùng hai đầu đó, đã quy ra số frame. Truyền sẵn thay vì để
                // SubmitForm tính lại: hai chỗ tính rời nhau là hai chỗ có thể
                // lệch nhau, mà đây là con số sẽ nằm lại trong giỏ.
                markedRange={markedRange}
                getPlayhead={livePosition}
                trakeSlot={trakeSlot}
              />
            </div>
          )}

          {/* Vòng chung kết: đề xuất nộp DRES tại thời điểm đang phát. Tách
              khỏi SubmitForm ở trên — đó là giỏ xếp hạng của sơ tuyển.
              Khi DRES_ONLY thì khối này lên cột phải, thế chỗ giỏ. */}
          {!DRES_ONLY && (
            <DresPropose
              videoId={videoId}
              getPlayhead={livePosition}
              defaultType={activeTask?.type}
            />
          )}
        </div>

        <div className="w-[340px] shrink-0 border-l border-proto-line flex flex-col overflow-hidden">
          {/* Có task đang mở thì Add Answer ghi thẳng lên server, nên panel
              phải đọc từ đó. Giỏ Zustand bên dưới chỉ còn dùng khi chưa nhận
              task nào.

              Chung kết: cột này chỉ còn "Nộp DRES", mở sẵn — giỏ 100 dòng
              (và Điền tự động) không còn việc gì khi mỗi câu nộp một đáp án. */}
          {DRES_ONLY ? (
            <div className="flex-1 overflow-y-auto p-3">
              <DresPropose
                videoId={videoId}
                getPlayhead={livePosition}
                defaultType={activeTask?.type}
                defaultOpen
                currentSeconds={playhead}
              />
            </div>
          ) : activeTask ? (
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
